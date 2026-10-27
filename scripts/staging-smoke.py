"""Run only against the isolated staging simulator. Never print its API key."""
import json, os, time, urllib.request, urllib.error, uuid
from pathlib import Path

base=os.environ.get('STAGING_URL','http://127.0.0.1:18081')
key=Path(os.environ.get('STAGING_KEY','/root/merchant-payments-staging/api-key')).read_text().strip()
proxy=os.environ.get('SMOKE_PROXY')
client=urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy} if proxy else {}))
def call(path,body=None,idem=None,auth=True):
    headers={'Content-Type':'application/json'}
    if auth: headers['X-API-Key']=key
    if idem: headers['Idempotency-Key']=idem
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with client.open(req,timeout=20) as r: return r.status,json.load(r)
    except urllib.error.HTTPError as e: return e.code,{}

assert call('/actuator/health',auth=False)[1]['status']=='UP'
assert call('/api/payment-orders/missing',auth=False)[0] in (401,403)
idem='ci-smoke-'+str(uuid.uuid4())
body={'merchantId':'staging-smoke','amountPaise':10000,'currency':'INR'}
code,order=call('/api/payment-orders',body,idem); assert code==201
code,retry=call('/api/payment-orders',body,idem); assert code==200 and retry['id']==order['id']
code,paid=call('/api/payment-orders/'+order['id']+'/simulate',{'outcome':'SUCCESS'}); assert code==200 and paid['status']=='SUCCESS'
code,refund=call('/api/payment-orders/'+order['id']+'/refund',{}); assert code==200 and refund['status']=='REFUNDED'
code,saved=call('/api/payment-orders/'+order['id']); assert code==200 and saved['status']=='REFUNDED'
result={'passed':True,'checks':['health','authentication','create','idempotency','payment','refund','readback']}
if proxy:
    def zap(path):
        with urllib.request.urlopen('http://127.0.0.1:8090'+path,timeout=20) as r:return r.read()
    time.sleep(3)
    messages=int(json.loads(zap('/JSON/core/view/numberOfMessages/'))['numberOfMessages'])
    assert messages>=7, 'ZAP did not capture the complete smoke traffic'
    for _ in range(90):
        if json.loads(zap('/JSON/pscan/view/recordsToScan/'))['recordsToScan']=='0':break
        time.sleep(2)
    else: raise RuntimeError('ZAP passive scan timed out')
    report=json.loads(zap('/OTHER/core/other/jsonreport/'))
    sites=report.get('site',[])
    assert sites, 'ZAP captured no sites'
    alerts=[a for s in sites for a in s.get('alerts',[])]
    blocking=[{'id':a['pluginid'],'name':a['name'],'risk':a['riskcode']} for a in alerts if int(a['riskcode'])>=2]
    result.update(passed=not blocking,blocking=blocking,alertCount=len(alerts),messages=messages,scan='passive authenticated payment traffic',zap=report,html=zap('/OTHER/core/other/htmlreport/').decode())
print(json.dumps(result).replace(key,'[REDACTED]'))
