# LightGBM vs pickup backtest (APS-02): point forecasts, quantile intervals, CQR, interval score.
# Usage: python Solution/docs/research/forecast_backtest_lightgbm.py DynamicPricing/data/APS-02.db
# Needs pandas, numpy, scikit-learn, scipy, lightgbm. Results are recorded in docs/ARCHITECTURE.md section 7.3.
import sqlite3, pandas as pd, numpy as np, warnings
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy import stats
warnings.filterwarnings('ignore')
import sys
c=sqlite3.connect(sys.argv[1] if len(sys.argv)>1 else 'DynamicPricing/data/APS-02.db')
e=pd.read_sql("select e.event_type,e.city_id,e.occurred_at,e.for_date,e.lead_time_days,ct.region,ct.peak_months,ct.population from pricing_events e join cities ct using(city_id)",c)
e['occ']=pd.to_datetime(e.occurred_at.str[:10]); e['fd']=pd.to_datetime(e.for_date)
cities=e[['city_id','region','peak_months']].drop_duplicates('city_id').set_index('city_id')
B=e[e.event_type=='booking']
tot=B.groupby(['city_id','fd']).size()
leadcdf=lambda h,Bt: (Bt.lead_time_days< h).mean()
H=60
def frame(T):
    T=pd.Timestamp(T); past=e[e.occ<T]
    Bt=B[(B.occ<T)&(B.fd<T)&(B.fd>=T-pd.Timedelta(days=180))]
    # trailing city rate (stay dates in last 56d, complete)
    win=B[(B.fd<T)&(B.fd>=T-pd.Timedelta(days=56))]
    rate=win.groupby('city_id').size()/56
    rate180=Bt.groupby('city_id').size()/180
    nat=len(win)/56
    otb=past.groupby(['city_id','fd','event_type']).size().unstack(fill_value=0)
    rows=[]
    ds=pd.date_range(T+pd.Timedelta(days=1),T+pd.Timedelta(days=H))
    for cid in cities.index:
        for d in ds:
            h=(d-T).days
            o=otb.loc[(cid,d)] if (cid,d) in otb.index else None
            g=lambda k: (o[k] if (o is not None and k in o) else 0)
            rows.append(dict(T=T,city_id=cid,region=cities.region[cid],fd=d,h=h,
              otb_b=g('booking'),otb_c=g('cancellation'),otb_s=g('search'),otb_v=g('view'),otb_a=g('abandon'),
              rate56=rate.get(cid,0.0),rate180=rate180.get(cid,0.0),nat=nat,
              month=d.month,peak=int(str(d.month) in cities.peak_months[cid].split(',')),
              pick=leadcdf(h,Bt), y=tot.get((cid,d),0)))
    return pd.DataFrame(rows)
train=pd.concat([frame(T) for T in pd.date_range('2025-10-01','2026-04-01',freq='7D')])
train=train[train.fd<'2026-06-01']
test=pd.concat([frame(T) for T in ['2026-06-01','2026-06-15','2026-07-01']])
test=test[test.fd<='2026-08-30']
print(len(train),len(test), "test mean y %.3f"%test.y.mean())
import lightgbm as lgb
def add_region(df):
    df['rreg']=df.groupby(['T','region']).rate56.transform('mean'); return df
train=add_region(train); test=add_region(test)
def base(df): 
    shr=(df.rate56*56+df.rate180*180+56*df.rreg)/(56+180+56)
    return df.otb_b+shr*df.pick
train['pk']=base(train); test['pk']=base(test)
def pdev(y,m):
    m=np.clip(m,1e-6,None); return 2*np.mean(np.where(y>0,y*np.log(y/m),0)-(y-m))
feats=['h','otb_b','otb_c','otb_s','otb_v','otb_a','rate56','rate180','rreg','nat','month','peak','pick']
P=dict(learning_rate=0.03,num_leaves=15,min_data_in_leaf=200,lambda_l2=1.0,feature_fraction=0.8,bagging_fraction=0.8,bagging_freq=1,seed=0,verbose=-1)
# 1) LightGBM Poisson standalone
m1=lgb.train({**P,'objective':'poisson'},lgb.Dataset(train[feats],train.y),num_boost_round=400)
test['lgb_pois']=m1.predict(test[feats])
# 2) LightGBM Tweedie
m2=lgb.train({**P,'objective':'tweedie','tweedie_variance_power':1.2},lgb.Dataset(train[feats],train.y),num_boost_round=400)
test['lgb_tw']=m2.predict(test[feats])
# 3) Hybrid: pickup as offset (init_score=log pk), LightGBM learns multiplicative correction
ds=lgb.Dataset(train[feats],train.y,init_score=np.log(np.clip(train.pk,1e-4,None)))
m3=lgb.train({**P,'objective':'poisson','learning_rate':0.02},ds,num_boost_round=200)
test['hybrid']=np.exp(m3.predict(test[feats],raw_score=True)+np.log(np.clip(test.pk,1e-4,None)))
# 4) sklearn HGB for reference
g=HistGradientBoostingRegressor(loss='poisson',max_iter=300,learning_rate=0.05,max_leaf_nodes=15,min_samples_leaf=200,l2_regularization=1.0,random_state=0)
g.fit(train[feats],train.y); test['hgb']=g.predict(test[feats])
test['naive']=test.rate56
M=['naive','pk','hgb','lgb_pois','lgb_tw','hybrid']
print("city x stay-date:")
for k in M: print(f"  {k:9s} MAE {np.mean(abs(test.y-test[k])):.4f}  PoisDev {pdev(test.y,test[k]):.4f}")
for lvl,grp in [('city x 7d',None),('region x day',['T','region','fd']),('national x day',['T','fd'])]:
    if grp is None:
        t=test.sort_values(['T','city_id','fd']); a={}
        for k in ['y']+M: a[k]=t.groupby(['T','city_id'])[k].transform(lambda s:s.rolling(7,center=True,min_periods=4).sum())
        a=pd.DataFrame(a).dropna()
    else: a=test.groupby(grp)[['y']+M].sum()
    print(lvl+" WAPE: "+"  ".join(f"{k} {np.sum(abs(a.y-a[k]))/np.sum(a.y):.3f}" for k in M))
# quantile LightGBM P10/P90 on the 7-day signal vs conformal on pickup
t=test.sort_values(['T','city_id','fd']).copy(); tr=train.sort_values(['T','city_id','fd']).copy()
for df in (t,tr):
    df['y7']=df.groupby(['T','city_id']).y.transform(lambda s:s.rolling(7,center=True,min_periods=4).sum())
    df['pk7']=df.groupby(['T','city_id']).pk.transform(lambda s:s.rolling(7,center=True,min_periods=4).sum())
    df['otb7']=df.groupby(['T','city_id']).otb_b.transform(lambda s:s.rolling(7,center=True,min_periods=4).sum())
t=t.dropna(subset=['y7']); tr=tr.dropna(subset=['y7'])
f2=feats+['pk7','otb7']
q={}
for a in (0.1,0.9):
    mq=lgb.train({**P,'objective':'quantile','alpha':a},lgb.Dataset(tr[f2],tr.y7),num_boost_round=300); q[a]=mq.predict(t[f2])
ev=t['T']!='2026-06-01'
print("LightGBM quantile P10-P90 coverage: %.3f   mean width %.2f"%(np.mean((t.y7[ev]>=q[.1][ev])&(t.y7[ev]<=q[.9][ev])), np.mean(q[.9][ev]-q[.1][ev])))
cal=t[~ev]; e2=t[ev]
r=(cal.y7-cal.pk7)/np.sqrt(cal.pk7+0.25); lo_q,hi_q=np.quantile(r,.1),np.quantile(r,.9); s=np.sqrt(e2.pk7+0.25)
lo=np.maximum(0,e2.pk7+lo_q*s); hi=e2.pk7+hi_q*s
print("Conformal-on-pickup P10-P90 coverage: %.3f   mean width %.2f"%(np.mean((e2.y7>=lo)&(e2.y7<=hi)), np.mean(hi-lo)))
imp=sorted(zip(feats,m3.feature_importance('gain')),key=lambda x:-x[1])[:5]; print("hybrid top gain:",[(a,int(b)) for a,b in imp])
# CQR: conformalize the LightGBM quantiles on the calibration origin
c10,c90=q[.1][~ev],q[.9][~ev]; yc=t.y7[~ev].values
E=np.maximum(c10-yc, yc-c90); n=len(E); Q=np.quantile(E, min(1,(np.ceil((n+1)*0.8))/n))
lo=np.maximum(0,q[.1][ev]-Q); hi=q[.9][ev]+Q
print("CQR (LightGBM quantile + conformal) coverage: %.3f   mean width %.2f  (Q=%.3f)"%(np.mean((t.y7[ev]>=lo)&(t.y7[ev]<=hi)), np.mean(hi-lo), Q))
# interval score (lower=better): width + 2/alpha * misses, alpha=0.2
def iscore(y,l,h,a=0.2): return np.mean((h-l)+2/a*(l-y)*(y<l)+2/a*(y-h)*(y>h))
y=t.y7[ev].values
print("interval score  LGB-quantile %.3f | CQR %.3f | conformal-pickup %.3f"%(
  iscore(y,q[.1][ev],q[.9][ev]), iscore(y,lo,hi),
  iscore(y,np.maximum(0,e2.pk7+lo_q*np.sqrt(e2.pk7+0.25)).values,(e2.pk7+hi_q*np.sqrt(e2.pk7+0.25)).values)))
