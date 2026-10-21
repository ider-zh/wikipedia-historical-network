#!/usr/bin/env python3
"""Apply latest filename classifier to retained observations, no source rescans."""
import argparse
import datetime
import gzip
import hashlib
import json
import pathlib
import shutil
from inventory import classify
from inventory_run import audit


def refine(source, output):
    source, output = pathlib.Path(source), pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=False)
    scanner = pathlib.Path(__file__).with_name('inventory.py')
    changed = files = 0
    with gzip.open(source / 'inventory.jsonl.gz', 'rt') as before, gzip.open(output / 'inventory.jsonl.gz', 'wt', compresslevel=3) as after:
        for line in before:
            row = json.loads(line)
            if row['type'] == 'file':
                files += 1
                latest = classify(row['path'])
                if row['size_bytes'] == 0:
                    latest['source_eligible_candidate'] = False
                    reasons = latest['source_eligibility_reasons']
                    assert isinstance(reasons, list)
                    reasons.append('zero_size_file')
                changed += any(row.get(k) != value for k, value in latest.items())
                row.update(latest)
            after.write(json.dumps(row) + '\n')
    for name in ('execution.json', 'stderr.log', 'scanner.py'):
        if (source / name).exists():
            shutil.copyfile(source / name, output / name)
    provenance = dict(source_inventory=str(source / 'inventory.jsonl.gz'),
                      classified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      classifier_sha256=hashlib.sha256(scanner.read_bytes()).hexdigest(),
                      observed_file_count=files, changed_file_count=changed,
                      source_stat_observations_preserved=True, source_rescanned=False)
    (output / 'classifier.py').write_bytes(scanner.read_bytes())
    (output / 'classification.json').write_text(json.dumps(provenance, indent=2) + '\n')
    result = audit(output)
    result['classification'] = provenance
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='completed run directory containing host subdirectories')
    parser.add_argument('--output', required=True, help='new immutable corrected-view directory')
    args = parser.parse_args()
    source, output = pathlib.Path(args.source), pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for host in sorted(p for p in source.iterdir() if p.is_dir() and (p / 'inventory.jsonl.gz').exists()):
        result = refine(host, output / host.name)
        results.append(result)
        print(json.dumps(dict(label=host.name, candidate_files=result['candidate_files'], source_eligible_candidates=result['source_eligible_candidates'], coverage_audited=result['coverage_audited'])), flush=True)
    (output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    if not results or not all(r['coverage_audited'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
