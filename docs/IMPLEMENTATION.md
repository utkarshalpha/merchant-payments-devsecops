# Implementation walkthrough

This records the original private staging lab, verified by Jenkins build #17 on 28 October 2026 (IST). The public portfolio edition has account-specific values removed, resolves its account through STS, and supplies the image repository as an Argo CD Helm parameter; those portability changes have not been redeployed to AWS. See the main README for four screenshots and scope limits. Commands below explain the workflow; they are not a one-command cloud installer. Host paths, credentials, tools and runtime secrets must already be provisioned.

## 1. Application and Git

Built the Spring Boot payment simulator with validation, an API-key filter, transactional state changes, idempotency, Flyway migrations, health endpoints and tests. Created the private GitHub repository and connected Jenkins through a read-only SSH deploy key. Jenkins polls `main` every minute while EC2 is running.

On the Windows PC, PowerShell, Git and GitHub CLI were used to edit, commit and push project files. AWS CLI used an approved temporary session, not a permanent access key.

```sh
git add <changed-files>
git commit -m "Describe the change"
git push
```

The push changes Git; Jenkins then fetches that commit and runs **Jenkinsfile.ci**. A number such as `#17` is a Jenkins build number, not a command typed into the app.

## 2. AWS and Jenkins setup

Used one EC2 instance, an encrypted existing EBS disk, an SSM instance role and a private ECR repository. Added repository-scoped image push/pull permissions. Installed Jenkins, Java 21, Maven and the scanner tools on EC2. Docker runs rootless as the Jenkins user; a second EC2 was not required.

Administration commands ran on EC2 through SSM Run Command/Session Manager. Local CLI commands opened SSM port-forwarding sessions, which is why Jenkins appeared at `localhost:8080` on the PC even though Jenkins ran on AWS.

Representative local command, with your instance ID substituted:

```sh
aws ssm start-session --profile jenkins-lab --region ap-southeast-2 \
  --target <instance-id> --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=8080,localPortNumber=8080'
```

## 3. Build and security gates

Jenkins executes these repository scripts on EC2, in order:

```sh
gitleaks git --redact --no-banner .
mvn --batch-mode --no-transfer-progress -DargLine=-Xmx384m clean verify
sh .ci/sast.sh
sh .ci/sca.sh
python3 -m unittest discover -s tests_gitops -v
bash .ci/container-lab.sh
sh .ci/iac.sh
bash .ci/sign.sh
bash .ci/registry.sh
```

`MAVEN_OPTS` caps the ordinary build heap; the SCA script sets its own bounded heap. Scanner versions and flags are recorded in the scripts. Dependency fixes included moving the project to Spring Boot 4.1.2 and adapting its Jackson usage. Container fixes pinned the Java runtime image and upgraded the vulnerable Alpine package. All application tests were rerun after the upgrades.

The Dockerfile builds the application container. `.ci/image.sh` and `.ci/container-lab.sh` build/export it, scan the exact tar, generate the SBOM and check container health. `.ci/sign.sh` signs/verifies the archive. `.ci/registry.sh` loads that scanned archive, pushes an immutable commit/build tag, resolves its digest, signs the registry digest and verifies the commit annotation. Temporary registry login configuration is removed afterward.

## 4. Staging deployment

Installed K3s and the required Argo CD components on the same EC2. Created the staging namespace, PostgreSQL deployment/PVC, runtime secrets, ECR pull-secret refresh and network policies. Secrets and signing private keys stay outside Git.

The deployment entry point is:

```sh
bash .ci/staging.sh deploy
```

It reads `reports/registry/release.json`, then calls `/usr/local/sbin/merchant-staging` via a narrowly scoped sudo rule. The helper is installed as a root-owned file from `scripts/merchant-staging.py`; repository changes do not automatically replace that privileged installed copy. Supporting smoke code and the scanner image reference live under `/usr/local/lib/merchant-staging/` on EC2.

The helper validates the digest/commit, independently verifies Cosign, patches only the designated staging Argo Application, pins its source revision and Helm image parameters, and waits for Synced/Healthy plus the expected deployment image. It does not provide Jenkins with the administrator kubeconfig. This implementation updates the Argo Application parameters directly; it does not create a separate Git promotion commit for every build.

## 5. Smoke tests and ZAP

```sh
bash .ci/staging.sh smoke
bash .ci/staging.sh dast
```

Smoke tests restart/wait for the private staging connection, then check health, missing-auth rejection, creation, idempotent replay, successful simulated payment, refund and readback. Test orders use a staging-smoke merchant and synthetic amounts; no money moves.

DAST creates a temporary, resource-limited ZAP pod with no service-account token, using the pinned image in `.ci/zap-image.txt`. The smoke requests run through ZAP's local proxy with the staging API key read from its mounted secret. ZAP's API binds to pod loopback. The helper waits for passive scanning, checks traffic was captured and returns sanitized reports. Medium/high alerts fail the stage; the temporary pod is deleted afterward.

Build #17 captured 12 messages and reported zero alerts. This measures the exercised payment paths only; it is not exhaustive security coverage.

## 6. Evidence and troubleshooting

Jenkins archives `reports/sca`, `reports/iac`, `reports/signing`, `reports/registry`, `reports/staging`, `reports/dast`, Semgrep results, container findings and the SBOM. ZAP emits HTML and JSON reports. Large Docker image tar archives were removed from retention because ECR holds the images.

Useful read-only commands on the EC2 host:

```sh
free -m
df -h /
systemctl status jenkins
sudo k3s kubectl -n argocd get applications
sudo k3s kubectl -n merchant-payments-staging get pods
systemctl list-timers jenkins-lab-autostop.timer
```

The major recovery lessons were shared-host memory limits, disk pressure from scanner images, and waiting for a port-forward after pod replacement. Failed runs remain useful evidence: #13 was interrupted during memory recovery, #15 timed out during disk-pressure recovery, #16 caught connection timing, and #17 passed the corrected complete workflow.

## What to say when presenting this project

“I built a merchant-payments simulator and automated its delivery on AWS with Jenkins. The pipeline tests payment behavior, checks secrets, code, dependencies, containers and Helm manifests, signs immutable ECR images, deploys a verified digest through Argo CD, and runs staging payment tests plus passive ZAP scanning. I kept it on one instance for the lab and resolved memory, disk and rollout-readiness issues. It is a simulator and staging demonstration, not a production payments system.”
