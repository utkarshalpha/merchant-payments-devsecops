"""Check a known-vulnerable artifact in a temporary project; never execute it."""
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {'m': 'http://maven.apache.org/POM/4.0.0'}
ET.register_namespace('', NS['m'])
tree = ET.parse('pom.xml')
root = tree.getroot()
dependencies = root.find('m:dependencies', NS)
dependencies.clear()
dependency = ET.SubElement(dependencies, f"{{{NS['m']}}}dependency")
for tag, value in [('groupId', 'commons-collections'), ('artifactId', 'commons-collections'), ('version', '3.2.1')]:
    ET.SubElement(dependency, f"{{{NS['m']}}}{tag}").text = value

with tempfile.TemporaryDirectory(prefix='sca-gate-') as temporary:
    project = Path(temporary)
    tree.write(project / 'pom.xml', encoding='utf-8', xml_declaration=True)
    result = subprocess.run([
        'mvn', '--batch-mode', '--no-transfer-progress', '-Psca',
        'org.owasp:dependency-check-maven:13.0.0:check',
    ], cwd=project, capture_output=True, text=True)
    report_path = project / 'reports/sca/dependency-check-report.json'
    if not report_path.exists():
        raise RuntimeError('Probe produced no report:\n' + result.stdout[-5000:] + result.stderr[-1000:])
    report = json.loads(report_path.read_text())
    assert not report.get('scanInfo', {}).get('analysisExceptions'), 'Probe failed due to scanner errors'
    findings = [v for dep in report['dependencies'] for v in dep.get('vulnerabilities', [])]
    high = [v for v in findings if max(
        float(v.get('cvssv3', {}).get('baseScore', 0)),
        float(v.get('cvssv2', {}).get('score', 0)),
        float(v.get('cvssv4', {}).get('baseScore', 0)),
    ) >= 7]
    assert high and result.returncode != 0, 'Known-vulnerable dependency did not block the build'
    evidence = {'artifact': 'commons-collections:commons-collections:3.2.1',
                'expected': 'blocked', 'exitCode': result.returncode,
                'highSeverityVulnerabilities': sorted({v['name'] for v in high})}
    Path('reports/sca/gate-self-test.json').write_text(json.dumps(evidence, indent=2))
    print(f'SCA blocking self-test passed: vulnerable library rejected ({len(high)} high/critical findings).')
