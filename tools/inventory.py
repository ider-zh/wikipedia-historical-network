#!/usr/bin/env python3
"""Read-only metadata inventory. Only stdout; never writes source paths."""
import os
import re
import stat
import time

EXCLUDED_NAMES = frozenset(('.git', 'node_modules', '__pycache__', '.venv', 'venv', '.cache', '.npm', '.cargo', '.rustup', '.conda', '.local', '.hermes', '.vscode-server', '.ssh', '.gnupg', '.config', '.mozilla', '.docker', '.codex', '.claude', '.bun', 'site-packages', 'dist-packages', 'miniconda3', 'miniconda38', 'anaconda3', 'overlay2', 'rootfs', 'containerd', 'nginx_cache', 'elasticsearch', 'opensearch', 'mongodb', 'mongod', 'mysql', 'mariadb', 'redis', '$RECYCLE.BIN', 'System Volume Information'))


def walk_root(root, boundaries=(), exclude_paths=(), max_entries=10000000, max_depth=64, max_seconds=7200):
    """Yield exact observed metadata and root-level completion evidence."""
    root = os.path.abspath(root)
    boundaries = set(os.path.abspath(p) for p in boundaries) - {root}
    excluded = set(os.path.abspath(p) for p in exclude_paths)
    started = time.monotonic()
    counts = dict(entries=0, directories=0, regular_files=0, files=0, aliases=0, errors=0, excluded=0)
    yield dict(type='root_start', root=root, bounds=dict(max_entries=max_entries, max_depth=max_depth, max_seconds=max_seconds), uid=os.geteuid())
    stack = [(root, 0)]
    truncated = False
    while stack:
        directory, depth = stack.pop()
        if counts['entries'] >= max_entries or time.monotonic() - started > max_seconds:
            truncated = True
            yield dict(type='error', root=root, path=directory, operation='walk', error='root_budget_exhausted')
            counts['errors'] += 1
            break
        if depth > max_depth:
            truncated = True
            yield dict(type='error', root=root, path=directory, operation='walk', error='max_depth')
            counts['errors'] += 1
            continue
        if os.path.islink(directory):
            counts['aliases'] += 1
            yield dict(type='alias', root=root, path=directory, target=os.readlink(directory), followed=False)
            continue
        try:
            with os.scandir(directory) as iterator:
                entries = []
                for entry in iterator:
                    entries.append(entry)
                    if len(entries) + counts['entries'] >= max_entries:
                        truncated = True
                        break
            counts['directories'] += 1
        except OSError as exc:
            counts['errors'] += 1
            yield dict(type='error', root=root, path=directory, operation='scandir', error=type(exc).__name__, errno=exc.errno)
            continue
        manifests = sorted(e.path for e in entries if re.search(r'(?:md5|sha1|sha256|sha512)(?:sums?)?|checksums?', e.name, re.I) and not e.is_symlink())
        for entry in entries:
            counts['entries'] += 1
            path = entry.path
            if counts['entries'] % 10000 == 0:
                yield dict(type='progress', root=root, path=directory, elapsed_seconds=round(time.monotonic()-started, 3), **counts)
            try:
                if entry.is_symlink():
                    counts['aliases'] += 1
                    yield dict(type='alias', root=root, path=path, target=os.readlink(path), followed=False)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    engine = bool(re.match(r'^(?:mongo(?:db)?\d+|mysql_file|mysql_data|postgres_data|postgresql_data|elastic[-_]data|es[-_].*data|docker|containerd|seaweedfs_data.*|milvus_data)$', entry.name, re.I))
                    reason = 'mount_boundary' if path in boundaries else 'excluded_path' if any(path == p or path.startswith(p + os.sep) for p in excluded) else 'engine_directory' if engine else 'excluded_name' if entry.name in EXCLUDED_NAMES else None
                    if reason:
                        counts['excluded'] += 1
                        yield dict(type='excluded', root=root, path=path, reason=reason)
                    else:
                        stack.append((path, depth + 1))
                    continue
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    continue
                counts['regular_files'] += 1
                if not candidate(path):
                    continue
                counts['files'] += 1
                yield dict(type='file', root=root, path=path, size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                           device=info.st_dev, inode=info.st_ino, mode=stat.S_IMODE(info.st_mode),
                           checksums=dict(computed=False, verification='not_performed', neighbor_manifests=manifests), **classify(path))
            except OSError as exc:
                counts['errors'] += 1
                yield dict(type='error', root=root, path=path, operation='entry_metadata', error=type(exc).__name__, errno=exc.errno)
        if truncated:
            counts['errors'] += 1
            yield dict(type='error', root=root, path=directory, operation='scandir', error='entry_budget_exhausted')
            break
    yield dict(type='root_end', root=root, status='truncated' if truncated else 'complete_with_errors' if counts['errors'] else 'complete',
               truncated=truncated, elapsed_seconds=round(time.monotonic()-started, 3), **counts)

TABLES = ('categorylinks', 'pagelinks', 'linktarget', 'page_props', 'page', 'redirect', 'category', 'revision', 'slots', 'content', 'text', 'externallinks', 'imagelinks', 'langlinks', 'templatelinks', 'logging', 'user', 'site_stats', 'protected_titles', 'geo_tags', 'iwlinks')

def plan_roots(mount_document):
    """Select data filesystems; every mount remains a nonfollowing boundary."""
    flat = []
    def visit(rows):
        for row in rows:
            flat.append({k: v for k, v in row.items() if k != 'children'})
            visit(row.get('children', []))
    visit(mount_document.get('filesystems', []))
    roots = set(('/mnt', '/data', '/srv', '/home/ider'))
    skipped = []
    data_types = {'ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'fuseblk', 'ntfs', 'ntfs3', 'zfs', 'exfat', 'nfs', 'nfs4', 'cifs', 'fuse.sshfs'}
    for mount in flat:
        target = mount['target']
        reason = 'system_or_pseudo_mount'
        if mount.get('fstype') in data_types and target not in ('/', '/boot', '/boot/efi'):
            if target.startswith(('/var/lib/docker/', '/var/lib/containerd/', '/tmp/', '/snap/', '/run/')):
                reason = 'engine_or_system_bind'
            else:
                roots.add(target)
                continue
        skipped.append(dict(path=target, reason=reason))
    return dict(roots=sorted(roots), boundaries=sorted(set(m['target'] for m in flat) | roots), mounts=flat, skipped_mounts=skipped)


def candidate(path):
    return bool(re.search(r'wiki|维基|維基|categorylinks|pagelinks|history|histry|sql', path, re.I) or re.search(r'\.(?:zip|7z|rar|tar|tgz)(?:\.(?:gz|bz2|xz|zst|7z))?(?:\.(?:part|partial|tmp|crdownload))?$', path, re.I))


def classify(path):
    lower = path.lower()
    name = os.path.basename(lower)
    wiki_codes = r'(?:[a-z]{2,3}|simple|test2?|commons|species|zh_min_nan|zh_yue|zh_classical|be_x_old|bat_smg|map_bms|nds_nl|roa_rup|roa_tara|fiu_vro|cbk_zam)'
    wikis = sorted(set(re.findall(r'(?<![a-z0-9])(' + wiki_codes + r'wiki)(?![a-z])', lower)))
    date_context = re.sub(r'-p[0-9]+p[0-9]+(?=[./_-]|$)', '', lower)
    dates = sorted(set(re.findall(r'(?<!\d)((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))(?!\d)', date_context)))
    tables = sorted(t for t in TABLES if re.search(r'(?:^|[-_/.])' + t + r'(?:[-.]|_(?=[0-9])|$)', name))
    partial = bool(re.search(r'\.(?:part|partial|filepart|download|tmp|crdownload|aria2)$', name))
    opaque = bool(re.search(r'\.(?:tar|tgz|zip|rar)(?:\.|$)', name) or ('.sql' in name and re.search(r'\.7z(?:\.|$)', name)))
    years = sorted(set(re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', lower)))
    representation = 'opaque_archive' if opaque else 'xml_stub' if '.xml' in name and 'stub' in name else 'xml_index' if 'index' in name and ('history' in name or '.xml' in name or 'multistream' in name) else 'sql_schema' if '.sql' in name and ('-schema' in name or '_schema' in name) else 'sql' if '.sql' in name else 'tabular_dat' if re.search(r'\.dat(?:\.|$)', name) else 'xml_history' if '.xml' in name and 'history' in name else 'xml' if '.xml' in name else 'opaque_archive' if re.search(r'\.(?:tar|tgz|zip|7z|rar|gz|bz2|xz|zst)(?:\.|$)', name) else 'parquet' if '.parquet' in name else 'checksum_manifest' if re.search(r'(?:md5|sha1|sha256|sha512|checksums?)', name) else 'unknown'
    canonical_xml = bool(re.fullmatch(wiki_codes + r'wiki-(?:[0-9]{8}|latest)-pages-(?:meta-history|meta-current|articles(?:-multistream)?)[0-9]*\.xml(?:-p[0-9]+p[0-9]+)?(?:\.(?:bz2|7z|gz|xz|zst))?', name))
    fixture = any(part in ('testdata', 'fixtures', 'test-fixtures', 'tests', 'examples') for part in lower.split('/'))
    reasons = []
    if partial:
        reasons.append('partial_download_filename')
    if fixture:
        reasons.append('test_fixture_path')
    if representation in ('xml', 'xml_history') and not canonical_xml:
        reasons.append('noncanonical_xml_dump_filename')
    if representation not in ('sql', 'xml', 'xml_history'):
        reasons.append('representation_not_direct_payload_candidate')
    return dict(inferred_wikis=wikis, inferred_dates=dates, inferred_years=years, tables=tables,
                representation=representation, truncated=partial, source_eligibility_reasons=reasons,
                inference_evidence='path_name_only',
                candidate_evidence='keyword_path_match' if re.search(r'wiki|维基|維基|categorylinks|pagelinks|history|histry|sql', path, re.I) else 'unscoped_archive_filename_only',
                source_eligible_candidate=not reasons)


def main():
    import argparse
    import datetime
    import json
    import socket
    import subprocess
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', default=[])
    parser.add_argument('--exclude-path', action='append', default=[])
    parser.add_argument('--max-entries', type=int, default=10000000)
    parser.add_argument('--max-depth', type=int, default=64)
    parser.add_argument('--max-seconds', type=int, default=7200)
    args = parser.parse_args()
    mounts = json.loads(subprocess.check_output(['findmnt', '-J', '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'], universal_newlines=True))
    plan = plan_roots(mounts)
    if args.root:
        plan['roots'] = sorted(set(os.path.abspath(p) for p in args.root))
        plan['boundaries'] = sorted(set(plan['boundaries']) | set(plan['roots']))
    host = socket.gethostname()
    def emit(event):
        event.update(schema_version=1, host=host, observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        print(json.dumps(event, ensure_ascii=True), flush=True)
    emit(dict(type='discovery', uid=os.geteuid(), exclusion_names=sorted(EXCLUDED_NAMES), exclude_paths=args.exclude_path, **plan))
    for root in plan['roots']:
        for event in walk_root(root, boundaries=plan['boundaries'], exclude_paths=args.exclude_path,
                               max_entries=args.max_entries, max_depth=args.max_depth, max_seconds=args.max_seconds):
            emit(event)
    emit(dict(type='host_end', root_count=len(plan['roots'])))


if __name__ == '__main__':
    main()
