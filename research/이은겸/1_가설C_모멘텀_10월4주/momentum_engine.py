import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
W='data'  # momentum_fetch.py data 로 수집한 폴더
P=pd.read_pickle(W+'/prices.pkl'); U=pd.read_pickle(W+'/universe.pkl').set_index('Code')
C=P['Close']; O=P['Open'].replace(0,np.nan).fillna(C); H=P['High'].replace(0,np.nan).fillna(C); V=P['Volume']
bm='069500'; stocks=[c for c in C.columns if c!=bm]
cap=C[stocks]*U.loc[stocks,'Stocks']; tv=(C*V)[stocks].rolling(20).mean()
ret=C.pct_change(fill_method=None); dates=C.index
BUY,SELL=0.00015,0.00215
START=dates.get_loc(dates[dates>='2024-01-01'][0])
def univ(i,N):
    t=dates[i]; u=cap.loc[t].dropna().nlargest(N).index
    return [c for c in u if tv.loc[t,c]>5e9]
def score(kind,i,u,L):
    if kind=='mom': return C.iloc[i][u]/C.iloc[i-L][u]-1
    if kind=='mom_skip': return C.iloc[i-5][u]/C.iloc[i-L][u]-1
    if kind=='rev': return -(C.iloc[i][u]/C.iloc[i-L][u]-1)
    if kind=='beta':
        r=ret.iloc[i-L+1:i+1]; b=r[bm]; return r[u].apply(lambda x:x.cov(b))/b.var()
    if kind=='high52': return C.iloc[i][u]/H.iloc[max(0,i-250):i+1][u].max()
    if kind=='cap': return cap.iloc[i][u]
    raise ValueError(kind)
def weights(spec,i):
    """spec: dict(kind,N,L,K, core=비중(0~1, 시총가중 상위 N 코어), regime=None|'ma')"""
    u=univ(i,spec['N']); w=pd.Series(0.0,index=stocks)
    core=spec.get('core',0)
    if core>0:
        cw=cap.iloc[i][u]; w[u]+=core*cw/cw.sum()
    kind=spec['kind']
    if spec.get('regime')=='ma':   # 지수가 60일 이평 위면 원래 신호, 아래면 저베타/시총가중
        b=C[bm].iloc[i-59:i+1].mean()
        if C[bm].iloc[i]<b: kind='cap'
    s=score(kind,i,u,spec['L']).dropna().nlargest(spec['K']).index
    w[s]+=(1-core)/len(s)
    return w
def run(spec,H=20,end=None):
    """H거래일마다 리밸런싱. 결정은 i일 종가, 체결은 i+1일 시가."""
    w=pd.Series(0.0,index=stocks); out=[]; i=START-1
    reb=set(range(START-1,len(dates)-1,H))
    for j in range(START,len(dates)):
        if j-1 in reb:
            nw=weights(spec,j-1)
            # j일 시가까지는 기존 보유, 시가에 교체
            g1=(w*(O.iloc[j]/C.iloc[j-1]-1).fillna(0)).sum()
            wv=w*(O.iloc[j]/C.iloc[j-1]).fillna(1); wv=wv/wv.sum()*(1+0) if wv.sum()>0 else wv
            dw=nw-wv; cost=(dw.clip(lower=0)*BUY).sum()+((-dw).clip(lower=0)*SELL).sum()
            g2=(nw*(C.iloc[j]/O.iloc[j]-1).fillna(0)).sum()
            r=(1+g1)*(1+g2)*(1-cost)-1 if w.sum()>0 else (1+g2)*(1-cost)-1
            w=nw*(C.iloc[j]/O.iloc[j]).fillna(1); w=w/w.sum()
        else:
            g=(w*ret.iloc[j].fillna(0)).sum(); r=g
            w=w*(1+ret.iloc[j].fillna(0)); w=w/w.sum()
        out.append(r)
    pr=pd.Series(out,index=dates[START:])
    return pr
def monthly(pr):
    br=ret[bm].loc[pr.index]
    m=pd.DataFrame({'s':(1+pr).groupby(pr.index.to_period('M')).prod()-1,
                    'b':(1+br).groupby(br.index.to_period('M')).prod()-1})
    m['ex']=m.s-m.b; return m
def summ(m):
    tr=m.ex[:'2025-06']; te=m.ex['2025-07':]
    return dict(ex_all=m.ex.mean()*100,win=(m.ex>0).mean()*100,ex_tr=tr.mean()*100,win_tr=(tr>0).mean()*100,
                ex_te=te.mean()*100,win_te=(te>0).mean()*100,t=m.ex.mean()/m.ex.std()*np.sqrt(len(m)),
                cum=((1+m.s).prod()-1)*100,cum_bm=((1+m.b).prod()-1)*100)
