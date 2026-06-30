# Ver.0.1.8 — PDF 요구사항 구조화 구현

## 버전 목표

`docs/Komsco_ai_agent_final.pdf` (요구사항 명세서)가 정의하는
**Tool Plan JSON → Evidence 수집 → RCA Context JSON** 흐름을
현재 구현에 맞춰 완성한다.

특히 Lightspeed 응답이 완료된 뒤 구조화된 **RCA 결과
(cause_candidates, confidence, action_candidates)** 가 누락되어 있던 부분을 채운다.

---

## 완료 기준

- [ ] `GET /v1/rca/last` → `rcaResult.cause_candidates` 비어 있지 않음
- [ ] `analysisPlan.evidenceCollectionSteps` — `evidence_refs`로 collected/failed 반영됨
- [ ] "journalctl 오류" 질문 → `task_type == "linux_service_diagnosis"`
- [ ] "windows event log" 질문 → `task_type == "windows_event_diagnosis"`
- [ ] `pytest -q` 전체 통과

---

## 구현 내용

### A — Post-answer RCA Result 추출

`komsco_ai_gateway/rca_result_parser.py` (신규)

Lightspeed 스트리밍이 완료된 후 답변 텍스트에서 원인/조치/신뢰도를 정규식으로 파싱한다.
`chat_stream()` 완료 직전에 `LAST_RCA_CONTEXT["rcaResult"]`로 삽입된다.

```json
{
  "cause_candidates": ["OOMKilled 감지 — 메모리 limit 초과"],
  "action_candidates": ["메모리 limit을 512Mi로 증가"],
  "confidence": 0.75,
  "evidence_types": ["openshift_event_lookup", "pod_status_evidence"],
  "extractedAt": "2026-06-29T06:00:00Z"
}
```

### B — `/v1/rca/last` API 엔드포인트

`main.py`에 `GET /v1/rca/last` 추가.
Bearer 토큰 필요. 최근 채팅의 Tool Plan + RCA Context + 결과를 JSON으로 반환.

```bash
curl -s -H "Authorization: Bearer <token>" http://localhost:18080/v1/rca/last | jq .rcaContext.rcaResult
```

### C — OS Context 분류 확장

`aiops_contracts.py`의 `build_runtime_tool_plan()`에 Linux/Windows 시나리오 추가.

| 키워드 예시 | task_type |
|---|---|
| journalctl, systemctl, dmesg | `linux_service_diagnosis` |
| windows, event log, get-winevent | `windows_event_diagnosis` |
| (기존) pod, restart, operator | OCP 시나리오 유지 |

실제 Linux/Windows 명령 실행은 0.1.9+.
0.1.8에서는 분류 + 런북 검색(runbook_tool) 라우팅까지만 구현.

---

## 범위 밖 (0.1.9+)

- Linux `journalctl`/`systemctl` 실제 명령 실행 어댑터
- Windows `Get-WinEvent`/`Get-Content` 실제 명령 실행 어댑터
- Prometheus/Thanos `metric_tool` 실제 구현
- KomscoAIAssistant CR 기반 자동 배포 (OLM 5단계)
- AIOps 전용 모델 파인튜닝 (SFT/QLoRA)
- Console Plugin RCA 결과 시각화 컴포넌트

---

## 검증 명령

```bash
# 1. 테스트 전체 통과 확인
task kugnus:dev:be:test

# 2. Gateway 실행
task kugnus:rag:dev:up
task kugnus:dev:be:execute:rag

# 3. 채팅 후 RCA 결과 확인
curl -s -H "Authorization: Bearer <oc-token>" \
  http://localhost:18080/v1/rca/last | jq '{
    task_type: .toolPlan.task_type,
    cause_candidates: .rcaContext.rcaResult.cause_candidates,
    confidence: .rcaContext.rcaResult.confidence
  }'
```
