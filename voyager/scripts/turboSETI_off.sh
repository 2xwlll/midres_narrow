BASE=/datag/public/voyager_2020

OUT=/datax/scratch/wlll2x/turboSETI_voyager_results

SCRIPT=/home/wlll2x/midres_narrow/voyager/scripts/turboSETI_midres_search.py

NFPC=1024
SNR=5
MIN_DRIFT=0
MAX_DRIFT=40

mkdir -p "$OUT"

for FILE in "$BASE"/spliced*.rawspec.0002.h5
do
    [ ! -f "$FILE" ] && continue

    NAME=$(basename "$FILE" .h5)

    echo ""
    echo "=================================================="
    echo "Running:"
    echo "$FILE"
    echo "=================================================="

    python "$SCRIPT" \
        --case "${NAME}=$FILE" \
        --output-dir "$OUT" \
        --nfpc $NFPC \
        --snr $SNR \
        --min-drift $MIN_DRIFT \
        --max-drift $MAX_DRIFT
done

echo ""
echo "Done."
echo "Results:"
echo "$OUT"