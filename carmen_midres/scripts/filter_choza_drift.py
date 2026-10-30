#!/usr/bin/env python3
"""Apply absolute drift limits to saved hits, then recompute cadence events."""
import argparse
import csv
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cadence', help='Filter one completed cadence before the full search finishes')
    args = parser.parse_args(argv)
    if not args.cadence and not (args.output / 'COMPLETE').exists():
        parser.exit(2, 'The search has not finished in this directory. Run the sweep first; '
                    'apply this filter after its COMPLETE marker appears.\n')
    manifests = sorted(args.output.glob('drift_*/cadence_*/snr_*/dat_files.lst'))
    if args.cadence:
        manifests = [m for m in manifests if m.parents[1].name == args.cadence]
        for drift in (10, 20, 30, 40):
            if not (args.output / f'drift_{drift}' / args.cadence / 'COMPLETE').exists():
                parser.error('Cadence must complete all four drift settings before filtering')
    if not manifests:
        parser.exit(2, 'No completed cadence hit manifests found in this directory.\n')
    from turbo_seti.find_event.find_event import find_events
    import pandas as pd
    summaries = []
    summary_path = args.output / 'drift_filtered_summary.csv'
    if args.cadence and summary_path.exists():
        previous = pd.read_csv(summary_path)
        summaries = previous[previous['cadence'] != args.cadence].to_dict('records')
    for manifest in manifests:
        limit = float(manifest.parents[2].name.removeprefix('drift_'))
        destination = manifest.parent / 'drift_filtered'
        destination.mkdir(exist_ok=True)
        files, kept, removed = [], 0, 0
        for source in manifest.read_text().splitlines():
            if not source.strip():
                continue
            source = Path(source.strip())
            target = destination / source.name
            with source.open() as inp, target.open('w') as out:
                for line in inp:
                    if not line.strip() or line.lstrip().startswith('#'):
                        out.write(line)
                    elif abs(float(line.split()[1])) <= limit:
                        out.write(line); kept += 1
                    else:
                        removed += 1
            files.append(str(target.resolve()))
        if len(files) != 6:
            raise ValueError(f'Expected six scans in {manifest}')
        (destination / 'dat_files.lst').write_text('\n'.join(files)+'\n')
        events = find_events(files, filter_threshold=3, check_zero_drift=True,
                             SNR_cut=None, max_drift_rate=None)
        if events is None:
            events = pd.DataFrame(columns=['Hit_ID', 'Freq', 'DriftRate', 'SNR'])
        events.to_csv(destination / 'events.csv', index=False)
        summaries.append(dict(cadence=manifest.parents[1].name,
                              snr=float(manifest.parent.name.removeprefix('snr_')),
                              max_drift=limit, kept_hits=kept, removed_hits=removed,
                              event_rows=len(events),
                              unique_events=events['Hit_ID'].nunique() if len(events) else 0))
    if not summaries:
        raise RuntimeError('No completed cadence hit manifests found')
    pd.DataFrame(summaries).to_csv(args.output / 'drift_filtered_summary.csv', index=False)
    marker = args.output / 'cadence_complete' / args.cadence if args.cadence else args.output / 'DRIFT_FILTER_COMPLETE'
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('Post-search drift filtering completed.\n')


if __name__ == '__main__':
    main()
