# 환경 설정과 복구 기록

이 디렉터리는 보드 설정, 빌드 환경, 호스트 환경의 복구 입력을 모은다.
실행 코드와 검증기는 저장소 루트의 `host/`, `firmware/`에 있다.

| 위치 | 내용 |
| --- | --- |
| [board/current/](board/current/) | 캡처 시점의 보드 설정. 현재 실보드와 다시 동기화했다는 뜻은 아니다. |
| [board/history/](board/history/) | bring-up 과정의 과거 설정. 파일 이름에 기록된 사건을 보존한다. |
| [board/RECOVERY_ARCHIVE.sha256](board/RECOVERY_ARCHIVE.sha256) | 별도 보드 복구 아카이브의 위치와 해시. 내부 경로는 그 외부 아카이브 기준이다. |
| [build/BUILD_ENVIRONMENT.yaml](build/BUILD_ENVIRONMENT.yaml) | 툴체인·컨테이너·입력/출력 해시와 과거 복구 검증 결과. 파일 필드는 이 YAML의 디렉터리를 기준으로 읽는다. |
| [build/archive/container-build-context/](build/archive/container-build-context/) | 외부 시뮬레이터 프로젝트의 보관본. 원래 디렉터리 구조와 바이트를 유지한다. |
| [host/HOST_RESTORE.md](host/HOST_RESTORE.md) | 호스트 인터프리터와 의존성 복구 기록. |
| [host/serial-bindings.yaml](host/serial-bindings.yaml) | 보드 시리얼 바인딩 조사 기록. 실행 시 자동으로 읽는 설정은 아니다. |

빌드 작업 트리 `build/archive/selftest-worktree.tgz`와 벤더 배포본
`build/archive/fi101-selftest-src.tgz`는 Git에 포함되지 않는다. 필요한 경우
기록된 원본 위치에서 별도로 확보하고 `BUILD_ENVIRONMENT.yaml`의 해시와 대조한다.
복구 명령의 `environment/...` 경로는 저장소 루트를 기준으로 한다.

보관된 컨테이너 프로젝트에는 미완성 devcontainer 설정과 별도 프로젝트의
workflow가 포함돼 있다. 이 Dockerfile이 실제 사용한 컨테이너를 재현하지 못한다는
기존 조사 결과도 유지한다. 이번 배치 변경으로 빌드 환경을 새로 검증한 것은 아니다.

## 이전 경로 대응

| 이전 경로 | 현재 경로 |
| --- | --- |
| `board-config/current/` | `environment/board/current/` |
| `board-config/config.txt.*`, `board-config/images.txt.*` | `environment/board/history/` |
| `board-config/RECOVERY_ARCHIVE.sha256` | `environment/board/RECOVERY_ARCHIVE.sha256` |
| `build-env/BUILD_ENVIRONMENT.yaml` | `environment/build/BUILD_ENVIRONMENT.yaml` |
| `build-env/container-build-context/` | `environment/build/archive/container-build-context/` |
| `build-env/*.tgz` | `environment/build/archive/*.tgz` |
| `host-environment/` | `environment/host/` |

`provenance/`와 과거 대화 기록의 옛 경로는 동결 원문으로 남겨 둔다.
이동 후 위치는 위 대응표를 사용한다. 보드 history의 두 동일한 config 파일도
서로 다른 사건 이름을 보존하기 위해 유지한다.
