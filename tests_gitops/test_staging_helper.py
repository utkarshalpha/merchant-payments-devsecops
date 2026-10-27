import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / 'scripts/merchant-staging.py'
DIGEST = 'sha256:' + 'a' * 64
COMMIT = 'b' * 40
ACCOUNT = '111111111111'
REPOSITORY = ACCOUNT + '.dkr.ecr.ap-southeast-2.amazonaws.com/merchant-payments-lab'


class StagingHelperTests(unittest.TestCase):
    def execute(self, account=ACCOUNT, reject_signature=False):
        self.commands = []
        self.argo_patch = None

        def output(args, **kwargs):
            self.commands.append(args)
            if args[1:3] == ['sts', 'get-caller-identity']:
                return account + '\n'
            if args[1:3] == ['ecr', 'get-login-password']:
                return 'synthetic-test-password\n'
            if args[1] == 'verify':
                if reject_signature:
                    raise subprocess.CalledProcessError(1, args)
                return '{}'
            if 'patch' in args:
                self.argo_patch = json.loads(args[args.index('-p') + 1])
                return '{}'
            if 'application' in args:
                return json.dumps({'status': {
                    'sync': {'revision': COMMIT, 'status': 'Synced'},
                    'health': {'status': 'Healthy'}}})
            if 'deployment' in args:
                return json.dumps({
                    'spec': {'template': {'spec': {'containers': [
                        {'image': REPOSITORY + '@' + DIGEST}]}}},
                    'status': {'availableReplicas': 1}})
            raise AssertionError('Unexpected command: ' + str(args))

        with patch('sys.argv', [str(HELPER), 'deploy', DIGEST, COMMIT]), \
                patch('subprocess.check_output', side_effect=output), \
                patch('subprocess.run') as login, \
                contextlib.redirect_stdout(io.StringIO()) as captured:
            runpy.run_path(str(HELPER), run_name='__main__')
        return json.loads(captured.getvalue()), login

    def test_runtime_account_and_verified_release_are_pinned_in_argo(self):
        result, login = self.execute()
        self.assertTrue(result['passed'])
        self.assertEqual(result['image'], REPOSITORY + '@' + DIGEST)
        parameters = self.argo_patch['spec']['source']['helm']['parameters']
        self.assertEqual({p['name']: p['value'] for p in parameters}, {
            'image.repository': REPOSITORY,
            'image.digest': DIGEST,
            'image.sourceCommit': COMMIT})
        verify_index = next(i for i, c in enumerate(self.commands) if c[1] == 'verify')
        patch_index = next(i for i, c in enumerate(self.commands) if 'patch' in c)
        self.assertLess(verify_index, patch_index)
        login.assert_called_once()

    def test_malformed_account_blocks_deployment(self):
        with self.assertRaisesRegex(AssertionError, 'Invalid AWS account identity'):
            self.execute(account='unexpected-account')
        self.assertIsNone(self.argo_patch)
        self.assertEqual(len(self.commands), 1)

    def test_failed_signature_never_patches_argo(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(reject_signature=True)
        self.assertIsNone(self.argo_patch)


if __name__ == '__main__':
    unittest.main()
