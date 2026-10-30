import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import h5py
import numpy as np

from midres_search.boundary_study import block_crossing, matches, run, signal_track


class StudyTests(unittest.TestCase):
    def test_sky_drift_sign_and_crossing(self):
        track, centers = signal_track((16, 128), 65, 1, -.000001, 1, 1)
        self.assertEqual(centers[-1], 50)
        self.assertTrue(block_crossing(centers, 64))
        self.assertFalse(block_crossing(centers, 128))
        self.assertEqual(np.argmax(track[0]), 65)
        _, increasing = signal_track((16, 128), 50, 1, .000001, 1, 1)
        self.assertEqual(increasing[-1], 65)

    def test_subbin_and_crop_guard(self):
        _, centers = signal_track((16, 128), 60.5, 0, .000001, 1, 1)
        np.testing.assert_allclose(centers, 60.5)
        with self.assertRaises(ValueError):
            signal_track((16, 128), 3, -1, .000001, 1, 1)

    def test_match_requires_frequency_and_drift(self):
        hits = [dict(frequency=100., drift=2., snr=9.)]
        self.assertEqual(len(matches(hits, 100., 2., .01, .1)), 1)
        self.assertEqual(matches(hits, 100., -2., .01, .1), [])

    def test_resume_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.h5'
            with h5py.File(source, 'w') as f:
                d = f.create_dataset('data', data=np.random.default_rng(4).uniform(1, 2, (8, 1, 6144)))
                d.attrs['tsamp'], d.attrs['foff'], d.attrs['fch1'] = 1., -.001, 1500.
            original = source.read_bytes()
            config = dict(sources=[dict(path=str(source), blocks=[2])], coarse_width=1024,
                offsets=[0, 40], strengths=[10], drifts=[0], widths_bins=[1],
                subbin_phases=[0], methods=['raw'], detector_nfpc=[1024, 3072])
            searches = []

            def fake_detector(command, **kwargs):
                if '--help' in command:
                    return SimpleNamespace(stdout='test executable')
                searches.append(command)
                path = Path(command[command.index('--output')+1])
                path.write_text('# synthetic empty detector output\n')
                return SimpleNamespace(returncode=0)

            with patch('midres_search.boundary_study.shutil.which', return_value=sys.executable), \
                 patch('midres_search.boundary_study.subprocess.run', side_effect=fake_detector):
                run(config, root/'out', '1', limit=1)
                self.assertFalse((root/'out/COMPLETE.json').exists())
                run(config, root/'out', '1')
                self.assertTrue((root/'out/COMPLETE.json').exists())
                self.assertEqual(len(list((root/'out/cases').glob('*.json'))), 4)
                before = len(searches)
                run(config, root/'out', '1')
                self.assertEqual(len(searches), before)
                config['strengths'] = [20]
                with self.assertRaises(ValueError):
                    run(config, root/'out', '1')
            self.assertEqual(source.read_bytes(), original)
