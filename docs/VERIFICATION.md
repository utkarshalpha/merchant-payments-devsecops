> Historical planning/verification document. For the implemented AWS staging lab and build #17 evidence, see [the current README](../README.md) and [implementation walkthrough](IMPLEMENTATION.md). Statements below may describe earlier milestones or deferred work.

# First application milestone

Verified on this PC on 27 October 2026.

- Spring Boot 3.5.16, Java 21 compilation target, built using the existing Java 25.0.1 JDK and Maven 3.9.16.
- `mvn clean verify`: 19 tests passed, zero failures/errors/skips.
- Tests include simultaneous duplicate requests, idempotency conflicts, merchant/key scoping, payment/refund transitions, invalid amounts, request typing, API-key checks, and metric behavior on replay.
- An executable `target/merchant-payments.jar` was produced.
- A separate temporary JAR process passed live HTTP checks for health, missing-key rejection, order creation, safe replay, conflicting-key rejection, simulated success, refund, and refund retry.
- Prometheus returned `merchant_payment_orders_total 1.0` after creation plus a matching replay, confirming the replay did not increment the counter.
- Temporary HTTP verification used H2 in-memory storage and a randomly generated environment API key. The process was stopped afterward.

The concurrent-create test can log an expected unique-constraint violation internally: one racing transaction loses, rolls back, and reads the already-created order in a fresh transaction. The test requires both HTTP responses to succeed with one stored order.

Not yet verified: PostgreSQL integration, default file-backed persistence/restart behavior, code SAST, packaged dependency/image vulnerability scans, Jenkins execution, Docker image/runtime, EC2/ECR, Kubernetes, or cloud deployment. The application has no real payment-network integration and transferred no funds. No AWS resources were created.

These checks were performed by the assistant. The learner's independent execution and explanation are separate preparation milestones.

## GitOps configuration milestone

- Rebuilt offline after adding the Kubernetes profile: all 19 application tests still pass and the JAR contains the new profile.
- Seven promotion-policy tests pass, including rejection of mutable tags, placeholder digests, failed scan metadata, mismatched staging evidence, and preservation of production-specific settings.
- Helm 3.22.1 lint and staging/production renders pass. YAML parsing confirms the workload uses a digest, a non-root user, and a read-only root filesystem.
- Trivy 0.76.1 configuration scan reports no HIGH/CRITICAL findings for the Dockerfile, Argo definitions, namespaces, and rendered workloads.
- The secret-only filesystem scan passes with no findings. Its first online attempt hit Maven Central HTTP 429; the secret-only scan now uses offline dependency analysis, which does not require remote Maven metadata. This is not a dependency vulnerability audit.
- The CI shell script passes Bash syntax validation.

Argo CD Applications, ECR publishing, and the Kubernetes staging verification script are implemented but not integration-tested here. They need the user's actual Git URL, trusted Jenkins agent, registry, cluster, PostgreSQL, and runtime Secrets. The checked-in registry/repository placeholders intentionally cannot be promoted by the helper. Jenkins Declarative validation still requires a Jenkins server. Runtime NetworkPolicy, TLS/ingress, and cluster authorization need platform configuration.
# Public portfolio edition — 28 October 2026

The original private lab's 20-commit history passed Gitleaks 8.30.1 with no findings. The public edition starts with a fresh history and excludes the original account-specific registry and deployment values. All four published screenshots were visually reviewed.

Validation performed on this public edition:

- Maven `clean verify`: 19 application tests passed, zero failures/errors/skips; application JAR packaged successfully.
- Python deployment-policy/helper suite: 10 tests passed, including runtime-account resolution, signed-repository/digest pinning and refusal to deploy after signature verification fails.
- Registry Bash syntax and Python helper compilation passed.
- Gitleaks scan of the staged public source: no findings.

The account-lookup and Argo repository-parameter changes have not been deployed to AWS. Build #17 screenshots and end-to-end cloud results refer to the original private lab. No cloud resources were started for publication.

---
