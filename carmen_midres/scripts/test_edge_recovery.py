#!/usr/bin/env python3
"""Small paired zero-drift injection test on real mid-resolution noise."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('/datag/pipeline/AGBT18A_999_103/collate/spliced_blc0001020304050607_guppi_58306_31766_DDO210_0002.gpuspec.0002.h5'))
    p.add_argument('--output',type=Path,default=Path('/datax/scratch/wlll2x/carmen_midres/edge_recovery_test'))
    p.add_argument('--gpu',default='1')
    a=p.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES']=a.gpu
    os.environ.setdefault('MPLCONFIGDIR','/tmp/choza-matplotlib')
    import h5py,hdf5plugin
    import numpy as np
    import setigen as stg
    from astropy import units as u
    from scipy.ndimage import median_filter
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run=a.output/time.strftime('%Y%m%dT%H%M%S');run.mkdir(parents=True)
    with h5py.File(a.source) as f:
        d=f['data'];width=1024;center=d.shape[-1]//width//2
        lo=(center-1)*width;hi=(center+2)*width;pad=50
        data=d[:,0,lo-pad:hi+pad].astype('float64')
        attrs=dict(d.attrs);rootattrs=dict(f.attrs)
    foff=float(attrs['foff']);df=abs(foff)*1e6
    fch1=float(attrs['fch1'])+lo*foff; nt=data.shape[0]
    positions={'center_away_from_DC':1024+768,'boundary':1024,'shoulder':1024+40}
    rows=[]
    def write_h5(path,array):
        with h5py.File(path,'w') as f:
            for k,v in rootattrs.items():f.attrs[k]=v
            f.attrs['nfpc']=1024
            d=f.create_dataset('data',data=array[:,None,:].astype('float32'))
            for k,v in attrs.items():d.attrs[k]=v
            d.attrs['fch1']=fch1;d.attrs['nchans']=hi-lo;d.attrs['nfpc']=1024
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
    for treatment in ['raw','median101']:
        array=raw if treatment=='raw' else (data/median_filter(data,size=(1,101),mode='reflect'))[:,pad:-pad]
        controls[treatment]=search(array,'control_'+treatment)
    for location,index in positions.items():
        # Temporal MAD of the target bin controls local brightness scaling.
        values=raw[:,index];sigma=1.4826*np.median(np.abs(values-np.median(values)))
        if sigma<=0:raise ValueError('Nonpositive local noise')
        frequency=fch1+index*foff
        for requested in [5,10,20,40]:
            frame=stg.Frame(shape=data.shape,df=df*u.Hz,dt=float(attrs['tsamp'])*u.s,
                            fch1=(fch1+(hi-lo-1+pad)*foff)*u.MHz,ascending=True)
            signal=frame.add_constant_signal(f_start=frequency*u.MHz,drift_rate=0*u.Hz/u.s,
                     level=requested*sigma/np.sqrt(nt),width=df*u.Hz,f_profile_type='gaussian')
            if foff<0:signal=signal[:,::-1]
            peak=int(np.argmax(signal[0]))
            if peak!=index+pad:raise ValueError(f'Frequency-axis mismatch: {peak} != {index+pad}')
            injected=data+signal
            measured=np.mean(signal[:,index+pad])/sigma*np.sqrt(nt)
            for treatment in ['raw','median101']:
                array=injected[:,pad:-pad] if treatment=='raw' else (injected/median_filter(injected,size=(1,101),mode='reflect'))[:,pad:-pad]
                hits=search(array,f'{location}_snr{requested}_{treatment}')
                def matched(hits):return [h for h in hits if abs(h['frequency']-frequency)<=abs(foff)*.51 and abs(h['drift'])<1e-6]
                recovered=matched(hits);background=matched(controls[treatment])
                rows.append(dict(location=location,input_track_snr=float(measured),requested_track_snr=requested,
                   treatment=treatment,frequency_mhz=frequency,local_temporal_sigma=float(sigma),
                   recovered=bool(recovered),control_hit=bool(background),
                   reported_snr=max((h['snr'] for h in recovered),default=None)))
                with (run/'recovery.csv').open('w') as f:
                    writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for ax,treatment in zip(axes,['raw','median101']):
        grid=np.zeros((3,4))
        for i,location in enumerate(positions):
            for j,strength in enumerate([5,10,20,40]):
                row=next(r for r in rows if r['location']==location and r['treatment']==treatment and r['requested_track_snr']==strength)
                grid[i,j]=int(row['recovered'])
                ax.text(j,i,f"SNR {row['reported_snr']:.2f}" if row['recovered'] else 'Not recovered',ha='center',va='center',fontsize=9)
        ax.imshow(grid,cmap='Pastel1_r',vmin=0,vmax=1,aspect='auto')
        ax.set_xticks(range(4),[5,10,20,40]);ax.set_yticks(range(3),list(positions))
        ax.set_title(treatment);ax.set_xlabel('Injected local temporal track SNR')
    fig.suptitle('One real-noise scan, zero drift, SETIcore threshold 5; no pre-existing matches')
    fig.savefig(run/'recovery.png',dpi=160);plt.close(fig)
    metadata=dict(source=str(a.source),gpu=a.gpu,original_shape=list(data.shape),time_samples=nt,
        sigma_method='Target-bin temporal MAD × 1.4826; amplitude = requested track SNR × sigma / sqrt(Ntime)',
        note='Local track SNR is not calibrated to SETIcore SNR. One real-noise example, not a recovery probability or cadence-event test. Instrument-response attenuation before detection is not simulated.',
        preprocessing='101-channel division with 50-bin context; identical added signal compared before/after normalization')
    (run/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Results:',run)
    for r in rows:print(r)


if __name__=='__main__':main()
