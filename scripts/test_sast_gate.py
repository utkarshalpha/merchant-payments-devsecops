"""Prove the scanner rejects unsafe crypto and accepts a safe counterpart."""
import json
import subprocess
import tempfile
from pathlib import Path

rules = Path('.semgrep/java.yml').resolve()
with tempfile.TemporaryDirectory(prefix='sast-gate-') as temporary:
    root = Path(temporary)
    source = root / 'CryptoProbe.java'
    for algorithm, expected_exit in [('MD5', 1), ('SHA-256', 0)]:
        source.write_text(
            'import java.security.MessageDigest;\n'
            'class CryptoProbe { Object digest() throws Exception {\n'
            f'  return MessageDigest.getInstance("{algorithm}");\n'
            '} }\n'
        )
        result = subprocess.run([
            'semgrep', 'scan', '--config', str(rules), '--metrics=off',
            '--disable-version-check', '--oss-only', '--strict', '--error',
            '--jobs', '1', '--max-memory', '768', '--json',
            '--no-git-ignore', str(source),
        ], capture_output=True, text=True)
        if result.returncode != expected_exit:
            raise RuntimeError(f'{algorithm} gate probe failed: {result.stderr}\n{result.stdout}')
        report = json.loads(result.stdout)
        assert not report.get('errors'), report['errors']
        assert report['paths']['scanned'], 'Probe was not scanned'
        if expected_exit:
            assert any('use-of-md5' in finding['check_id'] for finding in report['results'])
        else:
            assert not report['results']
        print(f'SAST gate self-test: {algorithm} returned {expected_exit} as expected.')
