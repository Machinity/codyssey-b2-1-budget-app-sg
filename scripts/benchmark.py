"""대량 데이터 성능 측정 (표준 라이브러리만 사용).

사용법 (저장소 루트에서):
    python scripts/benchmark.py              # 기본 100,000건
    python scripts/benchmark.py --rows 1000000

임시 폴더에 거래 N건을 만든 뒤 아래를 측정한다. ./data 는 건드리지 않는다.
  1) 명령별 소요 시간 (service 메서드 직접 호출)
  2) 최대 메모리: 스트리밍(heapq 상위 N) vs 전체 로드(list)
  3) 읽기/쓰기 버퍼 크기별 소요 시간
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from budget_app.service import BudgetService  # noqa: E402
from budget_app.storage import TransactionRepository  # noqa: E402

CATEGORIES = ["food", "transport", "rent", "salary", "etc"]


def make_data(data_dir: Path, rows: int) -> None:
    rnd = random.Random(42)
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "transactions.jsonl").open("w", encoding="utf-8") as f:
        for i in range(1, rows + 1):
            rec = {
                "id": f"TX-{i:06d}",
                "date": f"{rnd.randint(2020, 2024)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
                "type": "income" if rnd.random() < 0.1 else "expense",
                "category": rnd.choice(CATEGORIES),
                "amount": rnd.randint(1000, 100000),
                "memo": rnd.choice(["점심", "저녁", "버스", "월세", "커피", ""]),
                "tags": rnd.choice([["meal"], ["cafe"], [], ["fixed", "home"]]),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def timed(fn: Callable[[], object]) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def peak_mib(fn: Callable[[], object]) -> float:
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024 / 1024


def scan_with_buffer(path: Path, buffering: int) -> int:
    n = 0
    with open(path, encoding="utf-8", buffering=buffering) as f:
        for line in f:
            json.loads(line)
            n += 1
    return n


def write_with_buffer(src: Path, dst: Path, buffering: int) -> None:
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8", buffering=buffering) as fout:
        for line in fin:
            fout.write(json.dumps(json.loads(line), ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=100_000)
    rows = ap.parse_args().rows

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        make_data(data, rows)
        tx_file = data / "transactions.jsonl"
        size_mib = tx_file.stat().st_size / 1024 / 1024
        print(f"Python {sys.version.split()[0]} / {sys.platform} / 거래 {rows:,}건 / "
              f"transactions.jsonl {size_mib:.1f} MiB / 기본 버퍼 {io.DEFAULT_BUFFER_SIZE} B\n")

        svc = BudgetService(data)
        import_csv = Path(tmp) / "import.csv"
        import_csv.write_text("date,type,category,amount\n" + "2024-01-01,expense,food,100\n" * 10_000,
                              encoding="utf-8")
        mid = f"TX-{rows // 2:06d}"
        cases: list[tuple[str, Callable[[], object]]] = [
            ("list --limit 10", lambda: svc.latest(10)),
            ("search --q 점심 --limit 10", lambda: svc.search(q="점심", limit=10)),
            ("search --category food (전체 정렬)", lambda: svc.search(category="food")),
            ("summary --month 2024-01", lambda: svc.summary("2024-01", 3)),
            ("export --from 2020-01-01 --to 2024-12-31", lambda: svc.export_csv(Path(tmp) / "out.csv", None,
                                                                                 "2020-01-01", "2024-12-31")),
            ("add (1건 append, id 발급 위해 전체 스캔)", lambda: svc.add("2024-01-01", "expense", "food", 1000)),
            ("import --from (1만 행, 배치 쓰기)", lambda: svc.import_csv(import_csv)),
            ("update --id (전체 재작성)", lambda: svc.update(mid, amount="1234")),
            ("delete --id (전체 재작성)", lambda: svc.delete(mid)),
        ]
        print("1) 명령별 소요 시간")
        print(f"   {'명령':<44} {'시간(초)':>8}")
        for name, fn in cases:
            print(f"   {name:<44} {timed(fn):>8.3f}")

        repo = TransactionRepository(data)
        print("\n2) 최대 메모리 (tracemalloc peak)")
        print(f"   스트리밍  svc.latest(10)        : {peak_mib(lambda: svc.latest(10)):8.2f} MiB")
        print(f"   전체 로드 list(repo.iter_all()) : {peak_mib(lambda: list(repo.iter_all())):8.2f} MiB")

        print("\n3) 버퍼 크기별 소요 시간 (각 3회 중 최솟값)")
        print(f"   {'buffering':>10}  {'읽기+파싱(초)':>12}  {'파싱+쓰기(초)':>12}")
        for buf in (4 * 1024, 8 * 1024, 64 * 1024, 1024 * 1024):
            r = min(timed(lambda: scan_with_buffer(tx_file, buf)) for _ in range(3))
            w = min(timed(lambda: write_with_buffer(tx_file, Path(tmp) / "w.jsonl", buf)) for _ in range(3))
            print(f"   {buf // 1024:>7} KiB  {r:>12.3f}  {w:>12.3f}")


if __name__ == "__main__":
    main()
