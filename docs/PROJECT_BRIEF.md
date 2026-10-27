> Historical planning/verification document. For the implemented AWS staging lab and build #17 evidence, see [the current README](../README.md) and [implementation walkthrough](IMPLEMENTATION.md). Statements below may describe earlier milestones or deferred work.

# The project we are building

**Merchant Payments Simulator with a DevSecOps pipeline on AWS.**

This is our own payments-related Spring Boot application. The car/driver repository is a reference for pipeline concepts, not the application we will deploy.

## User story

A merchant wants to create a payment order for 100 rupees. The request times out, so their system retries. Our API must return the original order rather than create another. A simulator can record success or failure. A successful order can receive a simulated full refund.

No funds are transferred. This is a test-data application for learning software delivery and reliability.

## The important behavior

| Action | Expected result | What it demonstrates |
|---|---|---|
| Create an order | One order with status CREATED | HTTP APIs, validation, database writes |
| Retry with the same merchant/key/details | Return the existing order | Idempotency |
| Reuse a key with a different amount | HTTP 409 conflict | Preventing ambiguous retries |
| Send two matching requests simultaneously | One database order | Database constraints and concurrency |
| Simulate a result | CREATED becomes SUCCESS or FAILED | Controlled state transitions |
| Refund | SUCCESS becomes REFUNDED | Business rules and retry safety |
| Use invalid money values | Reject the request | Strict integer paise and input validation |
| Omit the API key | HTTP 401 | Basic demo API access control |

## Where the code lives

| File | Responsibility |
|---|---|
| `PaymentApi.java` | HTTP endpoints, request validation, response shape |
| `PaymentService.java` | Idempotency, transactions, outcomes, refunds |
| `PaymentOrderRepository.java` | Database reads, writes, and row locks |
| `PaymentOrder.java` | Stored order fields |
| `ApiKeyFilter.java` | Checks the demo API key |
| `V1__payment_orders.sql` | Version-controlled database schema and constraints |
| `PaymentApiTest.java` | Automated behavior checks |
| `Jenkinsfile` | Initial build/test automation; delivery stages come next |

## Delivery milestones

1. Build the JAR, run payment-behavior tests, and exercise HTTP endpoints locally.
2. Repeat the commands yourself and explain source code, build output, tests, idempotency, and exit codes.
3. Verify AWS Free plan/credits, choose a reviewed EC2 configuration, and connect to Linux.
4. Set up Jenkins, container packaging, security gates, registry publishing, and deployment.
5. Demonstrate a rejected release, inspect logs/metrics, and practise recovery.
6. Extend with Kubernetes, Terraform, GitOps, and monitoring according to available time and budget.

The application build/test milestone is verified. CI/container and Argo CD deployment definitions plus promotion helpers are now included; full CI and cloud delivery have not been executed. Do not present the full architecture as completed production experience. See `GITOPS.md` for the prerequisites and promotion workflow.

## Interview framing

“I am building a merchant payment simulator and its delivery pipeline. I use idempotency keys and database constraints to prevent duplicate orders, validate monetary input in integer paise, and test allowed payment/refund transitions. My DevOps work packages and checks this application, enforces release gates, and verifies deployments.”

State which parts you personally ran and understood. Domain relevance can make the discussion more concrete, but does not guarantee preference or selection.
