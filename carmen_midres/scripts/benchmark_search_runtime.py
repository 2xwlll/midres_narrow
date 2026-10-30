#!/usr/bin/env python3
"""Benchmark common validated file shapes in an isolated scratch directory."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from choza_midres_search import flatten


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=Path(__file__).resolve().parents[1] / 'outputs/search_runtime_audit.json')
    parser.add_argument('--output', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/runtime_benchmark'))
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--shapes', type=int, default=3)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.shapes < 1:
        parser.error('--shapes must be positive')
    selected = json.loads(args.audit.read_text())['shapes'][:args.shapes]
    if args.dry_run:
        print(json.dumps(selected, indent=2))
        return
    import os
    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
    executable = shutil.which('seticore')
    if executable is None:
        parser.error('seticore is not on PATH')
    subprocess.run(['nvidia-smi', '-L'], check=True)
    args.output.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an earlier benchmark or share its intermediate files.
    run = args.output / time.strftime('%Y%m%dT%H%M%S')
    run.mkdir()
    rows = []
    for index, item in enumerate(selected):
        folder = run / f'shape_{index}'
        folder.mkdir()
        source = Path(item['representative_source'])
        target = folder / source.name
        started = time.monotonic()
        flatten(source, target, 101)
        preprocessing = time.monotonic() - started
        for drift in (10, 20, 30, 40):
            output = folder / f'drift_{drift}.dat'
            started = time.monotonic()
            with output.with_suffix('.log').open('w') as log:
                subprocess.run([executable, str(target), '--output', str(output),
                                '--max_drift', str(drift), '--snr', '5'],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            rows.append(dict(source=str(source), shape=item['shape'], gpu=args.gpu,
                             drift=drift, snr=5, preprocessing_seconds=preprocessing,
                             search_wall_seconds=time.monotonic() - started))
            (run / 'timings.json').write_text(json.dumps(rows, indent=2) + '\n')
        target.unlink()
    print('Benchmark timings:', run / 'timings.json')
    print('SNR=5 only; SNR-dependent runtime still needs validation.')


if __name__ == '__main__':
    main()
