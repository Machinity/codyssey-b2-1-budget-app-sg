#!/usr/bin/env bash
# 종료 코드 규약(0 정상 / 1 오류 / 2 인자 오류 / 130 입력 취소)을 실제 프로세스로 검증한다.
# 사용법: bash scripts/check_exit_codes.sh   (저장소 루트에서 실행)
# 임시 폴더에서 실행(데이터는 임시 폴더/data)하므로 ./data 는 건드리지 않는다.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export PYTHONPATH="$ROOT"
cd "$WORK"

fail=0

# check <기대 코드> <설명> <stdin 내용> <인자...>
check() {
  local expected="$1" desc="$2" stdin="$3"
  shift 3
  local out actual
  out="$(printf '%b' "$stdin" | "$PY" -m budget_app "$@" 2>&1)"
  actual=$?
  if [ "$actual" -eq "$expected" ]; then
    printf 'PASS  exit=%-3s (expected %-3s)  $ python -m budget_app %s   # %s\n' "$actual" "$expected" "$*" "$desc"
  else
    printf 'FAIL  exit=%-3s (expected %-3s)  $ python -m budget_app %s   # %s\n' "$actual" "$expected" "$*" "$desc"
    printf '%s\n' "$out" | sed 's/^/      | /'
    fail=1
  fi
}

check 0   "add (정상)"               '2024-01-15\nexpense\nfood\n15000\n점심\nmeal\n' add
check 0   "list (정상)"              '' list --limit 5
check 0   "budget set (정상)"        '' budget set --month 2024-01 --amount 500000
check 0   "summary (정상)"           '' summary --month 2024-01
check 0   "export (정상)"            '' export --out out.csv --month 2024-01
check 1   "delete 없는 id"           '' delete --id TX-999999
check 1   "export 기간 조건 없음"    '' export --out x.csv
check 1   "import 파일 없음"         '' import --from none.csv
check 1   "summary 월 형식 오류"     '' summary --month 2024/01
check 1   "category 사용 중 삭제"    '' category remove --name food
check 2   "summary --month 누락"     '' summary
check 2   "list --limit 형식 오류"   '' list --limit abc
check 130 "add 입력 중 EOF(취소)"    '' add

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS"
else
  echo "SOME FAILED"
fi
exit "$fail"
