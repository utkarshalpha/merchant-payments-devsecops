#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p reports .tools
TRIVY_IMAGE=ghcr.io/aquasecurity/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c

trivy() {
  docker run --rm --user "$(id -u):$(id -g)" -e TRIVY_CACHE_DIR=/tmp/trivy \
    -v "$PWD:/workspace:ro" -v "$PWD/reports:/reports" -w /workspace "$TRIVY_IMAGE" "$@"
}

case "${1:?Pass config, build, scan, smoke, publish, or cleanup}" in
  config)
    for tool in docker helm curl python3 openssl; do command -v "$tool" >/dev/null; done
    docker info >/dev/null
    helm lint deploy/chart --strict
    helm template merchant-payments deploy/chart -f deploy/chart/environments/staging.json \
      --namespace merchant-payments-staging > reports/kubernetes-staging.yaml
    helm template merchant-payments deploy/chart -f deploy/chart/environments/production.json \
      --namespace merchant-payments-production > reports/kubernetes-production.yaml
    # Secret detection needs local text, not remote Maven dependency resolution.
    trivy fs --scanners secret --offline-scan --exit-code 1 --format json --output /reports/secrets.json \
      --skip-dirs .git --skip-dirs .tools --skip-dirs .m2 --skip-dirs target --skip-dirs reports .
    trivy config --severity HIGH,CRITICAL --exit-code 1 --format json --output /reports/config.json \
      --skip-dirs .git --skip-dirs .tools --skip-dirs .m2 --skip-dirs target --skip-dirs deploy/chart .
    ;;
  build)
    docker build --label "org.opencontainers.image.revision=$SOURCE_COMMIT" -t "$APP_IMAGE" .
    docker save --output reports/image.tar "$APP_IMAGE"
    ;;
  scan)
    trivy image --input /reports/image.tar --format cyclonedx --output /reports/sbom.cdx.json
    trivy image --input /reports/image.tar --scanners vuln --severity HIGH,CRITICAL \
      --exit-code 1 --format json --output /reports/image-vulnerabilities.json
    ;;
  smoke)
    # Key goes through the environment, not a command argument or build artifact.
    export PAYMENTS_API_KEY
    PAYMENTS_API_KEY=$(openssl rand -hex 32)
    trap 'docker rm --force "$SMOKE_CONTAINER" >/dev/null 2>&1 || true' EXIT
    docker run --detach --rm --name "$SMOKE_CONTAINER" --memory 768m --cpus 1 \
      --read-only --tmpfs /tmp:rw,nosuid,noexec,size=128m --cap-drop ALL \
      --security-opt no-new-privileges --publish 127.0.0.1::8081 \
      --env PAYMENTS_API_KEY --env 'DB_URL=jdbc:h2:mem:ci-smoke' "$APP_IMAGE" >/dev/null
    address=$(docker port "$SMOKE_CONTAINER" 8081/tcp | head -n 1)
    for attempt in $(seq 1 60); do
      if curl --fail --silent --max-time 3 "http://$address/actuator/health" > /dev/null; then
        echo 'PASS: container HTTP health check'
        exit 0
      fi
      sleep 2
    done
    docker logs --tail 100 "$SMOKE_CONTAINER"
    echo 'Container smoke check failed' >&2
    exit 1
    ;;
  publish)
    command -v aws >/dev/null
    [[ ${AWS_ACCOUNT_ID:-} =~ ^[0-9]{12}$ ]]
    [[ ${AWS_REGION:-} =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]]
    [[ ${ECR_REPOSITORY:-} =~ ^[a-z0-9][a-z0-9._/-]*$ ]]
    test "$(aws sts get-caller-identity --query Account --output text)" = "$AWS_ACCOUNT_ID"
    export DOCKER_CONFIG="$PWD/.tools/registry-auth"
    registry="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    tag="$SOURCE_COMMIT-$RUN_ID"
    remote="$registry/$ECR_REPOSITORY:$tag"
    printf '%s' "$remote" > .tools/published-image
    aws ecr get-login-password --region "$AWS_REGION" \
      | docker login --username AWS --password-stdin "$registry"
    docker tag "$APP_IMAGE" "$remote"
    docker push "$remote"
    digest=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$ECR_REPOSITORY" \
      --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)
    [[ $digest =~ ^sha256:[a-f0-9]{64}$ ]]
    export RELEASE_IMAGE="$registry/$ECR_REPOSITORY@$digest"
    python3 - <<'PY'
import json, os
from pathlib import Path
report = {"image": os.environ["RELEASE_IMAGE"], "sourceCommit": os.environ["SOURCE_COMMIT"],
          "imageScan": "passed", "containerSmoke": "passed"}
Path("reports/release.json").write_text(json.dumps(report, indent=2) + "\n")
PY
    ;;
  cleanup)
    if [ -n "${SMOKE_CONTAINER:-}" ]; then docker rm --force "$SMOKE_CONTAINER" >/dev/null 2>&1 || true; fi
    if [ -f .tools/published-image ]; then docker image rm "$(cat .tools/published-image)" >/dev/null 2>&1 || true; fi
    if [ -n "${APP_IMAGE:-}" ]; then docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true; fi
    rm -f reports/image.tar .tools/registry-auth/config.json .tools/published-image
    ;;
  *) echo 'Unknown image stage' >&2; exit 2 ;;
esac
