import FinanceDataReader as fdr, pandas as pd, time
from concurrent.futures import ThreadPoolExecutor
lst=fdr.StockListing('KOSPI'); lst=lst[lst.Code.str.endswith('0')].copy()
for c in ['Marcap','Stocks']: lst[c]=pd.to_numeric(lst[c],errors='coerce')
lst=lst.dropna(subset=['Marcap']).sort_values('Marcap',ascending=False)
lst=lst[~lst.Name.str.contains(r'리츠$|인프라|스팩')].head(80)
lst[['Code','Name','Marcap','Stocks']].to_pickle('data/universe.pkl')
def get(c):
    for i in range(3):
        try: return c, fdr.DataReader(c,'2023-06-01','2026-11-23')
        except Exception: time.sleep(1)
    return c,None
with ThreadPoolExecutor(8) as ex: res=dict(ex.map(get,list(lst.Code)+['069500']))
F={f:pd.DataFrame({c:d[f] for c,d in res.items() if d is not None and len(d)}) for f in ['Open','High','Low','Close','Volume']}
pd.to_pickle(F,'data/prices.pkl'); print(F['Close'].shape, F['Close'].index[-3:].tolist())
print(lst.head(30).Name.tolist())
