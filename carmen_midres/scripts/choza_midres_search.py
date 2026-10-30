#!/usr/bin/env python3
"""Seticore + turboSETI find_events pilot; originals are never modified."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def flatten(source, target, width):
    import h5py
    import numpy as np
    from scipy.ndimage import median_filter
    temporary = target.with_suffix('.partial.h5')
    shutil.copy2(source, temporary)
    with h5py.File(temporary, 'r+') as f:
        d = f['data']
        if d.dtype.kind != 'f':
            raise ValueError('Flattening requires floating-point input')
        for start in range(0, d.shape[0], 8):
            x = d[start:start + 8]
            baseline = median_filter(x, size=(1, 1, width), mode='reflect')
            if not np.isfinite(x).all() or not np.isfinite(baseline).all() or (baseline <= 0).any():
                raise ValueError(f'Nonfinite data or nonpositive median in {source}')
            d[start:start + 8] = x / baseline
        f.attrs['flatten_method'] = 'divide by row-wise running median; reflect edges'
        f.attrs['flatten_width'] = width
        f.attrs['nfpc'] = 1024
        d.attrs['nfpc'] = 1024
    temporary.replace(target)


def main(argv=None, prepared_manifest=None, only_cadence=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres'))
    p.add_argument('--output', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/choza_pilot'))
    p.add_argument('--cadences', type=int, nargs='+', default=[0, 1, 2])
    p.add_argument('--snr', type=float, nargs='+', default=[5, 7, 10])
    p.add_argument('--max-drift', type=float, default=40)
    p.add_argument('--width', type=int, default=101)
    p.add_argument('--gpu', default='0')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--keep-flattened', action='store_true',
                   help='Keep generated flattened H5 files after successful searches')
    p.add_argument('--strict-drift-range', action='store_true',
                   help='Stop before event filtering if reported drifts exceed the request by more than one drift bin')
    a = p.parse_args(argv)
    if a.width < 3 or a.width % 2 != 1 or a.max_drift <= 0 or any(s <= 0 for s in a.snr):
        p.error('width must be odd >=3; drift and SNR must be positive')
    import h5py
    if prepared_manifest is None:
        manifest = {}
        for number in a.cadences:
            name = f'cadence_{number:03d}'
            folder = a.base / name
            paths = [Path(x.strip()) for x in (folder / 'all.lst').read_text().splitlines() if x.strip()]
            if len(paths) != 6:
                raise ValueError(f'{name}: expected six ABACAD scans')
            for kind, expected in [('on', paths[::2]), ('off', paths[1::2])]:
                actual = [Path(x.strip()) for x in (folder / f'{kind}.lst').read_text().splitlines() if x.strip()]
                if actual != expected:
                    raise ValueError(f'{name}: {kind}.lst does not match ABACAD ordering')
            scans = []
            for path in paths:
                with h5py.File(path, 'r') as f:
                    d = f['data']
                    if d.ndim != 3 or d.shape[1] != 1:
                        raise ValueError(f'Unsupported data shape: {d.shape}')
                    attrs = d.attrs
                    scans.append(dict(path=str(path), shape=list(d.shape), dtype=str(d.dtype),
                                      source=str(attrs['source_name']), tstart=float(attrs['tstart']),
                                      tsamp=float(attrs['tsamp']), foff=float(attrs['foff']),
                                      nfpc=int(attrs['nfpc']) if 'nfpc' in attrs else None))
            if len({x['source'] for x in scans[::2]}) != 1:
                raise ValueError(f'{name}: ON sources differ')
            if any(x['tstart'] >= y['tstart'] for x,y in zip(scans, scans[1:])):
                raise ValueError(f'{name}: scan times are not increasing')
            manifest[name] = scans
            print(f"{name}: six readable scans; ON={scans[0]['source']}; shape={scans[0]['shape']}", flush=True)
    else:
        manifest = prepared_manifest
    settings = dict(base=str(a.base), cadences=a.cadences, snr=a.snr, max_drift=a.max_drift,
                    median_width=a.width, flattened_nfpc=1024, flatten='divide, reflect edges', filter_level=3,
                    include_zero_drift=True, event_snr_cut=None, event_max_drift=None,
                    gpu=a.gpu, manifest=manifest,
                    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if a.strict_drift_range:
        settings['strict_drift_range'] = True
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'dry_run.json').write_text(json.dumps(settings, indent=2))
    if a.dry_run:
        print(f'DRY RUN passed. Manifest: {a.output / "dry_run.json"}', flush=True)
        return
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/choza-matplotlib')
    import pandas as pd
    from turbo_seti.find_event.find_event import find_events, read_dat
    executable = shutil.which('seticore')
    if not executable:
        raise RuntimeError('seticore is not on PATH')
    subprocess.run(['nvidia-smi', '-L'], check=True)
    settings_file = a.output / 'settings.json'
    if settings_file.exists():
        old = json.loads(settings_file.read_text())
        compatible_hashes = {settings['script_sha256'],
                             '27309586ddfab10a0e7a2b72ea67d71f5fb68705915ab8b408a92357be28f32c'}
        if old.get('script_sha256') not in compatible_hashes:
            raise ValueError('Unrecognized previous script version; cannot reuse results')
        if any(old.get(k) != v for k,v in settings.items() if k not in {'script_sha256', 'base'}) or Path(old['base']).resolve() != a.base.resolve():
            raise ValueError('Settings changed: choose a new --output directory')
    else:
        settings['started_utc'] = datetime.now(timezone.utc).isoformat()
        settings['seticore_help'] = subprocess.run([executable, '--help'], capture_output=True, text=True).stdout
        settings_file.write_text(json.dumps(settings, indent=2))
    counts, summaries = [], []
    if only_cadence is not None:
        for filename, target in [('raw_hit_counts.csv', counts), ('event_summary.csv', summaries)]:
            path = a.output / filename
            if path.exists():
                previous = pd.read_csv(path)
                target.extend(previous[previous['cadence'] != only_cadence].to_dict('records'))
    for name, scans in manifest.items():
        if only_cadence is not None and name != only_cadence:
            continue
        flat_dir = a.output / name / 'flattened'
        flat_dir.mkdir(parents=True, exist_ok=True)
        flattened = []
        for scan in scans:
            source = Path(scan['path'])
            target = flat_dir / source.name
            flattened.append(target)
            if all((a.output / name / f'snr_{snr:g}' / (target.stem + '.done')).exists()
                   for snr in a.snr):
                continue
            if not target.exists():
                print(f'Flattening {name}/{source.name}', flush=True)
                flatten(source, target, a.width)
            with h5py.File(target, 'r+') as f:
                f.attrs['nfpc'] = 1024
                f['data'].attrs['nfpc'] = 1024
        for snr in a.snr:
            out = a.output / name / f'snr_{snr:g}'
            out.mkdir(exist_ok=True)
            dats = []
            for i, target in enumerate(flattened):
                dat = out / (target.stem + '.dat')
                done = dat.with_suffix('.done')
                if not done.exists():
                    command = [executable, str(target), '--output', str(dat), '--max_drift', str(a.max_drift), '--snr', str(snr)]
                    print('Running: ' + ' '.join(command), flush=True)
                    with dat.with_suffix('.log').open('w') as log:
                        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                    read_dat(str(dat))
                    done.write_text('success\n')
                hits = read_dat(str(dat))
                drift = hits['DriftRate'] if len(hits) else pd.Series(dtype=float)
                counts.append(dict(cadence=name, snr=snr, scan=i, role='ON' if i%2==0 else 'OFF',
                                   dat=str(dat), raw_hits=len(hits), min_drift=drift.min(), max_drift=drift.max(),
                                   max_abs_drift=drift.abs().max(), outside_requested_drift=int((drift.abs()>a.max_drift).sum())))
                pd.DataFrame(counts).to_csv(a.output/'raw_hit_counts.csv', index=False)
                if len(hits):
                    hits.loc[drift.abs()>a.max_drift].to_csv(dat.with_suffix('.outside_drift.csv'), index=False)
                # Seticore pads time to a power of two; permit one quantized bin
                # at the requested boundary, but fail on substantially larger rates.
                current_scan = scans[i]
                padded_samples = 1 << (current_scan['shape'][0] - 1).bit_length()
                drift_bin = abs(current_scan['foff']) * 1e6 / (current_scan['tsamp'] * padded_samples)
                if a.strict_drift_range and (drift.abs() > a.max_drift + drift_bin + 1e-5).any():
                    raise RuntimeError(f'Reported drift exceeds requested range in {dat}; '
                                       'raw results saved; resolve Seticore behavior before continuing')
                dats.append(str(dat))
            (out/'dat_files.lst').write_text('\n'.join(dats)+'\n')
            events = find_events(dats, filter_threshold=3, check_zero_drift=True, SNR_cut=None, max_drift_rate=None)
            if events is None:
                events = pd.DataFrame(columns=['Hit_ID','Freq','DriftRate','SNR'])
            events.to_csv(out/'events.csv', index=False)
            summaries.append(dict(cadence=name, snr=snr, event_rows=len(events),
                                  unique_events=events['Hit_ID'].nunique() if len(events) else 0))
            pd.DataFrame(summaries).to_csv(a.output/'event_summary.csv', index=False)
            print(summaries[-1], flush=True)
        # The sweep owns shared preprocessing and removes it after all drift settings.
        if not a.keep_flattened and not flat_dir.is_symlink():
            for target in flattened:
                target.unlink(missing_ok=True)
            print(f'Removed flattened H5 files for {name}', flush=True)
    complete = a.output / only_cadence / 'COMPLETE' if only_cadence else a.output / 'COMPLETE'
    complete.write_text(datetime.now(timezone.utc).isoformat()+'\n')
    print('Pilot complete:', a.output, flush=True)


if __name__ == '__main__':
    main()
