# 11/9 대회 기간(15거래일) 맞춤 대안 비교 시뮬레이션
# 데이터: ../1_가설C_모멘텀_10월4주/momentum_fetch.py 로 받은 data/prices.pkl, data/universe.pkl (끝 날짜를 2026-11-09로)
# 실행: python contest15_sim.py → data/sim.pkl 생성, 결과 표는 contest15_report.py
# 2024-01 이후 3거래일 간격 시작, i일 종가로 종목 선정 → i+1일 시가 진입 → 15거래일 뒤 종가 청산
import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
P=pd.read_pickle('data/prices.pkl'); U=pd.read_pickle('data/universe.pkl').set_index('Code')
C=P['Close'].ffill(limit=3); O=P['Open'].replace(0,np.nan).fillna(C); V=P['Volume']
bm='069500'; st=[c for c in C.columns if c!=bm]
cap=C[st]*U.loc[st,'Stocks']; tv=(C*V)[st].rolling(20).mean(); ret=C.pct_change(fill_method=None); D=C.index
HOLD=15; BUY,SELL=.00015,.00215

def picks(i):
    t=D[i]
    u=[c for c in cap.loc[t].dropna().nlargest(30).index if tv.loc[t,c]>5e9]
    mom=(C.iloc[i-5][u]/C.iloc[i-120][u]-1).dropna()
    vol=ret.iloc[i-59:i+1][u].std()
    r={}
    r['현재: 모멘텀5']=list(mom.nlargest(5).index)
    r['모멘텀10']=list(mom.nlargest(10).index)
    r['모멘텀15']=list(mom.nlargest(15).index)
    r['저변동5']=list(vol.nsmallest(5).index)
    r['저변동10']=list(vol.nsmallest(10).index)
    top=mom.nlargest(10).index; r['모멘텀10중 저변동5']=list(vol[top].nsmallest(5).index)
    va=(mom/vol.reindex(mom.index)).dropna(); r['변동성조정 모멘텀5']=list(va.nlargest(5).index); r['변동성조정 모멘텀10']=list(va.nlargest(10).index)
    rv=(C.iloc[i][u]/C.iloc[i-20][u]-1).dropna(); r['20일 낙폭과대5']=list(rv.nsmallest(5).index)
    r['시총상위10']=list(cap.loc[t,u].nlargest(10).index)
    return r

def path(codes,i):
    """i+1 시가 진입 후 i+HOLD 종가까지 동일비중 매수후보유 누적 경로"""
    ent=O.iloc[i+1][codes]; px=C.iloc[i+1:i+HOLD+1][codes].ffill()
    return (px/ent).mean(axis=1).values

rows=[]
s0=D.get_indexer([pd.Timestamp('2024-01-02')],method='bfill')[0]
for i in range(s0,len(D)-HOLD,3):
    b=C[bm]; bpath=C[bm].iloc[i+1:i+HOLD+1].values/O[bm].iloc[i+1]
    ma20,ma60=b.iloc[i-19:i+1].mean(),b.iloc[i-59:i+1].mean()
    vol20=ret[bm].iloc[i-19:i+1].std()*np.sqrt(252); r20=b.iloc[i]/b.iloc[i-20]-1
    base=dict(date=D[i],bm=bpath[-1]-1,ma20=b.iloc[i]<ma20,ma60=b.iloc[i]<ma60,vol20=vol20,r20=r20)
    for name,codes in picks(i).items():
        p=path(codes,i); gross=p[-1]*(1-SELL)*(1-BUY)-1
        for ov,f in {'100%':1.0,'80%':.8,'50%':.5,'30%':.3}.items():
            rows.append({**base,'s':name,'ov':ov,'ret':f*gross})
        # 오버레이 (주식 80% 기준)
        rows.append({**base,'s':name,'ov':'MA20 아래면 현금','ret':0.0 if base['ma20'] else .8*gross})
        rows.append({**base,'s':name,'ov':'MA60 아래면 현금','ret':0.0 if base['ma60'] else .8*gross})
        rows.append({**base,'s':name,'ov':'변동성타깃20%','ret':min(.8,.20/vol20)*gross})
        for stop in (-.05,-.08):  # 계좌 손절: 종가가 기준 아래면 다음 날 시가 청산
            hit=np.where(p-1<=stop)[0]
            val=np.nanmean((O.iloc[i+2+hit[0]][codes]/O.iloc[i+1][codes]).values) if len(hit) and hit[0]<HOLD-1 else p[-1]
            rows.append({**base,'s':name,'ov':f'계좌손절{int(stop*100)}%','ret':.8*(val*(1-SELL)*(1-BUY)-1)})
pd.DataFrame(rows).to_pickle('data/sim.pkl')
print('saved', len(rows))
