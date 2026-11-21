"""저장소 계층: JSONL 파일 I/O (스트리밍 읽기, 원자적 재작성)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import AppError, Transaction

DEFAULT_CATEGORIES = ["food", "transport", "rent", "salary", "etc"]


class JsonlFile:
    """한 줄에 JSON 객체 하나를 저장하는 파일."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)  # 초기 실행 시 자동 생성

    def iter_records(self) -> Iterator[dict[str, Any]]:
        """파일을 한 줄씩 읽어 yield 한다 (전체를 메모리에 올리지 않음)."""
        with self.path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    raise AppError(
                        f"{self.path} {lineno}번째 줄이 손상되었습니다.",
                        "해당 줄을 수정하거나 삭제한 뒤 다시 실행하세요.",
                    ) from None

    def append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def rewrite(self, records: Iterable[dict[str, Any]]) -> None:
        """임시 파일에 전부 쓴 뒤 os.replace 로 원자적 교체."""
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise


class TransactionRepository:
    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / "transactions.jsonl")

    def iter_all(self) -> Iterator[Transaction]:
        for rec in self.file.iter_records():
            yield Transaction.from_dict(rec)

    def get(self, tx_id: str) -> Transaction | None:
        return next((t for t in self.iter_all() if t.id == tx_id), None)

    def next_number(self) -> int:
        return max((int(t.id.split("-")[-1]) for t in self.iter_all()), default=0) + 1

    def add(self, tx: Transaction) -> None:
        self.file.append(tx.to_dict())

    def replace(self, tx_id: str, new: Transaction | None) -> None:
        """id 가 같은 거래를 new 로 교체한다. new 가 None 이면 삭제."""

        def records() -> Iterator[dict[str, Any]]:
            for rec in self.file.iter_records():
                if rec["id"] != tx_id:
                    yield rec
                elif new is not None:
                    yield new.to_dict()

        self.file.rewrite(records())


class CategoryStore:
    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / "categories.jsonl")
        if not self.list():  # 비어 있으면 기본 카테고리 자동 생성 (안 A)
            self.file.rewrite({"name": n} for n in DEFAULT_CATEGORIES)

    def list(self) -> list[str]:
        return [rec["name"] for rec in self.file.iter_records()]

    def exists(self, name: str) -> bool:
        return name in self.list()

    def add(self, name: str) -> None:
        self.file.append({"name": name})

    def remove(self, name: str) -> None:
        self.file.rewrite(r for r in self.file.iter_records() if r["name"] != name)


class BudgetStore:
    def __init__(self, data_dir: Path) -> None:
        self.file = JsonlFile(data_dir / "budgets.jsonl")

    def get(self, month: str) -> int | None:
        for rec in self.file.iter_records():
            if rec["month"] == month:
                return int(rec["amount"])
        return None

    def set(self, month: str, amount: int) -> None:
        others = [r for r in self.file.iter_records() if r["month"] != month]
        self.file.rewrite(sorted(others + [{"month": month, "amount": amount}], key=lambda r: r["month"]))
