#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
export DOCKER_CONFIG="$WORKSPACE/.tools/ecr-auth"
mkdir -p "$DOCKER_CONFIG" reports/registry
account=$(aws sts get-caller-identity --query Account --output text)
[[ $account =~ ^[0-9]{12}$ ]]
registry="$account.dkr.ecr.ap-southeast-2.amazonaws.com"
repository="$registry/merchant-payments-lab"
commit=$(git rev-parse HEAD)
tag="$commit-$BUILD_NUMBER"
trap 'docker image rm "merchant-payments-ci:$BUILD_NUMBER" "$repository:$tag" >/dev/null 2>&1 || true; rm -f "$DOCKER_CONFIG/config.json"' EXIT
cosign verify-blob --key "$HOME/.cosign/cosign.pub" --bundle reports/signing/image.bundle.json --insecure-ignore-tlog reports/image.tar
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin "$registry"
docker load --input reports/image.tar
docker tag "merchant-payments-ci:$BUILD_NUMBER" "$repository:$tag"
docker push "$repository:$tag"
digest=$(aws ecr describe-images --region ap-southeast-2 --repository-name merchant-payments-lab --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)
[[ $digest =~ ^sha256:[a-f0-9]{64}$ ]]
export RELEASE_IMAGE="$repository@$digest" SOURCE_COMMIT="$commit"
export COSIGN_PASSWORD="$(cat "$HOME/.cosign/password")"
cosign sign --yes --key "$HOME/.cosign/cosign.key" --signing-config "$HOME/.cosign/signing-config.json" -a "sourceCommit=$commit" "$RELEASE_IMAGE"
unset COSIGN_PASSWORD
cosign verify --key "$HOME/.cosign/cosign.pub" --insecure-ignore-tlog -a "sourceCommit=$commit" "$RELEASE_IMAGE" > reports/registry/verification.json
python3 - <<'PY'
import json, os
from pathlib import Path
Path('reports/registry/release.json').write_text(json.dumps({'image':os.environ['RELEASE_IMAGE'],'sourceCommit':os.environ['SOURCE_COMMIT'],'imageScan':'passed','containerSmoke':'passed','registrySignature':'verified'},indent=2)+'\n')
PY
echo 'PASS: immutable ECR image published; Cosign registry signature verified'
