#!/usr/bin/python3
"""Root-owned lab helper; only fixed staging resources and validated releases."""
import json,os,re,subprocess,sys,tempfile,time
from pathlib import Path

mode,digest,commit=sys.argv[1:]
assert mode in ('deploy','smoke','dast')
assert re.fullmatch(r'sha256:[0-9a-f]{64}',digest)
assert re.fullmatch(r'[0-9a-f]{40}',commit)
ns='merchant-payments-staging'
account=subprocess.check_output(['/usr/local/bin/aws','sts','get-caller-identity','--query','Account','--output','text'],text=True).strip()
assert re.fullmatch(r'[0-9]{12}',account),'Invalid AWS account identity'
repository=account+'.dkr.ecr.ap-southeast-2.amazonaws.com/merchant-payments-lab'
image=repository+'@'+digest
def run(args,**kw):return subprocess.check_output(args,text=True,**kw)
def kub(*args,**kw):return run(['/usr/local/bin/k3s','kubectl',*args],**kw)
def obj(namespace,kind,name):return json.loads(kub('-n',namespace,'get',kind,name,'-o','json'))
def deployed():
    d=obj(ns,'deployment','merchant-payments')
    assert d['spec']['template']['spec']['containers'][0]['image']==image,'Staging image mismatch'
    assert d['status'].get('availableReplicas',0)==1,'Staging unavailable'

if mode=='deploy':
    with tempfile.TemporaryDirectory() as auth:
        env=dict(os.environ,DOCKER_CONFIG=auth)
        password=run(['/usr/local/bin/aws','ecr','get-login-password','--region','ap-southeast-2'])
        subprocess.run(['docker','login','--username','AWS','--password-stdin',image.split('/')[0]],input=password,text=True,stdout=subprocess.DEVNULL,check=True,env=env)
        run(['/usr/local/bin/cosign','verify','--key','/var/lib/jenkins/.cosign/cosign.pub','--insecure-ignore-tlog','-a','sourceCommit='+commit,image],env=env)
    patch={'spec':{'source':{'targetRevision':commit,'helm':{'parameters':[{'name':'image.repository','value':repository},{'name':'image.digest','value':digest},{'name':'image.sourceCommit','value':commit}]}}},'metadata':{'annotations':{'argocd.argoproj.io/refresh':'hard'}}}
    kub('-n','argocd','patch','application','merchant-payments-staging','--type','merge','-p',json.dumps(patch))
    for _ in range(90):
        app=obj('argocd','application','merchant-payments-staging')
        if app.get('status',{}).get('sync',{}).get('revision')==commit and app['status']['sync']['status']=='Synced' and app['status'].get('health',{}).get('status')=='Healthy':
            deployed();break
        time.sleep(3)
    else:raise RuntimeError('Argo rollout did not reach the signed revision')
    print(json.dumps({'passed':True,'image':image,'revision':commit,'argo':'Synced Healthy'}))
elif mode=='smoke':
    deployed()
    subprocess.run(['systemctl','restart','merchant-payments-staging-forward'],check=True)
    for _ in range(30):
        probe=subprocess.run(['curl','-fsS','--max-time','2','http://127.0.0.1:18081/actuator/health'],capture_output=True,text=True)
        if probe.returncode==0 and json.loads(probe.stdout).get('status')=='UP':break
        time.sleep(2)
    else:raise RuntimeError('Private staging connection is not ready')
    print(run(['/usr/bin/python3','/usr/local/lib/merchant-staging/staging-smoke.py']),end='')
else:
    deployed()
    zapimage=Path('/usr/local/lib/merchant-staging/zap-image').read_text().strip()
    assert re.fullmatch(r'ghcr.io/zaproxy/zaproxy@sha256:[0-9a-f]{64}',zapimage)
    name='merchant-zap'
    pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':ns,'labels':{'payments-client':'true'}},'spec':{'restartPolicy':'Never','activeDeadlineSeconds':420,'automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'zap','image':zapimage,'command':['/zap/zap.sh','-daemon','-host','127.0.0.1','-port','8090','-config','api.disablekey=true','-config','autoupdate.checkOnStart=false','-config','autoupdate.installAddonUpdates=false'],'env':[{'name':'JAVA_OPTS','value':'-Xmx512m'}],'resources':{'requests':{'cpu':'100m','memory':'512Mi'},'limits':{'cpu':'1','memory':'768Mi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'volumeMounts':[{'name':'key','mountPath':'/run/staging','readOnly':True}]}],'volumes':[{'name':'key','secret':{'secretName':'merchant-payments-staging-runtime','items':[{'key':'api-key','path':'api-key'}]}}]}}
    try:
        kub('apply','-f','-',input=json.dumps(pod))
        kub('-n',ns,'wait','--for=condition=Ready','pod/'+name,'--timeout=180s')
        ready="import urllib.request,time\nfor i in range(60):\n try:\n  urllib.request.urlopen('http://127.0.0.1:8090/JSON/core/view/version/',timeout=2);break\n except Exception:time.sleep(2)\nelse:raise RuntimeError('ZAP startup timeout')"
        kub('-n',ns,'exec',name,'--','python3','-c',ready)
        code=Path('/usr/local/lib/merchant-staging/staging-smoke.py').read_text()
        result=kub('-n',ns,'exec','-i',name,'--','env','STAGING_URL=http://merchant-payments','STAGING_KEY=/run/staging/api-key','SMOKE_PROXY=http://127.0.0.1:8090','NO_PROXY=127.0.0.1,localhost','python3','-',input=code)
        print(result,end='')
    finally:
        kub('-n',ns,'delete','pod',name,'--ignore-not-found=true','--wait=false')
