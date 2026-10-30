"""Experimental normalizations of time × frequency power arrays.

No method here is selected automatically for the production search.
"""
import numpy as np
from scipy.ndimage import median_filter

METHODS = ('raw', 'median101', 'block_median101')


def normalize(power, method, *, width=101, coarse_width=1024, first_channel=0):
    """Return a float64 copy, optionally divided by a frequency running median.

    block_median101 reflects within each physical coarse block rather than
    mixing samples across its edges. first_channel is the crop's global index.
    This is a candidate to test, not a correction for missing instrument gain.
    """
    x = np.asarray(power, dtype=np.float64)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError('Expected finite time × frequency power')
    if method not in METHODS:
        raise ValueError(f'Unknown normalization: {method}')
    if width < 3 or width % 2 != 1 or coarse_width < 1 or first_channel < 0:
        raise ValueError('Require odd width >=3, coarse_width >=1, first_channel >=0')
    if method == 'raw':
        return x.copy()
    if method == 'median101':
        baseline = median_filter(x, size=(1, width), mode='reflect')
    else:
        baseline = np.empty_like(x)
        start = 0
        while start < x.shape[1]:
            stop = min(x.shape[1], start + coarse_width - (first_channel + start) % coarse_width)
            baseline[:, start:stop] = median_filter(x[:, start:stop], size=(1, width), mode='reflect')
            start = stop
    if (baseline <= 0).any():
        raise ValueError('Normalization requires strictly positive baselines')
    return x / baseline
