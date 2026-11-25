# 11/9 키 노출 수정 검증: 네트워크 오류를 흉내 내 로그·예외에 키가 남는지 확인 (실제 호출 없음)
# 팀 저장소 루트에서: python test_keys.py
import sys, os, requests
sys.path.insert(0, '.')
from agent import dart_filter, surge
SECRET = 'TESTKEY123'
captured = {}
def boom(url, **kw):
    captured.update(url=url, headers=kw.get('headers'))
    raise requests.ConnectionError(f'Max retries exceeded with url: {url}?{kw.get("params")}')
requests.post = boom; requests.get = boom
os.environ['GEMINI_KEY'] = SECRET; os.environ['DART_KEY'] = SECRET
buf = []; surge.log = buf.append
assert surge.llm_confirm('X', 't', {}) is True
assert SECRET not in buf[0] and captured['headers']['x-goog-api-key'] == SECRET and SECRET not in captured['url']
print('gemini ok:', buf[0][:70])
try:
    dart_filter.fetch(1)
    raise SystemExit('no raise')
except RuntimeError as e:
    assert SECRET not in str(e) and e.__suppress_context__
    print('dart ok:', e)
print('KEY PASS')
