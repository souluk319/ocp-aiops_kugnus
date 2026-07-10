# 회사 OCP 배포 Runbook

이 문서는 `cywell-aiops`를 회사 OCP에 등록, 설치, 재배포할 때 사용하는 저장소 전용 절차다.
실제 동작 기준은 항상 현재 `Taskfile.yml`, `scripts/kugnus-olm.sh`, `scripts/olm-deploy.sh`다.

## 명령 구분

| 명령 | 목적 | 서버 변경 |
|---|---|---|
| `task aiops:company:check` | 대상 서버와 로컬 OLM 패키지 확인 | 없음 |
| `task aiops:company:publish` | 이미지 빌드와 OperatorHub 카탈로그 등록 | 있음 |
| `task aiops:company:install` | Subscription과 AIOps 런타임 설치 | 있음 |
| `task aiops:company:redeploy` | 설치된 환경에 현재 코드를 다시 빌드·재시작 | 있음 |
| `task aiops:company:status` | 카탈로그, 설치, 런타임 상태 조회 | 없음 |

`publish`와 `install`은 별도 단계다. 카탈로그만 갱신할 때 `install`까지 실행하지 않는다.

## 현재 기본값

- 회사 API 서버: `https://api.ocp.cywell.server:6443`
- 패키지: `cywell-aiops`
- 카탈로그: `openshift-marketplace/cywell-aiops-catalog`
- 설치 및 런타임 namespace: `cywell-aiops`
- ConsolePlugin: `cywell-aiops-console-plugin`
- 스크립트 기본 Operator/CSV 버전: `0.1.10`

실제 배포 버전은 `KOMSCO_AIOPS_OPERATOR_VERSION`으로 바뀔 수 있다. 생성된 CSV 이름과
`task aiops:company:check` 출력으로 확인하며, Gateway 컨테이너의 별도 이미지 태그와 혼동하지 않는다.

## 0. 작업 위치와 대상 확인

```bash
git branch --show-current
git rev-parse --short HEAD
git status --short
oc whoami
oc whoami --show-server
```

확인 기준:

- 배포할 branch와 commit SHA를 기록한다.
- 의도하지 않은 작업트리 변경이 없어야 한다.
- `oc whoami --show-server`가 회사 API 서버와 정확히 같아야 한다.
- 다른 서버를 보고 있으면 회사용 Task가 중단되어야 정상이다.

## 1. 안전 확인

```bash
task aiops:company:check
```

이 명령은 다음 작업만 한다.

- 현재 `oc` 대상 서버가 회사 API 서버인지 확인한다.
- OLM bundle, catalog, install manifest를 로컬 `olm/generated/`에 생성한다.
- 생성된 package, CSV, AIOpsInstallation, ConsolePlugin 설정을 검증한다.

클러스터 리소스를 생성하거나 변경하지 않는다.

## 2. 최초 이미지 빌드와 카탈로그 등록

```bash
task aiops:company:publish
```

Task가 내부적으로 회사 서버를 다시 확인하고 다음 승인값을 적용한다.

```bash
KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY=openshift \
KOMSCO_AIOPS_FORCE_IMAGE_BUILD=true \
KOMSCO_AIOPS_APPROVE_PUBLISH=cywell-aiops \
./scripts/kugnus-olm.sh publish
```

현재 구현에서 발생하는 서버 변경:

- `cywell-aiops` namespace가 없으면 생성한다.
- Gateway와 Console Plugin용 ImageStream, BuildConfig, Build를 생성하거나 갱신한다.
- Gateway 이미지를 Operator 이미지로도 사용한다.
- `cywell-aiops` 내부 registry 이미지 pull 권한을 갱신한다.
- 현재 구현은 `system:serviceaccounts` 그룹에도 `cywell-aiops` 이미지 pull 권한을 부여한다.
- `openshift-marketplace`에 catalog ConfigMap과 `cywell-aiops-catalog` CatalogSource를 적용한다.
- 새 catalog 내용을 읽도록 기존 catalog Pod를 삭제하고 OLM이 재생성하게 한다.
- PackageManifest가 기대 CSV를 가리키는지 확인한다.

이 단계에서 하지 않는 작업:

- Subscription 설치
- AIOpsInstallation 설치
- Gateway, Console Plugin, Action Executor 런타임 설치
- 기존 보호 대상 `komsco-ai-console-plugin`, `lightspeed-console-plugin` 교체

## 3. 카탈로그 상태 확인

```bash
task aiops:company:status
```

최초 publish 직후에는 CatalogSource와 PackageManifest가 확인되어야 한다. 아직 install 전이면
Subscription, CSV, AIOpsInstallation, operand가 없는 것이 정상이다.

## 4. 승인 후 최초 설치

현재 스크립트 기본값은 `mode=execute`, `mutations=true`, `unrestrictedCommands=true`다.
읽기 전용 우선 배포를 원하면 기본값에 의존하지 말고 다음처럼 명시한다.

```bash
KOMSCO_AIOPS_MODE=evidence-check \
KOMSCO_AIOPS_ENABLE_MUTATIONS=false \
KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS=false \
task aiops:company:install
```

실행 가능 모드 설치는 정책과 승인 범위를 확인한 뒤 별도로 수행한다.

```bash
KOMSCO_AIOPS_MODE=execute \
KOMSCO_AIOPS_ENABLE_MUTATIONS=true \
KOMSCO_AIOPS_ENABLE_UNRESTRICTED_COMMANDS=false \
task aiops:company:install
task aiops:company:status
```

`unrestrictedCommands=true` 설치는 별도의 정책 승인 없이는 사용하지 않는다. 이 Runbook은 임의 명령 실행을
일반 설치 절차로 오인하지 않도록 unrestricted 설치 명령 예시를 제공하지 않는다.

설치 단계에서 생성·연결되는 주요 리소스:

- namespace와 OperatorGroup
- Subscription과 OLM이 생성하는 CSV
- `cywell-aiops-operator` Deployment
- AIOpsInstallation
- Gateway와 Console Plugin 관련 Deployment와 Service
- Action Executor 관련 리소스는 `mutations=true`일 때 생성·검증한다.
- Host Diagnostics 관련 리소스는 `diagnostics=true`일 때 생성·검증한다.
- ServiceAccount, Role, RoleBinding, ClusterRole, ClusterRoleBinding, NetworkPolicy
- cluster-scoped ConsolePlugin과 OpenShift Console plugin 설정

설치 후 `task aiops:company:status`에서 CatalogSource, PackageManifest, Subscription, CSV,
AIOpsInstallation, ConsolePlugin, operand Deployment와 Service를 확인한다.

## 5. 기설치 환경에 현재 코드 재배포

이미 설치가 끝난 회사 환경에 코드 변경을 반영할 때 사용한다.

```bash
KOMSCO_AIOPS_APPROVE_REDEPLOY=cywell-aiops \
task aiops:company:redeploy
```

이 명령은 다음 순서로 동작한다.

1. 현재 Gateway와 Console Plugin 이미지를 다시 빌드한다.
2. 카탈로그를 갱신한다.
3. Operator, Console Plugin, Gateway Deployment를 순서대로 재시작한다.
4. 각 rollout 완료와 최종 클러스터 상태를 확인한다.

기설치 환경의 코드 반영에는 `publish`만 실행하고 끝내지 않는다. 같은 이미지 태그를 다시 빌드해도
기존 Pod는 자동으로 교체되지 않을 수 있으므로 승인된 `redeploy` 흐름으로 rollout을 확인한다.

## 6. 기존 이미지 재사용

이미지를 새로 빌드하지 않고 동일한 ImageStreamTag를 재사용할 때만 사용한다.

```bash
KOMSCO_AIOPS_FORCE_IMAGE_BUILD=false task aiops:company:publish
```

코드가 변경되었다면 기존 이미지를 재사용하면 안 된다.

## 실패 시 먼저 확인할 곳

```bash
task aiops:company:status
oc get builds -n cywell-aiops
oc get pods -n cywell-aiops
oc get catalogsource cywell-aiops-catalog -n openshift-marketplace
oc get subscription,csv -n cywell-aiops
```

같은 실패 명령을 반복하기 전에 Build, CatalogSource, Subscription/CSV, Operator, operand 중
어느 단계가 실패했는지 먼저 구분한다.

## 코드 기준 위치

- 짧은 Task 명령: `Taskfile.yml`
- 회사 서버 및 승인 차단: `scripts/kugnus-olm.sh`
- OLM package/catalog/install/status: `scripts/olm-deploy.sh`
- 상세 참고: `docs/Ver.0.1.0/deployment-runbook.md`
