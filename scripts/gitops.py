"""Prepare reviewable GitOps changes; never pushes Git or contacts a cluster."""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = Path("deploy/chart/environments")
IMAGE = re.compile(r"([a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+)@(sha256:[a-f0-9]{64})")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def identity(image, commit):
    match = IMAGE.fullmatch(image)
    if not match or "registry.invalid" in image or "replace-me" in image:
        raise ValueError("A real registry image pinned with @sha256 is required")
    if match[2] == "sha256:" + "0" * 64:
        raise ValueError("Placeholder digests cannot be promoted")
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or commit == "0" * 40:
        raise ValueError("A real 40-character source commit is required")
    return {"repository": match[1], "digest": match[2], "sourceCommit": commit}


def stage(root, release_file):
    release = read(release_file)
    if release.get("imageScan") != "passed" or release.get("containerSmoke") != "passed":
        raise ValueError("Release metadata must record passed image and container smoke gates")
    image = identity(release["image"], release["sourceCommit"])
    path = Path(root) / ENVIRONMENTS / "staging.json"
    values = read(path)
    values["image"] = image
    write(path, values)


def promote(root, evidence_file):
    staging = read(Path(root) / ENVIRONMENTS / "staging.json")
    selected = staging["image"]
    full_image = selected["repository"] + "@" + selected["digest"]
    image = identity(full_image, selected["sourceCommit"])
    evidence = read(evidence_file)
    if (evidence.get("namespace") != "merchant-payments-staging"
            or evidence.get("image") != full_image
            or evidence.get("sourceCommit") != image["sourceCommit"]
            or evidence.get("checks", {}).get("rollout") is not True
            or evidence.get("checks", {}).get("paymentFlow") is not True):
        raise ValueError("Passing staging evidence must match this exact image and source commit")
    path = Path(root) / ENVIRONMENTS / "production.json"
    production = read(path)
    production["image"] = image
    write(path, production)


def validate(root, environment):
    values = read(Path(root) / ENVIRONMENTS / (environment + ".json"))
    image = values["image"]
    identity(image["repository"] + "@" + image["digest"], image["sourceCommit"])
    for path in (Path(root) / "gitops/argocd").glob("*.yaml"):
        if "REPLACE_ME" in path.read_text():
            raise ValueError("Configure your own Git repository URL in " + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stage").add_argument("--release", required=True)
    commands.add_parser("promote").add_argument("--evidence", required=True)
    commands.add_parser("validate").add_argument("--environment", choices=["staging", "production"], required=True)
    args = parser.parse_args()
    try:
        if args.command == "stage":
            stage(ROOT, args.release)
        elif args.command == "promote":
            promote(ROOT, args.evidence)
        else:
            validate(ROOT, args.environment)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    print("Prepared/validated locally. Review the Git diff; nothing was pushed or deployed.")


if __name__ == "__main__":
    main()
