#!/usr/bin/env bash
# Launch on a GPU host after the catalog header-validation job finishes.
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
CATALOG_DIR="$PROJECT_DIR/outputs/catalog_midres"
OUTPUT_DIR="/datax/scratch/wlll2x/carmen_midres/choza_full_sweep_unrestricted"
mkdir -p "$OUTPUT_DIR"
exec 9>"$OUTPUT_DIR/launcher.lock"
flock -n 9 || { echo 'A full-search launcher is already running.'; exit 1; }
nvidia-smi -L
while [ ! -f "$CATALOG_DIR/validation_summary.json" ]; do
    echo 'Waiting for catalog header validation to finish.'
    python - "$CATALOG_DIR/headers.jsonl" <<'PY'
import sys, time
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists() or time.time() - p.stat().st_mtime > 300:
    raise SystemExit('Validation is not progressing. Resume scripts/validate_catalog_midres.py before launching.')
PY
    sleep 10
done
python - "$CATALOG_DIR/validation_summary.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
print(json.dumps(report, indent=2), flush=True)
if report['validated_targets'] != 97:
    raise SystemExit('Validation did not produce coverage of all 97 targets; inspect rejected_groups.json.')
PY
exec python -u "$SCRIPT_DIR/choza_parameter_sweep.py" \
    --base "$CATALOG_DIR/validated_cadences" \
    --output "$OUTPUT_DIR" --continue-on-read-error "$@"
