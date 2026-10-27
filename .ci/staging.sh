#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports/staging reports/dast
readarray -t release < <(python3 - <<'PY'
import json
r=json.load(open('reports/registry/release.json'))
assert r['registrySignature']=='verified'
print(r['image'].split('@')[1]); print(r['sourceCommit'])
PY
)
sudo /usr/local/sbin/merchant-staging "$1" "${release[0]}" "${release[1]}" > "reports/$([ "$1" = dast ] && echo dast || echo staging)/$1.json"
python3 - "$1" <<'PY'
import json,sys,pathlib
mode=sys.argv[1]; p=pathlib.Path('reports/dast' if mode=='dast' else 'reports/staging')
r=json.loads((p/(mode+'.json')).read_text())
if mode=='dast':
    (p/'zap.html').write_text(r.pop('html'))
    (p/'zap.json').write_text(json.dumps(r.pop('zap'),indent=2))
    (p/'dast.json').write_text(json.dumps(r,indent=2))
assert r['passed'],r
print(json.dumps(r,indent=2))
PY
