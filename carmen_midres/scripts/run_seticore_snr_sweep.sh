#!/bin/bash

# Exit if an unhandled command fails.
set -e

# Make unmatched wildcards expand to nothing instead of
# remaining as literal text.
shopt -s nullglob


# ==========================================================
# Directories
# ==========================================================

BASE=/datax/scratch/wlll2x/carmen_midres/seticore_snr_sweep
OUT=/datax/scratch/wlll2x/carmen_midres/seticore_snr_results


# ==========================================================
# Seticore parameters
# ==========================================================

MAX_DRIFT=40
SNR_THRESHOLD=5


# ==========================================================
# Counters
# ==========================================================

processed=0
skipped=0
failed=0


# ==========================================================
# Loop over injected SNR directories
# ==========================================================

for snr_dir in "$BASE"/snr_*
do
    [ -d "$snr_dir" ] || continue

    snr_name=$(basename "$snr_dir")

    echo
    echo "======================================================"
    echo "Injection directory: $snr_name"
    echo "======================================================"


    # ======================================================
    # Loop over the first three cadence directories
    # ======================================================

    for cadence_dir in "$snr_dir"/cadence_*
    do
        [ -d "$cadence_dir" ] || continue

        cadence_name=$(basename "$cadence_dir")
        cadence_out="$OUT/$snr_name/$cadence_name"

        mkdir -p "$cadence_out"

        echo
        echo "------------------------------------------------------"
        echo "Cadence: $cadence_name"
        echo "------------------------------------------------------"


        # ==================================================
        # Loop over extracted coarse-channel files
        # ==================================================

        files=("$cadence_dir"/*_coarse30.h5)

        if [ ${#files[@]} -eq 0 ]
        then
            echo "No *_coarse30.h5 files found."
            echo "Directory: $cadence_dir"

            skipped=$((skipped + 1))
            continue
        fi


        for f in "${files[@]}"
        do
            filename=$(basename "$f" .h5)
            output_dat="$cadence_out/${filename}.dat"

            echo
            echo "Processing: $filename"
            echo "Input     : $f"
            echo "Output    : $output_dat"

            if seticore \
                "$f" \
                --output "$output_dat" \
                --max_drift "$MAX_DRIFT" \
                --snr "$SNR_THRESHOLD"
            then
                processed=$((processed + 1))
            else
                echo "WARNING: seticore failed on:"
                echo "$f"

                failed=$((failed + 1))
            fi
        done
    done
done


# ==========================================================
# Final summary
# ==========================================================

echo
echo "======================================================"
echo "Seticore SNR sweep complete"
echo "======================================================"
echo "Processed files : $processed"
echo "Skipped groups  : $skipped"
echo "Failed files    : $failed"
echo "Results root    : $OUT"
echo "Maximum drift   : $MAX_DRIFT Hz/s"
echo "SNR threshold   : $SNR_THRESHOLD"
echo "======================================================"