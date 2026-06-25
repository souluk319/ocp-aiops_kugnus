## [cite_start]Evidence 기반 AI 장애 분석 시나리오 [cite: 164]

[cite_start]사용자 질문에 대해 AI Gateway가 과거 증적(Evidence) 기반 RCA(장애 원인 분석)를 수행하는 전체 흐름이야[cite: 165].

[cite_start]**💬 사용자 질문 예시 (Chat UI):** "어제 새벽에 default namespace Pod가 왜 재시작됐어?" [cite: 166, 167]

### [cite_start]1단계: Agentic Tool Plan 생성 [cite: 168]
* [cite_start]**OS/OCP Context 판단:** 특화 모델이 질문을 분석하여 OpenShift Pod 재시작 RCA 질의로 분류해[cite: 169, 170].
* [cite_start]**Tool Plan JSON 생성:** 분석에 필요한 `event_tool`, `grep_tool`, `metric_tool`, `snapshot_tool`을 선택해[cite: 171, 172].
* [cite_start]**Tool Adapter 실행:** 선택된 도구를 실제 환경에 맞는 명령으로 변환하여 안전하게 실행해[cite: 173, 174, 175].

### [cite_start]2단계: Evidence 기반 다각도 분석 [cite: 176]
* [cite_start]**과거 이벤트 조회:** 해당 시간대 Pod Event, Killing, OOMKilled, Eviction 등을 확인해[cite: 177, 178].
* [cite_start]**과거 로그 분석:** 재시작 전후 Container Log에서 OOM 등 오류 패턴을 추출해[cite: 179, 180].
* [cite_start]**장기 메트릭 분석:** CPU 및 Memory 사용량, Node Pressure, Restart 추세를 확인해[cite: 181, 182].

### [cite_start]3단계: Context 구조화 및 Lightspeed 연동 [cite: 183]
* [cite_start]**RCA Context JSON 생성:** 수집된 증적, 원인 후보, 신뢰도, 조치 후보를 구조화해[cite: 184, 185, 186].
* [cite_start]**Lightspeed 기반 최종 분석:** RCA Context와 사내 Runbook을 OpenShift Lightspeed에 전달하여 최종 답변을 생성해[cite: 187, 188, 189].
* [cite_start]**최종 답변 제공:** RCA, 즉시 조치, 재발 방지책, 참고 증적을 Chat UI에 깔끔하게 제공해[cite: 190, 191].