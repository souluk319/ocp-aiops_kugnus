# Ver.0.1.0 작업 방향

작성 기준일: 2026-06-23 KST

## 현재 판단

Ver.0.1.0의 방향은 "회사 OCP에 바로 설치"가 아니다. 이 단계의 핵심은 WSL 로컬 개발환경에서 개발용 OpenShift Console bridge를 띄우고, 회사 OCP에 `oc login`과 port-forward로 연결해 기능을 확인한 뒤, Software Catalog 등록 준비까지 정리하는 것이다.

CRC는 이번 Ver.0.1.0의 target이 아니다. CRC는 개인 실습과 별도 프로젝트 검증용으로만 본다.

## 핵심 개념

로컬 개발환경은 로컬에 OCP 전체를 설치하는 방식이 아니다.

```text
WSL local
  - FastAPI Gateway: localhost:18080
  - Console plugin dev server: localhost:9001
  - OpenShift Console bridge: localhost:9000

Company OCP
  - OpenShift API
  - openshift-lightspeed service
  - live cluster data
  - user auth/RBAC

Connection
  - oc login
  - oc port-forward
  - local console bridge
```

즉 브라우저에서는 `http://localhost:9000`을 열지만, 그 안에서 보는 OpenShift 데이터와 인증 컨텍스트는 회사 OCP 쪽을 사용한다. 운영 콘솔을 직접 수정하지 않고, 로컬 개발 중인 플러그인과 Gateway를 끼워 넣어 확인하는 구조다.

## Ver.0.1.0 목표

- WSL에서 repo 개발환경을 준비한다.
- 회사 OCP에 `oc login`할 수 있는지 확인한다.
- `task be:dev`로 Gateway와 Lightspeed port-forward 개발 루프를 준비한다.
- `task fe:dev`로 plugin dev server와 local console bridge를 준비한다.
- `http://localhost:9000`에서 개발용 웹콘솔을 확인한다.
- Software Catalog 등록 준비를 한다.
- 실제 설치, 기존 챗봇 교체, ConsolePlugin 활성 목록 변경은 하지 않는다.

## 작업 순서

1. WSL에서 repo 위치 확인

```bash
cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus
git status --short --branch
```

2. 필수 도구 확인

```bash
git --version
python3 --version
pip3 --version
node --version
yarn --version
task --version
oc version --client
helm version
```

3. 회사 OCP context 확인

```bash
oc whoami --show-server
oc config current-context
```

회사 OCP 작업이면 server가 `ocp.cywell.server` 계열이어야 한다. `api.crc.testing`이면 개인 CRC context다.

4. 회사 OCP의 기존 콘솔 확장 상태를 read-only로 조사

```bash
oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'
oc get consoleplugin
oc get deploy,svc -A
```

이 단계는 조회만 한다. 기존 챗봇, Lightspeed, ConsolePlugin, namespace, proxy alias를 건드리지 않는다.

5. 로컬 개발 루프 실행 준비

```bash
task be:dev
task fe:dev
```

초기 실행에서는 Python venv, pip dependency, yarn install, webpack dev server 준비 때문에 시간이 오래 걸릴 수 있다.

6. 개발용 웹콘솔 확인

```text
http://localhost:9000
```

이 콘솔은 회사 OCP 운영 콘솔을 대체 설치하는 것이 아니라, 로컬 개발용 bridge다.

7. Software Catalog 준비

```bash
task catalog:package
task catalog:register
task catalog:status
```

`catalog:register`는 Software Catalog에 Helm chart repository를 보이게 등록하는 단계다. 실제 chart 설치와 다르다.

## 하지 않을 것

다음 명령은 Ver.0.1.0 기본 범위에서 실행하지 않는다.

```bash
task catalog:deploy
task catalog:release
task catalog:runtime:apply
task olm:deploy
task olm:release
task olm:install
scripts/enable-console-plugin.sh
```

회사 OCP에 이미 존재하는 커스텀 챗봇, ConsolePlugin, Gateway, namespace, proxy alias를 제거하거나 교체하지 않는다.

기존 `lightspeed-console-plugin`을 제거하거나 새 `komsco-ai-console-plugin`을 운영 콘솔 활성 목록에 추가하지 않는다.

CRC에서 확인한 결과를 회사 OCP 검증 결과로 보고하지 않는다.

`.env.local`, kubeconfig, token, password, private key, Authorization header 등 인증정보를 commit하지 않는다.

## 조심할 것

Software Catalog URL은 개발자 브라우저뿐 아니라 OCP console/cluster가 접근할 수 있어야 한다. 로컬 `localhost` URL은 정식 등록 URL로 쓰면 안 된다.

`실험 무제한` 모드는 회사 OCP에서 기본 사용하지 않는다. 이 모드는 disposable local lab에서만 다룬다.

`task catalog:register`와 `task catalog:deploy`는 다르다. 등록은 catalog entry를 보이게 하는 것이고, deploy는 실제 설치다.

## 완료 기준

Ver.0.1.0은 다음 조건을 만족하면 완료로 본다.

- WSL에서 필수 도구 설치 상태가 확인됐다.
- 회사 OCP context와 CRC context가 구분됐다.
- 기존 회사 OCP 콘솔 확장 상태가 read-only로 조사됐다.
- 로컬 개발용 console bridge 구조를 이해하고 실행 준비가 됐다.
- Software Catalog 등록 준비 단계와 실제 설치 단계가 분리됐다.
- 금지 명령을 실행하지 않았다.

## 현재 결론

Ver.0.1.0은 "회사 OCP에 설치" 단계가 아니라 "회사 OCP에 붙는 로컬 개발 콘솔 + Software Catalog 등록 준비" 단계다. 실제 설치나 운영 콘솔 변경은 Ver.0.1.0의 기본 범위가 아니다.
