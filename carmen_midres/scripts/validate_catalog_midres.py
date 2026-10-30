#!/usr/bin/env python3
"""Resume header validation and build deduplicated catalog cadence manifests."""
import collections
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import h5py

ROOT = Path(__file__).resolve().parents[1] / 'outputs/catalog_midres'

def inspect(path):
    try:
        with h5py.File(path, 'r') as f:
            d = f['data']; a = d.attrs
            source = a['source_name']
            if isinstance(source, bytes): source = source.decode()
            info = dict(path=path, shape=list(d.shape), dtype=str(d.dtype), source=str(source),
                        size_bytes=Path(path).stat().st_size,
                        **{k: float(a[k]) for k in ('tstart','tsamp','foff','fch1')})
            if d.ndim != 3 or d.shape[1] != 1 or d.dtype.kind != 'f':
                raise ValueError('Unsupported data shape or dtype')
            if info['tsamp'] <= 0 or info['foff'] == 0:
                raise ValueError('Invalid time/frequency resolution')
            return info
    except Exception as exc:
        return dict(path=path, error=str(exc))

def normalize(source):
    return source.upper().replace('_', '').replace(' ', '')

def main():
    groups = json.loads((ROOT/'complete_cadences.json').read_text())
    unique = {tuple(g['paths']): g for g in groups}
    cache_path = ROOT/'headers.jsonl'
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            try:
                row = json.loads(line); cache[row['path']] = row
            except json.JSONDecodeError:
                continue
    paths = sorted({p for key in unique for p in key})
    pending = [p for p in paths if p not in cache or 'error' in cache[p]]
    print(f'{len(unique)} unique groups; {len(paths)} unique files; {len(pending)} headers to inspect', flush=True)
    with cache_path.open('a') as out, ThreadPoolExecutor(max_workers=8) as pool:
        for i, row in enumerate(pool.map(inspect, pending), 1):
            cache[row['path']] = row
            out.write(json.dumps(row)+'\n'); out.flush()
            if i % 100 == 0: print(f'Headers checked: {i}/{len(pending)}', flush=True)
    valid, rejected = [], []
    cadence_base = ROOT/'validated_cadences'
    cadence_base.mkdir(exist_ok=True)
    for key, group in unique.items():
        scans = [cache[p] for p in key]
        reason = None
        if any('error' in s for s in scans): reason = 'Unreadable or unsupported file'
        else:
            scans.sort(key=lambda s:s['tstart'])
            on = normalize(group['target'])
            if any(normalize(s['source']) != on for s in scans[::2]): reason = 'ON identities differ from catalog target'
            elif any(normalize(s['source']) == on for s in scans[1::2]): reason = 'OFF identity equals ON target'
            elif any(a['tstart'] >= b['tstart'] for a,b in zip(scans,scans[1:])): reason = 'Non-increasing times'
            elif len({(tuple(s['shape']),s['tsamp'],s['foff'],s['fch1']) for s in scans}) != 1: reason = 'Scan dimensions or frequency/time grids differ'
        if reason:
            rejected.append({**group,'reason':reason});continue
        name=f'cadence_{len(valid):03d}'
        folder=cadence_base/name;folder.mkdir(exist_ok=True)
        ordered=[s['path'] for s in scans]
        for kind, selected in [('all',ordered),('on',ordered[::2]),('off',ordered[1::2])]:
            (folder/f'{kind}.lst').write_text('\n'.join(selected)+'\n')
        valid.append({**group,'name':name,'paths':ordered})
    (ROOT/'validated_groups.json').write_text(json.dumps(valid,indent=2)+'\n')
    (ROOT/'rejected_groups.json').write_text(json.dumps(rejected,indent=2)+'\n')
    report=dict(unique_groups=len(unique),validated_groups=len(valid),rejected_groups=len(rejected),
                validated_targets=len({g['target'] for g in valid}),
                targets_without_validated_groups=sorted({g['target'] for g in groups}-{g['target'] for g in valid}),
                unique_files=len(paths),input_bytes=sum(cache[p].get('size_bytes',0) for p in paths),
                scan_searches_before_cross_group_file_reuse=len(valid)*6*20)
    (ROOT/'validation_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__ == '__main__': main()
