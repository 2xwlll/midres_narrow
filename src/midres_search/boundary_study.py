"""Resume-aware paired detector experiments, configured with a JSON matrix."""
import argparse
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import h5py
import hdf5plugin  # noqa: F401
import numpy as np

from .normalization import METHODS, normalize


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def signal_track(shape, start, drift_hz_s, foff_mhz, tsamp, width_bins):
    """Sample a Gaussian of unit peak; positive drift increases sky frequency."""
    centers = start + np.arange(shape[0]) * tsamp * drift_hz_s / (foff_mhz * 1e6)
    sigma = width_bins / (2 * np.sqrt(2 * np.log(2)))
    if centers.min() - 4*sigma < 0 or centers.max() + 4*sigma >= shape[1]:
        raise ValueError('Injection leaves crop; use a larger crop or smaller drift')
    track = np.exp(-.5*((np.arange(shape[1])[None, :] - centers[:, None])/sigma)**2)
    return track, centers


def block_crossing(centers, nfpc):
    return bool(np.floor(centers.min()/nfpc) != np.floor(centers.max()/nfpc))


def parse_dat(path):
    hits = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        values = line.split()
        try:
            int(values[0])
        except (ValueError, IndexError):
            continue
        # Numeric records must parse: never silently report a broken file as no hits.
        hits.append(dict(drift=float(values[1]), snr=float(values[2]), frequency=float(values[3])))
    return hits


def matches(hits, frequency, drift, frequency_tolerance, drift_tolerance):
    return [h for h in hits if abs(h['frequency']-frequency) <= frequency_tolerance
            and abs(h['drift']-drift) <= drift_tolerance]


def summarize(output):
    rows = [json.loads(p.read_text()) for p in sorted((output/'cases').glob('*.json'))]
    if not rows:
        return
    temporary = output/'measurements.tmp'
    with temporary.open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(output/'measurements.csv')


def run(config, output, gpu, limit=None):
    for key in ('sources', 'offsets', 'strengths', 'drifts', 'widths_bins',
                'subbin_phases', 'methods', 'detector_nfpc'):
        if not config.get(key):
            raise ValueError(f'Empty or missing matrix dimension: {key}')
    if any(s <= 0 for s in config['strengths']) or any(w <= 0 for w in config['widths_bins']):
        raise ValueError('Strengths and widths must be positive')
    if config['coarse_width'] < 102 or any(n < 1 or int(n) != n for n in config['detector_nfpc']):
        raise ValueError('Invalid coarse width or detector nfpc')
    if any(m not in (*METHODS, 'frozen_median101') for m in config['methods']):
        raise ValueError('Unknown normalization method')
    if limit is not None and limit < 1:
        raise ValueError('Limit must be positive')
    if any(abs(d) > config.get('max_drift', 10) for d in config['drifts']):
        raise ValueError('Injected drift exceeds requested detector range')
    executable = shutil.which('seticore')
    if not executable:
        raise RuntimeError('seticore is not on PATH')
    # Binary identity is stronger than relying on a version string alone.
    identity = dict(config=config, runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        normalization_sha256=hashlib.sha256(Path(__file__).with_name('normalization.py').read_bytes()).hexdigest(),
        binary_sha256=hashlib.sha256(Path(executable).read_bytes()).hexdigest())
    sources = []
    for entry in config['sources']:
        path = Path(entry['path']).resolve()
        stat = path.stat()
        sources.append(dict(path=str(path), bytes=stat.st_size, mtime_ns=stat.st_mtime_ns))
    identity['source_identity'] = sources
    signature = digest(identity)
    output.mkdir(parents=True, exist_ok=True)
    for directory in ('cases', 'detector', 'crops'):
        (output/directory).mkdir(exist_ok=True)
    provenance = output/'study.json'
    if provenance.exists():
        if json.loads(provenance.read_text())['signature'] != signature:
            raise ValueError('Configuration, source, runner, or binary changed; use a new output')
    else:
        atomic_json(provenance, dict(signature=signature, identity=identity,
            numpy_version=np.__version__, seticore_help=subprocess.run([executable, '--help'],
            capture_output=True, text=True).stdout,
            interpretation='Post-instrument Gaussian injections. Local track SNR is not detector SNR. '
            'Reusing identical noise does not create independent trials. Merged nfpc is diagnostic, '
            'not a proposed metadata correction. No production changes.'))
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = str(gpu)
    threshold = float(config.get('threshold', 5))
    max_drift = float(config.get('max_drift', 10))
    count = 0
    for source_index, entry in enumerate(config['sources']):
        for block in entry['blocks']:
            coarse = int(config['coarse_width'])
            pad = 50
            with h5py.File(entry['path']) as original:
                d = original['data']
                lo, hi = (block-1)*coarse, (block+2)*coarse
                if d.ndim != 3 or d.shape[1] != 1 or lo < pad or hi+pad > d.shape[-1]:
                    raise ValueError('Need three interior blocks plus 50-bin context')
                raw = np.asarray(d[:, 0, lo-pad:hi+pad], dtype=float)
                attrs, rootattrs = dict(d.attrs), dict(original.attrs)
            if not np.isfinite(raw).all():
                raise ValueError('Nonfinite source power')
            tsamp, foff = float(attrs['tsamp']), float(attrs['foff'])
            fch1 = float(attrs['fch1'])+lo*foff
            shape = (raw.shape[0], hi-lo)
            rounded = 1 << (shape[0]-1).bit_length()
            drift_bin = abs(foff)*1e6/((rounded-1)*tsamp)
            crop_id = f's{source_index}_b{block}'
            crop_hash = hashlib.sha256(raw.tobytes()).hexdigest()
            crop_report = output/'crops'/f'{crop_id}.json'
            if crop_report.exists() and json.loads(crop_report.read_text())['sha256'] != crop_hash:
                raise ValueError('Crop changed since previous run')
            atomic_json(crop_report, dict(sha256=crop_hash, source=entry['path'],
                global_channel_start=lo-pad, shape=list(raw.shape), attrs={
                    k: str(v) for k, v in attrs.items()}))
            controls = {}
            control_arrays = {}
            frozen_baseline = None

            def treatment(array, method):
                nonlocal frozen_baseline
                if method == 'frozen_median101':
                    # Oracle ablation: fit to the paired control, not injected data.
                    # Isolates self-normalization; unavailable for a blind search.
                    if frozen_baseline is None:
                        frozen_baseline = raw / normalize(raw, 'median101', first_channel=lo-pad)
                    return (array/frozen_baseline)[:, pad:-pad]
                return normalize(array, method, coarse_width=coarse, first_channel=lo-pad)[:, pad:-pad]

            def detector(array, name, nfpc):
                prefix = output/'detector'/name
                success = prefix.with_suffix('.success.json')
                dat = prefix.with_suffix('.dat')
                array32 = array.astype('float32')
                array_hash = hashlib.sha256(array32.tobytes()).hexdigest()
                if success.exists():
                    previous = json.loads(success.read_text())
                    if previous['array_sha256'] != array_hash or not dat.exists():
                        raise ValueError('Cached detector input differs or output is missing')
                    return parse_dat(dat)
                h5 = prefix.with_suffix('.h5')
                with h5py.File(h5, 'w') as f:
                    for key, value in rootattrs.items():
                        f.attrs[key] = value
                    d = f.create_dataset('data', data=array32[:, None, :])
                    for key, value in attrs.items():
                        d.attrs[key] = value
                    d.attrs['fch1'], d.attrs['nchans'], d.attrs['nfpc'] = fch1, shape[1], nfpc
                    f.attrs['nfpc'] = nfpc
                with prefix.with_suffix('.log').open('w') as log:
                    subprocess.run([executable, str(h5), '--output', str(dat), '--snr', str(threshold),
                        '--max_drift', str(max_drift)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
                hits = parse_dat(dat)
                atomic_json(success, dict(array_sha256=array_hash, hits=len(hits)))
                h5.unlink()
                return hits

            matrix = itertools.product(config['offsets'], config['strengths'], config['drifts'],
                config['widths_bins'], config['subbin_phases'], config['methods'], config['detector_nfpc'])
            for offset, strength, drift, width, phase, method, nfpc in matrix:
                if shape[1] % nfpc:
                    raise ValueError('Detector nfpc must divide the crop channel count')
                case = dict(crop=crop_id, offset=offset, strength=strength, drift=drift,
                            width_bins=width, phase=phase, method=method, nfpc=nfpc)
                key = digest(case)[:24]
                path = output/'cases'/f'{key}.json'
                if path.exists():
                    continue
                control_key = (method, nfpc)
                if control_key not in controls:
                    if method not in control_arrays:
                        control_arrays[method] = treatment(raw, method)
                    controls[control_key] = detector(control_arrays[method],
                        f'{crop_id}_{method}_nfpc{nfpc}_control', nfpc)
                start = coarse+offset+phase
                track, centers = signal_track(shape, start, drift, foff, tsamp, width)
                indices = np.rint(centers).astype(int)
                values = raw[np.arange(shape[0]), indices+pad]
                # Noise is estimated per channel over time, then along the track.
                selected = raw[:, np.unique(indices)+pad]
                noise = 1.4826*np.median(np.abs(selected-np.median(selected, axis=0)), axis=0)
                sigma = float(np.median(noise))
                if sigma <= 0 or not np.isfinite(sigma):
                    raise ValueError('Invalid temporal noise estimate')
                sampled_peak = float(np.mean(track[np.arange(shape[0]), indices]))
                amplitude = strength*sigma/(np.sqrt(shape[0])*sampled_peak)
                injected = raw.copy()
                injected[:, pad:-pad] += amplitude*track
                hits = detector(treatment(injected, method), key, nfpc)
                frequency = fch1+start*foff
                # One-bin tolerance allows sampled/sub-bin starting frequencies.
                ftol = abs(foff)*config.get('frequency_tolerance_bins', 1)
                dtol = drift_bin*config.get('drift_tolerance_bins', 1.1)
                found = matches(hits, frequency, drift, ftol, dtol)
                background = matches(controls[control_key], frequency, drift, ftol, dtol)
                start_bin = int(np.rint(start))
                block_lo = (start_bin//nfpc)*nfpc
                column_sums = control_arrays[method][:, block_lo:block_lo+nfpc].sum(axis=0)
                ordered = np.sort(column_sums)
                central = ordered[int(np.ceil(.05*nfpc)):int(np.floor(.95*nfpc))+1]
                column_sigma = float(np.std(central))
                deficit = (float(column_sums[start_bin-block_lo])-float(np.median(column_sums)))
                best = max(found, key=lambda h: h['snr']) if found else None
                row = dict(case, source=entry['path'], crop_sha256=crop_hash,
                    start_frequency_mhz=frequency, end_channel=float(centers[-1]),
                    detector_block_crossing=block_crossing(centers, nfpc),
                    physical_block_crossing=block_crossing(centers+lo, coarse),
                    local_sigma=sigma, amplitude=float(amplitude), control_track_mean=float(np.mean(values)),
                    drift_bin_hz_s=drift_bin, recovered=bool(found), control_hit=bool(background),
                    new_recovery=bool(found) and not bool(background),
                    reported_snr=max((h['snr'] for h in found), default=None),
                    matched_drift_hz_s=best['drift'] if best else None,
                    matched_frequency_mhz=best['frequency'] if best else None,
                    control_column_deficit_sigma=deficit/column_sigma if column_sigma > 0 else None,
                    all_control_hits=len(controls[control_key]), all_injected_hits=len(hits))
                atomic_json(path, row)
                count += 1
                if count % 12 == 0:
                    summarize(output)
                    print(f'{count} new cases completed; {crop_id}', flush=True)
                if limit is not None and count >= limit:
                    summarize(output)
                    return
    summarize(output)
    atomic_json(output/'COMPLETE.json', dict(signature=signature, completed_unix=time.time()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gpu', default='1')
    parser.add_argument('--limit', type=int, help='Maximum new injected cases for a bounded pilot')
    args = parser.parse_args()
    import fcntl
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output/'study.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(json.loads(args.config.read_text()), args.output, args.gpu, args.limit)


if __name__ == '__main__':
    main()
