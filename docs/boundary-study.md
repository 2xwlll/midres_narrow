# Boundary study protocol

The aim is to explain lost sensitivity and measure recovery, not simply make a
plot look flat. The production catalog remains on its existing normalization.

## Mechanisms to separate

| Mechanism | Distinguishing experiment |
| --- | --- |
| Residual mean bandpass depresses a column below the detector's reference level | Measure column-sum deficit alongside recovery and reported detector SNR |
| Median window crosses a discontinuity or smooths over an edge trough | Raw vs median101 vs block_median101, offsets on both sides |
| Signal changes its own fitted baseline | Refit median vs median fitted to the uninjected control (`frozen_median101`) |
| Drift track leaves a processing block | Same data with `nfpc=1024` vs `nfpc=3072`; record crossings explicitly |
| DC replacement suppresses or changes a signal | Include physical center (+512 bins), log telescope metadata, move processing centers with nfpc |
| Detector threshold or nearby stronger hit suppresses a candidate | Retain all .dat files and control hit counts; test bright positive controls |
| Incorrect assumed physical boundaries | Verify metadata and repeated bandpass structure before physical interpretation |

These are hypotheses, not established causes. The installed binary reports
SETIcore 1.0.6. Current upstream
[dedoppler.cu](https://github.com/lacker/seticore/blob/master/dedoppler.cu)
uses a central-90%-of-column-sums noise estimate, a median reference, and
neighborhood hit suppression. It rejects paths leaving its processing block.
[h5_reader.cpp](https://github.com/lacker/seticore/blob/master/h5_reader.cpp)
loads one coarse block at a time and conditionally replaces its middle column.
Upstream source is a mechanism guide; it does not prove the installed binary
has identical code. Every experiment records the installed executable hash.

Dividing by a smoothed median cannot guarantee a flat column-sum baseline or
equal noise. A notch narrower than the window can remain depressed, and scaling
signal and noise together cannot undo prior information loss. A change in nfpc
also changes reference statistics and potentially DC replacement; it is not a
pure isolation of path crossing. Check stationary and interior controls too.

## Stages

1. **Execution and coordinate checks.** Unit-test both signs of frequency spacing,
   positive sky drift, sub-bin position, crop containment, hit matching, resume,
   and input preservation. Run a short real GPU pilot with controls.
2. **Original-scan dose response.** Five offsets (-1, 0, +1, +40, +768), strengths
   20, 40, 80, 160, four treatments and two detector block sizes: 160 cases plus
   eight control searches. Include very bright injections before interpreting
   a complete lack of recovery. One noise realization is not 160 trials of a
   recovery probability.
3. **Development matrix.** At least two different scans/targets and two separated
   frequency blocks per scan. Nine offsets including DC and interior controls;
   strengths spanning the observed transition; negative, zero and positive
   drift; one- and three-bin Gaussian FWHM; phases 0 and 0.5 bin. This is roughly
   ten thousand cases; estimate time from stage 2 before launching.
4. **Detector-only controls.** Generate independent flat-noise realizations,
   then known multiplicative bandpasses and notches. Compare with real data;
   vary telescope/DC behavior explicitly in synthetic files. These are required
   before claiming an instrument-specific cause. This generator is not yet
   implemented in the matrix runner.
5. **Alternative estimation.** Only after diagnosis: compare median window
   widths and a response template fitted on other coarse blocks/scans, with
   robust noise scaling. Fit on development data only. The frozen-control
   treatment is an oracle ablation, not a deployable normalization.
6. **Held-out validation.** Independent scans, observing epochs and blocks;
   calibrate to a common false-positive budget using uninjected and shuffled
   controls. Test full-length files and six-scan cadence event recovery, not
   only cropped single-scan hits. Freeze the method before this stage.

## Executable matrix

```bash
PYTHONPATH=src python -m midres_search.boundary_study \
  --config /path/to/matrix.json --output results/my-boundary-study --gpu 1
```

See [the example matrix](../examples/boundary-matrix.json). Replace its source
path and select valid interior block indices. The assumed 1024-bin physical
block width requires verification for each input product. Crops contain three
full blocks with 50 bins of median context. The source is never modified.

`--limit 8` executes at most eight new injected cases as a bounded smoke test.
Repeating the command resumes. A lock prevents two writers; changed settings,
source identity, code, or binary require a new output directory. Successful
detector calls are cached individually. Temporary H5 inputs are deleted only
after successful parsing; failed inputs remain for diagnosis. This runner has
no automatic restart daemon: rerun the identical command after correcting an
execution failure.

Generate separate figures for each crop, drift, width and sub-bin phase:

```bash
PYTHONPATH=src python -m midres_search.boundary_report --study results/my-boundary-study
```

Install the `search` optional dependencies for Matplotlib. Labels distinguish
background matches from new recoveries; incomplete cases remain blank.

Outputs:

* `study.json`: configuration, code/binary hashes and executable help.
* `crops/*.json`: original metadata, channel origin and crop hashes.
* `cases/*.json`: atomic successful case records, including background matches.
* `measurements.csv`: regenerable combined measurements (updated every 12 cases).
* `detector/`: cached hit files, per-call logs and input hashes.
* `COMPLETE.json`: all configured cases finished successfully.

Track amplitude is calibrated against temporal MAD along the injected track;
strength is local track SNR, not SETIcore SNR. Gaussian profiles are sampled at
time centers; intra-integration drift smearing and pre-instrument attenuation
are not simulated. Record those limitations in any conclusions.

Matching allows one frequency bin and 1.1 padded-time drift bins. This is a
predeclared tolerance, not evidence of exact drift recovery. Inspect reported
frequency/drift, quantify chance matches with controls, and distinguish a
pre-existing match from a new recovery. Drift sign follows sky frequency,
regardless of the sign of `foff`.

## Analysis and decisions

Plot recovery versus offset and strength separately by method, nfpc, drift,
width and phase. Also plot reported SNR, control column-sum deficit, background
hit rate, and whether tracks cross detector boundaries. Diagnose candidate
suppression from retained hit files, not just a binary recovery flag.

Repeated injections in identical noise are paired measurements. Count
independent observing sessions/scans as sampling units, report paired method
differences, and use cluster resampling by session/scan for uncertainty once
there are enough independent units. Two scans cannot establish robust
population confidence intervals. Report nondetections and background matches,
not just recovered cases. Do not pool real and synthetic data.

Adopt a new normalization only if held-out edge recovery improves without
material interior loss at a matched false-positive rate, and cadence-event
performance supports the result. Decide the acceptable interior loss and
false-positive budget before validation. Until then, findings are diagnostic.
