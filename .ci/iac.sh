#!/bin/sh
set -eu
test "$(checkov --version)" = '3.3.30'
mkdir -p reports/iac
helm lint deploy/chart --strict
for environment in staging production; do
  helm template merchant-payments deploy/chart -f "deploy/chart/environments/$environment.json" \
    --namespace "merchant-payments-$environment" > "reports/iac/$environment.yaml"
  checkov --file "reports/iac/$environment.yaml" --framework kubernetes --skip-download \
    --output json > "reports/iac/$environment.json"
done
python3 - <<'PY'
import json
from pathlib import Path
for env in ('staging', 'production'):
    report = json.loads(Path(f'reports/iac/{env}.json').read_text())
    s = report['summary']
    assert s['passed'] > 0 and s['resource_count'] >= 5, 'Empty or incomplete scan'
    assert not (s['failed'] or s['skipped'] or s['parsing_errors']), s
    print(f"PASS: {env}: {s['passed']} checks, zero failed/skipped/parsing errors")
PY
