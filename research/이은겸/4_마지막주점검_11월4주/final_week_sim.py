import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
P=pd.read_pickle('data/prices.pkl'); U=pd.read_pickle('data/universe.pkl').set_index('Code')
C=P['Close'].ffill(limit=3); O=P['Open'].replace(0,np.nan).fillna(C); V=P['Volume']
bm='069500'; st=[c for c in C.columns if c!=bm]
cap=C[st]*U.loc[st,'Stocks']; tv=(C*V)[st].rolling(20).mean(); ret=C.pct_change(fill_method=None); D=C.index
H=5; W=.95; COST=(1-.00015)*(1-.00215)
T4,T3,T1,GAP=5.94,10.15,13.42,6.84
def picks(i):
    t=D[i]; u=[c for c in cap.loc[t].dropna().nlargest(30).index if tv.loc[t,c]>5e9]
    r60=ret.iloc[i-59:i+1]; vol=r60[u].std(); b=r60[bm]; beta=r60[u].apply(lambda x:x.cov(b))/b.var()
    mom=(C.iloc[i-5][u]/C.iloc[i-120][u]-1); r5=C.iloc[i][u]/C.iloc[i-5][u]-1
    hv10=vol.nlargest(10).index
    w={}
    for k in (2,3,4,5,6): w[f'고변동성{k}']={c:1/k for c in vol.nlargest(k).index}
    w['베타4']={c:.25 for c in beta.nlargest(4).index}
    w['고변동성10중 5일낙폭4']={c:.25 for c in r5[hv10].nsmallest(4).index}
    w['고변동성10중 5일강세4']={c:.25 for c in r5[hv10].nlargest(4).index}
    w['삼성전자+하이닉스']={'005930':.5,'000660':.5}
    w['6개월모멘텀5']={c:.2 for c in mom.nlargest(5).index}
    cw=cap.loc[t,u].nlargest(10); cw=(cw/cw.sum()).clip(upper=.2); w['지수추종10']=(cw/cw.sum()).to_dict()
    return w
rows=[]
s0=D.get_indexer([pd.Timestamp('2024-01-02')],method='bfill')[0]
for i in range(s0,len(D)-H):
    b=C[bm]; bret=C[bm].iloc[i+H]/O[bm].iloc[i+1]-1
    meta=dict(date=D[i],bm=bret,down=b.iloc[i]<b.iloc[i-59:i+1].mean(),r20=b.iloc[i]/b.iloc[i-20]-1)
    for k,w in picks(i).items():
        r=sum(v*(C[c].iloc[i+H]/O[c].iloc[i+1]) for c,v in w.items())
        rows.append({**meta,'s':k,'ret':W*(r*COST-1)})
    rows.append({**meta,'s':'현금','ret':0.0})
R=pd.DataFrame(rows); R.to_pickle('data/sim5.pkl')
def S(x):
    r=x.ret*100; e=(x.ret-x.bm)*100
    return pd.Series({'n':len(x),'평균':r.mean(),'중앙':r.median(),'4위↑(+5.94)':(r>=T4).mean()*100,'3위↑(+10.15)':(r>=T3).mean()*100,'1위(+13.42)':(r>=T1).mean()*100,'지수아래':(e<=-GAP).mean()*100,'하위10':r.quantile(.1)})
pd.set_option('display.width',250)
order=list(dict.fromkeys(R.s))
for lab,m in [('전체',R.date==R.date),('하락국면(KODEX<60일선)',R.down),('급락 후(20일 -10%↓)',R.r20<-.10),('최근 절반(2025-06~)',R.date>='2025-06-01')]:
    x=R[m]; print(f'\n## {lab}  시작일 {x.date.nunique()}개'); print(x.groupby('s').apply(S).loc[order].round(1).to_string())
i=len(D)-1; b=C[bm]; n=dict(zip(U.index,U.Name))
print('\n현재 KODEX/60일선 %.1f%%, 20일 %.1f%%'%((b.iloc[i]/b.iloc[i-59:i+1].mean()-1)*100,(b.iloc[i]/b.iloc[i-20]-1)*100))
for k,w in picks(i).items():
    if k in('고변동성4','고변동성2','베타4','고변동성10중 5일낙폭4'): print(k,[n.get(c,c) for c in w])
