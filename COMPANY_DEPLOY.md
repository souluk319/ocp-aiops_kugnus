# 회사 OCP 배포 Runbook

이 문서는 `cywell-aiops`를 회사 OCP에 등록, 설치, 재배포할 때 사용하는 저장소 전용 절차다.
실제 동작 기준은 항상 현재 `Taskfile.yml`, `scripts/kugnus-olm.sh`, `scripts/olm-deploy.sh`다.

## 명령 구분

| 명령 | 목적 | 서버 변경 |
|---|---|---|
| `task aiops:company:check` | 대상 서버와 로컬 OLM 패키지 확인 | 없음 |
| `task aiops:company:publish` | 이미지 빌드와 OperatorHub 카탈로그 등록 | 있음 |
| `task aiops:company:install` | Manual Subscription을 만들고 InstallPlan 검토 대기 | 있음 |
| `task aiops:company:approve-install` | 검토한 InstallPlan 승인 후 AIOps 런타임 설치 | 있음 |
| `KOMSCO_AIOPS_APPROVE_ROLLBACK=cywell-aiops task aiops:company:rollback` | 검증된 `/tmp` 백업으로 직전 배포 복구 | 있음 |
| `task aiops:company:redeploy` | 설치된 환경에 현재 코드를 다시 빌드·재시작 | 있음 |
| `task aiops:company:status` | 카탈로그, 설치, 런타임 상태 조회 | 없음 |

`publish`와 `install`은 별도 단계다. 카탈로그만 갱신할 때 `install`까지 실행하지 않는다.

## 현재 기본값

- 회사 API 서버: `https://api.ocp.cywell.server:6443`
- 패키지: `cywell-aiops`
- 카탈로그: `openshift-marketplace/cywell-aiops-catalog`
- 설치 및 런타임 namespace: `cywell-aiops`
- ConsolePlugin: `cywell-aiops-console-plugin`
- 스크립트 기본 Operator/CSV 버전: `0.1.17`
- 이전 CSV: `cywell-aiops-operator.v0.1.14`
- 기본 InstallPlan 승인: `Manual`
- 기본 실행 모드: `evidence-check`
- 독립 포털: `https://aiops.cywell.co.kr`
- 승인 TLS Secret: `cywell-aiops/cywell-aiops-route-tls`

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
- 다른 namespace의 AIOpsInstallation, Subscription, Operator Deployment가 없는지 확인한다.
- OLM bundle, catalog, install manifest를 로컬 `olm/generated/`에 생성한다.
- 생성된 package, CSV, AIOpsInstallation, ConsolePlugin, 독립 포털 설정을 검증한다.

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
- Gateway, Console Plugin, 독립 포털용 ImageStream, BuildConfig, Build를 생성하거나 갱신한다.
- Gateway 이미지를 Operator 이미지로도 사용한다.
- `cywell-aiops` 내부 registry 이미지 pull 권한을 갱신한다.
- 이미지 pull 권한은 `cywell-aiops` namespace의 ServiceAccount 그룹에만 부여한다.
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

## 4. 설치 전 인프라 자산 확인

독립 포털 Route는 승인된 회사 인증서를 Secret에서 읽는다. 인증서와 개인 키는 Git이나
`AIOpsInstallation` CR에 넣지 않는다.

```bash
oc get secret cywell-aiops-route-tls -n cywell-aiops
```

정상 기준:

- Secret type은 `kubernetes.io/tls`다.
- `tls.crt`, `tls.key`가 있다.
- 사설 CA 체인이 필요하면 `ca.crt`도 있다.
- Secret 내용은 터미널이나 로그에 출력하지 않는다.
- 재배포 전후 `aiops.cywell.co.kr` 인증서 fingerprint가 동일해야 한다.

## 5. Manual InstallPlan 생성

기본 설치는 읽기 전용이다. 별도 환경 변수 없이 다음 명령을 실행한다.

```bash
task aiops:company:install
```

이 단계는 Subscription을 만들고 OLM이 InstallPlan을 계산할 때까지 기다린다. InstallPlan은
`Manual` 상태이므로 아직 승인하지 않으며, `AIOpsInstallation` CR도 적용하지 않는다.

```bash
oc get installplan -n cywell-aiops
oc get installplan <INSTALL_PLAN_NAME> -n cywell-aiops -o yaml
```

검토 기준:

- CSV가 `cywell-aiops-operator.v0.1.17`이다.
- `replaces` 대상이 `cywell-aiops-operator.v0.1.14`다.
- 설치 namespace가 `cywell-aiops`다.
- 예상하지 않은 CRD, ClusterRole, 이미지가 없다.

## 6. 검토한 InstallPlan 승인과 런타임 설치

InstallPlan 검토 후에만 다음 명령을 실행한다.

```bash
task aiops:company:approve-install
task aiops:company:status
```

이 명령은 승인 대기 InstallPlan을 승인하고 CSV 성공을 확인한 뒤, 읽기 전용 기본값의
`AIOpsInstallation` CR을 적용한다.

- `mode=evidence-check`
- `mutations=false`
- `unrestrictedCommands=false`

실행 가능 모드는 정책과 승인 범위를 별도 검토한 뒤 CR을 명시적으로 변경한다.
`unrestrictedCommands=true`는 일반 설치 절차로 사용하지 않는다.

설치 단계에서 생성·연결되는 주요 리소스:

- namespace와 OperatorGroup
- Subscription과 OLM이 생성하는 CSV
- `cywell-aiops-operator` Deployment
- AIOpsInstallation
- Gateway와 Console Plugin 관련 Deployment와 Service
- 독립 포털 Deployment, Service, ConfigMap, NetworkPolicy, Route
- 명시적 OAuthClient와 OAuth client/cookie Secret
- Application Menu ConsoleLink
- Action Executor 관련 리소스는 `mutations=true`일 때 생성·검증한다.
- Host Diagnostics 관련 리소스는 `diagnostics=true`일 때 생성·검증한다.
- ServiceAccount, Role, RoleBinding, ClusterRole, ClusterRoleBinding, NetworkPolicy
- cluster-scoped ConsolePlugin과 OpenShift Console plugin 설정

설치 후 `task aiops:company:status`에서 CatalogSource, PackageManifest, Subscription, CSV,
AIOpsInstallation, ConsolePlugin, operand Deployment와 Service를 확인한다.

현재 중간발표 환경에는 구형 Operator의 Gateway NetworkPolicy를 보완하기 위한
`komsco-ai-core-standalone-to-gateway` 정책이 임시로 존재한다. `0.1.17` 설치 후에는 먼저
기본 `komsco-ai-gateway-ingress`가 `app=komsco-ai-core-standalone`을 허용하는지 확인한다.

```bash
oc get networkpolicy komsco-ai-gateway-ingress -n cywell-aiops -o yaml
```

기본 정책 반영과 독립 포털의 Gateway API `200` 응답을 모두 확인한 뒤에만 임시 정책을 제거한다.

```bash
oc delete networkpolicy komsco-ai-core-standalone-to-gateway -n cywell-aiops
```

## 7. 기설치 환경에 현재 코드 재배포

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

## 8. 기존 이미지 재사용

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
oc get installplan -n cywell-aiops
oc get route cywell-aiops-standalone -n cywell-aiops
oc get oauthclient cywell-aiops-standalone
```

같은 실패 명령을 반복하기 전에 Build, CatalogSource, Subscription/CSV, Operator, operand 중
어느 단계가 실패했는지 먼저 구분한다.

0.1.17 rollout 실패가 선언된 경우에만 다음 복구 명령을 사용한다. 백업 체크섬, 회사 서버,
명시 승인값이 하나라도 맞지 않으면 스크립트는 중단한다.

```bash
KOMSCO_AIOPS_APPROVE_ROLLBACK=cywell-aiops \
KOMSCO_AIOPS_ROLLBACK_DRY_RUN=true \
task aiops:company:rollback

KOMSCO_AIOPS_APPROVE_ROLLBACK=cywell-aiops task aiops:company:rollback
```

## 코드 기준 위치

- 짧은 Task 명령: `Taskfile.yml`
- 회사 서버 및 승인 차단: `scripts/kugnus-olm.sh`
- OLM package/catalog/install/status: `scripts/olm-deploy.sh`
- 상세 참고: `docs/Ver.0.1.0/deployment-runbook.md`
