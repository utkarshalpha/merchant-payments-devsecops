#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
keydir="$HOME/.cosign"
mkdir -p reports/signing
test -s reports/image.tar
export COSIGN_PASSWORD="$(cat "$keydir/password")"
# Private lab trust: explicit public key, no public transparency-log upload.
# This signs the scanned archive; registry digest signing is a later milestone.
cosign sign-blob --yes --key "$keydir/cosign.key" --signing-config "$keydir/signing-config.json" \
  --bundle reports/signing/image.bundle.json reports/image.tar
unset COSIGN_PASSWORD
cosign verify-blob --key "$keydir/cosign.pub" --bundle reports/signing/image.bundle.json \
  --insecure-ignore-tlog reports/image.tar
printf 'tampered image archive' > reports/signing/tampered-test.txt
if cosign verify-blob --key "$keydir/cosign.pub" --bundle reports/signing/image.bundle.json \
  --insecure-ignore-tlog reports/signing/tampered-test.txt > reports/signing/tamper-check.log 2>&1; then
  echo 'FAIL: tampered artifact accepted' >&2; exit 1
fi
grep -Ei 'digest|signature' reports/signing/tamper-check.log >/dev/null
rm reports/signing/tampered-test.txt
cp "$keydir/cosign.pub" reports/signing/cosign.pub
sha256sum reports/image.tar > reports/signing/image.sha256
printf '{"artifact":"image.tar","signatureVerified":true,"tamperedArtifactRejected":true,"trust":"local-key; no transparency log"}\n' > reports/signing/summary.json
echo 'PASS: scanned image archive signed and verified; tampered artifact rejected'
