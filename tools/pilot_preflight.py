"""Metadata-only pilot preflight helpers; no extraction or source writes."""
import re


def archive_member(listing):
    records = []
    for block in listing.strip().split('\n\n'):
        fields = dict(line.split(' = ', 1) for line in block.splitlines() if ' = ' in line)
        if 'Path' in fields:
            records.append(fields)
    if len(records) != 1:
        raise ValueError('expected exactly one archive member')
    member = records[0]
    if member.get('Encrypted') != '-' or not re.fullmatch('[0-9A-Fa-f]{8}', member.get('CRC', '')):
        raise ValueError('encrypted member or missing CRC')
    return {'path': member['Path'], 'size_bytes': int(member['Size']),
            'crc32': member['CRC'].upper(), 'encrypted': False}


def range_coverage(names):
    ranges = []
    for name in names:
        match = re.search(r'\.xml-p(\d+)p(\d+)\.7z$', name)
        if not match:
            raise ValueError('invalid declared shard filename')
        start, end = map(int, match.groups())
        if start > end:
            raise ValueError('reversed declared range')
        ranges.append((start, end))
    gaps, overlaps = [], []
    frontier = None
    for start, end in sorted(ranges):
        if frontier is not None:
            if start > frontier + 1:
                gaps.append([frontier + 1, start - 1])
            elif start <= frontier:
                overlaps.append([start, min(frontier, end)])
        frontier = max(frontier or 0, end)
    return {'ranges': sorted(ranges), 'gaps': gaps, 'overlaps': overlaps,
            'unique_names': len(set(names)) == len(names),
            'official_completeness_verified': False}
