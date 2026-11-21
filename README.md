# 나만의 용돈 기입장 (budget_app)

표준 라이브러리만 사용하는 콘솔 가계부입니다. (Python 3.10 이상)

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

## 저장 파일 위치 / 형식

저장 포맷은 **JSONL**(한 줄에 JSON 객체 하나, UTF-8)입니다. 파일이 없으면 첫 실행 때 자동 생성됩니다.

| 파일 | 한 줄 예시 |
| --- | --- |
| `data/transactions.jsonl` | `{"id": "TX-000001", "date": "2024-01-15", "type": "expense", "category": "food", "amount": 15000, "memo": "점심", "tags": ["meal"]}` |
| `data/categories.jsonl` | `{"name": "food"}` |
| `data/budgets.jsonl` | `{"month": "2024-01", "amount": 500000}` |

- 카테고리 파일이 비어 있으면 기본 카테고리(`food, transport, rent, salary, etc`)를 자동 생성합니다. (안 A)
- update/delete/카테고리 삭제/예산 설정은 임시 파일에 전체를 다시 쓴 뒤 `os.replace`로 원자적 교체합니다.

## 주요 명령 예시

```bash
# 거래 추가 (대화형)
python -m budget_app add
# 날짜(YYYY-MM-DD): 2024-01-15
# 타입(income/expense): expense
# 카테고리: food
# 금액(양수): 15000
# 메모(선택): 점심
# 태그(쉼표로 구분, 없으면 엔터): meal
# [저장 완료] id=TX-000001

# 목록 (최신순, 기본 10개)
python -m budget_app list --limit 3

# 검색 (조건은 모두 선택, AND 결합, 최신순)
python -m budget_app search --from 2024-01-01 --to 2024-01-31 --category food --type expense --q 점심 --tag meal

# 월별 요약 + 예산
python -m budget_app budget set --month 2024-01 --amount 500000
python -m budget_app budget show --month 2024-01
python -m budget_app summary --month 2024-01 --top 3

# 카테고리 (--name 생략 시 대화형 입력)
python -m budget_app category add --name hobby
python -m budget_app category list
python -m budget_app category remove --name hobby   # 사용 중인 카테고리는 삭제 거부

# 수정 (옵션 방식으로 고정: 준 옵션만 변경)
python -m budget_app update --id TX-000001 --amount 20000 --memo 저녁 --tags meal,dinner

# 삭제
python -m budget_app delete --id TX-000001

# 가져오기 / 내보내기
python -m budget_app import --from import.csv
python -m budget_app export --out export.csv --month 2024-01
python -m budget_app export --out export.csv --from 2024-01-01 --to 2024-03-31
```

- `update`는 **옵션 방식(안 A)** 으로 고정입니다: `update --id <id> [--date] [--type] [--category] [--amount] [--memo] [--tags]`
- 없는 id 로 update/delete 하면 "없는 데이터" 오류를 출력하고 종료 코드 1을 반환합니다.
- `export`는 `--month` 또는 `--from`/`--to` 중 하나 이상이 필수입니다.

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

```csv
date,type,category,amount,memo,tags
2024-01-14,income,salary,3000000,월급,
2024-01-15,expense,food,15000,점심,"meal,lunch"
```

import 시 검증에 실패한 행(형식 오류, 미등록 카테고리 등)은 건너뛰고 행 번호와 이유를 출력합니다.
id 는 import 시 새로 발급되므로 CSV 에 포함하지 않습니다.

## 구조

| 모듈 | 계층 | 책임 |
| --- | --- | --- |
| `models.py` | 모델 | `Transaction` dataclass, `AppError`, 값 검증 함수 |
| `storage.py` | 저장소 | `JsonlFile`(스트리밍 읽기/원자적 재작성), `TransactionRepository`, `CategoryStore`, `BudgetStore` |
| `service.py` | 서비스 | `BudgetService`: 추가/수정/삭제, 검색, 요약, 예산, 카테고리 규칙, CSV 입출력 |
| `decorators.py` | 공통 관심사 | `@cli_command`: 예외 → [오류]/[힌트] 변환, 종료 코드, 실행 시간 로그 |
| `cli.py` | CLI | argparse 파서, 대화형 입력, 화면 출력 |

- **제너레이터 스트리밍**: `JsonlFile.iter_records()`가 파일을 한 줄씩 `yield`합니다. `list --limit N`은 `heapq.nlargest`로 최신 N건만 메모리에 유지하고, summary/검색/export 도 한 줄씩 흘려보내며 처리합니다.
- **데코레이터**: 각 명령에서 try/except 와 로그 코드를 반복하지 않도록 `@cli_command` 한 곳에 모았습니다.
- **타입 힌트**: 모든 함수의 인자/반환 타입을 명시했습니다. (예: `def latest(self, limit: int) -> list[Transaction]`)
