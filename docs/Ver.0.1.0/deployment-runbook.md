# Ver.0.1.0 Deployment Runbook

작성 기준일: 2026-06-24 KST

## 목표

Kugnus 전용 KOMSCO AIOps 패키지를 회사 OCP의 OLM/OperatorHub 카탈로그에 등록한다. 콘솔 안의 제품명은 `Cywell AI`로 표시하고, 기본 publish는 `CatalogSource`와 `PackageManifest` 노출까지만 수행한다. runtime 설치는 별도 승인 후 진행한다.

## 사전 확인

```bash
oc whoami
oc whoami --show-server
oc registry info
oc registry info --internal
```

Pass:

- server가 `https://api.ocp.cywell.server:6443`
- push registry가 `default-route-openshift-image-registry.apps.ocp.cywell.server`
- pull registry가 `image-registry.openshift-image-registry.svc:5000`

## 기본 publish 절차

현재 회사 OCP 환경의 선호 명령은 다음이다. 등록 담당자는 내부 환경변수를 외울 필요 없이 이 task만 사용한다.
현재 로컬 package/check 기준 생성 CSV는 `komsco-aiops-kugnus-operator.v0.1.6`이다.

```bash
task kugnus:company:check
task kugnus:company:publish
task kugnus:company:status
```

의미:

- 로컬 Docker push를 사용하지 않는다.
- OpenShift `BuildConfig` binary build로 gateway/plugin 이미지를 만든다.
- 이미지는 `komsco-ai-kugnus` namespace의 ImageStreamTag로 들어간다.
- 이후 `CatalogSource`와 `PackageManifest`만 등록한다.
- `Subscription`, `CSV`, `AIOpsInstallation`은 만들지 않는다.
- task가 대상 서버를 `https://api.ocp.cywell.server:6443`로 확인하고, 다르면 중단한다.

소스 변경을 이미지에 반드시 반영하는 것이 기본이다. 기존 ImageStreamTag를 재사용해야 하는 예외 상황에서만 아래처럼 실행한다.

```bash
KOMSCO_AIOPS_FORCE_IMAGE_BUILD=false task kugnus:company:publish
```

로컬 Docker/Podman push가 되는 환경에서는 다음도 가능하다.

```bash
task kugnus:package
task kugnus:publish
task kugnus:status
```

`kugnus:publish`가 수행하는 일:

1. `komsco-ai-kugnus` namespace 준비
2. gateway/operator image build and push
3. console plugin image build and push
4. Kugnus OLM bundle/catalog 생성
5. `openshift-marketplace/komsco-aiops-catalog-kugnus` 적용
6. `komsco-aiops-kugnus` PackageManifest 대기

`kugnus:publish`가 하지 않는 일:

- Subscription 생성
- CSV 설치
- AIOpsInstallation 생성
- 기존 Lightspeed UI 비활성화
- 기존 `komsco-ai-console-plugin` 교체

## 과거 publish evidence

2026-06-24 KST 당시 확인된 상태:

```bash
oc get catalogsource komsco-aiops-catalog-kugnus -n openshift-marketplace
oc get packagemanifest komsco-aiops-kugnus -n openshift-marketplace
oc get imagestream,buildconfig -n komsco-ai-kugnus
```

Pass:

- `CatalogSource/komsco-aiops-catalog-kugnus` exists
- `PackageManifest/komsco-aiops-kugnus` exists
- `CatalogSource` display is `Cywell AI Kugnus Catalog`
- `PackageManifest` currentCSV is `komsco-aiops-kugnus-operator.v0.1.2`
- `ImageStreamTag/komsco-ai-gateway:0.1.2` exists
- `ImageStreamTag/komsco-ai-console-plugin:0.1.2` exists
- `Subscription`, `CSV`, `AIOpsInstallation` are absent
- 기존 `komsco-ai-console-plugin`과 `lightspeed-console-plugin` are unchanged

## 선택 설치 절차

별도 승인 후에만 실행한다.

```bash
task kugnus:company:install
task kugnus:company:status
```

Pass:

- `Subscription/komsco-aiops-kugnus` exists in `komsco-ai-kugnus`
- CSV phase is `Succeeded`
- `AIOpsInstallation/komsco-aiops-kugnus` status phase is `Ready`
- `ConsolePlugin/komsco-ai-console-plugin-kugnus` exists
- Gateway and console plugin deployments are available in `komsco-ai-kugnus`

## 검증 명령

```bash
oc get catalogsource komsco-aiops-catalog-kugnus -n openshift-marketplace
oc get catalogsource komsco-aiops-catalog-kugnus -n openshift-marketplace -o jsonpath='{.status.connectionState.lastObservedState}{"\n"}'
oc get packagemanifest komsco-aiops-kugnus -n openshift-marketplace
oc get packagemanifest komsco-aiops-kugnus -n openshift-marketplace -o jsonpath='{.status.channels[0].currentCSV}{"\n"}'
oc get consoleplugin komsco-ai-console-plugin-kugnus
oc get deploy,svc -n komsco-ai-kugnus
```

기존 공용 리소스 보호 확인:

```bash
oc get consoleplugin komsco-ai-console-plugin
oc get consoleplugin lightspeed-console-plugin
oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'
```

Pass:

- `komsco-ai-console-plugin` backend가 기존 namespace를 유지한다.
- `lightspeed-console-plugin`은 삭제되지 않는다.
- install 전에는 Kugnus plugin `komsco-ai-console-plugin-kugnus`가 존재하지 않아야 정상이다.
- install 후 Kugnus plugin은 `komsco-ai-console-plugin-kugnus`로 별도 노출된다.

## 롤백

Kugnus 전용 리소스만 제거:

```bash
KOMSCO_AIOPS_APPROVE_UNINSTALL=komsco-ai-kugnus task kugnus:uninstall
```

주의:

- uninstall은 runtime 리소스 삭제를 포함할 수 있으므로 실제 사용 전 대상 namespace와 `olm/generated` manifest를 확인한다.
- 공용 `komsco-aiops`와 `komsco-aiops-jk`는 삭제 대상이 아니다.

## 로컬 프리뷰 주의

첫 실행:

```bash
AIOPS_GATEWAY_MODE=read-only task be:dev
INSTALL_DEPS=true task fe:dev
```

의존성이 설치된 뒤:

```bash
AIOPS_GATEWAY_MODE=read-only task be:dev
task fe:dev
```

WSL에서 console container가 WSL Gateway에 붙어야 하면 Gateway를 `0.0.0.0`로 열고, console proxy endpoint는 WSL IP를 사용한다. `host.docker.internal`은 Windows host 쪽 다른 서비스로 향할 수 있으므로 Gateway 응답이 Cywell AI가 맞는지 `/v1/aiops/status`로 확인한다.

## 금지 명령

```bash
task olm:deploy
task olm:release
task olm:install
task catalog:deploy
task catalog:release
scripts/enable-console-plugin.sh
```

위 명령은 공용 설치/전환 경로를 탈 수 있으므로 Ver.0.1.0 Kugnus 기본 publish에서는 사용하지 않는다.
