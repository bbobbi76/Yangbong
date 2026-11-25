# 11/9 버그 수정 검증: 가짜 API로만 실행 (실제 서버 호출·주문 없음)
# 팀 저장소 루트에서: python test_fix.py old_rebalance.py
#   old_rebalance.py = 수정 전 agent/rebalance.py (git show f637b48:agent/rebalance.py > old_rebalance.py)
import sys, os, json, tempfile, importlib.util
from pathlib import Path
import pandas as pd
sys.path.insert(0, '.')
os.environ['TEAM_CODE'] = 'FAKE'; os.environ['DART_KEY'] = 'FAKE'; os.environ.pop('GEMINI_KEY', None)
import agent.rebalance as new
from agent.aqua import AquaError
spec = importlib.util.spec_from_file_location('old_rb', sys.argv[1])
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)

class Fake:
    book = None; script = None; log = None
    def __init__(self): pass
    def symbols(self): return set('ABCDEFGH')
    def portfolio(self):
        return dict(totalAssetValue=1_000_000, holdings=[dict(symbol=s, availableQuantity=q) for s, q in Fake.book.items()])
    def prices(self, ss): return {s: 100 for s in ss}
    def order(self, s, side, q):
        Fake.log.append((s, side, q)); act = Fake.script.get((s, side), 'all')
        if act == 'fail':
            raise AquaError(429, 'SYMBOL_COOLDOWN', 'x')
        f = q if act == 'all' else min(q, act)
        Fake.book[s] = Fake.book.get(s, 0) + (f if side == 'BUY' else -f)
        if Fake.book[s] == 0:
            del Fake.book[s]
        return dict(status='FILLED', filledQuantity=f, executedPrice=100)

def day(m, state, book, script, bad):
    d = Path(tempfile.mkdtemp()) / 'c.json'; d.write_text(json.dumps(state)); m.STATE = d
    m.Aqua = Fake; m.load_dotenv = lambda: None; m.trading_days_since = lambda x: 3
    m.momentum.ranked = lambda: pd.DataFrame(dict(code=list('FGHABCDE'), name=list('FGHABCDE')))
    m.dart_filter.blocked = lambda c: {s: '악재' for s in bad}
    Fake.book = book; Fake.script = script; Fake.log = []; sys.argv = ['x', '--execute']; m.main()
    return json.loads(d.read_text()), dict(Fake.book), Fake.log

S0 = dict(targets=list('ABCDE'), rebalanced='2026-11-06')
B0 = {c: 1600 for c in 'ABCDE'}

print('[수정 전] 매도 실패 재현')
st, bk, lg = day(old, dict(S0), dict(B0), {('B', 'SELL'): 'fail'}, ['B'])
assert 'B' not in st['targets'] and bk['B'] == 1600
print('RESULT old: B는 목록에서 사라졌는데 계좌에', bk['B'], '주 남음')

print('[수정 후] 매도 실패 + 매수 일부 체결')
st, bk, lg = day(new, dict(S0), dict(B0), {('B', 'SELL'): 'fail', ('F', 'BUY'): 500}, ['B'])
assert st['pending_sell'] == ['B'] and st['short'] == {'F': 1100} and bk['B'] == 1600 and bk['F'] == 500
st, bk, lg = day(new, st, bk, {}, [])
assert st['pending_sell'] == [] and st['short'] == {} and 'B' not in bk and bk['F'] == 1600
assert ('B', 'SELL', 1600) in lg and ('F', 'BUY', 1100) in lg
print('RESULT 1 ok', lg)

print('[수정 후] 매도 일부 체결')
st, bk, lg = day(new, dict(S0), dict(B0), {('B', 'SELL'): 1000}, ['B'])
assert st['pending_sell'] == ['B'] and bk['B'] == 600
st, bk, lg = day(new, st, bk, {}, [])
assert 'B' not in bk and st['pending_sell'] == []
print('RESULT 2 ok', lg)

print('[수정 후] 옛 상태 파일 + 평상시: 주문 없음')
st, bk, lg = day(new, dict(S0), dict(B0), {}, [])
assert lg == [] and st['pending_sell'] == [] and st['short'] == {}
print('RESULT 3 ok')

print('[수정 후] 월중 보유분 수량 차이는 보충 안 함')
b = dict(B0); b['A'] = 1000
st, bk, lg = day(new, dict(S0), b, {}, [])
assert lg == []
print('RESULT 4 ok')

print('[수정 후] 대기 매도 종목이 다시 목표에 들어오면 매도 안 함')
s = dict(S0, targets=list('ACDE'), pending_sell=['F']); b = {c: 1600 for c in 'ACDEF'}
st, bk, lg = day(new, s, b, {}, [])
assert not any(x[:2] == ('F', 'SELL') for x in lg) and st['pending_sell'] == []
print('RESULT 5 ok', st['targets'], lg)
print('ALL PASS')
