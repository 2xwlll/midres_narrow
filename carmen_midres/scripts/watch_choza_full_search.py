#!/usr/bin/env python3
"""Run from cron every ten minutes, using the search's Python environment."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

OUTPUT = Path('/datax/scratch/wlll2x/carmen_midres/choza_full_sweep_unrestricted')
LAUNCHER = Path(__file__).resolve().with_name('run_choza_full_search.sh')
MAX_FAILURES = 5


def log(message):
    print(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + message, flush=True)


def complete():
    return all((OUTPUT / name).is_file() for name in ('COMPLETE', 'DRIFT_FILTER_COMPLETE'))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / 'watchdog.lock').open('a') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if complete():
            return
        # These also detect the search started manually before cron was installed.
        for name in ('launcher.lock', 'sweep.lock'):
            with (OUTPUT / name).open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
        state_path = OUTPUT / 'watchdog_state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        failures = state.get('failures', 0)
        if failures >= MAX_FAILURES or time.time() < state.get('next_attempt', 0):
            return
        env = os.environ.copy()
        # The launcher calls `python`; use this watchdog's virtual environment.
        env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '/usr/bin:/bin')
        log('Starting/resuming full search')
        started = time.time()
        with (OUTPUT / 'run.log').open('a') as output:
            result = subprocess.run(['bash', str(LAUNCHER)], env=env,
                                    stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        if complete():
            state_path.unlink(missing_ok=True)
            log('Search complete; no further launches')
            return
        # An hour of execution resets the consecutive short-failure counter.
        failures = 1 if time.time() - started >= 3600 else failures + 1
        delay = min(600 * 2 ** (failures - 1), 21600)
        state = {'failures': failures, 'next_attempt': time.time() + delay,
                 'last_exit_code': result.returncode}
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(state_path)
        log(f'Search exited {result.returncode} without completion; failure {failures}/{MAX_FAILURES}. '
            + ('Automatic retries stopped; inspect run.log.' if failures >= MAX_FAILURES
               else f'Retry eligible in {delay // 60} minutes.'))


if __name__ == '__main__':
    main()
