#!/usr/bin/env python3
"""Sample NVIDIA per-process GPU memory while running one diagnostic command."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu',default='0')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args()
    command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command:p.error('Provide a command after --')
    a.output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=a.gpu)
    samples=[];start=time.monotonic()
    with (a.output/'command.log').open('w') as log:
        child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        while child.poll() is None:
            result=subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory',
                                   '--format=csv,noheader,nounits'],capture_output=True,text=True)
            for row in csv.reader(result.stdout.splitlines()):
                if len(row)==2 and row[0].strip()==str(child.pid):
                    try:samples.append(dict(seconds=time.monotonic()-start,used_mib=float(row[1])))
                    except ValueError:pass
            time.sleep(.05)
        code=child.wait()
    report=dict(command=command,gpu=a.gpu,pid=child.pid,exit_code=code,
                wall_seconds=time.monotonic()-start,samples=len(samples),
                sampled_peak_mib=max((x['used_mib'] for x in samples),default=None),
                limitation='Sampled NVIDIA per-process allocation; brief peaks may be missed. Not total system RAM.',
                readings=samples)
    (a.output/'memory.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='readings'},indent=2))
    raise SystemExit(code)


if __name__=='__main__':main()
