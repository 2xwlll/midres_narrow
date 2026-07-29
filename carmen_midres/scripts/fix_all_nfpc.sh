#!/bin/bash


FIXER=~/midres_narrow/carmen_midres/scripts/fix_nfpc.py

BASE=/datax/scratch/wlll2x/seticore_test


echo "===================================="
echo "Fixing Voyager files"
echo "===================================="


while read file
do

    name=$(basename "$file" .h5)

    python "$FIXER" \
        "$file" \
        "$BASE/voyager_fixed/${name}_nfpc.h5"

done < "$BASE/voyager.lst"



echo ""
echo "===================================="
echo "Fixing CARMEN OFF files"
echo "===================================="


while read file
do

    name=$(basename "$file" .h5)

    python "$FIXER" \
        "$file" \
        "$BASE/carmen_off_fixed/${name}_nfpc.h5"

done < "$BASE/carmen_off.lst"


echo ""
echo "DONE"
