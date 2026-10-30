import unittest
import numpy as np
from midres_search.normalization import normalize


class NormalizationTests(unittest.TestCase):
    def test_block_step_does_not_mix_gain_across_boundary(self):
        # A sharp drop has a very different response in adjacent coarse blocks.
        x = np.tile(np.r_[np.full(8, 100.), np.full(8, 2.)], (4, 1))
        np.testing.assert_allclose(normalize(x, 'block_median101', width=5, coarse_width=8), 1)

    def test_cropped_global_alignment(self):
        x = np.tile(np.r_[np.full(5, 10.), np.full(8, 2.), np.full(3, 7.)], (4, 1))
        np.testing.assert_allclose(normalize(x, 'block_median101', width=5,
                                           coarse_width=8, first_channel=3), 1)

    def test_narrow_injection_survives_without_mutating_input(self):
        x = np.ones((4, 32))
        x[:, 16] += 3
        before = x.copy()
        y = normalize(x, 'block_median101', width=5, coarse_width=16)
        np.testing.assert_array_equal(x, before)
        np.testing.assert_allclose(y[:, 16], 4)

    def test_invalid_noise_rejected(self):
        with self.assertRaises(ValueError):
            normalize(np.zeros((4, 16)), 'median101')
        with self.assertRaises(ValueError):
            normalize(np.full((4, 16), np.nan), 'raw')


if __name__ == '__main__':
    unittest.main()
