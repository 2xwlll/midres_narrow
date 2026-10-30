# Your first six-scan search

## 1. Check your environment

Follow the install commands in the root README, then check:

```bash
python -c 'import h5py, hdf5plugin, pandas, turbo_seti'
command -v seticore
nvidia-smi -L
```

Choose an available GPU rather than sharing one with a large existing job.

## 2. Describe an ABACAD cadence

Create `my-data/cadence_000/`. Supply three text files, one absolute H5 path per
line. Each observation must contain `data` shaped `(time, 1, frequency)` with
`source_name`, `tstart`, `tsamp`, and `foff` attributes on that dataset.

| File | Ordered contents |
| --- | --- |
| `all.lst` | A1, B, A2, C, A3, D (six distinct observations, increasing time) |
| `on.lst` | A1, A2, A3 (same target) |
| `off.lst` | B, C, D (reference observations) |

The list order matters. You must establish that references are scientifically
appropriate; passing header validation alone cannot establish this.

## 3. Validate before processing

From the repository root:

```bash
python carmen_midres/scripts/choza_midres_search.py \
  --base "$PWD/my-data" --output "$PWD/results/pilot" \
  --cadences 0 --snr 5 10 --max-drift 10 --dry-run
```

Inspect `results/pilot/dry_run.json`: paths, scan order, target labels, frequency
resolution, time sampling, and dimensions. This reads headers without running a
GPU search.

## 4. Run a pilot

```bash
python carmen_midres/scripts/choza_midres_search.py \
  --base "$PWD/my-data" --output "$PWD/results/pilot" \
  --cadences 0 --snr 5 10 --max-drift 10 --gpu 0
```

Raw observations remain unchanged. The script creates normalized copies,
searches each scan with SETIcore, and applies turboSETI event filtering across
the cadence. The current production normalization divides each time row by a
101-bin running median and writes `nfpc=1024` for SETIcore. **Verify that 1024
matches your instrument before using this workflow for other products.**

## 5. Inspect and resume

| Output | Meaning |
| --- | --- |
| `settings.json` | Search configuration and script identity |
| `raw_hit_counts.csv` | Per-scan counts and drift diagnostics |
| `event_summary.csv` | Per-cadence and threshold event counts |
| `cadence_000/snr_*/events.csv` | Events surviving cadence filtering |
| `cadence_000/snr_*/*.log` | SETIcore diagnostics |
| `cadence_000/snr_*/*.done` | Successfully searched and parsed scans |
| `COMPLETE` | Requested processing finished, not a scientific detection claim |

Repeat the identical command to reuse completed scan searches. A new scientific
configuration requires a new output directory. Event tables can be regenerated
on resume; do not interpret this as rerunning every GPU search. Neither hits nor
cadence events alone establish an astrophysical signal.

## 6. Scale after reviewing the pilot

```bash
python carmen_midres/scripts/choza_parameter_sweep.py \
  --base "$PWD/my-data" --output "$PWD/results/sweep" --gpu 0
```

This runs four maximum drift ranges (10, 20, 30, 40 Hz/s) and five thresholds
(5, 7, 10, 12, 15), finishing each cadence before the next. Completed scan
searches are reused. Flattened copies are deleted after successful cadence
processing unless `--keep-flattened` is supplied. Budget disk space for those
copies and test runtime on your own inputs first. Sweep directories have locks
to prevent concurrent writers; the standalone pilot should have one writer.

The historical `run_choza_full_search.sh` and watchdog target a specific host and
catalog. They are not the portable tutorial entry point.
