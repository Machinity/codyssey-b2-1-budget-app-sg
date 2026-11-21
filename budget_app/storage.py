"""저장소 계층: 모든 파일 I/O (JSONL 데이터 파일 + import/export CSV)."""
from __future__ import annotations

import csv
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import AppError, Transaction

DEFAULT_CATEGORIES = ["food", "transport", "rent", "salary", "etc"]
CSV_FIELDS = ["date", "type", "category", "amount", "memo", "tags"]
CSV_REQUIRED = ("date", "type", "category", "amount")


LOCK_TIMEOUT = 5.0  # 잠금 대기 최대 시간(초)


class FileLock:
    """data 폴더 단위 쓰기 잠금.

    O_CREAT|O_EXCL 로 잠금 파일을 '없을 때만' 만들어 한 프로세스만 통과시킨다(OS 무관).
    파일에는 PID 를 적고, 그 프로세스가 이미 죽었으면(비정상 종료) 남은 잠금을 치운다(POSIX).
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> FileLock:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    self.path.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise AppError(
                        "다른 budget_app 실행이 데이터를 수정 중입니다 (잠금 대기 시간 초과).",
                        f"잠시 후 다시 실행하세요. 실행 중인 budget_app 이 없다면 {self.path} 를 삭제하세요.",
                    ) from None
                time.sleep(0.1)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return self

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)

    def _is_stale(self) -> bool:
        """잠금을 만든 프로세스가 더 이상 없으면 True. 판단할 수 없으면 False(안전 쪽)."""
        if os.name != "posix":  # Windows 의 os.kill(pid, 0) 은 프로세스를 종료시키므로 쓰지 않음
            return False
        try:
            pid = int(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # 막 생성되어 아직 PID 를 쓰는 중일 수 있음
            return False
        try:
            os.kill(pid, 0)  # 신호를 보내지 않고 존재 여부만 확인
        except ProcessLookupError:
            return True
        except PermissionError:  # 다른 사용자의 살아 있는 프로세스
            return False
        return False


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
        self.append_many([record])

    def append_many(self, records: Iterable[dict[str, Any]]) -> int:
        """여러 줄을 파일을 한 번만 열어 추가한다 (대량 import 용 배치 쓰기)."""
        count = 0
        with self.path.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
        return count

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

    def add_many(self, txs: Iterable[Transaction]) -> int:
        """거래 여러 건을 한 번의 파일 열기로 추가하고 건수를 돌려준다."""
        return self.file.append_many(t.to_dict() for t in txs)

    def add_many_atomic(self, txs: Iterable[Transaction]) -> int:
        """기존 거래 + 새 거래를 임시 파일에 쓴 뒤 한 번에 교체한다 (전부 반영 또는 전혀 반영 안 됨)."""
        count = 0

        def records() -> Iterator[dict[str, Any]]:
            nonlocal count
            yield from self.file.iter_records()
            for t in txs:
                count += 1
                yield t.to_dict()

        self.file.rewrite(records())
        return count

    def replace(self, tx_id: str, new: Transaction | None) -> None:
        """id 가 같은 거래를 new 로 교체한다. new 가 None 이면 삭제."""

        def records() -> Iterator[dict[str, Any]]:
            for rec in self.file.iter_records():
                if rec["id"] != tx_id:
                    yield rec
                elif new is not None:
                    yield new.to_dict()

        self.file.rewrite(records())

    def rename_category(self, old: str, new: str) -> int:
        """category 가 old 인 거래를 모두 new 로 바꾸고, 바뀐 건수를 돌려준다."""
        changed = 0

        def records() -> Iterator[dict[str, Any]]:
            nonlocal changed
            for rec in self.file.iter_records():
                if rec["category"] == old:
                    rec["category"] = new
                    changed += 1
                yield rec

        self.file.rewrite(records())
        return changed


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


class CsvTransactionFile:
    """import/export 용 거래 CSV (UTF-8, 헤더 포함, 스키마 CSV_FIELDS).

    파일 열기·헤더 검증·행 읽기/쓰기만 맡고, 행 값 검증(업무 규칙)은 service 가 한다.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def iter_rows(self) -> Iterator[tuple[int, dict[str, str]]]:
        """(CSV 행 번호, {컬럼: 문자열}) 를 한 행씩 yield 한다. 빈 칸은 ""."""
        if not self.path.is_file():
            raise AppError(f"파일을 찾을 수 없습니다: {self.path}", "경로를 확인하세요.")
        with self.path.open(encoding="utf-8-sig", newline="") as f:  # 엑셀 BOM 허용
            reader = csv.DictReader(f)
            missing = set(CSV_REQUIRED) - set(reader.fieldnames or [])
            if missing:
                raise AppError(f"CSV 필수 컬럼이 없습니다: {', '.join(sorted(missing))}",
                               f"헤더 예: {','.join(CSV_FIELDS)}")
            for lineno, row in enumerate(reader, start=2):
                yield lineno, {k: row.get(k) or "" for k in CSV_FIELDS}

    def write(self, transactions: Iterable[Transaction]) -> int:
        """헤더 + 거래들을 쓰고(덮어쓰기) 쓴 건수를 돌려준다. 0건이어도 헤더는 쓴다."""
        count = 0
        with self.path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for t in transactions:
                writer.writerow({"date": t.date, "type": t.type, "category": t.category,
                                 "amount": t.amount, "memo": t.memo, "tags": ",".join(t.tags)})
                count += 1
        return count


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
