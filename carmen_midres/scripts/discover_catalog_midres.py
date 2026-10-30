#!/usr/bin/env python3
"""Inventory medium-resolution counterparts without modifying source data."""
import argparse
import collections
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path('/home/cgchoza/galaxies/complete_cadences_catalog.csv'))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'outputs/catalog_midres')
    args = parser.parse_args()
    rows = list(csv.DictReader(args.catalog.open()))
    args.output.mkdir(parents=True, exist_ok=True)
    def list_products(folder):
        try:
            return folder, {p.name for p in folder.iterdir() if p.name.endswith('.0002.h5')}
        except OSError:
            return folder, set()
    parents = {Path(row['.h5 path']).parent for row in rows}
    with ThreadPoolExecutor(max_workers=12) as executor:
        directories = dict(executor.map(list_products, parents))
    groups = collections.defaultdict(list)
    mapped = []
    for row in rows:
        fine = Path(row['.h5 path'])
        stem = fine.name.rsplit('.', 3)[0]
        candidates = [fine.parent / (stem + '.' + backend + '.0002.h5') for backend in ('rawspec', 'gpuspec')]
        found = [p for p in candidates if p.name in directories[fine.parent]]
        # Prefer the same backend as the catalog; do not silently select between two products.
        same = [p for p in found if p.name.rsplit('.', 3)[1] == fine.name.rsplit('.', 3)[1]]
        mid = same[0] if same else (found[0] if len(found) == 1 else None)
        record = {**row, 'midres_path': str(mid) if mid else '', 'match_status': 'found' if mid else ('ambiguous' if found else 'missing')}
        mapped.append(record)
        # Different nodes may share catalog frequency labels; keep each stream separate.
        stream = fine.name.split('_guppi_')[0]
        key = tuple(row[k] for k in ('Target', 'Session', 'Band', 'Cadence ID', 'Frequency')) + (str(fine.parent), stream)
        groups[key].append(record)
    with (args.output / 'file_mapping.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(mapped[0]))
        writer.writeheader(); writer.writerows(mapped)
    complete = []
    for key, scans in groups.items():
        unique = {r['.h5 path']: r for r in scans}
        def observation_order(row):
            match = re.search(r'_(\d{5})_(\d+)_', Path(row['.h5 path']).name)
            return (0, *map(int, match.groups())) if match else (1, row['.h5 path'])
        ordered = sorted(unique.values(), key=observation_order)
        if len(ordered) == 6 and all(r['midres_path'] for r in ordered):
            complete.append({'target': key[0], 'session': key[1], 'band': key[2], 'catalog_cadence': key[3], 'frequency_label': key[4], 'paths': [r['midres_path'] for r in ordered]})
    (args.output / 'complete_cadences.json').write_text(json.dumps(complete, indent=2)+'\n')
    catalog_targets = {r['Target'] for r in rows}
    found_targets = {r['target'] for r in complete}
    report = {'catalog_targets': len(catalog_targets), 'catalog_rows': len(rows), 'mapped_rows': sum(bool(r['midres_path']) for r in mapped), 'complete_six_scan_groups': len(complete), 'targets_with_complete_groups': len(found_targets), 'targets_without_complete_groups': sorted(catalog_targets-found_targets), 'backend_counts': dict(collections.Counter(Path(r['midres_path']).name.rsplit('.',3)[1] for r in mapped if r['midres_path'])), 'validation': 'Filename existence and chronological ordering only; HDF5 headers and ON/OFF identities require validation before search.'}
    (args.output / 'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
