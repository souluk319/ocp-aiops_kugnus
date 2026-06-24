# AIOps Scenario Evaluation Set

이 디렉터리는 Ver.0.1.1 Stage 8의 자동 평가 입력이다.
각 JSON 파일은 한국어 OpenShift 운영 질문 1개와 기대되는 contract/evidence/safety/answer 조건을 담는다.

평가 원칙:

- UI 눈대중이 아니라 `komsco_ai_gateway.aiops_contracts`의 실제 ToolPlan, RcaContext, SafetyContract를 호출한다.
- OpenShift 회사 서버, CRC, LLM endpoint, `.env`, kubeconfig를 읽지 않는다.
- 모든 시나리오는 read-only safety contract를 기본값으로 검증한다.
- evidence 없이 원인을 단정하거나 schema가 깨지면 실패해야 한다.

실행:

```bash
task kugnus:evaluate
```

기본 report:

```text
.tmp-aiops-evaluation-report.json
```
