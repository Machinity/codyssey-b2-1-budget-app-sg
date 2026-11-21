"""서비스 계층: 비즈니스 규칙 (검증, 검색, 요약, 가져오기/내보내기)."""
from __future__ import annotations

import csv
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
from .storage import BudgetStore, CategoryStore, TransactionRepository

CSV_FIELDS = ["date", "type", "category", "amount", "memo", "tags"]


def _newest_key(t: Transaction) -> tuple[str, str]:
    return (t.date, t.id)


@dataclass
class Summary:
    month: str
    income: int
    expense: int
    count: int
    top: list[tuple[str, int]]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense


class BudgetService:
    def __init__(self, data_dir: Path) -> None:
        self.repo = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        self.budgets = BudgetStore(data_dir)

    # ---------- 검증 ----------
    def check_category(self, name: str) -> str:
        name = name.strip()
        if not self.categories.exists(name):
            raise AppError(
                f"존재하지 않는 카테고리입니다: {name!r}",
                f"등록된 카테고리: {', '.join(self.categories.list())} "
                f"(새로 등록: python -m budget_app category add --name {name})",
            )
        return name

    def _build(self, tx_id: str, date: str, type_: str, category: str,
               amount: str | int, memo: str = "", tags: str = "") -> Transaction:
        return Transaction(
            id=tx_id,
            date=parse_date(date),
            type=parse_type(type_),
            category=self.check_category(category),
            amount=parse_amount(amount),
            memo=memo.strip(),
            tags=parse_tags(tags),
        )

    @staticmethod
    def _make_id(number: int) -> str:
        return f"TX-{number:06d}"

    # ---------- 거래 CRUD ----------
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
    def set_budget(self, month: str, amount: int) -> None:
        self.budgets.set(month, amount)

    # ---------- 카테고리 ----------
    def add_category(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise AppError("카테고리명이 비어 있습니다.", "예: food")
        if self.categories.exists(name):
            raise AppError(f"이미 존재하는 카테고리입니다: {name}", "category list 로 목록을 확인하세요.")
        self.categories.add(name)
        return name

    def remove_category(self, name: str) -> None:
        self.check_category(name)
        if any(t.category == name for t in self.repo.iter_all()):
            raise AppError(
                f"사용 중인 카테고리는 삭제할 수 없습니다: {name}",
                f"search --category {name} 로 해당 거래를 확인하고 update 로 카테고리를 바꾼 뒤 다시 시도하세요.",
            )
        self.categories.remove(name)

    # ---------- 가져오기/내보내기 ----------
    def import_csv(self, path: Path) -> tuple[int, int, list[str]]:
        if not path.is_file():
            raise AppError(f"파일을 찾을 수 없습니다: {path}", "경로를 확인하세요.")
        imported = skipped = 0
        errors: list[str] = []
        number = self.repo.next_number()
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"date", "type", "category", "amount"} - set(reader.fieldnames or [])
            if missing:
                raise AppError(f"CSV 필수 컬럼이 없습니다: {', '.join(sorted(missing))}",
                               f"헤더 예: {','.join(CSV_FIELDS)}")
            for lineno, row in enumerate(reader, start=2):
                try:
                    tx = self._build(self._make_id(number), row.get("date") or "", row.get("type") or "",
                                     row.get("category") or "", row.get("amount") or "",
                                     row.get("memo") or "", row.get("tags") or "")
                except AppError as e:
                    skipped += 1
                    errors.append(f"{lineno}행: {e.message}")
                    continue
                self.repo.add(tx)
                number += 1
                imported += 1
        return imported, skipped, errors

    def export_csv(self, path: Path, month: str | None, date_from: str | None, date_to: str | None) -> int:
        if not (month or date_from or date_to):
            raise AppError("내보낼 기간 조건이 없습니다.", "--month YYYY-MM 또는 --from/--to YYYY-MM-DD 를 지정하세요.")
        count = 0
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for t in self._filter(date_from, date_to, None, None, None, None):
                if month and not t.date.startswith(month):
                    continue
                writer.writerow({"date": t.date, "type": t.type, "category": t.category,
                                 "amount": t.amount, "memo": t.memo, "tags": ",".join(t.tags)})
                count += 1
        return count
