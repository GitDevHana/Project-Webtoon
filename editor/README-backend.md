# 로컬 서버 API

실행·호환 범위·저장 방식의 전체 설명은 [README.md](README.md)를 참고하세요.

## 실행

편집기 폴더에서 `python server.py --open`을 실행합니다. 기본 주소는 `http://127.0.0.1:8765/`이며 `--port`로 포트를 변경할 수 있습니다. 서버는 loopback에만 연결됩니다. Python 표준 라이브러리를 사용합니다.

`importer.py`의 프로젝트 루트는 편집기 폴더의 상위 폴더입니다. 회차 가져오기는 프로젝트 회차 파일과 현재 `episodes/EP03/review/cdp.py`·Windows Chrome에 의존합니다. 이 보조 코드는 코드 저장소에 포함되지 않습니다. 일반 파일 불러오기와 구분하세요.

## 엔드포인트

| 메서드·경로 | 동작 |
| --- | --- |
| GET `/api/health` | 서버 상태·문서 스키마·프로젝트 루트 |
| GET `/api/episodes` | 실제 manifest로부터 회차 목록 구성 |
| GET `/api/episodes/EPXX` | 회차를 편집 문서로 가져오기. 최초 가져오기는 Chrome 사용 |
| GET `/api/context` | 프로젝트의 존재하는 AGENTS.md·PROMPT.md·공통 설정 연결 |
| GET `/api/saves` | 서버 저장본 목록 |
| GET `/api/saves/<파일명>` | 저장한 편집 문서 |
| POST `/api/save` | `{document}`를 새 `saves/*.wtedit.json` 파일로 저장 |
| POST `/api/handoff` | `{document, revision, previewHtml?}`로 새 전달 폴더 생성 |

문서 형식은 `projectWT.editor/1`입니다. JSON 요청 한도는 150MiB입니다. 기존 회차 원본은 읽기만 합니다. 사용자 제공 이름으로 임의 경로에 저장하지 않고, 서버가 날짜·마이크로초·임의 ID로 새 이름을 만듭니다.

`/api/handoff`는 문서·변경 내역·선택적 미리보기·반영 지침을 저장합니다. `handoff/latest.json`의 해당 문서 포인터를 갱신하되 이전 전달 폴더는 보존합니다. 로컬 프로젝트는 회차 키, 외부 작품은 문서 ID 키로 구분합니다. AI 호출이나 실제 그림 수정은 수행하지 않습니다.

자동 복구는 서버 API와 별개인 브라우저 IndexedDB 기능입니다. 서버 저장 실패 시 내려받기 동작도 클라이언트에서 처리합니다. 다운로드 요청만으로 실제 다운로드 완료를 확정하지 않습니다.

## 경로와 검증 범위

서버는 경로 탈출과 교차 출처 POST 요청을 거부하며, 캐시·서버 저장·전달 폴더는 일반 정적 경로로 제공하지 않습니다. 인터넷 공개용 서버로 검증된 프로그램은 아닙니다.

`test_backend.py`는 실제 projectWT 회차가 있는 환경의 통합 검사입니다. 서버 저장·전달·경로 제한·원본 manifest 비변경을 검사하며 새 PC에서 코드만 받았을 때의 독립 테스트는 아닙니다.

