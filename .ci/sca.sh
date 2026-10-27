#!/bin/sh
set -eu
mkdir -p reports/sca
# The project-maintained NVD mirror avoids an API key and repeated API downloads.
# Reject stale feed metadata rather than silently passing on old vulnerability data.
curl --fail --silent --show-error --connect-timeout 15 --max-time 60 \
  https://dependency-check.github.io/DependencyCheck_Builder/nvd_cache/nvdcve-modified.meta \
  -o reports/sca/nvd-feed.meta
python3 - <<'PY'
from datetime import datetime, timezone, timedelta
from pathlib import Path
metadata = dict(line.split(':', 1) for line in Path('reports/sca/nvd-feed.meta').read_text().splitlines() if ':' in line)
updated = datetime.fromisoformat(metadata['lastModifiedDate'].replace('Z', '+00:00'))
age = datetime.now(timezone.utc) - updated
assert timedelta(days=-1) <= age <= timedelta(days=3), f'NVD mirror is stale: {updated}'
print(f'NVD feed freshness check passed: {updated.isoformat()}')
PY
export MAVEN_OPTS="${MAVEN_OPTS:-} -Xmx768m"
python3 scripts/test_sca_gate.py
mvn --batch-mode --no-transfer-progress -Psca org.owasp:dependency-check-maven:13.0.0:check
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('reports/sca/dependency-check-report.json').read_text())
assert report.get('dependencies'), 'SCA report contains no dependencies'
assert not report.get('scanInfo', {}).get('analysisExceptions'), 'SCA analysis errors'
print(f"SCA gate passed: {len(report['dependencies'])} dependencies analyzed; no CVSS >= 7 findings.")
PY
