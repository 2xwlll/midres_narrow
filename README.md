# Mid-resolution narrowband searches

Build a small, inspectable search before scaling to a catalog. This repository
contains real-observation workflows, injection experiments, and reusable
normalization components. The tutorial path below is the supported starting
point; older notebooks and site-specific launchers remain research material.

## Install

```bash
git clone https://github.com/2xwlll/midres_narrow.git
cd midres_narrow
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[search,injections]'
```

Python 3.10+ is required. Scientific Python dependencies are declared in
`pyproject.toml`; this is an initial dependency specification, not a locked
environment. GPU searches additionally require a working NVIDIA driver and a
separately installed `seticore` executable on `PATH`. Observations are not
included. CPU diagnostics work without SETIcore or a GPU.

## Choose a tutorial

1. [Run one six-scan cadence](docs/first-search.md): organize your input lists,
   validate them, search, and interpret the output.
2. [Measure coarse-channel boundary recovery](docs/boundaries.md): compare
   normalizations with paired controls and injections before changing a search.

## Repository map

| Location | Responsibility |
| --- | --- |
| `src/midres_search/normalization.py` | Pure array transformations for experiments |
| `src/midres_search/boundaries.py` | CPU measurements and reproducibility metadata |
| `carmen_midres/scripts/choza_midres_search.py` | One-cadence or selected-cadence GPU search |
| `carmen_midres/scripts/choza_parameter_sweep.py` | Resume-aware catalog sweep |
| `carmen_midres/scripts/measure_boundary_recovery.py` | Paired SETIcore boundary benchmark |
| `carmen_midres/notebooks/` | Exploratory analysis |
| `gb_mars/`, `voyager/`, `A_Sign/` | Other research workflows; not yet migrated |

The production sweep still uses its original median normalization. Experimental
components are independent so changing them cannot silently change active jobs.
Existing site launchers contain local paths; start with the explicit arguments
in the tutorials instead. No observations, credentials, or large result folders
are needed for the source package.

## Development checks

```bash
python -m unittest discover -s tests -v
```

The first boundary experiment and its limitations are recorded in
[the measurement notes](docs/boundaries.md). Contributions should keep raw input
immutable, separate output directories by scientific settings, record controls,
and distinguish detector recovery from local signal-to-noise diagnostics.
