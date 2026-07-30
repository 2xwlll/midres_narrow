#!/bin/bash

# ==========================================================
# Seticore test on extracted coarse channel files
# ==========================================================

BASE=/datax/scratch/wlll2x/seticore_test

OUT=/datax/scratch/wlll2x/seticore_test/results

mkdir -p "$OUT"


# ==========================================================
# Run seticore
# ==========================================================

for f in "$BASE"/*_coarse30.h5

do

    filename=$(basename "$f" .h5)

    echo "======================================="
    echo "Processing:"
    echo "$filename"
    echo "======================================="


    seticore \
        "$f" \
        --output "$OUT/${filename}.dat" \
        --max_drift 40 \
        --snr 5


done


echo ""
echo "======================================="
echo "Seticore coarse channel test complete"
echo "======================================="

