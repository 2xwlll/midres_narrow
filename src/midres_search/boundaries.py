"""CPU-only paired boundary diagnostics; this does not run a signal detector."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import h5py
import hdf5plugin  # noqa: F401 -- register compression filters
import numpy as np

from .normalization import METHODS, normalize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New experiment directory')
    parser.add_argument('--coarse-width', type=int, default=1024, help='Verify against instrument metadata')
    parser.add_argument('--coarse-index', type=int, help='Index of central coarse block')
    parser.add_argument('--time-samples', type=int, default=128)
    parser.add_argument('--strengths', type=float, nargs='+', default=[5, 10, 20, 40])
    parser.add_argument('--offsets', type=int, nargs='+', default=[-40, -8, -1, 0, 1, 8, 40, 768])
    args = parser.parse_args(argv)
    if args.coarse_width < 102 or args.time_samples < 4 or any(s <= 0 for s in args.strengths):
        parser.error('Require coarse width >=102, at least four samples and positive strengths')
    if args.output.exists():
        parser.error('Output already exists; choose a new directory to keep experiments separate')
    with h5py.File(args.source) as source:
        d = source['data']
        if d.ndim != 3 or d.shape[1] != 1:
            parser.error('Expected H5 data shaped time × 1 × frequency')
        coarse = args.coarse_width
        center = args.coarse_index if args.coarse_index is not None else d.shape[-1] // coarse // 2
        lo, hi = (center - 1) * coarse, (center + 2) * coarse
        if lo < 50 or hi + 50 > d.shape[-1]:
            parser.error('Choose an interior block with three full coarse blocks and 50 context bins')
        # Extra context reproduces the production median at crop edges.
        raw = np.asarray(d[:args.time_samples, 0, lo-50:hi+50], dtype=float)
        if raw.shape[0] < 4:
            parser.error('Source contains fewer than four time samples')
        frequency_start, frequency_step = float(d.attrs['fch1']), float(d.attrs['foff'])
    positions = [coarse + offset + 50 for offset in args.offsets]
    if any(not 50 <= index < raw.shape[1]-50 for index in positions):
        parser.error('Offsets must lie inside the three-block measurement crop')
    controls = {m: normalize(raw, m, coarse_width=coarse, first_channel=lo-50) for m in METHODS}
    rows = []
    for offset, index in zip(args.offsets, positions):
        values = raw[:, index]
        sigma = 1.4826 * np.median(np.abs(values - np.median(values)))
        if not np.isfinite(sigma) or sigma <= 0:
            parser.error(f'Invalid temporal noise at offset {offset}')
        for strength in args.strengths:
            # Same one-bin, constant, zero-drift signal for every treatment.
            injected = raw.copy()
            amplitude = strength * sigma / np.sqrt(raw.shape[0])
            injected[:, index] += amplitude
            for method in METHODS:
                control = controls[method]
                treated = normalize(injected, method, coarse_width=coarse, first_channel=lo-50)
                noise = 1.4826 * np.median(np.abs(control[:, index] - np.median(control[:, index])))
                delta = float(np.mean(treated[:, index] - control[:, index]))
                local_snr = delta * np.sqrt(raw.shape[0]) / noise if noise > 0 else None
                spectrum = np.median(control[:, 50:-50], axis=0)
                reference = np.median(spectrum)
                rows.append(dict(offset_bins=offset, global_channel=lo+index-50,
                    frequency_mhz=frequency_start+(lo+index-50)*frequency_step,
                    requested_local_snr=strength, method=method,
                    paired_local_snr=local_snr,
                    snr_transfer=local_snr/strength if local_snr is not None else None,
                    boundary_relative_power=float(spectrum[index-50]/reference),
                    control_temporal_mad_sigma=float(noise)))
    args.output.mkdir(parents=True)
    with (args.output/'measurements.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    metadata = dict(source=str(args.source.resolve()), source_bytes=args.source.stat().st_size,
        source_mtime_ns=args.source.stat().st_mtime_ns, source_crop=[lo-50, hi+50],
        crop_sha256=hashlib.sha256(raw.tobytes()).hexdigest(), time_samples=raw.shape[0],
        assumed_coarse_width=coarse, coarse_index=center, offsets=args.offsets,
        strengths=args.strengths, methods=METHODS, command=sys.argv,
        numpy_version=np.__version__,
        interpretation='Paired local temporal-MAD SNR transfer, NOT SETIcore detection SNR or recovery probability. '
        'Single-bin zero-drift post-instrument injections do not simulate instrument attenuation. '
        'A flat baseline does not establish improved detection. Verify with held-out scans and detector controls.')
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(f'Wrote {len(rows)} paired measurements to {args.output}')


if __name__ == '__main__':
    main()
