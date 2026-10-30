# Coarse-channel boundary measurements

The [comprehensive study protocol](boundary-study.md) separates bandpass,
normalization, detector block geometry, DC handling and cadence recovery. Its
new resumable matrix runner adds signed drift, Gaussian widths, sub-bin phases,
processing-block ablations and an oracle baseline diagnostic. The historical
experiments below are preliminary evidence, not a completed study.

## What we know

The original experiment used one DDO210 scan, three locations, zero drift,
four injected local track strengths, and paired raw/median101 treatments.
At requested strengths 5, 10, 20, 40:

| Location | Raw recoveries | Median101 recoveries |
| --- | --- | --- |
| Interior, away from DC | None | 20, 40 |
| Exact assumed coarse boundary | None | None |
| Shoulder (+40 bins) | None | 40 |

These are individual outcomes, not recovery probabilities. Local temporal-MAD
track SNR is not SETIcore's reported SNR. Signals were injected after instrument
response, so the experiment does not model attenuation through the instrument.
The original report is `edge_recovery_test/20261013T155304` on the research host;
large data and result artifacts are not bundled with the source repository.

## Candidate normalization

`midres_search.normalization.normalize` implements three independent treatments:

* `raw`: unchanged power.
* `median101`: the existing row-wise running median, crossing coarse edges.
* `block_median101`: the same window reflected inside each coarse block.

The last method tests whether mixing different responses across an edge is
harmful. It may also create artifacts or change noise statistics. A flatter
baseline alone is insufficient evidence to choose it. It cannot restore
information lost at an instrument edge. Width 1024 is an assumption to verify,
not a boundary inferred from the spectrum.

## CPU diagnostic

After installing the local package:

```bash
midres-boundaries --source /absolute/path/observation.h5 \
  --output results/boundary-cpu-scan1 --time-samples 128
```

This reads three interior coarse blocks plus context, compares eight offsets
around a boundary, and injects identical constant one-bin signals at each
strength before normalization. Outputs are `measurements.csv` and
`metadata.json`, including the crop hash and assumed block width.
`paired_local_snr` measures the added mean power relative to the control's
temporal MAD; `boundary_relative_power` measures baseline shape. Neither
quantity reports detector recovery. Existing output directories are refused.

## First CPU comparison (2026-10-19)

On the original DDO210 scan, 128 time samples, eight offsets and four strengths
produced 96 paired measurements. At strength 40, the exact-edge local SNR
transfer was 1.056 for median101 and 0.860 for block_median101 (raw is 1.0 by
construction). Relative control power at the edge was 0.891 and 0.900,
respectively. Thus slightly flatter edge power did not imply better local
signal transfer. Nearby offsets were mixed; this does not support replacing
the production normalization. These measurements use single-bin injections,
whereas the detector benchmark uses Gaussian profiles.

Local artifacts are in
`carmen_midres/outputs/boundary_diagnostics/20261019_ddo210/` (ignored by Git).
Repeat the CPU command above with the same source to generate an independent
report; metadata records the exact crop and assumptions.

## Actual detector recovery

On a host with an available GPU and SETIcore:

```bash
python carmen_midres/scripts/measure_boundary_recovery.py \
  --source /absolute/path/observation.h5 \
  --output "$PWD/results/boundary-detector" --gpu 1 \
  --offsets -40 -8 -1 0 1 8 40 768 --strengths 5 10 20 40
```

Each run has a timestamp directory. This extends the original test without
changing it: three treatments, eight offsets, four strengths (96 injected
searches plus three controls). Gaussian injections, half-bin frequency
matching, and zero-drift matching follow the original experiment. `recovery.csv`
reports `recovered`, `control_hit`, and `new_recovery`; only a hit absent from
the corresponding control counts as a new recovery. Retain logs and metadata.
The timestamp output is isolated; this benchmark does not yet resume partial
runs. Start with fewer offsets/strengths to estimate runtime.

## Completion criteria before choosing a replacement

1. Run the expanded paired detector test on the original scan and several
   independent scans and coarse blocks (select with `--coarse-index`).
2. Check frequency-axis alignment, assumed block boundaries, and unmodified
   controls; tabulate background matches separately.
3. Add signed drift tracks, widths, and strengths near the detector threshold;
   the present benchmark covers zero drift only.
4. Compare edge/shoulder recovery and interior recovery, reported SNR, and
   false-positive behavior on held-out observations. Repeat enough independent
   trials to quantify uncertainty before reporting recovery probabilities.
5. Adopt a method only after detector validation, in a new production output
   directory with explicit normalization settings and provenance.

The CPU diagnostic and extended detector harness are implemented. Expanded GPU
recovery and drift/width coverage remain open research work; no replacement
normalization is validated or enabled in the active catalog search.
