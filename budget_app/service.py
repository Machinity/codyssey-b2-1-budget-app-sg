"""서비스 계층: 비즈니스 규칙 (검증, 검색, 요약, 가져오기/내보내기)."""
from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .models import (
    AppError,
    Transaction,
    parse_amount,
    parse_date,
    parse_tags,
    parse_type,
)
from .decorators import locked, timed
from .storage import BudgetStore, CategoryStore, CsvTransactionFile, TransactionRepository

CAUTION_RATE = 80.0  # 이 사용률(%) 이상이면 [주의]


def _newest_key(t: Transaction) -> tuple[str, str]:
    return (t.date, t.id)


@dataclass(frozen=True)
class Summary:
    """월별 요약 결과 (불변). BudgetService.summary() 가 만들고 cli 가 읽기만 한다."""

    month: str
    income: int
    expense: int
    count: int
    top: list[tuple[str, int]]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def usage_rate(self) -> float | None:
        return None if self.budget is None else self.expense / self.budget * 100

    @property
    def budget_level(self) -> str | None:
        """예산 알림 단계: None(예산 없음) / ok(<80%) / caution(80~100%) / over(>100%)."""
        rate = self.usage_rate
        if rate is None:
            return None
        if self.expense > (self.budget or 0):
            return "over"
        return "caution" if rate >= CAUTION_RATE else "ok"


@dataclass(frozen=True)
class ImportResult:
    """import 결과 (불변). first_id~last_id 는 이번에 추가된 거래의 id 범위(연속)."""

    imported: int
    skipped: int
    errors: list[str]
    first_id: str | None
    last_id: str | None


class BudgetService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir  # @locked 가 data_dir/.lock 을 잠근다
        self.repo = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        self.budgets = BudgetStore(data_dir)

    # ---------- 검증 ----------
    def check_category(self, name: str, known: set[str] | None = None) -> str:
        """등록된 카테고리인지 확인한다. known 을 주면 파일 대신 그 집합으로 확인(배치용)."""
        name = name.strip()
        exists = name in known if known is not None else self.categories.exists(name)
        if not exists:
            raise AppError(
                f"존재하지 않는 카테고리입니다: {name!r}",
                f"등록된 카테고리: {', '.join(self.categories.list())} "
                f"(새로 등록: python -m budget_app category add --name {name})",
            )
        return name

    def _build(self, tx_id: str, date: str, type_: str, category: str,
               amount: str | int, memo: str = "", tags: str = "",
               known: set[str] | None = None) -> Transaction:
        return Transaction(
            id=tx_id,
            date=parse_date(date),
            type=parse_type(type_),
            category=self.check_category(category, known),
            amount=parse_amount(amount),
            memo=memo.strip(),
            tags=parse_tags(tags),
        )

    @staticmethod
    def _make_id(number: int) -> str:
        return f"TX-{number:06d}"

    # ---------- 거래 CRUD ----------
    @locked  # 쓰기 작업: 동시 실행 방지
    def add(self, date: str, type_: str, category: str, amount: str | int,
            memo: str = "", tags: str = "") -> Transaction:
        tx = self._build(self._make_id(self.repo.next_number()), date, type_, category, amount, memo, tags)
        self.repo.add(tx)
        return tx

    def _require(self, tx_id: str) -> Transaction:
        tx = self.repo.get(tx_id)
        if tx is None:
            raise AppError(f"없는 데이터입니다: id={tx_id}", "python -m budget_app list 로 id 를 확인하세요.")
        return tx

    @locked  # 쓰기 작업: 동시 실행 방지
    def update(self, tx_id: str, date: str | None = None, type_: str | None = None,
               category: str | None = None, amount: str | None = None,
               memo: str | None = None, tags: str | None = None) -> Transaction:
        if all(v is None for v in (date, type_, category, amount, memo, tags)):
            raise AppError("수정할 필드가 없습니다.", "예: update --id TX-000001 --amount 20000")
        old = self._require(tx_id)
        new = self._build(
            tx_id,
            date if date is not None else old.date,
            type_ if type_ is not None else old.type,
            category if category is not None else old.category,
            amount if amount is not None else old.amount,
            memo if memo is not None else old.memo,
            tags if tags is not None else ",".join(old.tags),
        )
        self.repo.replace(tx_id, new)
        return new

    @locked  # 쓰기 작업: 동시 실행 방지
    def delete(self, tx_id: str) -> None:
        self._require(tx_id)
        self.repo.replace(tx_id, None)

    # ---------- 조회 ----------
    def latest(self, limit: int) -> list[Transaction]:
        """스트리밍하면서 최신 limit 개만 힙에 유지한다."""
        return heapq.nlargest(limit, self.repo.iter_all(), key=_newest_key)

    def _filter(self, date_from: str | None, date_to: str | None, category: str | None,
                type_: str | None, q: str | None, tag: str | None) -> Iterator[Transaction]:
        for t in self.repo.iter_all():
            if date_from and t.date < date_from:
                continue
            if date_to and t.date > date_to:
                continue
            if category and t.category != category:
                continue
            if type_ and t.type != type_:
                continue
            if q and q.lower() not in t.memo.lower():
                continue
            if tag and tag not in t.tags:
                continue
            yield t

    def search(self, date_from: str | None = None, date_to: str | None = None,
               category: str | None = None, type_: str | None = None,
               q: str | None = None, tag: str | None = None,
               limit: int | None = None) -> list[Transaction]:
        matches = self._filter(date_from, date_to, category, type_, q, tag)
        if limit is not None:
            return heapq.nlargest(limit, matches, key=_newest_key)
        return sorted(matches, key=_newest_key, reverse=True)

    def summary(self, month: str, top: int) -> Summary:
        income = expense = count = 0
        by_cat: dict[str, int] = defaultdict(int)
        for t in self.repo.iter_all():
            if not t.date.startswith(month):
                continue
            count += 1
            if t.type == "income":
                income += t.amount
            else:
                expense += t.amount
                by_cat[t.category] += t.amount
        top_list = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:top]
        return Summary(month, income, expense, count, top_list, self.budgets.get(month))

    # ---------- 예산 ----------
    @locked  # 쓰기 작업: 동시 실행 방지
    def set_budget(self, month: str, amount: int) -> None:
        self.budgets.set(month, amount)

    # ---------- 카테고리 ----------
    @locked  # 쓰기 작업: 동시 실행 방지
    def add_category(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise AppError("카테고리명이 비어 있습니다.", "예: food")
        if self.categories.exists(name):
            raise AppError(f"이미 존재하는 카테고리입니다: {name}", "category list 로 목록을 확인하세요.")
        self.categories.add(name)
        return name

    @locked  # 쓰기 작업: 동시 실행 방지
    def remove_category(self, name: str, replace_with: str | None = None) -> int:
        """카테고리를 삭제한다. 사용 중이면 거부하되, replace_with 를 주면
        해당 거래를 대체 카테고리로 옮긴 뒤 삭제한다. 옮긴 거래 수를 돌려준다."""
        name = self.check_category(name)
        if replace_with is None:
            if any(t.category == name for t in self.repo.iter_all()):
                raise AppError(
                    f"사용 중인 카테고리는 삭제할 수 없습니다: {name}",
                    f"대체 카테고리로 옮긴 뒤 삭제: category remove --name {name} --replace-with <카테고리>"
                    f" (사용 거래 확인: search --category {name})",
                )
            self.categories.remove(name)
            return 0
        target = self.check_category(replace_with)
        if target == name:
            raise AppError("대체 카테고리가 삭제할 카테고리와 같습니다.", "다른 카테고리를 지정하세요.")
        moved = self.repo.rename_category(name, target)
        self.categories.remove(name)
        return moved

    # ---------- 가져오기/내보내기 ----------
    @timed  # 대량 처리: 소요 시간 로그
    @locked  # 쓰기 작업: 동시 실행 방지
    def import_csv(self, path: Path, atomic: bool = False) -> ImportResult:
        """CSV 행을 검증해 등록한다.

        - 기본(부분 적용): 잘못된 행은 건너뛰고 사유를 모은다. 검증을 통과한 행은 바로 이어 쓴다(append).
          롤백 기능은 없다. 대신 결과의 first_id~last_id 로 이번에 추가된 거래를 알 수 있다.
        - atomic=True(전부 아니면 전무): 1차로 모든 행을 검증만 하고, 하나라도 틀리면 아무것도
          쓰지 않고 AppError. 모두 맞으면 기존+신규를 임시 파일에 쓴 뒤 os.replace 로 한 번에 교체한다.
          중간에 중단돼도 원본 파일은 그대로다.

        배치 처리: 카테고리 목록은 한 번만 읽고(set), 거래 파일은 한 번만 열어 스트리밍으로 쓴다.
        """
        known = set(self.categories.list())
        start = self.repo.next_number()
        errors: list[str] = []

        def valid_rows() -> Iterator[Transaction]:
            number = start
            for lineno, row in CsvTransactionFile(path).iter_rows():
                try:
                    tx = self._build(self._make_id(number), row["date"], row["type"], row["category"],
                                     row["amount"], row["memo"], row["tags"], known)
                except AppError as e:
                    errors.append(f"{lineno}행: {e.message}")
                    continue
                number += 1
                yield tx

        if atomic:
            for _ in valid_rows():  # 1차: 검증만 (아무것도 쓰지 않음)
                pass
            if errors:
                shown = "\n".join(f"  - {m}" for m in errors[:20])
                more = f"\n  ... 외 {len(errors) - 20}행" if len(errors) > 20 else ""
                raise AppError(
                    f"잘못된 행 {len(errors)}개가 있어 아무것도 가져오지 않았습니다 (--atomic).\n{shown}{more}",
                    "해당 행을 고친 뒤 다시 실행하거나, 잘못된 행만 건너뛰려면 --atomic 없이 실행하세요.",
                )
            imported = self.repo.add_many_atomic(valid_rows())  # 2차: 원자적 교체
        else:
            imported = self.repo.add_many(valid_rows())
        first = self._make_id(start) if imported else None
        last = self._make_id(start + imported - 1) if imported else None
        return ImportResult(imported, len(errors), errors, first, last)

    @timed  # 대량 처리: 소요 시간 로그
    def export_csv(self, path: Path, month: str | None, date_from: str | None, date_to: str | None) -> int:
        """기간 조건에 맞는 거래를 CSV 로 내보내고 건수를 돌려준다."""
        if not (month or date_from or date_to):
            raise AppError("내보낼 기간 조건이 없습니다.", "--month YYYY-MM 또는 --from/--to YYYY-MM-DD 를 지정하세요.")
        matches = (t for t in self._filter(date_from, date_to, None, None, None, None)
                   if not month or t.date.startswith(month))
        return CsvTransactionFile(path).write(matches)
