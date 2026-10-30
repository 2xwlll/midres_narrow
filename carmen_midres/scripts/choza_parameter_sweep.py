#!/usr/bin/env python3
"""Finish all drift/SNR settings per cadence, then remove its flattened copies."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import traceback
from datetime import datetime, timezone
from choza_midres_search import main as search
from filter_choza_drift import main as filter_events


def save_read_failure(output, name, error):
    """Keep failures separate from successful cadence completion markers."""
    directory = output / 'read_failures'
    directory.mkdir(exist_ok=True)
    report = dict(cadence=name, error=str(error), traceback=traceback.format_exc(),
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  status='unresolved; not scientifically complete')
    path = directory / f'{name}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(path)


def run_cadence(args, name, common, manifest):
    shared = args.output / 'flattened' / name
    shared.mkdir(parents=True, exist_ok=True)
    for drift in (10, 20, 30, 40):
        destination = args.output / f'drift_{drift}'
        folder = destination / name
        folder.mkdir(parents=True, exist_ok=True)
        link = folder / 'flattened'
        if not link.is_symlink() and not link.exists():
            link.symlink_to(shared, target_is_directory=True)
        elif link.resolve() != shared:
            raise ValueError(f'Unexpected preprocessing directory: {link}')
        print(f'{name}: drift +/-{drift} Hz/s (completed scans reused)', flush=True)
        try:
            search(common + ['--max-drift', str(drift), '--output', str(destination)],
                   prepared_manifest=manifest, only_cadence=name)
        except OSError as error:
            # Disk-full, permissions and generic I/O errors must still stop the
            # search. Only the observed HDF5 decompression failure is isolated.
            if not args.continue_on_read_error or 'filter returned failure during read' not in str(error):
                raise
            save_read_failure(args.output, name, error)
            print(f'{name}: unresolved HDF5 read failure; recorded in read_failures; continuing', flush=True)
            return False
    filter_events([str(args.output), '--cadence', name])
    if not args.keep_flattened:
        cleanup_cadence(args.output, name, manifest[name])
    (args.output / 'read_failures' / f'{name}.json').unlink(missing_ok=True)
    return True


def cleanup_cadence(output, name, scans):
    shared = output / 'flattened' / name
    if shared.is_symlink() or shared.parent.is_symlink():
        raise ValueError(f'Refusing cleanup through a symlink: {shared}')
    for scan in scans:
        target = shared / Path(scan['path']).name
        if target.resolve() == Path(scan['path']).resolve():
            raise ValueError(f'Refusing to remove an original observation: {target}')
        target.unlink(missing_ok=True)
    print(f'{name}: removed flattened copies after all 20 settings and event filtering succeeded', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres'))
    parser.add_argument('--output', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/choza_sweep'))
    parser.add_argument('--gpu', default='0')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep-flattened', action='store_true')
    parser.add_argument('--strict-drift-range', action='store_true')
    parser.add_argument('--continue-on-read-error', action='store_true',
                        help='Record HDF5 decompression failures and process other cadences; never mark them complete')
    parser.add_argument('--retry-read-errors', action='store_true',
                        help='Retry previously recorded read failures after their source data is repaired')
    args = parser.parse_args()
    cadences = sorted(int(p.name.removeprefix('cadence_')) for p in args.base.glob('cadence_*')
                      if p.is_dir() and p.name.removeprefix('cadence_').isdigit())
    if not cadences:
        parser.error('No cadence directories found')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'sweep.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        common = ['--base', str(args.base), '--cadences', *map(str, cadences),
                  '--snr', '5', '7', '10', '12', '15', '--gpu', args.gpu, '--keep-flattened']
        if args.strict_drift_range:
            common.append('--strict-drift-range')
        # Validate originals once, then reuse the manifest in this process.
        search(common + ['--max-drift', '10', '--output', str(args.output / 'drift_10'), '--dry-run'])
        manifest = json.loads((args.output / 'drift_10/dry_run.json').read_text())['manifest']
        print(f'Validated {len(cadences)} cadences; cadence-first scheduling with 20 settings each', flush=True)
        if args.dry_run:
            return
        subprocess.run(['nvidia-smi', '-L'], check=True)
        for cadence in cadences:
            name = f'cadence_{cadence:03d}'
            marker = args.output / 'cadence_complete' / name
            if marker.exists():
                if not args.keep_flattened:
                    cleanup_cadence(args.output, name, manifest[name])
                print(f'{name}: already complete; reusing results', flush=True)
                continue
            failure = args.output / 'read_failures' / f'{name}.json'
            if args.continue_on_read_error and failure.exists() and not args.retry_read_errors:
                print(f'{name}: unresolved read failure; deferred (use --retry-read-errors after repair)', flush=True)
                continue
            run_cadence(args, name, common, manifest)
        unresolved = sorted(p.stem for p in (args.output / 'read_failures').glob('cadence_*.json'))
        if unresolved:
            (args.output / 'INCOMPLETE_READ_FAILURES.json').write_text(json.dumps(unresolved, indent=2) + '\n')
            print(f'Available cadences processed; {len(unresolved)} unresolved read failures. Full search NOT complete.', flush=True)
            raise SystemExit(2)
        (args.output / 'INCOMPLETE_READ_FAILURES.json').unlink(missing_ok=True)
        for drift in (10, 20, 30, 40):
            (args.output / f'drift_{drift}' / 'COMPLETE').write_text('All cadences completed.\n')
        (args.output / 'COMPLETE').write_text('All 20 settings completed for every cadence.\n')
        (args.output / 'DRIFT_FILTER_COMPLETE').write_text('All cadences filtered including zero drift.\n')


if __name__ == '__main__':
    main()
