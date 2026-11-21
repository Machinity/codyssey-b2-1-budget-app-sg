"""CLI 계층: 인자 파싱, 대화형 입력, 출력."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Iterable

from .decorators import handle_errors, log_call, timed
from .models import AppError, Transaction, parse_amount, parse_date, parse_month, parse_type
from .service import BudgetService


# ---------- 입출력 도우미 ----------
def ask(prompt: str, check: Callable[[str], object]) -> str:
    """유효한 값이 들어올 때까지 다시 묻는다."""
    while True:
        value = input(prompt)
        try:
            check(value)
            return value
        except AppError as e:
            print(f"[오류] {e.message}")
            if e.hint:
                print(f"[힌트] {e.hint}")


def print_transactions(items: Iterable[Transaction]) -> None:
    empty = True
    for t in items:
        empty = False
        print(" | ".join([t.id, t.date, f"{t.type:<7}", t.category, str(t.amount), t.memo,
                          ",".join(t.tags)]).rstrip(" |"))
    if empty:
        print("[결과 없음] 조건에 맞는 거래가 없습니다.")


# ---------- 명령 ----------
def cmd_add(svc: BudgetService, args: argparse.Namespace) -> None:
    print(f"(등록된 카테고리: {', '.join(svc.categories.list())})")
    date = ask("날짜(YYYY-MM-DD): ", parse_date)
    type_ = ask("타입(income/expense): ", parse_type)
    category = ask("카테고리: ", svc.check_category)
    amount = ask("금액(양수): ", parse_amount)
    memo = input("메모(선택): ")
    tags = input("태그(쉼표로 구분, 없으면 엔터): ")
    tx = svc.add(date, type_, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")


def cmd_list(svc: BudgetService, args: argparse.Namespace) -> None:
    print_transactions(svc.latest(args.limit))


def cmd_search(svc: BudgetService, args: argparse.Namespace) -> None:
    print_transactions(svc.search(
        date_from=parse_date(args.date_from) if args.date_from else None,
        date_to=parse_date(args.date_to) if args.date_to else None,
        category=args.category,
        type_=parse_type(args.type) if args.type else None,
        q=args.q,
        tag=args.tag,
        limit=args.limit,
    ))


def cmd_summary(svc: BudgetService, args: argparse.Namespace) -> None:
    s = svc.summary(parse_month(args.month), args.top)
    if s.count == 0:
        print(f"[데이터 없음] {s.month} 거래 내역이 없습니다.")
        return
    print(f"[{s.month} 요약]")
    print(f"총 수입: {s.income}원")
    print(f"총 지출: {s.expense}원")
    print(f"잔액: {s.balance}원")
    if s.budget is not None:
        print(f"예산: {s.budget}원 (사용률 {s.usage_rate:.1f}%)")
        top_hint = f"지출 1위 '{s.top[0][0]}' 부터 줄이거나, " if s.top else ""
        if s.budget_level == "over":
            print(f"[경고] 예산을 {s.expense - s.budget}원 초과했습니다!")
            print(f"[권장] {top_hint}예산 조정: budget set --month {s.month} --amount <새 금액>")
        elif s.budget_level == "caution":
            print(f"[주의] 예산의 {s.usage_rate:.1f}%를 사용했습니다. (남은 예산 {s.budget - s.expense}원)")
            print(f"[권장] {top_hint}남은 기간 지출을 계획하세요.")
    print(f"\n지출 TOP {args.top}")
    if not s.top:
        print("(지출 없음)")
    for i, (cat, total) in enumerate(s.top, start=1):
        print(f"{i}) {cat} {total}원")


def cmd_budget_set(svc: BudgetService, args: argparse.Namespace) -> None:
    month, amount = parse_month(args.month), parse_amount(args.amount)
    svc.set_budget(month, amount)
    print(f"[저장 완료] {month} 예산 {amount}원")


def cmd_budget_show(svc: BudgetService, args: argparse.Namespace) -> None:
    month = parse_month(args.month)
    amount = svc.budgets.get(month)
    print(f"{month} 예산: {amount}원" if amount is not None else f"[데이터 없음] {month} 예산이 설정되지 않았습니다.")


def cmd_category_add(svc: BudgetService, args: argparse.Namespace) -> None:
    name = svc.add_category(args.name if args.name is not None else input("카테고리명: "))
    print(f"[저장 완료] category={name}")


def cmd_category_list(svc: BudgetService, args: argparse.Namespace) -> None:
    for name in svc.categories.list():
        print(f"- {name}")


def cmd_category_remove(svc: BudgetService, args: argparse.Namespace) -> None:
    name = args.name if args.name is not None else input("삭제할 카테고리명: ")
    moved = svc.remove_category(name, args.replace_with)
    if args.replace_with:
        print(f"[이동 완료] {name} → {args.replace_with} ({moved}건)")
    print(f"[삭제 완료] category={name}")


def cmd_update(svc: BudgetService, args: argparse.Namespace) -> None:
    tx = svc.update(args.id, date=args.date, type_=args.type, category=args.category,
                    amount=args.amount, memo=args.memo, tags=args.tags)
    print(f"[수정 완료] id={tx.id}")
    print_transactions([tx])


def cmd_delete(svc: BudgetService, args: argparse.Namespace) -> None:
    svc.delete(args.id)
    print(f"[삭제 완료] id={args.id}")


def cmd_import(svc: BudgetService, args: argparse.Namespace) -> None:
    r = svc.import_csv(Path(args.src), atomic=args.atomic)
    for msg in r.errors:
        print(f"[건너뜀] {msg}")
    id_range = f" (id {r.first_id} ~ {r.last_id})" if r.first_id else ""
    print(f"[완료] imported={r.imported}, skipped={r.skipped}{id_range}")
    if r.skipped and not args.atomic:
        print("[안내] 부분 적용: 위 행만 빠지고 나머지는 이미 저장되었습니다. 되돌리려면 위 id 범위를 delete 하세요.")


def cmd_export(svc: BudgetService, args: argparse.Namespace) -> None:
    count = svc.export_csv(
        Path(args.out),
        month=parse_month(args.month) if args.month else None,
        date_from=parse_date(args.date_from) if args.date_from else None,
        date_to=parse_date(args.date_to) if args.date_to else None,
    )
    print(f"[완료] {args.out} ({count} records)")


# ---------- 파서 ----------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m budget_app", description="나만의 용돈 기입장")
    p.add_argument("--data-dir", default="./data", help="데이터 저장 폴더 (기본: ./data)")
    p.add_argument("--verbose", action="store_true", help="실행 로그(소요 시간) 출력")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    sub.add_parser("add", help="거래 추가 (대화형)").set_defaults(func=cmd_add)

    s = sub.add_parser("list", help="거래 목록 (최신순)")
    s.add_argument("--limit", type=int, default=10, help="출력 개수 (기본 10)")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("search", help="조건 검색 (최신순)")
    s.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    s.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    s.add_argument("--category")
    s.add_argument("--type", help="income / expense")
    s.add_argument("--q", help="메모 키워드")
    s.add_argument("--tag")
    s.add_argument("--limit", type=int, help="최대 출력 개수")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("summary", help="월별 요약")
    s.add_argument("--month", required=True, help="YYYY-MM")
    s.add_argument("--top", type=int, default=3, help="지출 TOP N (기본 3)")
    s.set_defaults(func=cmd_summary)

    b = sub.add_parser("budget", help="월 예산 설정/조회").add_subparsers(dest="action", required=True)
    s = b.add_parser("set", help="월 예산 설정")
    s.add_argument("--month", required=True, help="YYYY-MM")
    s.add_argument("--amount", required=True, help="예산 금액 (양수)")
    s.set_defaults(func=cmd_budget_set)
    s = b.add_parser("show", help="월 예산 조회")
    s.add_argument("--month", required=True, help="YYYY-MM")
    s.set_defaults(func=cmd_budget_show)

    c = sub.add_parser("category", help="카테고리 관리").add_subparsers(dest="action", required=True)
    s = c.add_parser("add", help="카테고리 추가 (--name 생략 시 대화형)")
    s.add_argument("--name")
    s.set_defaults(func=cmd_category_add)
    c.add_parser("list", help="카테고리 목록").set_defaults(func=cmd_category_list)
    s = c.add_parser("remove", help="카테고리 삭제 (사용 중이면 거부, --replace-with 로 대체 후 삭제)")
    s.add_argument("--name")
    s.add_argument("--replace-with", help="사용 중인 거래를 옮길 대체 카테고리")
    s.set_defaults(func=cmd_category_remove)

    s = sub.add_parser("update", help="거래 수정 (옵션 방식)")
    s.add_argument("--id", required=True)
    s.add_argument("--date")
    s.add_argument("--type")
    s.add_argument("--category")
    s.add_argument("--amount")
    s.add_argument("--memo")
    s.add_argument("--tags", help="쉼표 구분")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("delete", help="거래 삭제")
    s.add_argument("--id", required=True)
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("import", help="CSV 가져오기 (기본: 잘못된 행만 건너뛰는 부분 적용)")
    s.add_argument("--from", dest="src", required=True, help="CSV 파일 경로")
    s.add_argument("--atomic", action="store_true",
                   help="전부 아니면 전무: 잘못된 행이 하나라도 있으면 아무것도 가져오지 않음")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("export", help="CSV 내보내기 (--month 또는 --from/--to 필수)")
    s.add_argument("--out", required=True, help="출력 CSV 경로")
    s.add_argument("--month", help="YYYY-MM")
    s.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    s.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    s.set_defaults(func=cmd_export)
    return p


@handle_errors  # 바깥: 예외 → [오류]/[힌트] + 종료 코드
@log_call       # 가운데: 시작/종료/예외 로그 (예외는 다시 던짐)
@timed          # 안쪽: 명령 자체의 소요 시간
def run(args: argparse.Namespace) -> None:
    svc = BudgetService(Path(args.data_dir))
    args.func(svc, args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)  # 인자 오류 시 argparse 가 exit 2
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="[로그] %(message)s")
    return run(args)
