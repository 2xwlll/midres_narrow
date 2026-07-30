#!/bin/bash

BASE=/datax/scratch/wlll2x/seticore_test

SETI_OUT=$BASE/seticore_outputs
TURBO_OUT=$BASE/turboSETI_outputs

mkdir -p "$SETI_OUT"
mkdir -p "$TURBO_OUT"


echo "===================================="
echo "Running Voyager"
echo "===================================="


for f in "$BASE"/voyager_fixed/*.h5
do

    name=$(basename "$f" .h5)

    echo ""
    echo "Processing $name"


    echo "---- seticore ----"

    seticore \
        "$f" \
        --output "$SETI_OUT/${name}.dat" \
        --max_drift 40 \
        --snr 3


    echo "---- turboSETI ----"

    python /home/wlll2x/midres_narrow/voyager/scripts/turboSEIT_midres_search.py \
        --case "$name=$f" \
        --output-dir "$TURBO_OUT" \
        --snr 3 \
        --min-drift 0 \
        --max-drift 40 \
        --nfpc 1024


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


    echo "---- seticore ----"

    seticore \
        "$f" \
        --output "$SETI_OUT/${name}.dat" \
        --max_drift 40 \
        --snr 3


    echo "---- turboSETI ----"

    python /home/wlll2x/midres_narrow/voyager/scripts/turboSEIT_midres_search.py \
        --case "$name=$f" \
        --output-dir "$TURBO_OUT" \
        --snr 3 \
        --min-drift 0 \
        --max-drift 40 \
        --nfpc 1024


done


echo ""
echo "COMPLETE"