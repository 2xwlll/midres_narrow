"""Produce descriptive recovery plots; repeated injections are not independent trials."""
import argparse
import csv
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    args = parser.parse_args()
    with (args.study/'measurements.csv').open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('No completed measurements')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # Keep crops, drifts, widths and phases separate; never silently pool them.
    conditions = sorted({(r['crop'], r['drift'], r['width_bins'], r['phase']) for r in rows})
    methods = list(dict.fromkeys(r['method'] for r in rows))
    nfpcs = sorted({int(r['nfpc']) for r in rows})
    offsets = sorted({float(r['offset']) for r in rows})
    strengths = sorted({float(r['strength']) for r in rows})
    output = args.study/'figures'
    output.mkdir(exist_ok=True)
    for condition in conditions:
        selected = [r for r in rows if (r['crop'], r['drift'], r['width_bins'], r['phase']) == condition]
        fig, axes = plt.subplots(len(nfpcs), len(methods), squeeze=False,
            figsize=(4*len(methods), 3.5*len(nfpcs)), constrained_layout=True)
        for i, nfpc in enumerate(nfpcs):
            for j, method in enumerate(methods):
                grid = np.full((len(offsets), len(strengths)), np.nan)
                ax = axes[i, j]
                for r in selected:
                    if int(r['nfpc']) != nfpc or r['method'] != method:
                        continue
                    y, x = offsets.index(float(r['offset'])), strengths.index(float(r['strength']))
                    background = r['control_hit'] == 'True'
                    grid[y, x] = int(r['new_recovery'] == 'True')
                    label = 'BG' if background else (f"{float(r['reported_snr']):.1f}" if r['reported_snr'] else 'miss')
                    ax.text(x, y, label, ha='center', va='center', fontsize=8)
                ax.imshow(grid, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')
                ax.set_xticks(range(len(strengths)), [f'{x:g}' for x in strengths])
                ax.set_yticks(range(len(offsets)), [f'{x:g}' for x in offsets])
                ax.set_title(f'{method}; detector nfpc={nfpc}')
                ax.set_xlabel('Injected local track SNR')
                ax.set_ylabel('Offset from assumed physical edge (bins)')
        fig.suptitle(f'Crop {condition[0]}; drift={condition[1]} Hz/s; FWHM={condition[2]} bins; phase={condition[3]}\n'
            'Green: new recovery; red: no new recovery; BG: pre-existing match; labels: detector SNR; blank: unmeasured')
        name = '_'.join(condition).replace('.', 'p')
        for ext in ('png', 'pdf'):
            fig.savefig(output/f'{name}.{ext}', dpi=160)
        plt.close(fig)
    print(f'Wrote {len(conditions)} descriptive recovery figures to {output}')


if __name__ == '__main__':
    main()
