import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gitops", SOURCE / "scripts/gitops.py")
gitops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gitops)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.envs = self.root / gitops.ENVIRONMENTS
        self.envs.mkdir(parents=True)
        for name, replicas in [("staging", 1), ("production", 2)]:
            gitops.write(self.envs / (name + ".json"), {
                "replicaCount": replicas, "runtimeSecret": name + "-secret", "image": {}})
        self.image = "111111111111.dkr.ecr.ap-south-1.amazonaws.com/merchant-payments@sha256:" + "a" * 64
        self.commit = "b" * 40
        self.release = self.root / "release.json"
        gitops.write(self.release, {"image": self.image, "sourceCommit": self.commit,
                                   "imageScan": "passed", "containerSmoke": "passed"})

    def evidence(self, **changes):
        report = {"namespace": "merchant-payments-staging", "image": self.image,
                  "sourceCommit": self.commit, "checks": {"rollout": True, "paymentFlow": True}}
        report.update(changes)
        path = self.root / "evidence.json"
        gitops.write(path, report)
        return path

    def test_same_digest_promoted_without_overwriting_production_settings(self):
        gitops.stage(self.root, self.release)
        gitops.promote(self.root, self.evidence())
        production = gitops.read(self.envs / "production.json")
        self.assertEqual(production["image"]["digest"], "sha256:" + "a" * 64)
        self.assertEqual(production["replicaCount"], 2)
        self.assertEqual(production["runtimeSecret"], "production-secret")

    def test_missing_image_scan_pass_blocks_staging(self):
        release = gitops.read(self.release)
        release["imageScan"] = "failed"
        gitops.write(self.release, release)
        with self.assertRaises(ValueError):
            gitops.stage(self.root, self.release)

    def test_mutable_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            gitops.identity("example.com/payments:latest", self.commit)

    def test_placeholder_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            gitops.identity("example.com/payments@sha256:" + "0" * 64, self.commit)

    def test_different_image_blocks_production(self):
        gitops.stage(self.root, self.release)
        before = (self.envs / "production.json").read_bytes()
        with self.assertRaises(ValueError):
            gitops.promote(self.root, self.evidence(image=self.image.replace("a" * 64, "c" * 64)))
        self.assertEqual(before, (self.envs / "production.json").read_bytes())

    def test_failed_smoke_blocks_production(self):
        gitops.stage(self.root, self.release)
        with self.assertRaises(ValueError):
            gitops.promote(self.root, self.evidence(checks={"rollout": True, "paymentFlow": False}))

    def test_wrong_source_commit_blocks_production(self):
        gitops.stage(self.root, self.release)
        with self.assertRaises(ValueError):
            gitops.promote(self.root, self.evidence(sourceCommit="c" * 40))


if __name__ == "__main__":
    unittest.main()
