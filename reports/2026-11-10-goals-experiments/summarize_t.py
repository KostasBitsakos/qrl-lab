"""Read only approved T validation outputs; no trainers and no test files."""
from pathlib import Path
import sys,json,hashlib,statistics as st
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from summarize_runs import collect
rows=collect('R-20261110-001')
assert len(rows)==40
out={'request':'R-20261110-001','attempts':len(rows),'groups':{},'sources':[]}
groups={}
for run,name,status,_,_ in rows:
 d=ROOT/'.lab/runs'/run
 se=json.loads((d/'spec_entry.json').read_text()); lj=json.loads((d/'launcher.json').read_text()); e=se['entry_spec']
 assert status=='done' and lj['exit_code']==0 and se['attempt']==1
 cmd=e['cmd']; assert cmd[cmd.index('--eval-split')+1]=='val'
 p=Path(se['cwd'])/cmd[cmd.index('--out')+1]; x=json.loads(p.read_text())
 assert x['eval_splits']==['val'] and x['total_ticks']==19968
 ck=str(x['checkpoints'][0]);assert len(x['checkpoints'])==1
 eps=x['checkpoint_results'][ck]['val']['episodes'];w=e['workload']; a=e['arm'];seed=e['seed']
 expected=list(range(13500,13510)) if w.endswith('shift') else list(range(16000,16020))
 assert x['eval_seeds']['val']==expected and len(eps)==len(expected) and x['seed']==seed
 assert all(ep['ticks']==5000 for ep in eps)
 groups.setdefault(w,{}).setdefault(a,[]).append((seed,x,eps))
 out['sources'].append({'run':run,'output':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
def iqm(v):
 s=np.sort(v,axis=-1);n=s.shape[-1];i=np.arange(n); weights=np.maximum(0,np.minimum(i+1,.75*n)-np.maximum(i,.25*n));return np.sum(s*weights,axis=-1)/weights.sum()
rng=np.random.default_rng(445)
for w, arms in sorted(groups.items()):
 g={};mat={}
 for a,lst in arms.items():
  lst.sort();assert [z[0] for z in lst]==list(range(19200,19210))
  mat[a]=np.array([[e['ret'] for e in es] for _,_,es in lst]); means=mat[a].mean(1)
  g[a]={'n':len(lst),'mean':float(means.mean()),'sd':float(means.std(ddof=1)),'iqm':float(iqm(means)),'per_seed':dict(zip([str(z[0]) for z in lst],means.tolist()))}
  for k in ['slo_viol_rate','p95_latency','mean_pods','pods_changes','drops','served']:
   g[a][k]=st.mean(e[k] for _,_,es in lst for e in es)
  for k in ['pretrain_cpu_s','target_train_cpu_s','eval_cpu_s','cpu_s','wall_s']:
   g[a][k+'_sum']=sum(x[k] for _,x,_ in lst)
  g[a]['pod_ticks']=g[a]['mean_pods']*5000
 n,m=mat['dinos'].shape;si=rng.integers(n,size=(10000,n));ti=rng.integers(m,size=(10000,m));bs={}
 for a in ['dinos','v2']:
  z=mat[a][si[:,:,None],ti[:,None,:]].mean(-1);bs[a]=z
  g[a]['mean_ci95']=np.percentile(z.mean(1),[2.5,97.5]).tolist();g[a]['iqm_ci95']=np.percentile(iqm(z),[2.5,97.5]).tolist()
 dif=mat['v2'].mean(1)-mat['dinos'].mean(1)
 def pi(v,d): return ((v[:,None,:]>d[None,:,:]).mean()+.5*(v[:,None,:]==d[None,:,:]).mean())
 pib=[]
 for i in range(10000):
  v=mat['v2'][si[i]][:,ti[i]];d=mat['dinos'][si[i]][:,ti[i]];pib.append(pi(v,d))
 g['v2_minus_dinos']={'mean':float(dif.mean()),'sd_paired':float(dif.std(ddof=1)),'mean_ci95':np.percentile(bs['v2'].mean(1)-bs['dinos'].mean(1),[2.5,97.5]).tolist(),'iqm':float(iqm(mat['v2'].mean(1))-iqm(mat['dinos'].mean(1))),'iqm_ci95':np.percentile(iqm(bs['v2'])-iqm(bs['dinos']),[2.5,97.5]).tolist(),'p_improvement':float(pi(mat['v2'],mat['dinos'])),'p_improvement_ci95':np.percentile(pib,[2.5,97.5]).tolist()}
 out['groups'][w]=g
out['method']='10000 paired crossed resamples, RNG445, percentile95%; fractional IQM over seed means; exploratory validation only'
(ROOT/'.lab/j450/T-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
for w,g in out['groups'].items():
 print(w)
 for a in ['dinos','v2']:print(a,{k:g[a][k] for k in ['mean','sd','slo_viol_rate','mean_pods']})
 print(g['v2_minus_dinos'])
