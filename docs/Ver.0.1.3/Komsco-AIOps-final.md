## 1. 추진 방향 및 핵심 아키텍처 전략

기존 OpenShift(OCP) 환경을 보존하면서 OpenShift Lightspeed의 기능을 사내 환경(RAG, Agent, 보안)에 맞게 통합하는 것이 주요 방향이야. OpenShift Console의 공식 확장 방식을 준수해 신규 Plugin과 AI Gateway로 OCP 네이티브 환경에 자연스럽게 녹아드는 아키텍처를 구현하고 있어.

| 구분 | 수행 방안 | 기대 효과 |
| :--- | :--- | :--- |
| **기존 UI 처리** | Console Operator로 기존 Lightspeed plugin 비활성화 | 충돌 방지 및 단일 진입점 확보 |
| **API 활용** | Lightspeed REST API 연동 유지 | 성능 및 답변 품질 보장 |
| **신규 UI 개발** | Dynamic Console Plugin 기반 자체 UI 개발 | OCP 네이티브 UX 제공 및 확장성 확보 |
| **Gateway 구축** | RAG, Agent Tool, 보안/감사를 전담하는 AI Gateway 배치 | 권한 통제(RBAC) 및 보안성 강화 |

* AI Gateway를 통해 RAG 연동, 감사로그 적재 및 민감정보 필터링을 수행하여 인증과 보안 측면에서 안정적인 통합을 제공해.

---

## 2. 목표 아키텍처 및 데이터 흐름

전체적인 흐름은 AIOps Agentic Model 기반의 End-to-End 연동 구조를 채택하고 있어. 사용자의 질문은 플러그인과 AI Gateway를 거쳐 안전하게 Lightspeed API로 스트리밍돼.

* **진입 통제:** OpenShift UserToken 기반 인증을 거치며, 권한 미달 시 AI Gateway 진입 단계에서 원천 차단해.
* **AIOps Agentic Model:** 특화 모델이 질문의 대상 환경(Linux/Windows/OCP)을 판단하고 Tool Plan JSON을 생성해 증적(Evidence) 기반의 장애 원인 분석(RCA)을 수행해.
* **Tool Adapter 변환:** 모델이 추상화된 Tool Plan을 내리면, 환경에 맞는 실제 조회 명령으로 변환하여 안전하게 실행해.
* **안전한 연동:** 민감정보를 제거하고 감사로그를 기록한 뒤 최종 답변을 제공하는 안전한 흐름이야.

---

## 3. AIOps 모델 적용 전략 및 라인업 비교

AI 모델은 운영 명령을 직접 실행하지 않고, 질문에 맞게 도구를 계획하고 원인을 분석하는 핵심 역할을 맡아. 

* **주요 모듈 역할:** OS Context Classifier가 환경을 판단하고, Tool Router가 필요한 조회 도구를 선택해. Evidence Planner가 증적 수집 순서를 계획하며, Safety Guard는 위험 명령(delete, patch 등)을 차단하지.

도입 목적에 따른 최적의 단일 모델을 선정하기 위해 라인업을 비교한 내용도 있어.

| 비교 항목 | Qwen3.6-27B | Gemma 4 26B A4B | 권장 역할 및 특징 |
| :--- | :--- | :--- | :--- |
| **모델 성격** | Agentic Coding, 복합 Reasoning 강조 | 고효율 추론, Function Calling, 빠른 Triage | 깊은 Tool Reasoning은 Qwen, 속도 효율은 Gemma |
| **구조/비용** | 27B 전체 파라미터 활성화 | MoE 구조 (토큰당 3.8B 활성화) | 장시간 복잡 추론은 Qwen, 대량 로그 요약은 Gemma |

* 정확한 RCA와 전문 추론이 우선이라면 Qwen을, 빠른 분류와 추론 효율성이 핵심이라면 Gemma를 선택하는 게 적합해.

---

## 4. OS별 도구 매핑 및 모델 학습 방식

동일한 장애 상황이라도 Linux, Windows, OCP 환경에 따라 알맞은 도구와 명령 체계를 선택하도록 설계되어 있어. 

* `read_tool`: Linux(cat, tail), Windows(Get-Content), OCP(oc get)
* `find_tool`: Linux(find), Windows(Get-ChildItem), OCP(label selector)
* `grep_tool`: Linux(grep), Windows(Select-String), OCP(log pattern search)

이러한 도구 선택과 RCA 생성을 고도화하기 위해 4단계 학습 방식을 제안해.
1. **SFT (지도학습):** 질문과 장애 상황, Tool Plan JSON 등을 학습.
2. **Preference Tuning:** 올바른 도구 선택과 잘못된 선택을 비교 학습.
3. **Safety Tuning:** 위험 명령 및 민감정보 접근 차단 학습.
4. **Continuous Learning:** 피드백과 검증 결과를 바탕으로 주기적 개선.

---

## 5. 단계별 구축 로드맵 및 하드웨어 구성 권장안

표준 운영 모델에 맞춰 안정적으로 구축하기 위한 5단계 로드맵이야.
1. 전용 Namespace 및 권한 경계 구성
2. AI Gateway 및 Plugin 이미지 빌드
3. Operator/OLM 카탈로그 패키징
4. CR 기반 자동 배포 및 Console 연동
5. UI 전환 및 운영 안정화

**GB10 2노드 모델 구성안**
* **1안 (혼합형 - 권장):** Mistral과 Gemma를 혼합 배치. 복합 RCA와 일반 질의 역할을 분리해서 품질과 속도의 균형이 우수해 가장 권장하는 운영안이야.
* **2안 (Active-Active):** Gemma 모델 2개를 배치해 고처리량과 무중단 장애 대응성이 필요할 때 병행 검토하기 좋아.
* **3안 (대형모델 결합):** 주력 서비스보다는 기술 시연이나 한계 검증 용도로만 제한적으로 권고해.

**RAG Vector DB 구성**
* Dell Pro Max GB10 단일 장비 환경을 고려할 때, 자원 사용량이 낮고 보안 통제가 용이한 **PostgreSQL + pgvector**를 기본 구성으로 권장하고 있어.