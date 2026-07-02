# 회사 서버 배포

Cywell 제공 AIOps를 회사 OKD/OCP OperatorHub 카탈로그에 등록할 때는 이 문서만 본다.

## 원리

`task aiops:company:*`는 OpenShift 공식 명령이 아니라 이 repo의 바로가기다.

현재 기본 배포 패키지 버전은 `0.1.9`이다. 그래서 생성되는 CSV는 `cywell-aiops-operator.v0.1.9`이어야 한다.

원래 흐름은 네 단계다.

```text
1. oc가 어느 서버를 보고 있는지 확인
2. gateway/plugin/operator 이미지를 빌드해서 회사 registry에 올림
3. OLM catalog를 만들어 OperatorHub에 등록
4. 승인 후 Subscription/AIOpsInstallation/ConsolePlugin 설치
```

`publish`는 1-3까지만 한다. 4번 설치는 `install`이다.

## 어떻게 감쌌나

새 파일을 만들어서 실행하는 것이 아니다.

`Taskfile.yml` 안에 `aiops:company:publish`라는 이름으로 실행 블록을 적어둔 것이다.

```text
내가 터미널에 입력:
task aiops:company:publish

Task가 대신 실행:
1. oc가 보고 있는 서버 주소를 확인한다.
2. 회사 서버 주소가 아니면 멈춘다.
3. 회사 서버가 맞으면 ./scripts/kugnus-olm.sh publish를 실행한다.
```

실제 위치는 `Taskfile.yml`의 `aiops:company:publish` 항목이다.
즉 짧은 명령 하나가 "회사 서버 확인 + 긴 publish 명령"을 대신 실행한다.

## 1. 안전 확인

```bash
task aiops:company:check
```

확인하는 것:

- 현재 `oc` 대상 서버가 `https://api.ocp.cywell.server:6443`인지 확인한다.
- 로컬 OLM 패키지를 생성하고 검증한다.
- 서버에는 아무것도 만들지 않는다.

## 2. 카탈로그 등록

```bash
task aiops:company:publish
```

원래 긴 명령:

```bash
KOMSCO_AIOPS_IMAGE_BUILD_STRATEGY=openshift \
KOMSCO_AIOPS_FORCE_IMAGE_BUILD=true \
KOMSCO_AIOPS_APPROVE_PUBLISH=cywell-aiops \
./scripts/kugnus-olm.sh publish
```

하는 일:

- OpenShift binary build로 gateway/plugin 이미지를 만든다.
- `openshift-marketplace/cywell-aiops-catalog` CatalogSource를 갱신한다.
- OperatorHub에서 `cywell-aiops` 패키지의 `AIOps`가 검색되게 만든다.

하지 않는 일:

- Subscription 생성 안 함
- AIOpsInstallation 생성 안 함
- ConsolePlugin 생성 안 함
- 기존 공용 plugin 삭제/교체 안 함

## 3. 등록 확인

```bash
task aiops:company:status
```

## 4. 설치 승인 후에만 실행

```bash
task aiops:company:install
task aiops:company:status
```

이 단계에서 `Subscription`, `AIOpsInstallation`, `ConsolePlugin`이 생성된다.

## 예외

이미지를 새로 빌드하지 않고 기존 ImageStreamTag를 재사용해야 할 때만 사용한다.

```bash
KOMSCO_AIOPS_FORCE_IMAGE_BUILD=false task aiops:company:publish
```

## 더 자세한 문서

- `docs/Ver.0.1.0/deployment-runbook.md`
- `docs/version-progress-book.html`
