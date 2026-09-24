# Forecast model selection backtest (APS-02). Rolling origins, as-of features, no leakage.
# Usage: python docs/research/forecast_backtest.py DynamicPricing/data/APS-02.db
# Needs pandas, numpy, scikit-learn, scipy. Results are recorded in docs/ARCHITECTURE.md section 7.
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
# region-level rate for empirical-Bayes shrinkage
def add_region(df):
    reg=df.groupby(['T','region']).rate56.transform('mean'); df['rreg']=reg; return df
train=add_region(train); test=add_region(test)
def pdev(y,m):
    m=np.clip(m,1e-6,None); return 2*np.mean(np.where(y>0,y*np.log(y/m),0)-(y-m))
res={}
test['naive']=test.rate56
test['pickup']=test.otb_b+0.5*(test.rate56+test.rate180)*test.pick
for k in [28,56,112]:
    shr=(test.rate56*56+test.rate180*180+k*test.rreg)/(56+180+k)
    test[f'pickup_eb{k}']=test.otb_b+shr*test.pick
# OTB multiplicative uplift learned per lead bucket (pooled): y ~ a(h)*otb + b(h)*rate
tr=train.copy(); tr['hb']=pd.cut(tr.h,[0,3,7,14,30,60]); test['hb']=pd.cut(test.h,[0,3,7,14,30,60])
from sklearn.linear_model import PoissonRegressor
test['pickup_fit']=0.0
for hb,g in tr.groupby('hb'):
    X=np.c_[g.otb_b,(g.rate56+g.rate180)/2]; m=PoissonRegressor(alpha=1e-4,max_iter=500).fit(np.log1p(X),g.y)
    idx=test.hb==hb; Xt=np.c_[test.loc[idx,'otb_b'],(test.loc[idx,'rate56']+test.loc[idx,'rate180'])/2]
    test.loc[idx,'pickup_fit']=m.predict(np.log1p(Xt))
feats=['h','otb_b','otb_c','otb_s','otb_v','otb_a','rate56','rate180','rreg','nat','month','peak','pick']
g=HistGradientBoostingRegressor(loss='poisson',max_iter=300,learning_rate=0.05,max_leaf_nodes=15,min_samples_leaf=200,l2_regularization=1.0,random_state=0)
g.fit(train[feats],train.y); test['gbm']=g.predict(test[feats])
test['blend']=0.5*test.pickup_eb56+0.5*test.gbm
test['blend73']=0.7*test.pickup_eb56+0.3*test.gbm
M=['naive','pickup','pickup_eb28','pickup_eb56','pickup_eb112','pickup_fit','gbm','blend','blend73']
print("city x stay-date:")
for k in M: print(f"  {k:13s} MAE {np.mean(abs(test.y-test[k])):.4f}  PoisDev {pdev(test.y,test[k]):.4f}")
# smoothed 7-day centred signal (what the price factor should consume)
print("city x 7-day window (rolling sum), WAPE:")
test=test.sort_values(['T','city_id','fd'])
for k in ['y']+M: test[k+'_r7']=test.groupby(['T','city_id'])[k].transform(lambda s:s.rolling(7,center=True,min_periods=4).sum())
for k in M: print(f"  {k:13s} {np.sum(abs(test.y_r7-test[k+'_r7']))/np.sum(test.y_r7):.3f}")
# split-conformal intervals on the 7-day signal: calibrate on T=06-01, test on 06-15,07-01
best='pickup_eb56'
cal=test[test['T']=='2026-06-01'].dropna(subset=['y_r7']); ev=test[test['T']!='2026-06-01'].dropna(subset=['y_r7'])
r=(cal.y_r7-cal[best+'_r7'])/np.sqrt(cal[best+'_r7']+0.25)
lo_q,hi_q=np.quantile(r,.1),np.quantile(r,.9)
s=np.sqrt(ev[best+'_r7']+0.25)
lo=np.maximum(0,ev[best+'_r7']+lo_q*s); hi=ev[best+'_r7']+hi_q*s
print("conformal P10-P90 coverage on held-out origins: %.3f (target 0.80)"%np.mean((ev.y_r7>=lo)&(ev.y_r7<=hi)))
lo2=stats.poisson.ppf(.1,ev[best+'_r7']); hi2=stats.poisson.ppf(.9,ev[best+'_r7'])
print("plain Poisson P10-P90 coverage: %.3f"%np.mean((ev.y_r7>=lo2)&(ev.y_r7<=hi2)))
# net demand: cancellations as a share of bookings, by lead bucket
B2=B.copy(); Cx=e[e.event_type=='cancellation']
print("cancellations / bookings overall %.2f"%(len(Cx)/len(B2)))
