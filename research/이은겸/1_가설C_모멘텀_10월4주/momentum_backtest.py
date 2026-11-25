import sys; from momentum_engine import *; import itertools
from concurrent.futures import ProcessPoolExecutor
def one(a):
    N,L,K=a; spec=dict(kind='mom_skip',N=N,L=L,K=K)
    m=monthly(run(spec,20)); d=summ(m); d.update(N=N,L=L,K=K,worst=m.ex.min()*100,best=m.ex.max()*100,med=m.ex.median()*100)
    return d,m
if __name__=='__main__':
    args=list(itertools.product([30,50],[100,120,150],[3,5,7]))
    with ProcessPoolExecutor(8) as ex: out=list(ex.map(one,args))
    R=pd.DataFrame([o[0] for o in out]).round(2); pd.set_option('display.width',250)
    print(R[['N','L','K','ex_all','med','win','ex_tr','ex_te','win_te','t','worst','best','cum','cum_bm']].to_string())
    m=out[args.index((30,120,5))][1]; m.to_pickle('data/best_monthly.pkl')
    print((m*100).round(2).to_string())
    # 현재(10/27 종가 기준) 선정 종목
    i=len(dates)-1; u=univ(i,30); s=score('mom_skip',i,u,120).nlargest(5)
    print(pd.DataFrame({'name':U.loc[s.index,'Name'],'mom%':(s*100).round(1)}))
