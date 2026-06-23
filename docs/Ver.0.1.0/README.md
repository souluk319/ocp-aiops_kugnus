# Ver.0.1.0 Kugnus AIOps 구축 방향

작성 기준일: 2026-06-24 KST

## 현재 판단

Ver.0.1.0의 기준 문서는 `OpenShift_Lightspeed_커스터마이징_구축_수행_방안.pdf`다. 이 문서의 결론은 OpenShift Lightspeed를 새로 대체 설치하는 것이 아니라, 기존 OpenShift 환경과 Lightspeed 기능을 보존하면서 KOMSCO AI Gateway, Dynamic Console Plugin, Operator/OLM 배포 모델을 얹는 것이다.

이번 단계의 기본 완료 목표는 **Kugnus 전용 OperatorHub/OLM 카탈로그 카드가 보이고, Install을 누르면 자동 배포될 수 있는 패키지까지 준비하는 것**이다. 실제 `Subscription` 설치와 `AIOpsInstallation` 생성은 별도 승인 단계로 둔다.

회사 OCP에는 이미 다음 공용 리소스가 있다.

| 구분 | 현재 상태 | Ver.0.1.0 기준 |
| :--- | :--- | :--- |
| Lightspeed | `openshift-lightspeed` namespace와 app/plugin/operator/postgres가 Running | 재설치하지 않음 |
| 공용 KOMSCO plugin | `ConsolePlugin/komsco-ai-console-plugin` 존재 | 덮어쓰지 않음 |
| 공용 catalog | `komsco-aiops`, `komsco-aiops-jk` PackageManifest 존재 | Kugnus 이름으로 분리 |
| 개인 후보 namespace | `komsco-ai-kugnus` 존재, runtime 미설치 | AIOps는 `komsco-ai-kugnus` 사용 |
| Kugnus catalog | `komsco-aiops-catalog-kugnus` 등록됨 | PackageManifest 확인 대상 |

## 목표 아키텍처

PDF의 목표 구조를 Ver.0.1.0 repo 작업으로 매핑하면 다음과 같다.

```text
OpenShift Console
  -> KOMSCO Dynamic Console Plugin
  -> ConsolePlugin proxy with UserToken
  -> KOMSCO AI Gateway
  -> Agentic Tool Plan / Evidence / Safety Guard
  -> OpenShift Lightspeed streaming_query
  -> Chat UI and AIOps dashboard
```

핵심은 역할 분리다.

| 구성요소 | 역할 |
| :--- | :--- |
| Dynamic Console Plugin | OpenShift 콘솔 안의 Cywell AI UI, Chat, Dashboard |
| AI Gateway | UserToken 전달, RBAC/민감정보/감사로그, Evidence/RAG/Tool Plan 구조화 |
| Lightspeed | OpenShift 기반 최종 RCA 답변과 MCP/RAG 역량 |
| Operator | `AIOpsInstallation` CR을 받아 Gateway, Plugin, ConsolePlugin, RBAC, Service CA를 자동 구성 |
| OLM CatalogSource | Software Catalog/OperatorHub에 설치 항목 노출 |

## Kugnus 전용 이름 기준

기존 공용 리소스를 덮어쓰지 않기 위해 Ver.0.1.0은 다음 이름을 기본값으로 사용한다.

| 구분 | 값 |
| :--- | :--- |
| PackageManifest | `komsco-aiops-kugnus` |
| CatalogSource | `komsco-aiops-catalog-kugnus` |
| Operator namespace | `komsco-ai-kugnus` |
| Operand namespace | `komsco-ai-kugnus` |
| ConsolePlugin | `komsco-ai-console-plugin-kugnus` |
| Console route base | `/aiops-kugnus` |
| Catalog display | `Cywell AI` |
| Catalog icon | `docs/Ver.0.1.0/design-assets/K_icon.png` |
| Assistant product title | `Cywell AI` |
| Assistant toggle mark | `docs/Ver.0.1.0/design-assets/K_icon.png` |
| Chat header logo | `docs/Ver.0.1.0/design-assets/komsco_logo.svg` |

중요: `ConsolePlugin`은 cluster-scoped 리소스다. namespace만 분리해도 `metadata.name`이 같으면 기존 공용 plugin을 덮어쓸 수 있다. 따라서 Kugnus 배포는 반드시 `komsco-ai-console-plugin-kugnus`를 사용한다.

## PDF 요구사항 추적표

| PDF page | 요구사항 | Ver.0.1.0 구현/산출물 |
| :--- | :--- | :--- |
| 1 | 기존 OpenShift 보존, Lightspeed REST 유지, 신규 Plugin/Gateway 구축 | 기존 Lightspeed/공용 plugin 미변경, Kugnus 전용 OLM 패키지 |
| 2 | UserToken RBAC, Agentic Model, Tool Adapter, 안전한 Lightspeed 연동 | Gateway proxy UserToken, safety contract, read-only 기본값 |
| 3 | Tool Plan, OS Adapter, Evidence API, Runbook/RAG, Lightspeed 통합 | Dashboard와 Gateway status에 Tool/Evidence 상태 표시 |
| 4 | OS Context, Tool Router, Evidence Planner, RCA Reasoner, Safety Guard | `AIOpsInstallation`와 Gateway 계약 문서화, 위험 작업 차단 |
| 5 | AIOps 모델 선정 근거 | Ver.0.1.0은 모델 학습이 아니라 Tool Plan/RCA JSON 인터페이스 준비 |
| 6 | OS-aware Tool Reasoning 구조 | Linux/Windows/OpenShift Adapter 개념을 dashboard-design-brief에 반영 |
| 7 | 학습/고도화 데이터 전략 | 감사로그, Evidence, Runbook, Tool 결과를 향후 학습 데이터 후보로 정의 |
| 8 | Tool Plan JSON, RCA Context JSON 표준화 | Gateway safety/evidence contract와 UI 상태 카드로 노출 |
| 9 | Evidence 기반 장애 분석 시나리오 | Cluster/Event/Metric/Audit 기반 read-only 챗봇 동작을 우선 검증 |
| 10 | Namespace/RBAC/Image/OLM/CR/Console 전환 로드맵 | Kugnus OLM package, catalog publish, optional install task로 분리 |

## 작업 기준

기본 작업은 WSL에서 수행한다.

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
```

로컬 개발 확인:

```bash
AIOPS_GATEWAY_MODE=read-only task be:dev
INSTALL_DEPS=true task fe:dev
```

두 번째 실행부터는 의존성이 이미 있으므로 `task fe:dev`만 실행한다. WSL에서 Docker Desktop console container가 WSL Gateway에 붙어야 하는 경우 `host.docker.internal`이 Windows 쪽 다른 서비스로 향할 수 있으므로, Gateway를 `0.0.0.0`로 열고 WSL IP proxy endpoint를 사용한다.

Kugnus 카탈로그 준비:

```bash
task kugnus:package
```

Kugnus 카탈로그 등록:

```bash
KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY=openshift task kugnus:publish
```

회사 OCP 현재 환경에서는 Docker Desktop이 외부 image registry route
`default-route-openshift-image-registry.apps.ocp.cywell.server`를 직접 resolve하지 못할 수 있다.
따라서 Ver.0.1.0의 선호 publish 경로는 OpenShift `BuildConfig` binary build를 사용해
`komsco-ai-kugnus` 내부 ImageStream에 이미지를 넣는 방식이다. 이 방식은 기존 공용 plugin이나
Lightspeed runtime을 건드리지 않는다.

Kugnus 카탈로그 상태 확인:

```bash
task kugnus:status
```

선택 설치는 별도 승인 후에만 실행한다.

```bash
KOMSCO_AIOPS_APPROVE_INSTALL=komsco-ai-kugnus task kugnus:install
```

승인 env 없이 `task kugnus:install`을 실행하면 스크립트가 거부해야 정상이다.

## 하지 않을 것

Ver.0.1.0 기본 범위에서 다음을 실행하지 않는다.

```bash
task catalog:deploy
task catalog:release
task catalog:runtime:apply
task olm:deploy
task olm:release
task olm:install
scripts/enable-console-plugin.sh
```

다음도 하지 않는다.

- 기존 `ConsolePlugin/komsco-ai-console-plugin` 수정
- 기존 `ConsolePlugin/lightspeed-console-plugin` 제거
- 기존 console active plugin 목록에서 Lightspeed 제거
- `komsco-ai`, `komsco-ai-dev`, `komsco-ai-jk` runtime 교체
- CRC 결과를 회사 OCP 결과로 보고
- `.env`, kubeconfig, token, password, private key commit

## 완료 기준

| 항목 | Pass 기준 | Evidence |
| :--- | :--- | :--- |
| 문서 | PDF 기준 아키텍처, 로드맵, 금지선, 실행 순서가 0.1.0 문서에 있음 | README, runbook, design brief |
| 이름 분리 | Kugnus package/catalog/ConsolePlugin 이름이 기존 공용 값과 다름 | generated CSV/ConfigMap |
| 아이콘 | CSV icon이 `image/png`이고 `K_icon.png`와 SHA256 일치 | local verification |
| 빌드 | Gateway tests와 console plugin build 통과 | pytest, yarn build |
| UI 계약 | Cywell AI header/sidebar/fullscreen/resize 기본 동작이 깨지지 않음 | `task kugnus:ui:verify` |
| 카탈로그 | `komsco-aiops-kugnus` PackageManifest가 보임 | `oc get packagemanifest` |
| 안전 | 기존 공용 plugin과 Lightspeed가 변경되지 않음 | before/after `oc get consoleplugin`, console plugins |

## 2026-06-24 publish 결과

현재 Ver.0.1.0 publish는 다음 상태까지 완료됐다.

| 항목 | 결과 |
| :--- | :--- |
| Namespace | `komsco-ai-kugnus` exists |
| Gateway image | `komsco-ai-kugnus/komsco-ai-gateway:0.1.2` ImageStreamTag exists |
| Console plugin image | `komsco-ai-kugnus/komsco-ai-console-plugin:0.1.2` ImageStreamTag exists |
| CatalogSource | `openshift-marketplace/komsco-aiops-catalog-kugnus` exists, display `Cywell AI Kugnus Catalog`, state `READY` |
| PackageManifest | `komsco-aiops-kugnus` exists, currentCSV `komsco-aiops-kugnus-operator.v0.1.2` |
| Subscription | not created |
| CSV | not installed |
| AIOpsInstallation | not created |
| Kugnus ConsolePlugin | not created yet; install 단계에서 생성 |
| 기존 공용 ConsolePlugin | `komsco-ai-console-plugin` -> `komsco-ai/komsco-ai-console-plugin`, `lightspeed-console-plugin` -> `openshift-lightspeed/lightspeed-console-plugin` 유지 |
| UI 검증 | `task kugnus:ui:verify` 42 checks pass |
| Gateway 검증 | `.venv/bin/python -m pytest -q` 131 passed, 2 warnings |

## 다음 단계

1. PDF 기준 문서 세트와 Kugnus package/publish 변경분을 commit한다.
2. OpenShift Console의 OperatorHub 또는 Software Catalog에서 `Cywell AI` 카드 노출을 눈으로 확인한다.
3. 고도화 단계에서만 `KOMSCO_AIOPS_APPROVE_INSTALL=komsco-ai-kugnus task kugnus:install` 또는 콘솔 Install 버튼으로 read-only 챗봇 runtime을 설치한다.
4. 설치 전까지는 `Subscription`, `CSV`, `AIOpsInstallation`, `ConsolePlugin/komsco-ai-console-plugin-kugnus`가 없는 상태가 정상이다.
