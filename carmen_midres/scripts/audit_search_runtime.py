#!/usr/bin/env python3
"""Audit validated file reuse and completed timings without touching search outputs."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'outputs/catalog_midres')
    parser.add_argument('--search', type=Path, default=Path('/datax/scratch/wlll2x/carmen_midres/choza_full_sweep_unrestricted'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    groups = json.loads((args.catalog / 'validated_groups.json').read_text())
    headers = {}
    with (args.catalog / 'headers.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            headers[row['path']] = row
    counts = Counter(path for group in groups for path in group['paths'])
    shapes = Counter(tuple(headers[path]['shape']) for path in counts)
    names = {group['name']: group for group in groups}
    timings = defaultdict(list)
    completed = 0
    for drift in args.search.glob('drift_*'):
        for cadence in drift.glob('cadence_*'):
            group = names.get(cadence.name)
            if group is None:
                continue
            sources = {Path(path).stem: path for path in group['paths']}
            for done in cadence.glob('snr_*/*.done'):
                source = sources.get(done.stem)
                log = done.with_suffix('.log')
                if source is None or not log.exists():
                    continue
                completed += 1
                with log.open('rb') as stream:
                    stream.seek(max(0, log.stat().st_size - 1024))
                    tail = stream.read().decode(errors='replace')
                match = re.search(r'dedoppler elapsed time: ([\d.]+)s', tail)
                if match:
                    key = (tuple(headers[source]['shape']), drift.name)
                    timings[key].append(float(match.group(1)))
    report = dict(groups=len(groups), scan_appearances=sum(counts.values()),
                  unique_files=len(counts), current_searches=sum(counts.values()) * 20,
                  searches_with_unique_file_reuse=len(counts) * 20,
                  reuse_savings_percent=100 * (sum(counts.values()) - len(counts)) / sum(counts.values()),
                  completed_scan_searches=completed,
                  shapes=[dict(shape=list(shape), unique_files=count,
                               representative_source=next(p for p in counts if tuple(headers[p]['shape']) == shape))
                          for shape, count in shapes.most_common()],
                  measured_timings=[dict(shape=list(shape), drift=drift, samples=len(values),
                                         median_seconds=statistics.median(values), mean_seconds=statistics.mean(values))
                                    for (shape, drift), values in sorted(timings.items())],
                  limitations=['Timings include dedoppler only, excluding preprocessing and other overhead.',
                               'Early groups are not representative of the file-size distribution.',
                               'Unmeasured shapes and drift passes need benchmarks before a full-run estimate.'])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'shapes'}, indent=2))
    print('Report:', args.report)


if __name__ == '__main__':
    main()
