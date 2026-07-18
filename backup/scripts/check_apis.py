import os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from app import main
app = main.app
with app.test_client() as client:
    r = client.get('/')
    print('GET /', r.status_code, 'len', len(r.data))
    r2 = client.get('/extractos')
    print('GET /extractos', r2.status_code, 'len', len(r2.data))
    re = client.get('/api/extractos')
    print('/api/extractos', re.status_code, len(re.get_json()) if re.status_code==200 else re.data)
    rr = client.get('/api/resumen')
    print('/api/resumen', rr.status_code)
    if rr.status_code==200:
        j = rr.get_json()
        print('resumen keys:', list(j.keys()))
        print('num transacciones in resumen:', j.get('num_transacciones'))
