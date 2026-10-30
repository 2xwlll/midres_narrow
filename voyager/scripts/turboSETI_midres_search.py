#!/usr/bin/env python3
"""
Minimal turboSETI mid-resolution search pipeline.

Runs turboSETI on rawspec mid-resolution HDF5 files.

Designed for:
- Breakthrough Listen Voyager mid-res data
- CARMENES injected mid-res tests

Important:
nfpc must be manually supplied because mid-resolution files
do not reliably store coarse-channel information.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from blimpy import Waterfall
from turbo_seti.find_doppler.find_doppler import FindDoppler
from turbo_seti.find_event.find_event import read_dat


DEFAULT_OUTDIR = (
    "/datax/scratch/wlll2x/"
    "turboSETI_midres_results"
)


# ------------------------------------------------------------
# Arguments
# ------------------------------------------------------------

def parse_args():

    parser = argparse.ArgumentParser(
        description="Run turboSETI on mid-resolution rawspec files"
    )

    parser.add_argument(
        "--case",
        required=True,
        help="label=/path/to/file.h5"
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTDIR
    )

    parser.add_argument(
        "--snr",
        type=float,
        default=10
    )

    parser.add_argument(
        "--max-drift",
        type=float,
        default=40
    )

    parser.add_argument(
        "--min-drift",
        type=float,
        default=0
    )

    parser.add_argument(
        "--nfpc",
        type=int,
        required=True,
        help="Fine channels per coarse channel"
    )

    parser.add_argument(
        "--candidate-window",
        type=float,
        default=5.0
    )

    return parser.parse_args()



# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def parse_case(case):

    if "=" not in case:
        raise ValueError(
            "Use label=/path/file.h5"
        )

    label, path = case.split("=", 1)

    if not os.path.exists(path):
        raise FileNotFoundError(path)

    return label, path



def safe_float(value, default=0.0):

    try:
        return float(value)

    except Exception:
        return default



def frequency_axis(header, nchan):

    fch1 = safe_float(
        header.get("fch1")
    )

    foff = safe_float(
        header.get("foff")
    )

    return (
        fch1 +
        np.arange(nchan) * foff
    )



def infer_n_coarse_chan(header, nfpc, nchan):

    nchans = int(
        header.get(
            "nchans",
            nchan
        )
    )

    n_coarse = round(
        nchans / nfpc
    )

    print()
    print(
        f"Using nfpc={nfpc}"
    )

    print(
        f"Total channels={nchans}"
    )

    print(
        f"Derived n_coarse_chan={n_coarse}"
    )

    return n_coarse



# ------------------------------------------------------------
# Plotting
# ------------------------------------------------------------

def plot_candidate(
    data,
    freqs,
    tsamp,
    candidate_freq,
    outfile,
    window
):

    mask = (
        np.abs(freqs - candidate_freq)
        <= window
    )

    if not np.any(mask):
        return


    data = data[:, mask]

    freqs = freqs[mask]


    data = np.maximum(
        data,
        1
    )


    data_db = (
        10*np.log10(data)
    )


    duration = (
        data.shape[0]
        *
        tsamp
    )


    fig, ax = plt.subplots(
        figsize=(12,5)
    )


    im = ax.imshow(
        data_db,
        aspect="auto",
        origin="lower",
        extent=[
            freqs[0],
            freqs[-1],
            0,
            duration
        ]
    )


    fig.colorbar(
        im,
        ax=ax,
        label="Power (dB)"
    )


    ax.set_xlabel(
        "Frequency MHz"
    )

    ax.set_ylabel(
        "Time seconds"
    )


    ax.set_title(
        f"Candidate {candidate_freq:.6f} MHz"
    )


    fig.tight_layout()

    fig.savefig(
        outfile,
        dpi=250
    )

    plt.close(fig)



# ------------------------------------------------------------
# Main search
# ------------------------------------------------------------

def run_case(label, filepath, args):

    outdir = (
        Path(args.output_dir)
        /
        label
    )

    outdir.mkdir(
        parents=True,
        exist_ok=True
    )


    print()
    print("="*60)
    print(filepath)
    print("="*60)


    t0 = time.time()


    wf = Waterfall(
        filepath,
        load_data=True
    )


    load_time = time.time()-t0


    data = wf.data[:,0,:]

    header = wf.header


    print()
    print("DATA INFORMATION")

    print(
        "shape:",
        data.shape
    )

    print(
        "nchans:",
        header.get("nchans")
    )

    print(
        "foff:",
        header.get("foff")
    )

    print(
        "fch1:",
        header.get("fch1")
    )


    freqs = frequency_axis(
        header,
        data.shape[1]
    )


    tsamp = safe_float(
        header.get("tsamp"),
        1.0
    )


    n_coarse_chan = infer_n_coarse_chan(
        header,
        args.nfpc,
        data.shape[1]
    )



    print()
    print("Running turboSETI...")


    t1 = time.time()


    fd = FindDoppler(
        filepath,
        max_drift=args.max_drift,
        min_drift=args.min_drift,
        snr=args.snr,
        out_dir=str(outdir),
        n_coarse_chan=n_coarse_chan
    )


    fd.search()


    search_time = time.time()-t1



    # Find dat file

    dat_files = list(
        outdir.glob("*.dat")
    )


    if len(dat_files) > 0:

        datfile = dat_files[0]

        hits = read_dat(
            str(datfile)
        )

    else:

        datfile = None

        hits = pd.DataFrame()



    summary = {

        "file": filepath,

        "shape": list(data.shape),

        "nfpc": args.nfpc,

        "n_coarse_chan": n_coarse_chan,

        "snr": args.snr,

        "min_drift": args.min_drift,

        "max_drift": args.max_drift,

        "candidate_count": len(hits),

        "search_time_sec": search_time,

    }



    if len(hits) > 0:


        print()
        print(
            "Candidates:",
            len(hits)
        )


        hits["SNR_abs"] = (
            hits["SNR"].abs()
        )


        hits = hits.sort_values(
            "SNR_abs",
            ascending=False
        )


        hits.to_csv(
            outdir/"candidates.csv",
            index=False
        )


        strongest = hits.iloc[0]


        freq = float(
            strongest["Freq"]
        )


        print()
        print("Strongest:")
        print(strongest)



        plot_candidate(
            data,
            freqs,
            tsamp,
            freq,
            outdir/"candidate_waterfall.png",
            args.candidate_window
        )


        summary["strongest_frequency_MHz"] = freq

        summary["strongest_SNR"] = float(
            strongest["SNR"]
        )


    else:

        print(
            "No candidates found"
        )



    with open(
        outdir/"summary.json",
        "w"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2
        )


    print()
    print("Finished")



def main():

    args = parse_args()

    label, filepath = parse_case(
        args.case
    )

    run_case(
        label,
        filepath,
        args
    )



if __name__ == "__main__":
    main()