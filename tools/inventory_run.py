#!/usr/bin/env python3
"""Run inventory over local/SSH hosts; retain private streams and audit them."""
import argparse
import collections
import concurrent.futures
import datetime
import gzip
import json
import pathlib
import shlex
import subprocess
import sys


def collect(target, output, scanner, roots=(), exclude_paths=(), sudo=False, max_entries=10000000, max_seconds=7200):
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=False)
    args = ['--max-entries', str(max_entries), '--max-seconds', str(max_seconds)]
    for root in roots:
        args += ['--root', root]
    for path in exclude_paths:
        args += ['--exclude-path', path]
    interpreter = ['sudo', '-n', 'python3'] if sudo else ['python3']
    script = pathlib.Path(scanner).read_bytes()
    (output / 'scanner.py').write_bytes(script)
    import hashlib
    scanner_sha256 = hashlib.sha256(script).hexdigest()
    if target == 'local':
        command = interpreter + ['-u', '-'] + args
    else:
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3', target,
                   shlex.join(interpreter + ['-u', '-'] + args)]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (output / 'stderr.log').open('wb') as err, gzip.open(output / 'inventory.jsonl.gz', 'wb', compresslevel=3) as stream:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err)
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(script)
        process.stdin.close()
        for line in process.stdout:
            stream.write(line)
        process.stdout.close()
        code = process.wait()
    result = dict(target=target, command=command, scanner_sha256=scanner_sha256, started_utc=started, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), returncode=code, sudo=sudo)
    (output / 'execution.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def audit(output):
    """Re-read the persisted gzip, never trust live in-memory walk counters."""
    output = pathlib.Path(output)
    counts = collections.Counter()
    by_wiki = collections.Counter()
    by_date = collections.Counter()
    by_repr = collections.Counter()
    by_table = collections.Counter()
    root_counts = collections.Counter()
    starts, ends, expected = {}, {}, []
    errors, exclusions, discoveries = [], [], []
    host_end = False
    host = None
    total_bytes = eligible = 0
    paths = set()
    duplicate_paths = 0
    with gzip.open(output / 'inventory.jsonl.gz', 'rt') as stream, gzip.open(output / 'files.jsonl.gz', 'wt', compresslevel=3) as files:
        for line in stream:
            row = json.loads(line)
            kind = row['type']
            counts[kind] += 1
            host = row['host']
            root = row.get('root')
            if kind == 'file':
                files.write(json.dumps(row) + '\n')
                root_counts[root] += 1
                total_bytes += row['size_bytes']
                eligible += bool(row['source_eligible_candidate'])
                by_wiki.update(row['inferred_wikis'] or ['unknown'])
                by_date.update(row['inferred_dates'] or ['unknown'])
                by_repr.update([row['representation']])
                by_table.update(row['tables'])
                if row['path'] in paths:
                    duplicate_paths += 1
                paths.add(row['path'])
            elif kind == 'root_start':
                starts[root] = row
            elif kind == 'root_end':
                ends[root] = row
            elif kind == 'error':
                errors.append(row)
            elif kind == 'excluded':
                exclusions.append(row)
            elif kind == 'discovery':
                expected = row['roots']
                discoveries.append(row)
            elif kind == 'host_end':
                host_end = True
    coverage = []
    covered_roots = set(expected) | set(starts) | set(ends) | set(root_counts)
    for root in sorted(covered_roots):
        end = ends.get(root, {})
        reported = end.get('files')
        coverage.append(dict(root=root, started=root in starts, ended=root in ends, status=end.get('status', 'incomplete'),
                             persisted_files=root_counts[root], reported_files=reported,
                             counts_match=reported == root_counts[root], walk=end, start=starts.get(root)))
    execution = json.loads((output / 'execution.json').read_text()) if (output / 'execution.json').exists() else {}
    audited = (bool(expected) and host_end and execution.get('returncode') == 0
               and set(expected) == set(starts) == set(ends) == covered_roots
               and sum(r['persisted_files'] for r in coverage) == counts['file']
               and all(r['counts_match'] and r['started'] and r['ended'] for r in coverage)
               and duplicate_paths == 0)
    complete = audited and all(r['status'] == 'complete' for r in coverage)
    summary = dict(schema_version=1, host=host, candidate_files=counts['file'], candidate_bytes=total_bytes,
                   source_eligible_candidates=eligible, by_wiki=dict(by_wiki), by_date=dict(by_date), by_representation=dict(by_repr), by_table=dict(by_table),
                   event_counts=dict(counts), root_count=len(coverage), coverage_audited=audited, scoped_walk_complete_without_errors=complete,
                   host_end=host_end, duplicate_paths=duplicate_paths, error_count=len(errors),
                   evidence='metadata_and_path_names_only; no_source_hashes_or_crc; no_archive_body_reads', execution=execution)
    for name, data in [('summary.json', summary), ('root-coverage.json', coverage), ('errors.json', errors), ('exclusions.json', exclusions), ('discovery.json', discoveries)]:
        (output / name).write_text(json.dumps(data, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='append', required=True, help='label=local or label=user@address')
    parser.add_argument('--output', required=True, help='new private run directory, preferably SSD')
    parser.add_argument('--exclude-path', action='append', default=[])
    parser.add_argument('--root', action='append', default=[])
    parser.add_argument('--sudo', action='store_true', help='metadata only, explicit authorization required')
    parser.add_argument('--max-entries', type=int, default=10000000)
    parser.add_argument('--max-seconds', type=int, default=7200)
    args = parser.parse_args()
    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    scanner = pathlib.Path(__file__).with_name('inventory.py')
    hosts = [value.split('=', 1) for value in args.host]
    if len(set(label for label, _ in hosts)) != len(hosts):
        parser.error('host labels must be unique')
    def run(item):
        label, target = item
        if '/' in label or label in ('.', '..'):
            raise ValueError('unsafe host label')
        collect(target, output / label, scanner, roots=args.root, exclude_paths=args.exclude_path,
                sudo=args.sudo, max_entries=args.max_entries, max_seconds=args.max_seconds)
        result = audit(output / label)
        print(json.dumps(dict(label=label, **result)), flush=True)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        results = list(pool.map(run, hosts))
    (output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    return 0 if all(r['coverage_audited'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
