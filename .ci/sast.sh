#!/bin/sh
set -eu
export SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0
test "$(semgrep --version)" = '1.182.1'
mkdir -p reports
python3 scripts/test_sast_gate.py
semgrep scan --config .semgrep/java.yml --metrics=off --disable-version-check \
  --oss-only --strict --error --jobs 1 --max-memory 768 --timeout 10 \
  --json-output reports/semgrep.json --sarif-output reports/semgrep.sarif src/main/java
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('reports/semgrep.json').read_text())
assert not report.get('errors'), 'Incomplete scan: Semgrep reported errors'
expected = {str(p) for p in Path('src/main/java').rglob('*.java')}
scanned = set(report['paths']['scanned'])
assert expected and expected <= scanned, f'Unscanned Java files: {expected - scanned}'
assert not report['results'], 'SAST findings block the build'
print(f'SAST gate passed: all {len(expected)} application Java files scanned; no findings.')
PY
