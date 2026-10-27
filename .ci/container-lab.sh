#!/usr/bin/env bash
set -euo pipefail
umask 077
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
export TRIVY_CACHE_DIR="$HOME/.cache/trivy"
# Ubuntu mounts /tmp in RAM; unpack the Java DB on the existing EBS disk.
export TMPDIR="$WORKSPACE/.tools/trivy-tmp"
mkdir -p "$TMPDIR"
export SOURCE_COMMIT="$(git rev-parse HEAD)"
export APP_IMAGE="merchant-payments-ci:${BUILD_NUMBER:?}"
export SMOKE_CONTAINER="merchant-payments-smoke-${BUILD_NUMBER}"
trap 'docker rm -f "$SMOKE_CONTAINER" >/dev/null 2>&1 || true; docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true; rm -rf -- "$TMPDIR"' EXIT
docker info --format '{{json .SecurityOptions}}' | grep -q 'name=rootless'
test "$(trivy --version | head -n 1)" = 'Version: 0.76.1'
bash .ci/image.sh build
trivy image --input reports/image.tar --format cyclonedx --output reports/sbom.cdx.json
trivy image --input reports/image.tar --scanners vuln --severity HIGH,CRITICAL \
  --exit-code 1 --format json --output reports/container-vulnerabilities.json
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('reports/container-vulnerabilities.json').read_text())
results = report.get('Results', [])
assert any(r.get('Class') == 'os-pkgs' for r in results), 'Missing OS package scan'
assert any(r.get('Type') == 'jar' for r in results), 'Missing Java dependency scan'
assert not any(r.get('Vulnerabilities') for r in results), 'Blocking vulnerabilities found'
print('PASS: Trivy OS and Java scans; zero HIGH/CRITICAL findings')
PY
bash .ci/image.sh smoke
printf '{"rootless":true,"trivy":"0.76.1","highCritical":0,"containerHealth":"passed"}\n' > reports/container-summary.json
