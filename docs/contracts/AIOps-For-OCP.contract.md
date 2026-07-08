# AIOps for OCP 최종 산출물 변환본

> 이 파일은 검색과 구현 확인을 위해 docs/AIOps-For-OCP.pdf를 Markdown으로 변환한 사본입니다.
> 원본 PDF가 공식 기준이며, 충돌 시 원본 PDF를 우선합니다.

- Source PDF: docs/AIOps-For-OCP.pdf
- Source SHA256: 193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5
- Converted At UTC: 2026-07-08T04:29:34+00:00
- Converter: pdfplumber text extraction

---

## Page 1

OpenShift Native
AIOps
with Lightspeed
OpenShift 운영을 위한
AI 기반 장애 분석·조치·감사 플랫폼
OpenShift Console, OpenShift Lightspeed, AI Gateway,
AIOps 관리포털을 결합해 운영자가 장애를 빠르게 파악하고, 증거
기반으로 원인을 분석하며, 승인된 조치와 감사 기록까지 연결하는
통합 운영 경험을 제공합니다.
AIOps for OCP

## Page 2

도입 배경: OpenShift 운영 환경의 과제
이슈 분석 및 보고 프로세스의 효율화와 보안/감사 체계 강화 필요성
⚠ 현재 운영 방식  AIOps 적용 후
다량의 알림 발생 시 핵심 이슈 식별 지연 의존성 기반 우선순위 식별
 
다수의 Alert 및 Event 중 서비스 영향도가 높은 주요 이슈를 선별하는 데 시 서비스 영향 지도와 RCA 센터를 통해 근본 원인과 파생 이슈를 명확히 구분
간 소요 하여 제시
분산된 모니터링 채널로 인한 분석 복잡성
 단일 진입점에서의 통합 분석

다양한 지표(Pod, Node, Event, Metric 등)를 개별 콘솔 및 도구에서 확인
OpenShift Console 내 AI Assistant와 대시보드에서 모든 지표와 로그를
해야 하는 번거로움
통합하여 증거 기반으로 분석
»
원인 분석(RCA) 및 보고서 작성의 수동화

RCA 증거 패키지 및 자동 보고서 생성

분석 결과를 문서화하고 감사 자료로 재구성하는 과정에서 업무 리소스 과다
수집된 증거와 분석 내역을 바탕으로 일일 운영 브리핑 및 RCA 보고서를 자
소모
동 산출
자동화 도입 시 보안 및 통제 체계 확보 필요

읽기 전용 기반, 승인/감사 통제형 조치

명확한 권한 제어(RBAC) 및 감사 기록 없이 운영 환경에 자동화 조치를 적용
하는 것에 대한 부담 AI는 제안만 하고, 운영자 승인 후 Action Executor가 제한된 조치만 수행하
며 모든 내역을 감사 원장에 기록
"운영 자동화의 핵심은 운영자가 신속하고 안전하게 의사결정을 내릴 수 있도록 투명한 근거와 표준화된 절차를 제공하는 것입니다."

## Page 3

솔루션 개념: OpenShift + Lightspeed + AIOps
실시간 클러스터 관측, AI 지식, 그리고 운영 통제 체계의 결합
 OpenShif t 운영 대상 플랫폼, Console Plugin, RBAC, Operat or/OLM 배포 기반을 제공하는 핵심 인프라 환경
⚡ OpenShif t Light speed Pod, Node, Event , Met ric, Resource 등 실시간 클러스터 관측과 AI 응답 기반 제공 (사용자 토큰 범위의 읽기 전용 방향)
 AI Gat eway UserToken 경계, RBAC 검증, 민감정보 제거, 감사로그, RAG/Tool 연동을 담당하는 보안 및 라우팅 계층
 AIOps Port al 대시보드, RCA 센터, 서비스 맵, 실행 기록, 위키, 보고서, 설정 등을 단일 화면으로 통합
 Act ion/Audit Layer 승인 기반 조치, 실행 기록, 감사 원장, 보고서 산출을 지원하는 통제 및 이력 관리 계층
"Light speed가 실시간 OpenShif t 지식과 관측을 담당하고, AIOps 계층은 우리 조직의 Runbook, Evidence, 승인 정책, 감사 체계까지 확장합니

다."

## Page 4

목표 운영 경험: Detect → Ask → RCA → Approve → Report
단일 플랫폼 내에서 끊김 없이 이어지는 통합 장애 대응 프로세스
1 2 3 4 5 6
     
Det ect Ask Collect Evidence RCA Approve & Audit & Report
(상황 인지) (질의 및 요청) (증거 수집) (원인 분석) Execut e (감사 및 보고)
(승인 및 조치)
대시보드에서 클러스터 OpenShift Console에서 Lightspeed/MCP, 이벤트, 수집된 증거를 바탕으로 모든 실행 기록은 감사
Health Score, 이슈 큐, AI Assistant에게 현재 메트릭, 로그, RAG, 과거 원인 후보, 신뢰도, 서비스 위험 작업은 typed 원장에 저장되며, RCA 증거
주요 리소스 상태를 보고 있는 화면 기준으로 장애 증적 등 관련 데이터 영향 경로, Runbook Gate action으로 제안되며, 패키지 및 운영 브리핑 자동
직관적으로 확인 질문 자동 수집 제시 운영자 승인 후 안전하게 생성
실행
"이 플랫폼의 핵심은 단편적인 기능 제공이 아닌 통합된 운영 워크플로우입니다. 이슈 인지부터 원인 분석, 조치, 그리고 감사 보고까지 전 과정이 유기적으
로 연결됩니다."

## Page 5

OpenShift Native Integration: 3가지 제공 방식
Dynamic Console Plugin과 Operator/OLM을 활용한 네이티브 통합 구조
 Operat or/OLM Int egrat ion ↗ Applicat ion Launcher Int egrat ion  Console Navigat ion Ext ension
• Sof t ware Cat alog 등록 AI Operator를 • 우상단 콘솔링크 OpenShift Console 우측 상단 • 사이드바 메뉴 확장 좌측 Navigation 메뉴에 대시보드,
CRD/CSV/Bundle로 패키징하여 노출 Application Menu에 AIOps/Cyntra 등록 RCA 센터 등 AIOps 항목 추가
• OLM 기반 관리 Subscription, InstallPlan을 통한 설 • ConsoleLink 활용 ConsoleLink CR을 통해 서비스 • Dynamic Console Plugin: Plugin 활성화 시 자체
치 및 업그레이드 라이프사이클 관리 진입점(href)을 제공하여 빠른 접근 지원 UI 페이지가 Console에 네이티브하게 통합
• 자동 구성 AIOps CR 생성 시 Gateway, Plugin
Service, RBAC 자동 구성
"AIOps for OCP는 별도의 외부 포털이 아닌, OpenShift의 공식 확장 방식(OLM, ConsoleLink, Dynamic Plugin)을 준수하여 관리자에게 일관된 사용자 경험을 제공합니다."

## Page 6

목표 아키텍처 및 데이터 흐름
AIOps Agentic Model 기반의 End-to-End 연동 구조

RBAC 및 진입 통제
OpenShift UserToken 기반 인증. 권한 미달 시 AI Gateway 진입 단계에서 원
천 차단.

AIOps Agent ic Model
특화 모델이 질문의 OS Context를 판단하고, Tool Plan JSON을 생성하여
Evidence 기반 RCA Reasoning을 수행합니다.
✓ OS Context 판단 (Linux/Windows/OCP)
✓ Tool Plan JSON 생성
✓ 위험 작업 승인 여부 판단

OS-aware Tool Adapt er
모델이 추상화된 Tool Plan을 내리면, Linux / Windows / OpenShift 환경에 맞
는 실제 조회 명령으로 변환하여 안전하게 실행합니다.

안전한 Light speed 연동
민감정보(Secrets 등)를 제거하고 전 구간 감사로그를 적재한 뒤, Lightspeed
API를 통해 최종 RCA 및 조치 가이드를 Streaming 제공합니다.

## Page 7

Lightspeed + AI Gateway 연동 흐름
AIOps Model의 Tool Plan을 바탕으로 각자의 전문 영역을 조회하여 최종 답변으로 통합
 사용자 질문
↓
 AIOps Model
↓
 Tool Plan JSON 생성
 Tool Adapt er  OpenShif t Light speed / MCP
 Linux / Windows OS Adapter (OS 진단/이벤트)  현재 Pod 및 Resource 상태 조회
 Evidence API (과거 증적 및 장기 데이터)  현재 Kubernetes Event 조회
 사내 Runbook / SOP 연동 (RAG)  Alert Context 연동 및 Metric Query
↓
 RCA JSON 통합
↓
 Light speed API 최종 답변 스트리밍

## Page 8

AI Assistant: OpenShift Console 안의 운영 Copilot
현재 화면의 맥락을 이해하고 증거 기반으로 응답하는 전역 오버레이
 Console 전역 AI Assist ant 오버레이
OpenShif t Console의 어느 화면에서나 호출 가능한 전역 패널 형태로, 작업 맥락을
끊지 않고 AI의 지원을 받을 수 있습니다. 
Page Context 자동 인식
⚡ 상황 맞춤형 Quick Prompt 제공  AIOps Assistant
Node 상태, 최근 경고, 조치 절차, 승인 실행 등 현재 상황에 가장 적합한 질문과 액션
을 추천합니다.  Context: namespace=aiops-demo, kind=Deployment,
name=web-app
 투명한 진행 타임라인 표시 이 대상 재시작 가능한지 알려줘.
AI가 어떤 도구를 호출하고 어떤 증거를 확인했는지 타임라인으로 투명하게 표시하여
현재 보고 계신 aiops-demo 네임스페이스의 web-app
신뢰성을 제공합니다.
Deployment 상태를 확인했습니다. 현재 가용 Replica가 부
족하여 재시작 시 서비스 영향이 있을 수 있습니다. 상세 증거
를 확인하시겠습니까?
 운영 대화 편의 기능
이미지 첨부, 코드 블록 복사, 표 렌더링 등 복잡한 운영 데이터를 쉽게 이해하고 다룰
수 있는 기능을 제공합니다. "운영자가 특정 화면에서 대명사로 질문해도, Assistant는 현재 화면의
namespace와 resource를 context로 추출하여 정확하게 분석합니
다."

## Page 9

운영 대시보드: 상황 인지와 이슈 진입점
클러스터 전반의 상태를 한눈에 파악하고 상세 분석으로 이어지는 운영 허브
 시스템 건강도 및 KPI
Health Score, OpenShift 버전, 최근 업데이트 시간을 상단
에 배치하고 즉시 확인이 필요한 이슈 건수를 한눈에 파악할 수
있습니다.
 서비스 영향 지도
Route → Service → Workload → Pod → Node/PVC로
이어지는 의존성 관계를 시각화하여 장애의 파급 범위를 직관
적으로 인지합니다.
 리소스 요약 및 이슈 큐
Pod, Deployment 등 리소스의 정상/비정상 상태를 요약하
고, 이슈 큐와 알림 목록에서 클릭 한 번으로 RCA 센터로 진입
합니다.
"대시보드는 단순 숫자판이 아니라 다음 행동으로 이동하는 운
영 허브입니다. Healt h Score를 보고 끝나는 것이 아니라,
이슈 큐와 서비스 맵을 통해 RCA로 바로 진입합니다."

## Page 10

RCA 센터와 서비스 맵: 증거 기반 원인 분석
AI의 분석 결과를 뒷받침하는 명확한 증거와 리소스 간의 의존성 추적
 RCA 센터  서비스 맵
원인 후보를 단순히 텍스트로 제시하는 것을 넘어, 분석에 사용된 출처, 필드, 상태, 실행 명령 Route부터 PVC까지 이어지는 리소스 관계 토폴로지를 시각화하여, 장애의 근본 원인과 파생
을 투명하게 공개합니다. 된 영향 범위를 추적합니다.
핵심 증거 패키지 (Evidence Package) 및 Runbook Gate 제공 핵심 의존성 기반 영향 경로 (Impact Path) 시각화
"운영자가 신뢰하는 RCA는 ‘AI가 그렇게 말했다’가 아니라 ‘어떤 이벤트, 어떤 메트릭, 어떤 리소스 관계가 그 결론을 뒷받침하는가’로 설명되어야 합니다."

## Page 11

안전한 조치: Read-only 우선, 승인 기반 실행
AI의 제안을 정책과 승인자가 검증하고 제한된 조치만 수행하는 통제 환경
조치 통제 및 보안 원칙
• 기본 관측은 UserToken 및 RBAC 범위 내의 읽기 전용으로 수행
• 위험 작업은 자연어 명령을 바로 실행하지 않고 Act ion Proposal로 변환
• Action Executor는 별도 ServiceAccount와 Typed Act ion만 사용
• 지원 조치 예 Deployment rollout restart, 안전 범위 내 scale 조절 등
• Arbitrary shell, generic patch 등 임의 조작은 원천 차단
승인 기반 실행 추적 흐름
1. 사용자 요청 (User Request )
↓
2. 조치 제안 (Act ion Proposal)
↓
3. 계획 봉인 (Sealed Act ion Plan)
↓
4. 승인 결정 (Approval Decision)
↓
5. 실행 권한 부여 (Execut ion Grant )
↓
"AI가 클러스터를 마음대로 바꾸지 않습니다. AI는 제안하고, 정책과 승인자가 검증하며,
실행기는 제한된 조치만 수행합니다." 6. 실행 및 기록 (Execut ion Record)

## Page 12

AIOps Lightspeed: 서비스 점검 및 원클릭 조치
멀티비전(Multi-vision) 기반 직관적 질의부터 검증된 조치 실행까지의 통합 워크플로우
 1. 멀티비전(Mult i-vision) 기반 직관적 질의 "이미지 첨부로 원인 분석"  3. 검증된 조치 계획 생성 및 원클릭 실행 "안전한 자동 복구"
→
 2. 자연어 기반 서비스 상태 점검 "장애 파드 점검 요청"

## Page 13

Runbook/RAG, 감사, 보고서: 운영 지식의 폐쇄 루프
내부 지식과 장애 이력이 다시 AI의 판단 기준으로 반영되는 선순환 체계
 위키 문서 관리 (Runbook/SOP)  운영 보고서 산출
     
〉 〉 〉 〉 〉
Runbook 검색 품질 정책 및 RCA 및 감사 및 품질 개선 및
등록 테스트 권한 배포 조치 수행 승인 검토 피드백 반영
• Runbook/SOP 관리 문서 등록, 임베딩 생성 및 검색 • 정책 관리 Namespace·그룹별 Tool 정책과 위험 작업
품질 테스트 지원 승인 기준 배포
• 감사 추적 사용자 질문, Tool Plan, Evidence, 최종 • 보고서 생성 일일 운영 브리핑, RCA 증거 패키지, 월간 "운영 AI는 한 번 구축하고 끝나는 시스템이 아닙니
RCA 감사로그 영구 보존 용량 리포트 산출
다. 조직의 Runbook, 승인 기준, 장애 이력, 품질
피드백이 계속 반영되어야 합니다."
• 지식 자산화 승인/거절 이력과 피드백을 다음 프롬프트
및 정책 버전에 반영

## Page 14

제품 로드맵: AIOps for OCP의 진화
관측과 제안에서 시작하여, 통제된 자동 조치와 예측형 운영으로 발전
v1.0 (현재) v2.0 (Next) v3.0 (Future)
Read-only Observability & Controlled Action & Audit Predictive Ops & Auto-
RCA remediation
AI의 제안을 정책과 승인 절차를 통해 안전하게 실행
하고 기록하는 통제 단계
클러스터의 상태를 읽고 분석하여 운영자에게 명확 장애 발생 전 예측하고, 승인된 패턴에 대해서는 자
한 원인과 증거를 제시하는 단계 율적으로 복구하는 고도화 단계
✓ Action Proposal 및 Sealed Action Plan
✓ Console 통합 AI Assistant 오버레이 ✓ 위험 작업에 대한 다단계 승인 워크플로우 ✓ 시계열 메트릭 기반의 이상 징후 및 장애 예측
✓ 통합 대시보드 및 서비스 영향 지도 ✓ 제한된 Typed Action을 수행하는 Action ✓ 사전 정의된 패턴에 대한 자율 복구(Auto-
〉 Executor 〉 remediation) 파이프라인
✓ 증거 기반 RCA 센터 및 Evidence Package
✓ 조치 실행 내역의 감사 원장(Audit Ledger) 기 ✓ 클러스터 리소스 및 비용 최적화 제안
✓ 위키 기반 Runbook RAG 연동
록
✓ LLM 기반의 자동 정책(Policy) 생성 및 시뮬레
✓ 사용자 권한(RBAC) 기반의 읽기 전용 접근
✓ 일일/월간 자동 운영 보고서 산출 이션
✓ 멀티 클러스터 통합 관제 및 글로벌 RCA
목표 장애 인지 및 분석 시간(MTTR) 50% 단 목표 안전한 조치 환경 확보 및 감사 대응 비용 목표 무중단 서비스 환경을 향한 자율 운영
축 최소화 (Aut onomous Ops)

## Page 15

[Appendix A] RAG를 넘어선 Agentic Model (Tool Use)
단순 문서 검색이 아닌, 실시간 API를 호출하여 증거를 수집하는 능동적 AI
Agent ic Model의 필요성  Tool Use Execut ion Flow
클러스터 장애는 정적인 문서에 답이 있지 않습니다. 현재의 상태, 로그, 메트릭
을 직접 확인해야만 정확한 원인을 파악할 수 있습니다. AIOps Assist ant 는
1. 사용자 질문 (예 "Web-app이 왜 죽었어?")
LLM이 직접 도구(Tool)를 선택하고 실행하여 실시간 데이터를 수집하는
↓
Agent ic Archit ect ure를 채택했습니다.
 LLM (Reasoning & Rout ing)
Agent ic Model (Tool ↓
구분 전통적 RAG (검색 기반)
Use)
2. 필요한 도구 선택 및 파라미터 생성
사전 학습된 지식, 위키, 매 실시간 API, 메트릭, 로그, 이
데이터 소스 뉴얼 등 정적 텍스트 벤트 등 동적 데이터  Get Event s  Query Met rics  Fet ch Logs
↓
목적에 맞는 Tool을 선택하
질문과 유사한 문서를 DB에
동작 방식 고 파라미터를 생성하여 직접
3. API 호출 및 데이터 수집
서 검색하여 요약
실행
 OpenShif t Clust er (API Server /
"현재 Node A의 네트워크
"이 에러 메시지는 보통 네트
Promet heus)
운영 적용 패킷 드랍이 5분 전부터 증가
워크 문제입니다." (일반론)
했습니다." (팩트 기반)
↺ 4. 수집된 데이터를 바탕으로 최종 분석 답변 생성

## Page 16

[Appendix B] AIOps Portal 관리 기능 범위
단일 클러스터를 넘어 멀티 클러스터와 다양한 LLM 모델을 수용하는 확장성
 정책 및 프롬프트 관리  알림 및 이슈 큐 연동  외부 엔드포인트 연동
• 시스템 전역 동작 파라미터 설정 • OpenShift Alertmanager 웹훅 수신 및 파싱 • 다양한 LLM Provider (OpenAI, Azure, Local LLM)
API Key 및 모델 매핑
• 역할(Role)별 시스템 프롬프트 템플릿 버전 관리 • 알림 심각도 기반의 자동 이슈 큐(Issue Queue) 생성
• 멀티 클러스터 관제를 위한 타 클러스터 API 접속 토큰
• 위험 명령어 및 Action Tool 사용 권한 제어 • Slack, Teams 등 외부 메신저로 RCA 요약본 발송 설
관리
정
• 감사 로그 보존 주기 및 데이터 마스킹 정책 설정
• 외부 ITSM (Jira, ServiceNow 등) 티켓 생성 연동
• 반복되는 알림에 대한 그룹핑(Grouping) 룰 관리
• 사내 위키(Confluence 등) RAG 데이터 소스 연결
