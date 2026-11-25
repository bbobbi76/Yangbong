import FinanceDataReader as fdr, pandas as pd, sys, time
from concurrent.futures import ThreadPoolExecutor
out=sys.argv[1]
lst=fdr.StockListing('KOSPI')
lst=lst[lst.Code.str.endswith('0') & ~lst.Name.str.contains(r'우$|우B$|우C$|스팩|리츠$|인프라')]  # 11/9 수정: '리츠'만 쓰면 메리츠금융지주까지 빠짐
lst=lst.sort_values('Marcap',ascending=False).head(300)
lst[['Code','Name','Marcap','Stocks']].to_pickle(out+'/universe.pkl')
def get(c):
    for i in range(3):
        try: return c, fdr.DataReader(c,'2023-06-01','2026-10-27')
        except Exception as e: time.sleep(1)
    return c, None
with ThreadPoolExecutor(8) as ex: res=dict(ex.map(get, list(lst.Code)+['069500']))
fields={}
for f in ['Open','High','Low','Close','Volume']:
    fields[f]=pd.DataFrame({c:d[f] for c,d in res.items() if d is not None and len(d)})
pd.to_pickle(fields,out+'/prices.pkl')
print('fetched',sum(d is not None for d in res.values()), fields['Close'].shape)
