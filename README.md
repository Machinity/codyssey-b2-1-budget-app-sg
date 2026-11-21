# 나만의 용돈 기입장 (budget_app)

표준 라이브러리만 사용하는 콘솔 가계부입니다. (Python 3.10 이상)

> **데이터 파일 (3개, JSONL, 기본 `./data`)**: 거래 `data/transactions.jsonl` · 카테고리 `data/categories.jsonl` · 예산 `data/budgets.jsonl`

## 실행 방법

```bash
python -m budget_app <command> [options]
python -m budget_app --help            # 전체 도움말
python -m budget_app <command> --help  # 명령별 도움말
```

공통 옵션 (명령 앞에 씀)

| 옵션 | 설명 |
| --- | --- |
| `--data-dir DIR` | 데이터 저장 폴더 (기본 `./data`) |
| `--verbose` | 실행 로그(명령 종료 코드, 소요 시간) 출력 |

종료 코드: 정상 `0`, 오류 `1`, 인자 오류 `2`(argparse), 입력 취소 `130`.
오류는 스택트레이스 대신 `[오류] 원인` + `[힌트] 해결 방법` 형식으로 출력합니다.

### 자주 발생하는 오류와 힌트

모든 오류는 `AppError(message, hint)`로 만들고, `@handle_errors` 데코레이터가 한 곳에서 아래 형식으로 출력합니다(stderr).
파일 시스템 오류(`OSError`)도 데코레이터가 잡아 같은 형식으로 바꿉니다. 아래 문구는 실제 출력입니다.

| 상황 | 예시 명령 | `[오류]` 출력 | `[힌트]` 출력 | 종료 코드 |
| --- | --- | --- | --- | --- |
| 날짜 형식 오류 | `search --from 2026/11/01` | 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD). | 예: 2026-11-15 | 1 |
| 월 형식 오류 | `summary --month 2026/11` | 월 형식이 올바르지 않습니다 (YYYY-MM). | 예: 2026-11 | 1 |
| 허용되지 않은 타입 | `update --id TX-000001 --type exp` | 허용되지 않은 타입입니다: 'exp' | income 또는 expense 중 하나를 입력하세요. | 1 |
| 금액이 숫자가 아님 | `budget set --month 2026-11 --amount abc` | 금액은 정수여야 합니다: 'abc' | 예: 15000 | 1 |
| 금액이 0 이하 | `budget set --month 2026-11 --amount -5` | 금액은 0보다 커야 합니다. | 양수 정수를 입력하세요. 예: 15000 | 1 |
| 없는 카테고리 | `update --id TX-000001 --category nope` | 존재하지 않는 카테고리입니다: 'nope' | 등록된 카테고리: … (새로 등록: python -m budget_app category add --name nope) | 1 |
| 이미 있는 카테고리 추가 | `category add --name food` | 이미 존재하는 카테고리입니다: food | category list 로 목록을 확인하세요. | 1 |
| 사용 중인 카테고리 삭제 | `category remove --name food` | 사용 중인 카테고리는 삭제할 수 없습니다: food | 대체 카테고리로 옮긴 뒤 삭제: category remove --name food --replace-with <카테고리> … | 1 |
| 없는 id | `delete --id TX-999999` | 없는 데이터입니다: id=TX-999999 | python -m budget_app list 로 id 를 확인하세요. | 1 |
| 수정할 필드 없음 | `update --id TX-000001` | 수정할 필드가 없습니다. | 예: update --id TX-000001 --amount 20000 | 1 |
| export 기간 조건 없음 | `export --out a.csv` | 내보낼 기간 조건이 없습니다. | --month YYYY-MM 또는 --from/--to YYYY-MM-DD 를 지정하세요. | 1 |
| import 파일 없음 | `import --from none.csv` | 파일을 찾을 수 없습니다: none.csv | 경로를 확인하세요. | 1 |
| import CSV 헤더 누락 | `import --from bad.csv` | CSV 필수 컬럼이 없습니다: amount, category, date, type | 헤더 예: date,type,category,amount,memo,tags | 1 |
| export 경로 폴더 없음 | `export --out nodir/x.csv --month 2026-11` | 파일 처리 실패: No such file or directory (nodir/x.csv) | 경로와 권한을 확인하세요. | 1 |
| 쓰기 권한 없음 | `export --out ro/x.csv --month 2026-11` | 파일 처리 실패: Permission denied (ro/x.csv) | 경로와 권한을 확인하세요. | 1 |
| 데이터 파일 손상 | (transactions.jsonl 에 깨진 줄) `list` | data/transactions.jsonl 1번째 줄이 손상되었습니다. | 해당 줄을 수정하거나 삭제한 뒤 다시 실행하세요. | 1 |
| 다른 실행이 쓰기 중 | 두 터미널에서 동시에 `import` | 다른 budget_app 실행이 데이터를 수정 중입니다 (잠금 대기 시간 초과). | 잠시 후 다시 실행하세요. 실행 중인 budget_app 이 없다면 data/.lock 를 삭제하세요. | 1 |
| `--atomic` import 에 잘못된 행 | `import --from mixed.csv --atomic` | 잘못된 행 2개가 있어 아무것도 가져오지 않았습니다 (--atomic). (아래에 행 번호·사유 목록) | 해당 행을 고친 뒤 다시 실행하거나, 잘못된 행만 건너뛰려면 --atomic 없이 실행하세요. | 1 |
| 입력 중 취소 | `add` 중 Ctrl+C / Ctrl+D | [중단] 입력이 취소되었습니다. | – | 130 |
| 옵션 누락/형식 오류 | `summary` (--month 없음), `list --limit abc` | argparse 사용법(usage) + error 한 줄 | `<명령> --help` 로 사용법 확인 | 2 |

참고:
- `add` 대화형 입력 중의 검증 오류(날짜·타입·카테고리·금액)는 종료하지 않고 같은 `[오류]/[힌트]`를 보여준 뒤 **다시 입력**을 받습니다.
- `import` 에서 개별 행의 검증 오류는 전체를 중단하지 않고 `[건너뜀] N행: <원인>` 으로 출력한 뒤 skipped 로 셉니다.

### 종료 코드 검증 (예제 스크립트 + CI)

[scripts/check_exit_codes.sh](scripts/check_exit_codes.sh) 는 실제 프로세스를 실행해 셸의 `$?` 로 종료 코드를 확인합니다.
임시 폴더에서 실행하므로 `./data` 를 건드리지 않으며, 하나라도 기대값과 다르면 `FAIL` 과 출력 내용을 보여주고 1로 종료합니다.

```text
$ bash scripts/check_exit_codes.sh
PASS  exit=0   (expected 0  )  $ python -m budget_app add   # add (정상)
PASS  exit=0   (expected 0  )  $ python -m budget_app list --limit 5   # list (정상)
PASS  exit=0   (expected 0  )  $ python -m budget_app budget set --month 2026-11 --amount 500000   # budget set (정상)
PASS  exit=0   (expected 0  )  $ python -m budget_app summary --month 2026-11   # summary (정상)
PASS  exit=0   (expected 0  )  $ python -m budget_app export --out out.csv --month 2026-11   # export (정상)
PASS  exit=1   (expected 1  )  $ python -m budget_app delete --id TX-999999   # delete 없는 id
PASS  exit=1   (expected 1  )  $ python -m budget_app export --out x.csv   # export 기간 조건 없음
PASS  exit=1   (expected 1  )  $ python -m budget_app import --from none.csv   # import 파일 없음
PASS  exit=1   (expected 1  )  $ python -m budget_app summary --month 2026/11   # summary 월 형식 오류
PASS  exit=1   (expected 1  )  $ python -m budget_app category remove --name food   # category 사용 중 삭제
PASS  exit=2   (expected 2  )  $ python -m budget_app summary   # summary --month 누락
PASS  exit=2   (expected 2  )  $ python -m budget_app list --limit abc   # list --limit 형식 오류
PASS  exit=130 (expected 130)  $ python -m budget_app add   # add 입력 중 EOF(취소)
ALL PASS
$ echo $?
0
```

직접 한 건씩 확인할 때:

```bash
python -m budget_app delete --id TX-999999; echo "exit=$?"   # exit=1
python -m budget_app summary;               echo "exit=$?"   # exit=2
```

GitHub Actions([.github/workflows/ci.yml](.github/workflows/ci.yml))가 push/PR 마다 Python 3.10·3.12 에서
`python -m mypy`(타입 검사), `python -m unittest -v`, `bash scripts/check_exit_codes.sh` 를 실행합니다. 하나라도 실패하면 CI 가 실패합니다.

## 저장 파일 위치 / 형식

저장 포맷은 **JSONL**(한 줄에 JSON 객체 하나, UTF-8)입니다. 파일이 없으면 첫 실행 때 자동 생성됩니다.

| 파일 | 한 줄 예시 |
| --- | --- |
| `data/transactions.jsonl` | `{"id": "TX-000001", "date": "2026-11-15", "type": "expense", "category": "food", "amount": 15000, "memo": "점심", "tags": ["meal"]}` |
| `data/categories.jsonl` | `{"name": "food"}` |
| `data/budgets.jsonl` | `{"month": "2026-11", "amount": 500000}` |

- 카테고리 파일이 비어 있으면 기본 카테고리(`food, transport, rent, salary, etc`)를 자동 생성합니다. (안 A)
- update/delete/카테고리 삭제/예산 설정은 임시 파일에 전체를 다시 쓴 뒤 `os.replace`로 원자적 교체합니다.
- 쓰기 명령은 실행 중 `data/.lock` 잠금 파일을 만듭니다(아래 "동시 실행과 잠금" 참고). 명령이 끝나면 자동으로 지워집니다.

### 저장 포맷 선택: 왜 JSONL 인가 (CSV 비교)

내부 저장은 **JSONL**, 사람·엑셀과 주고받는 import/export 는 **CSV** 로 역할을 나눴습니다.

| 기준 | JSONL (선택) | CSV | 이 앱에서의 의미 |
| --- | --- | --- | --- |
| 목록 필드(`tags`) | `["fixed", "home"]` 배열 그대로 저장 | `"fixed,home"` 문자열로 이어 붙이고 따옴표로 감싼 뒤 다시 split 해야 함 | 태그에 쉼표가 들어가면 CSV 는 구분 규칙을 따로 정해야 함 |
| 값의 타입 | `amount` 는 숫자, `tags` 는 배열로 저장·복원 (`json.loads`) | 모든 값이 문자열 → 읽을 때마다 `int()` 변환과 검증 필요 | 저장소가 타입을 보존해 `Transaction.from_dict` 가 단순함 |
| 필드 추가(스키마 변경) | 새 키를 넣으면 끝. 키가 없는 옛 줄은 `data.get("memo", "")` 처럼 기본값으로 읽힘 | 헤더와 모든 행의 열 위치를 함께 바꿔야 함 | `memo`/`tags` 같은 선택 필드를 넣고 빼기 쉬움 |
| 파일 3종의 형태 | 거래·카테고리·예산이 모두 "한 줄 = JSON 객체 하나" → `JsonlFile` 클래스 하나로 처리 | 파일마다 헤더가 따로 필요 | 저장소 코드가 하나로 통일됨 |
| 한 줄씩 스트리밍 / append | 가능 (줄 단위) | 가능 (행 단위) | 동일 — 둘 다 제너레이터 처리 가능 |
| 손상 감지 | 깨진 줄은 `json.loads` 가 실패 → "N번째 줄 손상" 으로 정확히 보고 | 열 수만 맞으면 잘못된 값도 그대로 읽힘 | 오류 메시지에 줄 번호 제공 |
| 한글·특수문자 | `ensure_ascii=False` 로 UTF-8 그대로, 쉼표·따옴표도 자동 이스케이프 | 메모에 쉼표·따옴표·줄바꿈이 있으면 인용 규칙에 의존 | 메모 자유 입력에 안전 |
| 파일 크기 (10만 건 실측) | **12.8 MiB** (줄마다 키 이름 반복) | **4.2 MiB** (id 열 제외 export 기준) | CSV 가 약 1/3 — JSONL 의 단점 |
| 읽기+객체 생성 속도 (10만 건 실측) | 0.372초 | 0.320초 | CSV 가 약 14% 빠름 — 체감 차이는 작음 |
| 사람이 보기 / 엑셀 | 텍스트 편집기로는 읽기 쉬움, 엑셀로 바로 열기 어려움 | 엑셀·스프레드시트에서 바로 열림 | 그래서 **import/export 는 CSV** 로 제공 |

결론: 거래 데이터에는 배열(`tags`)과 선택 필드가 있어 **타입과 구조를 그대로 보존하는 JSONL** 이 저장 코드를 단순하고 안전하게 만듭니다.
크기와 속도는 CSV 가 조금 유리하지만, 개인 가계부 규모(10만 건 이하, 1초 이내 처리, "대량 데이터 성능" 참고)에서는 문제가 되지 않습니다.
CSV 의 장점(엑셀 호환)은 import/export 로 따로 제공합니다.
크기가 문제가 되면 `json.dumps(..., separators=(",", ":"))` 로 공백을 빼서 줄일 수 있습니다.

같은 거래 1건의 저장 형태:

```text
JSONL: {"id": "TX-000001", "date": "2025-08-02", "type": "expense", "category": "rent", "amount": 33098, "memo": "저녁", "tags": ["cafe"]}
CSV  : 2025-08-02,expense,rent,33098,저녁,cafe
```

### 동시 실행과 잠금

같은 `--data-dir` 로 budget_app 을 **동시에 여러 개** 실행하면(터미널 두 개, 스크립트·cron 반복 실행 등)
"id 발급(next_number) → 파일 쓰기" 사이에 끼어들어 **id 중복이나 수정 내용 유실**이 생길 수 있습니다.
(실측: 잠금 없이 프로세스 5개가 동시에 20건씩 import 하면 100건 중 고유 id 가 40개뿐이었습니다.)
이를 막기 위해 data 폴더 단위 잠금을 겁니다.

| 항목 | 동작 |
| --- | --- |
| 잠금 방식 | `data/.lock` 을 `os.open(O_CREAT \| O_EXCL)` 로 생성 — 파일이 이미 있으면 실패하므로 한 프로세스만 통과 (표준 라이브러리, OS 무관) |
| 잠그는 명령 | 데이터를 바꾸는 명령: `add`, `update`, `delete`, `import`, `budget set`, `category add/remove` (`BudgetService` 메서드에 `@locked` 데코레이터) |
| 잠그지 않는 명령 | `list`, `search`, `summary`, `export`, `budget show`, `category list` — 교체가 `os.replace` 라 읽는 쪽은 항상 이전 또는 새 파일 전체를 봅니다 |
| 잠금 구간 | 실제 쓰기 작업 동안만. `add` 는 **대화형 입력이 끝난 뒤** 저장할 때만 잠그므로, 입력 중에 다른 명령을 막지 않습니다 |
| 이미 잠겨 있을 때 | 0.1초 간격으로 최대 5초(`storage.LOCK_TIMEOUT`) 기다린 뒤, 그래도 잠겨 있으면 오류 종료(코드 1) |
| 비정상 종료로 남은 잠금 | 잠금 파일에 PID 를 기록합니다. macOS/Linux 에서는 그 프로세스가 이미 없으면 남은 잠금을 자동 삭제하고 진행합니다 |

잠금 대기 시간 초과 시 출력:

```text
[오류] 다른 budget_app 실행이 데이터를 수정 중입니다 (잠금 대기 시간 초과).
[힌트] 잠시 후 다시 실행하세요. 실행 중인 budget_app 이 없다면 data/.lock 를 삭제하세요.
```

**사용자 주의사항**
- 실행 중인 budget_app 이 없는데 위 오류가 계속되면 `data/.lock` 을 직접 삭제하세요. (Windows 는 남은 잠금을 자동 판별하지 않습니다 — `os.kill(pid, 0)` 이 Windows 에서는 프로세스를 종료시키기 때문)
- 실행 중인 budget_app 이 **있을 때** `.lock` 을 지우면 보호가 깨집니다.
- 잠금은 같은 컴퓨터의 budget_app 끼리만 유효합니다. **네트워크 드라이브·클라우드 동기화 폴더**(Dropbox, iCloud 등)를 `--data-dir` 로 여러 컴퓨터에서 동시에 쓰는 것은 지원하지 않습니다.
- 프로그램 실행 중에 `data/*.jsonl` 을 편집기로 직접 고치지 마세요(잠금을 거치지 않음).
- 거의 동시에 비정상 종료 잠금을 두 프로세스가 함께 치우는 극히 드문 경우까지 완벽히 막지는 않습니다. 중요한 데이터는 `data/` 폴더를 주기적으로 복사해 백업하세요.

## 주요 명령 예시

```bash
# 거래 추가 (대화형)
python -m budget_app add
# 날짜(YYYY-MM-DD): 2026-11-15
# 타입(income/expense): expense
# 카테고리: food
# 금액(양수): 15000
# 메모(선택): 점심
# 태그(쉼표로 구분, 없으면 엔터): meal
# [저장 완료] id=TX-000001

# 목록 (최신순, 기본 10개)
python -m budget_app list --limit 3

# 검색 (조건은 모두 선택, AND 결합, 최신순)
python -m budget_app search --from 2026-11-01 --to 2026-11-31 --category food --type expense --q 점심 --tag meal

# 월별 요약 + 예산
python -m budget_app budget set --month 2026-11 --amount 500000
python -m budget_app budget show --month 2026-11
python -m budget_app summary --month 2026-11 --top 3

# 카테고리 (--name 생략 시 대화형 입력)
python -m budget_app category add --name hobby
python -m budget_app category list
python -m budget_app category remove --name hobby   # 사용 중인 카테고리는 삭제 거부
python -m budget_app category remove --name food --replace-with etc   # 사용 중인 거래를 etc 로 옮긴 뒤 삭제

# 수정 (옵션 방식으로 고정: 준 옵션만 변경)
python -m budget_app update --id TX-000001 --amount 20000 --memo 저녁 --tags meal,dinner

# 삭제
python -m budget_app delete --id TX-000001

# 가져오기 / 내보내기
python -m budget_app import --from import.csv            # 부분 적용: 잘못된 행만 건너뜀
python -m budget_app import --from import.csv --atomic   # 전부 아니면 전무: 잘못된 행이 있으면 아무것도 안 가져옴
python -m budget_app export --out export.csv --month 2026-11
python -m budget_app export --out export.csv --from 2026-11-01 --to 2026-11-30
```

- **예산 알림 단계** (`summary` 에 예산이 설정된 달만, 사용률 = 총 지출 ÷ 예산 × 100):

  | 단계 | 조건 | 출력 형식 | 권장 조치 (`[권장]` 줄) |
  | --- | --- | --- | --- |
  | 정상 | 사용률 80% 미만 | `예산: <예산>원 (사용률 N%)` | 없음 |
  | 주의 | 80% 이상, 예산 이하 | `[주의] 예산의 N%를 사용했습니다. (남은 예산 M원)` | 지출 1위 카테고리부터 줄이고 남은 기간 지출 계획 |
  | 경고 | 총 지출 > 예산 | `[경고] 예산을 M원 초과했습니다!` | 지출 1위 카테고리부터 줄이거나 `budget set --month <월> --amount <새 금액>` 으로 예산 조정 |

  알림은 화면 출력만 하며 거래나 예산을 자동으로 바꾸지 않습니다. 단계 판정은 `Summary.budget_level`(service.py)이 하고, 기준값은 `CAUTION_RATE = 80.0` 입니다.
- **카테고리 삭제 정책**: 해당 카테고리를 쓰는 거래가 있으면 기본적으로 **삭제를 거부**하고, 해결 명령을 힌트로 안내합니다.
  카테고리를 바꾸는 방법은 두 가지입니다.
  1. 한 번에 옮기기: `category remove --name <삭제할> --replace-with <대체>` → 해당 거래 전체를 대체 카테고리로 옮긴 뒤(원자적 재작성) 삭제
  2. 건별로 바꾸기: `search --category <삭제할>` 로 id 확인 → `update --id <id> --category <대체>` → `category remove --name <삭제할>`
- `update`는 **옵션 방식(안 A)** 으로 고정입니다: `update --id <id> [--date] [--type] [--category] [--amount] [--memo] [--tags]`
- 없는 id 로 update/delete 하면 "없는 데이터" 오류를 출력하고 종료 코드 1을 반환합니다.
- `export`는 `--month` 또는 `--from`/`--to` 중 하나 이상이 필수입니다.

## 명령별 실행 결과 (실제 실행 로그)

빈 폴더에서 아래 순서대로 실제 실행한 결과입니다. (`echo $?` = 종료 코드)
같은 시나리오를 [tests/test_commands.py](tests/test_commands.py)에서 명령별 테스트로 자동 검증합니다.

| 명령 | 실행 증거 (README) | 자동 테스트 |
| --- | --- | --- |
| add | [1. add](#1-add) | `TestAdd` |
| import | [2. import](#2-import) | `TestImport` |
| list | [3. list](#3-list) | `TestList` |
| search | [4. search](#4-search) | `TestSearch` |
| budget + summary | [5. budget + summary](#5-budget--summary) | `TestSummary` |
| update | [6. update](#6-update) | `TestUpdate` |
| delete | [7. delete](#7-delete) | `TestDelete` |
| export | [8. export](#8-export) | `TestExport` |
| category | [9. category](#9-category) | `TestCategory` |

```text
$ python -m unittest -v
test_add_reprompts_on_invalid_input (tests.test_commands.TestAdd) ... ok
test_add_saves_and_prints_id (tests.test_commands.TestAdd) ... ok
test_category_add_list_remove (tests.test_commands.TestCategory) ... ok
test_remove_in_use_category_is_blocked (tests.test_commands.TestCategory) ... ok
test_remove_with_invalid_replacement (tests.test_commands.TestCategory) ... ok
test_remove_with_replacement_moves_transactions (tests.test_commands.TestCategory) ... ok
test_handle_errors_converts_exceptions_to_exit_codes (tests.test_commands.TestDecorators) ... ok
test_log_call_logs_and_reraises (tests.test_commands.TestDecorators) ... ok
test_timed_logs_elapsed_and_keeps_return_value (tests.test_commands.TestDecorators) ... ok
test_delete_then_missing (tests.test_commands.TestDelete) ... ok
test_export_month (tests.test_commands.TestExport) ... ok
test_export_requires_period (tests.test_commands.TestExport) ... ok
test_export_then_import_roundtrip (tests.test_commands.TestExport) ... ok
test_export_zero_records_still_writes_header (tests.test_commands.TestExport) ... ok
test_import_counts_and_skips_invalid_rows (tests.test_commands.TestImport) ... ok
test_atomic_imports_all_when_valid (tests.test_commands.TestImportAtomic) ... ok
test_atomic_interrupted_write_keeps_original (tests.test_commands.TestImportAtomic)
쓰는 도중 중단(예: Ctrl+C)되면 원본 파일이 그대로 남는다. ... ok
test_atomic_rejects_whole_file_if_any_row_invalid (tests.test_commands.TestImportAtomic) ... ok
test_default_interrupted_write_keeps_rows_written_so_far (tests.test_commands.TestImportAtomic)
기본(부분 적용) 모드는 롤백이 없다: 중단 전까지 쓴 행은 남는다 (문서화된 동작). ... ok
test_list_newest_first_with_limit (tests.test_commands.TestList) ... ok
test_concurrent_imports_get_unique_ids (tests.test_commands.TestLock)
프로세스 5개가 동시에 20건씩 import → 100건, id 중복 없음. ... ok
test_read_commands_do_not_need_lock (tests.test_commands.TestLock) ... ok
test_stale_lock_from_dead_process_is_removed (tests.test_commands.TestLock) ... ok
test_write_waits_then_fails_while_locked (tests.test_commands.TestLock) ... ok
test_transaction_is_immutable (tests.test_commands.TestModel) ... ok
test_search_filters (tests.test_commands.TestSearch) ... ok
test_search_no_result (tests.test_commands.TestSearch) ... ok
test_summary_budget_caution (tests.test_commands.TestSummary) ... ok
test_summary_budget_exceeded (tests.test_commands.TestSummary) ... ok
test_summary_budget_ok_has_no_alert (tests.test_commands.TestSummary) ... ok
test_summary_no_data (tests.test_commands.TestSummary) ... ok
test_summary_with_budget (tests.test_commands.TestSummary) ... ok
test_update_changes_only_given_fields (tests.test_commands.TestUpdate) ... ok
test_update_missing_id (tests.test_commands.TestUpdate) ... ok

----------------------------------------------------------------------
Ran 34 tests in 1.012s

OK
```

### 1. add

```text
$ python -m budget_app add
(등록된 카테고리: food, transport, rent, salary, etc)
날짜(YYYY-MM-DD): 2026-13-40
[오류] 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[힌트] 예: 2026-11-15
날짜(YYYY-MM-DD): 2026-11-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
$ echo $?
0
```

### 2. import

```text
$ cat import.csv
date,type,category,amount,memo,tags
2026-11-14,income,salary,3000000,월급,
2026-11-12,expense,transport,20000,버스,
2026-11-01,expense,rent,150000,월세,"fixed,home"
2026-11-20,expense,food,30000,저녁,"meal,dinner"
2026-11-21,expense,nope,1000,,

$ python -m budget_app import --from import.csv
[건너뜀] 6행: 존재하지 않는 카테고리입니다: 'nope'
[완료] imported=4, skipped=1 (id TX-000002 ~ TX-000005)
[안내] 부분 적용: 위 행만 빠지고 나머지는 이미 저장되었습니다. 되돌리려면 위 id 범위를 delete 하세요.
$ echo $?
0
```

### 3. list

```text
$ python -m budget_app list --limit 3
TX-000005 | 2026-11-20 | expense | food | 30000 | 저녁 | meal,dinner
TX-000001 | 2026-11-15 | expense | food | 15000 | 점심 | meal
TX-000002 | 2026-11-14 | income  | salary | 3000000 | 월급
$ echo $?
0
```

### 4. search

```text
$ python -m budget_app search --type expense --tag meal
TX-000005 | 2026-11-20 | expense | food | 30000 | 저녁 | meal,dinner
TX-000001 | 2026-11-15 | expense | food | 15000 | 점심 | meal

$ python -m budget_app search --from 2026-11-01 --to 2026-11-13 --q 월
TX-000004 | 2026-11-01 | expense | rent | 150000 | 월세 | fixed,home
$ echo $?
0
```

### 5. budget + summary

```text
$ python -m budget_app budget set --month 2026-11 --amount 500000
[저장 완료] 2026-11 예산 500000원

$ python -m budget_app summary --month 2026-11 --top 3
[2026-11 요약]
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)

지출 TOP 3
1) rent 150000원
2) food 45000원
3) transport 20000원

$ python -m budget_app summary --month 2026-10
[데이터 없음] 2026-10 거래 내역이 없습니다.
$ echo $?
0
```

예산 알림 단계별 출력 (위 데이터에서 update 실행 후, 2026-11 총 지출 190000원):

```text
$ python -m budget_app budget set --month 2026-11 --amount 200000
[저장 완료] 2026-11 예산 200000원

$ python -m budget_app summary --month 2026-11 --top 3
[2026-11 요약]
총 수입: 3000000원
총 지출: 190000원
잔액: 2810000원
예산: 200000원 (사용률 95.0%)
[주의] 예산의 95.0%를 사용했습니다. (남은 예산 10000원)
[권장] 지출 1위 'rent' 부터 줄이거나, 남은 기간 지출을 계획하세요.

지출 TOP 3
1) rent 150000원
2) transport 25000원
3) food 15000원

$ python -m budget_app budget set --month 2026-11 --amount 150000
[저장 완료] 2026-11 예산 150000원

$ python -m budget_app summary --month 2026-11 --top 3
[2026-11 요약]
총 수입: 3000000원
총 지출: 190000원
잔액: 2810000원
예산: 150000원 (사용률 126.7%)
[경고] 예산을 40000원 초과했습니다!
[권장] 지출 1위 'rent' 부터 줄이거나, 예산 조정: budget set --month 2026-11 --amount <새 금액>

지출 TOP 3
1) rent 150000원
2) transport 25000원
3) food 15000원
```

### 6. update

```text
$ python -m budget_app update --id TX-000003 --amount 25000 --memo 택시
[수정 완료] id=TX-000003
TX-000003 | 2026-11-12 | expense | transport | 25000 | 택시
$ echo $?
0

$ python -m budget_app update --id TX-999999 --amount 1
[오류] 없는 데이터입니다: id=TX-999999
[힌트] python -m budget_app list 로 id 를 확인하세요.
$ echo $?
1
```

### 7. delete

```text
$ python -m budget_app delete --id TX-000005
[삭제 완료] id=TX-000005
$ echo $?
0

$ python -m budget_app delete --id TX-000005
[오류] 없는 데이터입니다: id=TX-000005
[힌트] python -m budget_app list 로 id 를 확인하세요.
$ echo $?
1
```

### 8. export

```text
$ python -m budget_app export --out export.csv --month 2026-11
[완료] export.csv (4 records)

$ cat export.csv
date,type,category,amount,memo,tags
2026-11-15,expense,food,15000,점심,meal
2026-11-14,income,salary,3000000,월급,
2026-11-12,expense,transport,25000,택시,
2026-11-01,expense,rent,150000,월세,"fixed,home"

$ python -m budget_app export --out export.csv
[오류] 내보낼 기간 조건이 없습니다.
[힌트] --month YYYY-MM 또는 --from/--to YYYY-MM-DD 를 지정하세요.
$ echo $?
1
```

### 9. category

```text
$ python -m budget_app category add --name hobby
[저장 완료] category=hobby

$ python -m budget_app category list
- food
- transport
- rent
- salary
- etc
- hobby

$ python -m budget_app category remove --name food
[오류] 사용 중인 카테고리는 삭제할 수 없습니다: food
[힌트] 대체 카테고리로 옮긴 뒤 삭제: category remove --name food --replace-with <카테고리> (사용 거래 확인: search --category food)
$ echo $?
1

$ python -m budget_app category remove --name food --replace-with etc
[이동 완료] food → etc (1건)
[삭제 완료] category=food
$ echo $?
0

$ python -m budget_app search --category etc
TX-000001 | 2026-11-15 | expense | etc | 15000 | 점심 | meal

$ python -m budget_app category list
- transport
- rent
- salary
- etc
- hobby
```

## import / export CSV 스키마

공통: UTF-8, 헤더 포함

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표(,) 구분 문자열 (CSV 안에서는 따옴표로 감쌈) |

**export 결과 헤더 (항상 첫 줄, 이 순서 고정):**

```csv
date,type,category,amount,memo,tags
```

- `export --out <파일>` 실행 시 해당 파일을 **새로 생성(이미 있으면 덮어씀)** 하고, 조건에 맞는 거래가 0건이어도 위 헤더 한 줄은 항상 씁니다.
- 인코딩 UTF-8(BOM 없음), 줄바꿈 CRLF(csv 모듈 기본), 정렬은 최신순입니다. id 컬럼은 포함하지 않습니다.
- export 결과 파일은 그대로 `import --from` 에 넣을 수 있습니다(같은 스키마).

예시 (`export --out export.csv --month 2026-11` 결과):

```csv
date,type,category,amount,memo,tags
2026-11-15,expense,food,15000,점심,meal
2026-11-14,income,salary,3000000,월급,
2026-11-01,expense,rent,150000,월세,"fixed,home"
```

import 는 위 헤더 중 `date,type,category,amount` 가 필수이며, 없으면 오류로 종료합니다. UTF-8 BOM 이 붙은 파일(엑셀 저장)도 읽을 수 있습니다(`utf-8-sig`).

id 는 import 시 새로 발급되므로 CSV 에 포함하지 않습니다.

### import 의 부분 적용과 롤백 (반드시 읽어 주세요)

> **기본 `import` 는 "부분 적용" 이며 자동 롤백이 없습니다.**
> 검증에 실패한 행(형식 오류, 미등록 카테고리 등)만 건너뛰고 **나머지 행은 즉시 저장**됩니다.
> 파일 전체가 다 들어가거나 아예 안 들어가야 한다면 **`--atomic`** 을 쓰세요.

| | 기본 `import --from x.csv` (부분 적용) | `import --from x.csv --atomic` (전부 아니면 전무) |
| --- | --- | --- |
| 잘못된 행이 있을 때 | 그 행만 `[건너뜀] N행: 사유` 출력, 나머지는 저장. 종료 코드 0 | **아무것도 저장하지 않음.** 잘못된 행 목록 출력, 종료 코드 1 |
| 처리 방식 | 검증하면서 바로 거래 파일에 이어 씀(append) | ① 전체 행 검증만 → ② 통과하면 기존+신규를 임시 파일에 쓰고 `os.replace` 로 한 번에 교체 |
| 도중에 중단(Ctrl+C, 디스크 오류, 강제 종료) | **그때까지 쓴 행은 남음.** 강제 종료·전원 차단이면 마지막 줄이 반쯤 쓰일 수 있음 → 다음 실행 때 `N번째 줄이 손상되었습니다` 오류 | **원본 파일 그대로.** 임시 파일만 지워짐 |
| 비용 | CSV 1회 읽기 + 추가분만 쓰기 | CSV 2회 읽기 + 기존 거래 전체 재작성 (실측: 10만 건 보유 상태에서 1만 행 import 0.63초 → 1.28초) |
| 언제 쓰나 | 일부 잘못된 행이 있어도 나머지는 넣고 싶을 때, 대용량 | 은행 내역처럼 빠짐없이 들어가야 하는 파일, 처음 이전할 때 |

부분 적용 결과를 되돌리는 방법 (기본 모드):
- 출력의 id 범위가 **이번 import 로 추가된 거래 전부**입니다(id 는 연속 발급).
  ```text
  [완료] imported=4, skipped=1 (id TX-000002 ~ TX-000005)
  [안내] 부분 적용: 위 행만 빠지고 나머지는 이미 저장되었습니다. 되돌리려면 위 id 범위를 delete 하세요.
  ```
  ```bash
  for i in 2 3 4 5; do python -m budget_app delete --id "TX-$(printf %06d $i)"; done
  ```
- 중단으로 마지막 줄이 깨졌다면, 오류 메시지의 줄 번호에 해당하는 줄을 `data/transactions.jsonl` 에서 지운 뒤 다시 실행하세요.
- 가장 안전한 방법: 큰 import 전에 `data/` 폴더를 복사해 두거나(`cp -r data data.bak`) `--atomic` 을 쓰세요.

실제 실행 예:

```text
$ python -m budget_app import --from mixed.csv --atomic
[오류] 잘못된 행 2개가 있어 아무것도 가져오지 않았습니다 (--atomic).
  - 4행: 존재하지 않는 카테고리입니다: 'nope'
  - 5행: 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[힌트] 해당 행을 고친 뒤 다시 실행하거나, 잘못된 행만 건너뛰려면 --atomic 없이 실행하세요.
$ echo $?
1
$ python -m budget_app list
[결과 없음] 조건에 맞는 거래가 없습니다.

$ python -m budget_app import --from mixed.csv
[건너뜀] 4행: 존재하지 않는 카테고리입니다: 'nope'
[건너뜀] 5행: 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[완료] imported=2, skipped=2 (id TX-000001 ~ TX-000002)
[안내] 부분 적용: 위 행만 빠지고 나머지는 이미 저장되었습니다. 되돌리려면 위 id 범위를 delete 하세요.

$ python -m budget_app import --from good.csv --atomic
[완료] imported=2, skipped=0 (id TX-000003 ~ TX-000004)
```

이 동작들은 `tests/test_commands.py::TestImportAtomic` 이 검증합니다. 그중 두 테스트는 쓰는 도중에 `KeyboardInterrupt` 를 일으켜 중단을 흉내 냅니다.
- `--atomic` 은 원본이 바이트 단위로 그대로이고 임시 파일도 남지 않는지 확인합니다.
- 기본 모드는 중단 전까지 쓴 행이 남는지(문서화된 동작) 확인합니다.

## 대량 데이터 성능 (측정값)

측정 스크립트: [scripts/benchmark.py](scripts/benchmark.py) — 임시 폴더에 거래 N건을 만들어 측정합니다(`./data` 미사용).

```bash
python scripts/benchmark.py                 # 100,000건
python scripts/benchmark.py --rows 1000000  # 1,000,000건
```

측정 환경: macOS, Apple M1 Pro, Python 3.9.6, 내장 SSD. 값은 환경마다 다르므로 비율로 보세요.
생성 데이터: 2022-01-01 ~ 2026-11-22(최근 5년) 사이 무작위 날짜, 시드 42 고정이라 매번 같은 데이터가 만들어집니다.

### 1) 명령별 소요 시간 — 건수에 정비례(O(N))

| 명령 | 10만 건 (12.8 MiB) | 100만 건 (128.5 MiB) |
| --- | ---: | ---: |
| `list --limit 10` | 0.40초 | 4.01초 |
| `search --q 점심 --limit 10` | 0.41초 | 4.06초 |
| `search --category food` (결과 전체 정렬) | 0.42초 | 4.37초 |
| `summary --month 2026-11` | 0.39초 | 4.08초 |
| `export --from 2022-01-01 --to 2026-11-22` (전체 내보내기) | 0.63초 | 6.50초 |
| `add` (1건 추가, id 발급용 전체 스캔 포함) | 0.41초 | 4.22초 |
| `update` / `delete` (전체 재작성) | 0.80초 | 7.72초 |
| `import` 1만 행 (배치 쓰기, id 발급 스캔 포함) | 0.63초 | 4.42초 |

### 2) 메모리 — 스트리밍이라 건수와 무관하게 일정

| 측정 | 10만 건 | 100만 건 |
| --- | ---: | ---: |
| `svc.latest(10)` 파이썬 객체 최대 메모리 (tracemalloc) | 0.05 MiB | 0.05 MiB |
| 비교: `list(repo.iter_all())` 로 전체 로드했다면 | 62.2 MiB | 587.3 MiB |
| `python -m budget_app list --limit 3` 프로세스 최대 RSS (`/usr/bin/time -l`) | 15.3 MB | 15.2 MB |

데이터가 10배 늘어도 메모리는 그대로입니다. `heapq.nlargest(limit, 제너레이터)` 가 상위 N건만 유지하기 때문입니다.
(예외: `search` 에 `--limit` 을 주지 않으면 결과 전체를 정렬하므로 **매칭 건수만큼** 메모리를 씁니다. 결과가 많을 때는 `--limit` 을 쓰세요.)

### 3) 버퍼 크기 — 차이 없음, 기본값(8 KiB) 유지 권장

| `open(..., buffering=)` | 읽기+JSON 파싱 (100만 건) | 파싱+쓰기 (100만 건) |
| ---: | ---: | ---: |
| 4 KiB | 1.992초 | 5.347초 |
| **8 KiB (기본값 `io.DEFAULT_BUFFER_SIZE`)** | **2.014초** | **5.554초** |
| 64 KiB | 1.996초 | 5.448초 |
| 1 MiB | 2.055초 | 5.350초 |

읽기는 최대 3%, 쓰기는 최대 4% 차이이고, 버퍼가 클수록 빨라지는 경향도 없습니다(측정 잡음 수준). 10만 건에서는 읽기 0.5%, 쓰기 2% 이내였습니다. 그래서 코드는 **기본 버퍼를 그대로** 씁니다.
버퍼를 키워도 빨라지지 않는 이유는 병목이 디스크 I/O 가 아니라 **CPU(JSON 파싱 + 객체 생성)** 이기 때문입니다.
`/usr/bin/time -l` 결과 100만 건 `list` 에서 user 4.05초, sys(커널 I/O) 0.07초였습니다.
(네트워크 드라이브처럼 I/O 가 느린 저장소라면 64 KiB~1 MiB 가 도움이 될 수 있으니 위 스크립트로 직접 측정하세요.)

### 4) 프로파일링 방법 — 어디서 시간이 드는가

```bash
# 함수별 누적 시간 (표준 라이브러리 cProfile)
python -m cProfile -s tottime -m budget_app list --limit 3 | head -20
# 프로세스 시간/최대 메모리 (macOS: -l, Linux: /usr/bin/time -v)
/usr/bin/time -l python -m budget_app list --limit 3
# 명령/대량 처리의 소요 시간 로그 (@timed, @log_call)
python -m budget_app --verbose list --limit 3
```

10만 건 `list --limit 3` 의 cProfile 결과 요약 (총 0.59초):

| 구간 | 함수 | 시간 | 비율 |
| --- | --- | ---: | ---: |
| JSON 파싱 | `json.loads` | 0.25초 | 약 42% |
| 객체 생성 | `Transaction.from_dict` + dataclass `__init__` | 0.19초 | 약 33% |
| 파일 줄 읽기 + 제너레이터 | `JsonlFile.iter_records` 자체 | 0.05초 | 약 9% |
| 상위 N 유지 | `heapq.nlargest` + `_newest_key` | 0.04초 | 약 6% |

### 5) 시나리오별 병목 분석 (10만 건)

각 명령을 cProfile 로 측정해 "파일을 몇 번 훑는가(스캔 횟수)" 와 "시간이 어디서 쓰이는가" 를 정리했습니다.
N = 거래 건수. 공통 바탕 비용은 **한 줄당 약 4µs** (JSON 파싱 42% + `Transaction` 생성 33% + 줄 읽기 9%, 위 4) 표)입니다.

| 시나리오 | 10만 건 시간 | 스캔/쓰기 횟수 | 병목 (측정 근거) | 분류 |
| --- | ---: | --- | --- | --- |
| `list`, `search`, `summary` | 0.39~0.42초 | 읽기 1회(N) | 전 줄을 파싱해 `Transaction` 을 만든 뒤 걸러냄. 조건에 안 맞는 줄도 객체 생성 비용을 냄 | CPU |
| `export` | 0.63초 | 읽기 1회 + CSV 쓰기 | 위 + CSV 직렬화 | CPU |
| `add` | 0.41초 | 읽기 1회(N) + 추가 1줄 | **`next_number()` 가 id 발급만을 위해 전체를 스캔.** 실제 저장(append)은 1ms 미만 | CPU (불필요한 스캔) |
| `update`, `delete` | 0.80초 | 읽기 약 1.5회 + 쓰기 1회(N) | ① `_require()`(`repo.get`)가 대상 id 까지 스캔(평균 N/2, 중간 id 기준 0.28초) ② 원자적 교체를 위해 전체를 다시 파싱·직렬화(`json.dumps` 10만 회 ≈ 0.34초, 프로파일러 포함) | CPU (재작성) |
| `category remove` (사용 중) | 1ms 이하 | 읽기 일부 | `any()` 가 첫 사용 거래에서 멈춤 | – |
| `category remove --replace-with` | 약 0.8초 | 읽기 1회 + 쓰기 1회 | update 와 같은 전체 재작성 | CPU (재작성) |
| `import` 1만 행 (개선 전) | 0.94초 | **행마다 파일 2번 열기** (2만 회) | 프로파일: 거래 파일 `append` 50%, 행마다 `categories.jsonl` 다시 읽는 `check_category` 33% | **I/O 호출 횟수** |
| `import` 1만 행 (개선 후) | **0.22초** | 카테고리 1회 + 거래 파일 1회 열기 | 행 검증(`parse_*`) + `json.dumps` | CPU |

### 6) 적용한 개선: import 배치 처리

| 측정 (빈 data 폴더에 import, 3회 중 최솟값) | 개선 전 (커밋 `a8220d5`) | 개선 후 | 효과 |
| --- | ---: | ---: | ---: |
| 1만 행 | 0.935초 | 0.216초 | 4.3배 |
| 10만 행 | 9.338초 | 2.140초 | 4.4배 |

- 카테고리 목록을 import 시작 시 **한 번만 읽어 `set`** 으로 검사합니다(`check_category(name, known)`). 이전에는 행마다 파일을 다시 읽었습니다.
- 검증을 통과한 행을 제너레이터로 흘려 **파일을 한 번만 열고 이어 씁니다**(`TransactionRepository.add_many` → `JsonlFile.append_many`). 메모리는 여전히 행 수와 무관합니다.
- 결과(건수·건너뛴 행·id 발급 순서)는 이전과 같습니다. 기존 import 테스트와 동시 실행 테스트가 그대로 통과합니다.

### 7) 남은 병목의 개선안 (제안, 미적용)

현재 규모(10만 건에 1초 이내)에서는 필요하지 않아 적용하지 않았습니다. 규모가 커질 때의 순서대로 적었습니다.

| 우선순위 | 대상 | 개선안 | 예상 효과 (10만 건) | 대가 / 주의점 |
| --- | --- | --- | --- | --- |
| 1 | `add`, `import` 의 id 발급 | **id 카운터 파일** `data/meta.json` 에 `{"next_id": 100001}` 저장. `@locked` 안에서 읽고 +1 해서 씀. 파일이 없거나 깨지면 지금처럼 전체 스캔으로 복구 | `add` 0.41초 → 수 ms (O(N) → O(1)) | 파일 4개째. 데이터 파일과 어긋나지 않게 반드시 잠금 안에서 함께 갱신 |
| 2 | `search`/`summary`/`export` | **객체 생성 전에 dict 단계에서 거르기**: 날짜·카테고리 조건을 `json.loads` 결과(dict)에서 먼저 보고, 맞는 줄만 `Transaction.from_dict` | 조건이 좁을수록 최대 약 33% 감소 (객체 생성 비용) | 필터 로직이 dict/객체 두 곳에 생기지 않게 정리 필요 |
| 3 | `summary`, 월 단위 `export` | **월별 파일 분할** `transactions/2026-11.jsonl`. 월 조건이면 해당 파일만 읽음 | 5년치 데이터면 읽는 양 1/60 → 수 ms | `list`(전체 최신순)는 최신 월부터 역순으로 읽어야 함. update 로 날짜가 바뀌면 파일 간 이동 |
| 4 | `summary` 반복 실행 | **월별 집계 캐시** `data/summary_cache.json`. 쓰기 명령이 해당 월 캐시를 무효화 | 캐시 적중 시 O(1) | 무효화 누락 시 틀린 값이 나옴 → 쓰기 경로 전체에 적용 필요 |
| 5 | `update`/`delete` 의 id 찾기 | **id 인덱스 파일** (id → 줄 번호/바이트 오프셋) | `_require()` 스캔(평균 N/2) 제거 → 0.80초 → 약 0.5초 | 재작성 비용(N)은 남음. 재작성할 때마다 인덱스도 다시 만들어야 함 |
| 6 | `update`/`delete` 의 재작성 | **추가 전용 로그 + 주기적 압축**: 수정은 새 버전을, 삭제는 `{"id":…, "deleted":true}` 를 append 하고, 읽을 때 마지막 버전만 사용. `compact` 명령으로 정리 | 수정·삭제 O(1) | 읽기 쪽이 id 별 최신 버전을 가려야 해서 복잡해지고 메모리 사용이 늘어남 |
| 7 | 100만 건 이상 | **`sqlite3`(표준 라이브러리)** 로 전환, `date`/`category`/`id` 인덱스 | 모든 조회가 인덱스 탐색, 트랜잭션·잠금 기본 제공 | 이번 미션 조건(JSONL/CSV 파일 저장)과 맞지 않아 미적용 |

운영 팁 (코드 변경 없이):
- 대량 수정은 `update` 를 여러 번 부르지 말고 `export` → 편집 → 새 data 폴더에 `import` 하세요. `update` 1회가 전체 재작성 1회입니다.
- 결과가 많은 `search` 는 `--limit` 을 쓰세요(위 2) 참고, 메모리 일정).
- 분석 재현: `python scripts/benchmark.py` 로 시간을, `python -m cProfile -s tottime -m budget_app <명령>` 으로 병목 함수를 확인합니다.

## 구조

| 모듈 | 계층 | 책임 |
| --- | --- | --- |
| `models.py` | 모델 | `Transaction` dataclass, `AppError`, 값 검증 함수 |
| `storage.py` | 저장소 | **모든 파일 I/O**: `JsonlFile`(스트리밍 읽기/원자적 재작성), `TransactionRepository`, `CategoryStore`, `BudgetStore`, `CsvTransactionFile`(import/export CSV) |
| `service.py` | 서비스 | `BudgetService`: 추가/수정/삭제, 검색, 요약, 예산, 카테고리 규칙, CSV 입출력 |
| `decorators.py` | 공통 관심사 | 관심사별 데코레이터 4개: `@handle_errors`(예외 → [오류]/[힌트] + 종료 코드), `@log_call`(실행 로그), `@timed`(시간 측정), `@locked`(쓰기 잠금) |
| `cli.py` | CLI | argparse 파서, 대화형 입력, 화면 출력 |

- **제너레이터 스트리밍**: `JsonlFile.iter_records()`가 파일을 한 줄씩 `yield`합니다. `list --limit N`은 `heapq.nlargest`로 최신 N건만 메모리에 유지하고, summary/검색/export 도 한 줄씩 흘려보내며 처리합니다.
- **데코레이터**: 예외 처리·로그·시간 측정·잠금을 관심사별 데코레이터로 나눠, 각 함수에 try/except·로그·`with FileLock(...)` 코드를 반복하지 않고 한 줄씩 붙입니다. (아래 "데코레이터 사용법" 참고)
- **타입 힌트**: 모든 함수의 인자/반환 타입을 명시했습니다. (예: `def latest(self, limit: int) -> list[Transaction]`) `mypy --strict` 로 검사합니다(아래).

### 타입 검사 (mypy)

mypy 는 **개발할 때만 쓰는 검사 도구**입니다. 앱 실행에는 필요 없으며, 앱 코드는 여전히 표준 라이브러리만 사용합니다.

설정: [mypy.ini](mypy.ini) — `budget_app`, `tests`, `scripts` 전체를 Python 3.10 기준 **strict 모드**로 검사합니다.

```ini
[mypy]
python_version = 3.10
files = budget_app, tests, scripts
strict = True
warn_unreachable = True
pretty = True
```

실행 방법:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # mypy==1.19.1
python -m mypy                                      # mypy.ini 설정 사용
```

기대 결과 (현재 코드, 종료 코드 0):

```text
$ python -m mypy
Success: no issues found in 10 source files
$ echo $?
0
```

`strict` 는 타입 힌트 누락(`disallow_untyped_defs`), `Any` 반환, `Optional` 미처리 등을 모두 오류로 봅니다. 위 결과는 이 규칙들을 모두 통과했다는 뜻입니다.

**타입 힌트가 잡아내는 실수 예시** — 아래처럼 계약을 어기는 코드를 쓰면, 실행하기 전에 mypy 가 막습니다.

```python
svc.latest("10")                 # limit 은 int
tx = svc.repo.get("TX-000001")
print(tx.amount)                 # get() 은 Transaction | None → None 확인 필요
s = svc.summary("2026-11", 3)
s.balance = 0                    # Summary 는 frozen, balance 는 읽기 전용
```

```text
$ mypy --strict type_error_demo.py
type_error_demo.py:6: error: Argument 1 to "latest" of "BudgetService" has incompatible type "str"; expected "int"  [arg-type]
type_error_demo.py:8: error: Item "None" of "Transaction | None" has no attribute "amount"  [union-attr]
type_error_demo.py:10: error: Property "balance" defined in "Summary" is read-only  [misc]
Found 3 errors in 1 file (checked 1 source file)
$ echo $?
1
```

특히 두 번째 오류(`Transaction | None`)는 "없는 id" 처리를 빠뜨리는 실수입니다. 서비스는 이 경우를 `_require()` 로 처리해 `[오류] 없는 데이터입니다` 를 냅니다.
CI 는 push/PR 마다 `python -m mypy` 를 먼저 실행합니다.

### 데코레이터 사용법 (관심사별)

[decorators.py](budget_app/decorators.py) 는 **관심사 하나당 데코레이터 하나**로 나뉘어 있고, 필요한 것만 골라 쌓아 씁니다.
로그(`@log_call`, `@timed`)는 `--verbose` 를 줄 때만 stderr 에 `[로그]` 로 보입니다.

| 데코레이터 | 관심사 | 감싼 함수의 반환 | 적용 위치 |
| --- | --- | --- | --- |
| `@handle_errors` | 예외 처리 → `[오류]/[힌트]` 출력 + 종료 코드 | `None` → `int`(0/1/130) | `cli.run` |
| `@log_call` | 실행 로그: 시작 / 정상 종료 / 예외 종류 (예외는 다시 던짐) | 그대로 | `cli.run` |
| `@timed` | 실행 시간 측정 (예외가 나도 측정) | 그대로 | `cli.run`, `BudgetService.import_csv`, `export_csv` |
| `@locked` | 쓰기 작업 동시 실행 방지 (`data/.lock`) | 그대로 | `BudgetService` 쓰기 메서드 7개 |

**1) `@handle_errors` — 예외 처리**

```python
@handle_errors
def run(args) -> None:
    raise AppError("없는 데이터입니다: id=TX-9", "list 로 id 를 확인하세요.")

code = run(args)   # stderr: [오류] 없는 데이터입니다: id=TX-9 / [힌트] list 로 id 를 확인하세요.
                   # code == 1 (스택트레이스 없음)
```

**2) `@log_call` — 실행 로그**

```python
@log_call
def sync() -> None: ...

sync()   # [로그] sync 시작 → [로그] sync 정상 종료   (예외 시: [로그] sync 예외: ValueError 후 다시 raise)
```

**3) `@timed` — 시간 측정**

```python
class BudgetService:
    @timed
    def export_csv(self, path, month, date_from, date_to) -> int: ...

svc.export_csv(...)   # [로그] BudgetService.export_csv 소요 1.6ms  (반환값은 그대로)
```

**4) `@locked` — 쓰기 잠금** (`self.data_dir` 가 있는 객체의 메서드)

```python
class BudgetService:
    @locked
    def delete(self, tx_id: str) -> None: ...   # data/.lock 을 잡은 상태로 실행, 끝나면 해제
```

**쌓는 순서** — 위에 쓴 것이 바깥(먼저 실행)입니다. `cli.run` 은 세 개를 쌓아 씁니다.

```python
@handle_errors  # 3. 바깥: 올라온 예외를 [오류]/[힌트] + 종료 코드로 변환 (여기서 예외가 멈춤)
@log_call       # 2. 시작/종료를 기록하고, 예외는 기록한 뒤 바깥으로 다시 던짐
@timed          # 1. 안쪽: 명령 본문만의 시간 측정
def run(args: argparse.Namespace) -> None: ...
```

`@handle_errors` 가 `@log_call` 보다 안쪽에 있으면 예외가 이미 종료 코드로 바뀌어 `log_call` 이 예외를 기록하지 못합니다. 그래서 예외 처리를 가장 바깥에 둡니다.
`import_csv` 는 `@timed` 를 `@locked` 바깥에 두어, 잠금 대기 시간까지 포함해 측정합니다.

실제 출력 (`--verbose`):

```text
$ python -m budget_app --verbose import --from in.csv
[로그] run 시작
[로그] BudgetService.import_csv 소요 1.6ms
[완료] imported=2, skipped=0 (id TX-000001 ~ TX-000002)
[로그] run 소요 2.4ms
[로그] run 정상 종료
[로그] run 종료 코드 0

$ python -m budget_app --verbose delete --id TX-999999
[로그] run 시작
[로그] run 소요 0.7ms
[로그] run 예외: AppError
[오류] 없는 데이터입니다: id=TX-999999
[힌트] python -m budget_app list 로 id 를 확인하세요.
[로그] run 종료 코드 1
```

각 데코레이터는 `tests/test_commands.py::TestDecorators` 에서 단독으로 검증합니다.

### 클래스별 책임과 라이프사이클

| 클래스 | 책임 (한 줄) | 생성 | 수정 | 소멸/수명 |
| --- | --- | --- | --- | --- |
| `Transaction` (models) | 거래 1건의 **불변 값 객체** | `BudgetService._build()` 가 검증을 통과한 값으로만 생성 (add/update/import), `TransactionRepository.iter_all()` 이 파일 줄에서 복원(`from_dict`) | **수정 불가**(`frozen=True`, tags 도 tuple). update 는 새 인스턴스를 만들어 `repo.replace()` 로 파일의 줄을 교체 | 명령 1회 동안만 메모리에 존재, 영속 상태는 `transactions.jsonl` |
| `Summary` (service) | 월별 집계 결과 + 예산 단계 계산 | `BudgetService.summary()` 가 스트리밍 집계 후 생성 | 수정 불가(`frozen=True`), cli 는 읽기만 | 출력 후 폐기 (저장 안 함) |
| `AppError` (models) | 사용자에게 보여줄 오류(원인 + 힌트) | models 의 `parse_*`, service, storage 가 규칙 위반 시 `raise` | – | `@handle_errors` 가 잡아 출력하고 종료 코드 1 로 끝남 |
| `JsonlFile` (storage) | JSONL 파일 1개의 읽기/추가/원자적 재작성 | 각 Store/Repository 생성자에서 1개씩 | 파일 경로는 고정, 내용만 변경 | 명령 1회 |
| `TransactionRepository` (storage) | 거래 파일 CRUD + 스트리밍 조회 | `BudgetService.__init__` | 상태 없음(파일이 유일한 상태) | 명령 1회 |
| `CategoryStore` (storage) | 카테고리 목록 저장 | `BudgetService.__init__` (파일이 비면 기본 카테고리 생성) | 상태 없음 | 명령 1회 |
| `BudgetStore` (storage) | 월 → 예산 금액 저장 | `BudgetService.__init__` | 상태 없음 | 명령 1회 |
| `CsvTransactionFile` (storage) | import/export CSV 1개의 열기·헤더 검증·행 읽기/쓰기 | `BudgetService.import_csv / export_csv` 가 호출마다 경로로 생성 | 상태 없음 | 호출 1회 |
| `BudgetService` (service) | 검증·검색·요약·카테고리 정책·CSV 입출력 등 업무 규칙 | `cli.run()` 이 `--data-dir` 로 명령마다 1개 | 상태 없음(저장소 3개를 조합만 함) | 명령 1회 |
| `FileLock` (storage) | data 폴더 쓰기 잠금(`data/.lock`) | `@locked` 가 쓰기 메서드 호출마다 생성(`with` 블록) | – | `with` 블록이 끝나면 잠금 파일 삭제 (예외가 나도 삭제) |

핵심 원칙:
- **데이터 객체(`Transaction`, `Summary`)는 불변**, 상태는 파일에만 있습니다. 메모리 객체를 고쳐 놓고 저장을 잊는 실수가 구조적으로 생기지 않습니다.
- **검증된 `Transaction` 만 존재**: 새 거래는 반드시 `_build()` (parse_* 검증 + 카테고리 확인)를 거쳐 만들어집니다.
- **서비스/저장소는 상태가 없음**: 명령이 실행될 때마다 `BudgetService` 가 새로 만들어지고, 끝나면 사라집니다.

```python
tx = Transaction("TX-000001", "2026-11-15", "expense", "food", 15000, "점심", ("meal",))
tx.amount = 20000                           # dataclasses.FrozenInstanceError
changed = dataclasses.replace(tx, amount=20000)  # 수정 = 새 인스턴스 (tx 는 그대로)
```

(위 동작은 `tests/test_commands.py::TestModel` 이 검증합니다.)

### 계층 간 입출력 경계

```text
cli.py ──(str 원본 입력, argparse.Namespace)──▶ service.py ──(Transaction, Path)──▶ storage.py ──▶ data/*.jsonl, *.csv
   ▲                                              │  │                                  │
   │◀──── Transaction / Summary / int / tuple ────┘  └──── models.py (검증, 데이터 구조) ◀─┘
   └── decorators.handle_errors: AppError/OSError → [오류]/[힌트] + 종료 코드(int)
```

| 경계 | 들어가는 값 | 나오는 값 | 오류 |
| --- | --- | --- | --- |
| cli → service | 사용자 입력 **문자열 그대로**(`"15000"`, `"2026-11-15"`, `"meal,lunch"`) | `Transaction`, `list[Transaction]`, `Summary`, 처리 건수 `int` | `AppError` 발생 |
| service → storage | **검증이 끝난** `Transaction` / `str` / `int` | `Iterator[Transaction]`(스트리밍), `int \| None` 등 | 손상된 줄은 `AppError`, 파일 오류는 `OSError` |
| storage → 파일 | `dict[str, Any]` (JSON 한 줄) / `Transaction` (CSV 한 행) | `Iterator[dict[str, Any]]` / `Iterator[tuple[int, dict[str, str]]]` (CSV 행 번호, 원본 문자열) | CSV 파일 없음·헤더 누락은 `AppError` |
| models | 원본 `str` | 정규화된 값(`"2026-11-15"`, `15000`, `["meal"]`) | 형식 오류 시 `AppError` |
| decorators | `Callable[..., None]` | `Callable[..., int]` (종료 코드) | 예외를 잡아 출력, 밖으로 던지지 않음 |

규칙:
- 화면 입출력: 정상 출력과 `input()` 은 **cli.py**, 오류 출력(stderr)은 **decorators.py** 에서만 합니다. service/storage/models 는 `print` 하지 않고 값을 돌려주거나 `AppError` 를 던집니다.
- 파일 접근: 데이터 파일(`data/*.jsonl`)과 사용자가 지정한 CSV(`import --from`, `export --out`) 모두 **storage.py** 에서만 읽고 씁니다. service 는 경로(`Path`)만 넘기고, CSV 행 값의 검증(날짜·금액·카테고리 등 업무 규칙)만 맡습니다.

### 모듈별 public API (핵심 서명)

**models.py** — 데이터 구조와 값 검증 (I/O 없음)

```python
TYPES: tuple[str, str] = ("income", "expense")

class AppError(Exception):
    def __init__(self, message: str, hint: str = "") -> None

@dataclass(frozen=True)
class Transaction:
    id: str; date: str; type: str; category: str; amount: int
    memo: str = ""; tags: tuple[str, ...] = ()
    def to_dict(self) -> dict[str, Any]
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction

def parse_date(text: str) -> str          # "2026-11-15" 형식 검증·정규화, 실패 시 AppError
def parse_month(text: str) -> str         # "2026-11"
def parse_type(text: str) -> str          # "income" | "expense"
def parse_amount(text: str | int) -> int  # 양의 정수
def parse_tags(text: str) -> tuple[str, ...]  # "a, b" -> ("a", "b")
```

**storage.py** — 모든 파일 I/O: JSONL 데이터 파일 + import/export CSV (비즈니스 규칙 없음)

```python
DEFAULT_CATEGORIES: list[str] = ["food", "transport", "rent", "salary", "etc"]
CSV_FIELDS: list[str] = ["date", "type", "category", "amount", "memo", "tags"]
CSV_REQUIRED: tuple[str, ...] = ("date", "type", "category", "amount")
LOCK_TIMEOUT: float = 5.0

class FileLock:                                   # with FileLock(data_dir / ".lock"): ...
    def __init__(self, path: Path) -> None
    def __enter__(self) -> FileLock               # 최대 LOCK_TIMEOUT 초 대기, 초과 시 AppError
    def __exit__(self, *exc: object) -> None      # 잠금 파일 삭제

class JsonlFile:
    def __init__(self, path: Path) -> None                       # 파일 없으면 생성
    def iter_records(self) -> Iterator[dict[str, Any]]           # 한 줄씩 yield
    def append(self, record: dict[str, Any]) -> None
    def append_many(self, records: Iterable[dict[str, Any]]) -> int  # 파일 1회 열기 배치 쓰기
    def rewrite(self, records: Iterable[dict[str, Any]]) -> None # 임시 파일 + os.replace

class TransactionRepository:
    def __init__(self, data_dir: Path) -> None
    def iter_all(self) -> Iterator[Transaction]
    def get(self, tx_id: str) -> Transaction | None
    def next_number(self) -> int
    def add(self, tx: Transaction) -> None
    def add_many(self, txs: Iterable[Transaction]) -> int        # import 배치 쓰기 (append)
    def add_many_atomic(self, txs: Iterable[Transaction]) -> int # 기존+신규를 임시 파일에 쓰고 os.replace
    def replace(self, tx_id: str, new: Transaction | None) -> None  # None 이면 삭제
    def rename_category(self, old: str, new: str) -> int            # 바뀐 건수

class CategoryStore:
    def __init__(self, data_dir: Path) -> None   # 비어 있으면 DEFAULT_CATEGORIES 생성
    def list(self) -> list[str]
    def exists(self, name: str) -> bool
    def add(self, name: str) -> None
    def remove(self, name: str) -> None

class BudgetStore:
    def __init__(self, data_dir: Path) -> None
    def get(self, month: str) -> int | None
    def set(self, month: str, amount: int) -> None

class CsvTransactionFile:
    def __init__(self, path: Path) -> None
    def iter_rows(self) -> Iterator[tuple[int, dict[str, str]]]  # (행 번호, 원본 값), 파일 없음/헤더 누락 시 AppError
    def write(self, transactions: Iterable[Transaction]) -> int  # 헤더 + 행, 쓴 건수 (0건이어도 헤더)
```

**service.py** — 비즈니스 규칙 (화면 출력 없음)

```python
CAUTION_RATE: float = 80.0

@dataclass(frozen=True)
class Summary:
    month: str; income: int; expense: int; count: int
    top: list[tuple[str, int]]; budget: int | None
    @property
    def balance(self) -> int
    @property
    def usage_rate(self) -> float | None
    @property
    def budget_level(self) -> str | None   # None | "ok" | "caution" | "over"

@dataclass(frozen=True)
class ImportResult:
    imported: int; skipped: int; errors: list[str]
    first_id: str | None; last_id: str | None      # 이번에 추가된 거래의 id 범위 (연속)

class BudgetService:
    def __init__(self, data_dir: Path) -> None   # self.data_dir 를 @locked 가 사용
    # 아래 중 add/update/delete/set_budget/add_category/remove_category/import_csv 는 @locked
    def check_category(self, name: str, known: set[str] | None = None) -> str  # known: 배치용 캐시
    def add(self, date: str, type_: str, category: str, amount: str | int,
            memo: str = "", tags: str = "") -> Transaction
    def update(self, tx_id: str, date: str | None = None, type_: str | None = None,
               category: str | None = None, amount: str | None = None,
               memo: str | None = None, tags: str | None = None) -> Transaction
    def delete(self, tx_id: str) -> None
    def latest(self, limit: int) -> list[Transaction]
    def search(self, date_from: str | None = None, date_to: str | None = None,
               category: str | None = None, type_: str | None = None,
               q: str | None = None, tag: str | None = None,
               limit: int | None = None) -> list[Transaction]
    def summary(self, month: str, top: int) -> Summary
    def set_budget(self, month: str, amount: int) -> None
    def add_category(self, name: str) -> str
    def remove_category(self, name: str, replace_with: str | None = None) -> int  # 옮긴 건수
    def import_csv(self, path: Path, atomic: bool = False) -> ImportResult  # 기본 부분 적용 / atomic: 전부 아니면 전무
    def export_csv(self, path: Path, month: str | None,
                   date_from: str | None, date_to: str | None) -> int  # 내보낸 건수
```

**decorators.py** — 공통 관심사

```python
def handle_errors(func: Callable[..., None]) -> Callable[..., int]
# AppError/OSError → [오류]/[힌트] 출력 후 1, KeyboardInterrupt/EOFError → 130, 정상 → 0

def log_call(func: Callable[..., T]) -> Callable[..., T]
# 시작/정상 종료/예외 로그(--verbose), 예외는 다시 던짐

def timed(func: Callable[..., T]) -> Callable[..., T]
# 소요 시간 로그(--verbose), 반환값은 그대로

def locked(method: Callable[..., T]) -> Callable[..., T]
# self.data_dir/.lock 을 잡은 상태로 메서드 실행 (쓰기 작업의 동시 실행 방지)
```

**cli.py** — 진입점과 화면 입출력

```python
def main(argv: list[str] | None = None) -> int        # __main__.py 가 sys.exit(main())
def build_parser() -> argparse.ArgumentParser
@handle_errors
@log_call
@timed
def run(args: argparse.Namespace) -> None              # handle_errors 적용 후 -> int
def ask(prompt: str, check: Callable[[str], object]) -> str   # 유효할 때까지 재입력
def print_transactions(items: Iterable[Transaction]) -> None
def cmd_<명령>(svc: BudgetService, args: argparse.Namespace) -> None
#   cmd_add, cmd_list, cmd_search, cmd_summary, cmd_budget_set, cmd_budget_show,
#   cmd_category_add, cmd_category_list, cmd_category_remove,
#   cmd_update, cmd_delete, cmd_import, cmd_export
```
