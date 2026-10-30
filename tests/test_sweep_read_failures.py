import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'carmen_midres/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('sweep', SCRIPTS / 'choza_parameter_sweep.py')
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)


class ReadFailureTests(unittest.TestCase):
    def test_bad_cadence_is_recorded_and_later_cadence_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder), continue_on_read_error=True, keep_flattened=True)
            with patch.object(sweep, 'search', side_effect=OSError('filter returned failure during read')):
                self.assertFalse(sweep.run_cadence(args, 'cadence_654', [], {}))
            self.assertTrue((args.output/'read_failures/cadence_654.json').is_file())
            self.assertFalse((args.output/'cadence_complete/cadence_654').exists())
            with patch.object(sweep, 'search') as search, patch.object(sweep, 'filter_events') as events:
                self.assertTrue(sweep.run_cadence(args, 'cadence_655', [], {}))
                self.assertEqual(search.call_count, 4)
                events.assert_called_once()

    def test_other_io_errors_still_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder), continue_on_read_error=True, keep_flattened=True)
            with patch.object(sweep, 'search', side_effect=OSError('No space left on device')):
                with self.assertRaises(OSError):
                    sweep.run_cadence(args, 'cadence_001', [], {})

    def test_successful_retry_clears_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder), continue_on_read_error=True, keep_flattened=True)
            sweep.save_read_failure(args.output, 'cadence_001', OSError('previous failure'))
            with patch.object(sweep, 'search'), patch.object(sweep, 'filter_events'):
                self.assertTrue(sweep.run_cadence(args, 'cadence_001', [], {}))
            self.assertFalse((args.output/'read_failures/cadence_001.json').exists())
