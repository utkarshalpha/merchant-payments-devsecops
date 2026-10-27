"""Verify a staging rollout and payment flow through a local kubectl port-forward."""

import argparse
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from uuid import uuid4


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def request(target, path, body=None, key=None, idem=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    if idem:
        headers["Idempotency-Key"] = idem
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=10)
    try:
        connection.request("POST" if body is not None else "GET", path,
                           body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18081")
    parser.add_argument("--output", default="reports/staging-evidence.json")
    args = parser.parse_args()
    target = urlsplit(args.url)
    check(target.scheme == "http" and target.hostname in {"127.0.0.1", "localhost", "::1"}
          and not target.username and not target.password and target.path in {"", "/"},
          "Use a local HTTP kubectl port-forward URL")
    namespace = "merchant-payments-staging"
    kubectl = ["kubectl", "-n", namespace]
    subprocess.run(kubectl + ["rollout", "status", "deployment/merchant-payments", "--timeout=180s"], check=True)
    workload = json.loads(subprocess.check_output(kubectl + ["get", "deployment", "merchant-payments", "-o", "json"]))
    values = json.loads((Path(__file__).resolve().parents[1] / "deploy/chart/environments/staging.json").read_text())
    selected = values["image"]
    expected = selected["repository"] + "@" + selected["digest"]
    from gitops import identity
    identity(expected, selected["sourceCommit"])
    actual = next(c["image"] for c in workload["spec"]["template"]["spec"]["containers"] if c["name"] == "api")
    check(actual == expected, "Cluster deployment does not match the staging image in this checkout")
    annotations = workload["spec"]["template"]["metadata"]["annotations"]
    check(annotations.get("source-commit") == selected["sourceCommit"], "Source commit does not match")
    key = os.environ.get("PAYMENTS_API_KEY", "")
    check(len(key) >= 32, "Set the staging PAYMENTS_API_KEY in this terminal environment")
    check(request(target, "/actuator/health")[0] == 200, "Health check failed")
    body = {"merchantId": "staging-smoke", "amountPaise": 10000, "currency": "INR"}
    idem = "verify-" + uuid4().hex
    check(request(target, "/api/payment-orders", body, idem=idem)[0] == 401, "Unauthenticated request was accepted")
    code, order = request(target, "/api/payment-orders", body, key, idem)
    check(code == 201 and order.get("status") == "CREATED", "Order creation failed")
    code, retry = request(target, "/api/payment-orders", body, key, idem)
    check(code == 200 and retry.get("id") == order["id"], "Idempotent replay failed")
    path = "/api/payment-orders/" + order["id"]
    code, outcome = request(target, path + "/simulate", {"outcome": "SUCCESS"}, key)
    check(code == 200 and outcome.get("status") == "SUCCESS", "Simulated success failed")
    code, refunded = request(target, path + "/refund", {}, key)
    check(code == 200 and refunded.get("status") == "REFUNDED", "Simulated refund failed")
    report = {"namespace": namespace, "image": expected, "sourceCommit": selected["sourceCommit"],
              "verifiedAt": datetime.now(timezone.utc).isoformat(),
              "checks": {"rollout": True, "paymentFlow": True}}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: staging rollout, exact image, and simulated payment flow. Evidence: " + str(output))


if __name__ == "__main__":
    main()
