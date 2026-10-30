import csv
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from midres_search.boundaries import main


class BoundaryCommandTests(unittest.TestCase):
    def test_writes_paired_measurements_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'scan.h5'
            with h5py.File(source, 'w') as f:
                data = f.create_dataset('data', data=np.random.default_rng(3).uniform(1, 2, (8, 1, 1024)))
                data.attrs['fch1'] = 1500.
                data.attrs['foff'] = -.001
            original = source.read_bytes()
            arguments = ['--source', str(source), '--output', str(root/'out'),
                         '--coarse-width', '128', '--offsets', '-1', '0', '1',
                         '--strengths', '10', '--time-samples', '8']
            main(arguments)
            with (root/'out/measurements.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 9)
            for row in rows:
                if row['method'] == 'raw':
                    self.assertAlmostEqual(float(row['snr_transfer']), 1)
            metadata = json.loads((root/'out/metadata.json').read_text())
            self.assertEqual(metadata['time_samples'], 8)
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaises(SystemExit):
                main(arguments)


if __name__ == '__main__':
    unittest.main()
