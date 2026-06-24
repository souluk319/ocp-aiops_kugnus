require('ts-node/register/transpile-only');

const assert = require('node:assert/strict');
const {
  evidenceCount,
  redactSensitiveText,
  safeEvidenceText,
  shortDigest,
} = require('../src/utils/evidenceDisplay.ts');

const sensitiveInputs = [
  'Bearer sha256~abcDEF_1234567890',
  'sha256~eu4NmzgyGdszEPdrSy7L_NG4CsHhFfdB_I_L4Qjce7I',
  'subject admin kubeadmin operator@example.com',
  'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImlhdCI6MTIzNDU2Nzg5MH0.signaturePart',
  'github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop',
  'glpat-abcdefghijklmnopqrstuvwxyz1234567890',
  'sk-abcdefghijklmnopqrstuvwxyz1234567890',
  'api_key=shortsecret',
  'apiKey=shortsecret',
  'x-api-key: shortsecret',
  'token=shortsecret',
  'client_secret=\"shortsecret\"',
  'client-key-data: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t',
  'client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t',
  'certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t',
  'client-key-data: |\n  LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t\n  UHJpdmF0ZUtleUJvZHk=',
  'client-certificate-data: |\n  LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t\n  Q2VydGlmaWNhdGVCb2R5',
  'AKIAIOSFODNN7EXAMPLE',
  'opaque_token abcdefghijklmnop.qrstuvwxyzABCDEFGHIJKLMN/OPQRSTUVWXYZ1234567890',
];

const forbiddenPatterns = [
  /Bearer\s+[A-Za-z0-9._~+\/=-]+/i,
  /sha256~[A-Za-z0-9._~-]+/i,
  /\b(admin|kubeadmin)\b/i,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/,
  /\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}/,
  /\b(?:github_pat|gh[pousr]|glpat|sk|xox[baprs])-?[A-Za-z0-9_=-]{16,}\b/i,
  /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/,
  /\b(?:x[-_]?api[-_]?key|api[-_]?key|apiKey|token|client[-_]?secret|client[-_]?key[-_]?data|client[-_]?certificate[-_]?data|certificate[-_]?authority[-_]?data)\s*[:=]\s*(?!\[redacted-secret\])["']?[^\s,"'`<>]+/i,
  /\bLS0tLS1CRUdJTiB(?:QUklWQVRFIEtFWS|Q0VSVElGSUNBVEU)[A-Za-z0-9+/=]*\b/,
  /\b(?=[A-Za-z0-9._~+\/=-]{40,}\b)(?=.*[._~+\/=-])[A-Za-z0-9._~+\/=-]+\b/,
];

for (const input of sensitiveInputs) {
  const output = safeEvidenceText(input);
  for (const pattern of forbiddenPatterns) {
    assert.equal(
      pattern.test(output),
      false,
      `redaction missed ${pattern} for output: ${output}`,
    );
  }
}

const sensitiveClipboardBody = [
  '정리 결과입니다.',
  '```bash',
  'export TOKEN=shortsecret',
  'curl -H "Authorization: Bearer sha256~abcDEF_1234567890" https://api.example.invalid',
  'x-api-key: shortsecret',
  'client-key-data: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t',
  'client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t',
  'client-key-data: |',
  '  LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t',
  '  UHJpdmF0ZUtleUJvZHk=',
  'user admin kubeadmin operator@example.com',
  'aws_access_key_id=AKIAIOSFODNN7EXAMPLE',
  '```',
  '마지막 안전 문장은 보존되어야 합니다.',
].join('\n');
const redactedClipboardBody = redactSensitiveText(sensitiveClipboardBody);
for (const pattern of forbiddenPatterns) {
  assert.equal(
    pattern.test(redactedClipboardBody),
    false,
    `clipboard redaction missed ${pattern} for output: ${redactedClipboardBody}`,
  );
}
assert.ok(redactedClipboardBody.includes('마지막 안전 문장은 보존되어야 합니다.'));

assert.equal(safeEvidenceText('Pod 개수 직접 조회 완료'), 'Pod 개수 직접 조회 완료');
assert.equal(redactSensitiveText('Pod 개수 직접 조회 완료'), 'Pod 개수 직접 조회 완료');
assert.equal(shortDigest('sha256:1234567890abcdef9999'), 'sha256:1234567890ab');
assert.equal(evidenceCount(0, 2, 1), 2);
assert.equal(evidenceCount(3, 0, 0), 3);

console.log('PASS evidence display redaction probes');
