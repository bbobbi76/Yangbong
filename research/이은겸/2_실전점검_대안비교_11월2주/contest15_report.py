# 11/9 contest15_sim.py 결과 요약: 전략별·오버레이별 15거래일 수익 분포
# 실행: python contest15_report.py (data/sim.pkl 필요)
import pandas as pd
R=pd.read_pickle('data/sim.pkl'); pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
NEED1=5.15  # 11/9 기준 1위(0%)를 따라잡는 데 필요한 수익

def S(x):
    r=x.ret*100; e=(x.ret-x.bm)*100
    return pd.Series(dict(n=len(x),평균=r.mean(),중앙=r.median(),플러스=(r>0).mean()*100,지수승=(e>0).mean()*100,
                          하위10=r.quantile(.1),최악=r.min(),표준=r.std(),**{'+5.15%↑':(r>=NEED1).mean()*100}))

stress=R.ma60&(R.r20<-.05)  # 지금과 비슷한 국면: 지수<60일선 & 20일 수익 -5% 미만
for title,mask in [('전체',R.date==R.date),('앞 구간 (~2025-06)',R.date<'2025-07-01'),
                   ('뒤 구간 (2025-07~)',R.date>='2025-07-01'),('조정장',stress)]:
    x=R[mask&(R.ov=='80%')]
    print(f'\n## {title} — 주식 80%, 시작일 {x.date.nunique()}개')
    print(x.groupby('s',sort=False)[['ret','bm']].apply(S).round(1).to_string())

x=R[R.s=='현재: 모멘텀5']
print('\n## 현재 전략(모멘텀5)에 오버레이'); print(x.groupby('ov',sort=False)[['ret','bm']].apply(S).round(1).to_string())
print('\n## 같은 오버레이, 조정장'); print(x[stress].groupby('ov',sort=False)[['ret','bm']].apply(S).round(1).to_string())

# 제안한 반반 조합: 모멘텀5와 저변동5를 절반씩
a=R[R.ov=='80%'].pivot(index='date',columns='s',values='ret'); meta=R.drop_duplicates('date').set_index('date')
mix=(a['현재: 모멘텀5']+a['저변동5'])/2
for title,m in [('전체',meta.index==meta.index),('조정장',(meta.ma60&(meta.r20<-.05)).values)]:
    r=mix[m]*100
    print(f'\n## 모멘텀5+저변동5 반반 ({title}) 평균 {r.mean():.2f} 중앙 {r.median():.2f} 플러스 {(r>0).mean()*100:.0f}% '
          f'하위10 {r.quantile(.1):.1f} 최악 {r.min():.1f} +5.15%↑ {(r>=NEED1).mean()*100:.0f}%')
