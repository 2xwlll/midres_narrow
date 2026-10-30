#!/usr/bin/env python3
"""Paired edge recovery benchmark; install the local midres-search package first."""
import argparse
import csv
import json
import hashlib
import os
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gpu',default='1')
    p.add_argument('--coarse-index',type=int,help='Central coarse-block index; use multiple blocks in separate runs')
    p.add_argument('--coarse-width',type=int,default=1024,help='Verify against instrument metadata')
    p.add_argument('--strengths',type=float,nargs='+',default=[5,10,20,40])
    p.add_argument('--offsets',type=int,nargs='+',default=[-40,-8,-1,0,1,8,40,768])
    a=p.parse_args()
    if a.coarse_width<102 or any(s<=0 for s in a.strengths):p.error('Invalid coarse width or strengths')
    from midres_search.normalization import METHODS, normalize
    os.environ['CUDA_VISIBLE_DEVICES']=a.gpu
    os.environ.setdefault('MPLCONFIGDIR','/tmp/choza-matplotlib')
    import h5py,hdf5plugin
    import numpy as np
    import setigen as stg
    from astropy import units as u
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run=a.output/time.strftime('%Y%m%dT%H%M%S');run.mkdir(parents=True,exist_ok=False)
    with h5py.File(a.source) as f:
        d=f['data'];width=a.coarse_width;center=a.coarse_index if a.coarse_index is not None else d.shape[-1]//width//2
        lo=(center-1)*width;hi=(center+2)*width;pad=50
        if lo<pad or hi+pad>d.shape[-1]:p.error('Choose an interior coarse block')
        if d.ndim!=3 or d.shape[1]!=1:p.error('Expected time x 1 x frequency input')
        data=d[:,0,lo-pad:hi+pad].astype('float64')
        attrs=dict(d.attrs);rootattrs=dict(f.attrs)
    foff=float(attrs['foff']);df=abs(foff)*1e6
    fch1=float(attrs['fch1'])+lo*foff; nt=data.shape[0]
    positions={f'offset_{offset:+d}':width+offset for offset in a.offsets}
    if any(not 0<=i<hi-lo for i in positions.values()):p.error('Offset outside crop')
    # Persist provenance before running the first detector, including failed runs.
    metadata=dict(source=str(a.source.resolve()),gpu=a.gpu,coarse_index=center,
        assumed_coarse_width=width,offsets=a.offsets,strengths=a.strengths,methods=METHODS,
        original_shape=list(data.shape),time_samples=nt,
        crop_sha256=hashlib.sha256(data.tobytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sigma_method='Target-bin temporal MAD x 1.4826; amplitude = requested track SNR x sigma / sqrt(Ntime)',
        note='Local track SNR is not calibrated to SETIcore SNR. One real-noise example, not a recovery probability or cadence-event test. Instrument-response attenuation before detection is not simulated.',
        preprocessing='101-bin median across or within coarse blocks; 50 context bins; identical added signal in all treatments',
        completed=False)
    (run/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    rows=[]
    def write_h5(path,array):
        with h5py.File(path,'w') as f:
            for k,v in rootattrs.items():f.attrs[k]=v
            f.attrs['nfpc']=width
            d=f.create_dataset('data',data=array[:,None,:].astype('float32'))
            for k,v in attrs.items():d.attrs[k]=v
            d.attrs['fch1']=fch1;d.attrs['nchans']=hi-lo;d.attrs['nfpc']=width
    def search(array,tag):
        path=run/(tag+'.h5');write_h5(path,array)
        dat=run/(tag+'.dat')
        with (run/(tag+'.log')).open('w') as log:
            subprocess.run(['seticore',str(path),'--output',str(dat),'--max_drift','10','--snr','5'],stdout=log,stderr=subprocess.STDOUT,check=True)
        hits=[]
        for line in dat.read_text().splitlines():
            parts=line.split()
            try:
                int(parts[0]);hits.append(dict(drift=float(parts[1]),snr=float(parts[2]),frequency=float(parts[3])))
            except (ValueError,IndexError):continue
        path.unlink()
        return hits
    raw=data[:,pad:-pad]
    controls={}
    def preprocess(array,treatment):
        return normalize(array,treatment,coarse_width=width,first_channel=lo-pad)[:,pad:-pad]
    for treatment in METHODS:
        array=preprocess(data,treatment)
        controls[treatment]=search(array,'control_'+treatment)
    for location,index in positions.items():
        # Temporal MAD of the target bin controls local brightness scaling.
        values=raw[:,index];sigma=1.4826*np.median(np.abs(values-np.median(values)))
        if not np.isfinite(sigma) or sigma<=0:raise ValueError('Invalid local noise')
        frequency=fch1+index*foff
        for requested in a.strengths:
            frame=stg.Frame(shape=data.shape,df=df*u.Hz,dt=float(attrs['tsamp'])*u.s,
                            fch1=min(fch1-pad*foff,fch1+(hi-lo-1+pad)*foff)*u.MHz,ascending=True)
            signal=frame.add_constant_signal(f_start=frequency*u.MHz,drift_rate=0*u.Hz/u.s,
                     level=requested*sigma/np.sqrt(nt),width=df*u.Hz,f_profile_type='gaussian')
            if foff<0:signal=signal[:,::-1]
            peak=int(np.argmax(signal[0]))
            if peak!=index+pad:raise ValueError(f'Frequency-axis mismatch: {peak} != {index+pad}')
            injected=data+signal
            measured=np.mean(signal[:,index+pad])/sigma*np.sqrt(nt)
            for treatment in METHODS:
                array=preprocess(injected,treatment)
                hits=search(array,f'{location}_snr{requested}_{treatment}')
                def matched(hits):return [h for h in hits if abs(h['frequency']-frequency)<=abs(foff)*.51 and abs(h['drift'])<1e-6]
                recovered=matched(hits);background=matched(controls[treatment])
                rows.append(dict(location=location,input_track_snr=float(measured),requested_track_snr=requested,
                   treatment=treatment,frequency_mhz=frequency,local_temporal_sigma=float(sigma),
                   recovered=bool(recovered),control_hit=bool(background),new_recovery=bool(recovered) and not bool(background),
                   reported_snr=max((h['snr'] for h in recovered),default=None)))
                with (run/'recovery.csv').open('w') as f:
                    writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,len(METHODS),figsize=(18,7),constrained_layout=True)
    for ax,treatment in zip(axes,METHODS):
        grid=np.zeros((len(positions),len(a.strengths)))
        for i,location in enumerate(positions):
            for j,strength in enumerate(a.strengths):
                row=next(r for r in rows if r['location']==location and r['treatment']==treatment and r['requested_track_snr']==strength)
                grid[i,j]=int(row['new_recovery'])
                ax.text(j,i,f"SNR {row['reported_snr']:.2f}" if row['recovered'] else 'Not recovered',ha='center',va='center',fontsize=9)
        ax.imshow(grid,cmap='Pastel1_r',vmin=0,vmax=1,aspect='auto')
        ax.set_xticks(range(len(a.strengths)),a.strengths);ax.set_yticks(range(len(positions)),list(positions))
        ax.set_title(treatment);ax.set_xlabel('Injected local temporal track SNR')
    fig.suptitle('One real-noise scan, zero drift, SETIcore threshold 5; check control_hit in CSV')
    fig.savefig(run/'recovery.png',dpi=160);plt.close(fig)
    metadata['completed']=True
    (run/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Results:',run)
    for r in rows:print(r)


if __name__=='__main__':main()
