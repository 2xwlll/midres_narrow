#!/usr/bin/env python3
"""Compare an original H5 scan with its saved median-normalized copy."""
import argparse
from pathlib import Path
import json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path)
    p.add_argument('--flattened', type=Path)
    p.add_argument('--search', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/choza_full_sweep_unrestricted'))
    p.add_argument('--output', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/flattening_comparison'))
    p.add_argument('--coarse-index', type=int, help='Central block index; defaults to the middle of the stored frequency axis')
    p.add_argument('--channels-per-coarse', type=int, default=1024,
                   help='Assumed coarse-channel width; verify against instrument metadata')
    p.add_argument('--time-index', type=int, default=0)
    a = p.parse_args()
    if (a.original is None) != (a.flattened is None):
        p.error('Supply both --original and --flattened, or neither')
    if a.original is None:
        settings = json.loads((a.search / 'drift_10/settings.json').read_text())
        for name, scans in settings['manifest'].items():
            candidate = a.search / 'flattened' / name / Path(scans[0]['path']).name
            if candidate.is_file():
                a.original = Path(scans[0]['path']); a.flattened = candidate
                break
        else:
            p.error('No saved flattened scan found')
    import h5py
    import hdf5plugin  # Register compression filters used by rawspec/gpuspec products.
    import numpy as np
    from scipy.ndimage import median_filter
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with h5py.File(a.original) as original, h5py.File(a.flattened) as flat:
        raw, normalized = original['data'], flat['data']
        if raw.shape != normalized.shape:
            p.error('Original and flattened shapes differ')
        width = int(flat.attrs['flatten_width'])
        coarse = a.channels_per_coarse
        if coarse < 1 or not 0 <= a.time_index < raw.shape[0]:
            p.error('Invalid coarse width or time index')
        center = a.coarse_index if a.coarse_index is not None else raw.shape[-1] // coarse // 2
        lo, hi = max(0, (center - 1) * coarse), min(raw.shape[-1], (center + 2) * coarse)
        if lo >= hi:
            p.error('Coarse index is outside the scan')
        padlo, padhi = max(0, lo - width // 2), min(raw.shape[-1], hi + width // 2)
        row = raw[a.time_index, 0, padlo:padhi]
        baseline = median_filter(row, size=width, mode='reflect')[lo-padlo:hi-padlo]
        row = row[lo-padlo:hi-padlo]
        flatrow = normalized[a.time_index, 0, lo:hi]
        attrs = raw.attrs
        frequency = float(attrs['fch1']) + np.arange(lo,hi) * float(attrs['foff'])
        source = attrs.get('source_name', 'unknown')
        if isinstance(source,bytes): source=source.decode()
        discrepancy = float(np.max(np.abs(flatrow - row / baseline)))
    scale = float(np.median(row))
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True, constrained_layout=True)
    axes[0].plot(frequency, row / scale, lw=.7, label='Original power / median original power')
    axes[0].plot(frequency, baseline / scale, lw=1.5, label=f'{width}-channel running median / same scale')
    axes[0].set_title(f'Single time step {a.time_index}: original and baseline')
    axes[1].plot(frequency, flatrow, lw=.7, label='Saved flattened power = original / running median')
    axes[1].set_title(f'Same time step {a.time_index}: flattened')
    for ax in axes:
        ax.set_ylim(0.3, 1.2)
        ax.set_ylabel('Relative power')
        ax.axhline(1, color='gray', ls=':', lw=1)
    for ax in axes:
        for boundary in range((lo//coarse+1)*coarse,hi,coarse):
            ax.axvline(frequency[boundary-lo],color='gray',ls='--',lw=.8)
        ax.grid(alpha=.2); ax.legend(fontsize=8);ax.set_xlim(frequency[0],frequency[-1])
    axes[-1].set_xlabel('Frequency (MHz); dashed lines: assumed 1024-channel block boundaries' if coarse==1024 else f'Frequency (MHz); dashed lines: assumed {coarse}-channel block boundaries')
    fig.suptitle(f'{source}: before and after running-median division\nThree adjacent frequency blocks; window crosses block boundaries',fontsize=13)
    a.output.mkdir(parents=True,exist_ok=True)
    for ext in ['png','pdf']:
        fig.savefig(a.output / f'flattening_comparison.{ext}',dpi=180)
    plt.close(fig)
    metadata=dict(original=str(a.original), flattened=str(a.flattened), source=str(source),
                  channel_start=lo,channel_stop=hi,assumed_channels_per_coarse=coarse,
                  median_width=width,time_index=a.time_index,original_display_scale=scale,
                  display_ylim=[0.3,1.2],tall_peaks_clipped=True,
                  max_saved_vs_recomputed_difference=discrepancy,
                  caution='One example; block boundaries are assumed, and this does not establish signal recovery or PFB correction across the dataset.')
    (a.output/'comparison_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))
    print('Plot:',a.output/'flattening_comparison.png')


if __name__ == '__main__':
    main()
