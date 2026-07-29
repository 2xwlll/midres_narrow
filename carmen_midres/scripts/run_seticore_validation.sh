#!/bin/bash

BASE=/datax/scratch/wlll2x/seticore_test
OUT=$BASE/outputs

mkdir -p "$OUT"


echo "===================================="
echo "Running Voyager"
echo "===================================="


for f in "$BASE"/voyager_fixed/*.h5
do

    name=$(basename "$f" .h5)

    echo ""
    echo "Processing $name"

    seticore \
        "$f" \
        --output "$OUT/${name}.dat" \
        --max_drift 40 \
        --snr 3

done


echo ""
echo "===================================="
echo "Running CARMEN OFF"
echo "===================================="


for f in "$BASE"/carmen_off_fixed/*.h5
do

    name=$(basename "$f" .h5)

    echo ""
    echo "Processing $name"


    seticore \
        "$f" \
        --output "$OUT/${name}.dat" \
        --max_drift 40 \
        --snr 3

done


echo ""
echo "COMPLETE"
