"""명령별 실행 테스트 (명령 1개 ↔ 테스트 클래스 1개).

실행: python -m unittest -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from budget_app.cli import main
from budget_app.models import Transaction


class CommandTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.data = self.dir / "data"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *argv: str, inputs: list[str] | None = None) -> tuple[int, str]:
        """CLI 를 실행하고 (종료 코드, stdout+stderr) 를 돌려준다."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                mock.patch("builtins.input", side_effect=inputs or []):
            code = main(["--data-dir", str(self.data), *argv])
        return code, out.getvalue()

    def add(self, date: str, type_: str, category: str, amount: str,
            memo: str = "", tags: str = "") -> str:
        code, out = self.run_cli("add", inputs=[date, type_, category, amount, memo, tags])
        self.assertEqual(code, 0, out)
        return out.strip().split("id=")[-1]

    def seed(self) -> None:
        self.add("2026-11-15", "expense", "food", "15000", "점심", "meal")      # TX-000001
        self.add("2026-11-14", "income", "salary", "3000000", "월급")           # TX-000002
        self.add("2026-11-12", "expense", "transport", "20000", "버스")         # TX-000003
        self.add("2026-11-01", "expense", "rent", "150000", "월세", "fixed")    # TX-000004
        self.add("2026-10-03", "expense", "food", "8000", "커피", "cafe")       # TX-000005 (지난달)


class TestModel(unittest.TestCase):
    def test_transaction_is_immutable(self) -> None:
        import dataclasses
        from budget_app.models import Transaction
        tx = Transaction("TX-000001", "2026-11-15", "expense", "food", 15000, "점심", ("meal",))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            tx.amount = 1  # type: ignore[misc]
        changed = dataclasses.replace(tx, amount=20000)  # 수정 = 새 인스턴스
        self.assertEqual((tx.amount, changed.amount), (15000, 20000))
        self.assertEqual(Transaction.from_dict(tx.to_dict()), tx)  # JSON 왕복 보존


class TestAdd(CommandTestCase):
    def test_add_saves_and_prints_id(self) -> None:
        code, out = self.run_cli("add", inputs=["2026-11-15", "expense", "food", "15000", "점심", "meal"])
        self.assertEqual(code, 0)
        self.assertIn("[저장 완료] id=TX-000001", out)
        rec = json.loads((self.data / "transactions.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(rec["amount"], 15000)
        self.assertEqual(rec["tags"], ["meal"])

    def test_add_reprompts_on_invalid_input(self) -> None:
        code, out = self.run_cli("add", inputs=[
            "2026-13-40", "2026-11-15",   # 잘못된 날짜 → 재입력
            "exp", "expense",             # 잘못된 타입 → 재입력
            "nope", "food",               # 없는 카테고리 → 재입력
            "0", "15000",                 # 0 금액 → 재입력
            "", "",
        ])
        self.assertEqual(code, 0)
        self.assertIn("[오류] 날짜 형식이 올바르지 않습니다", out)
        self.assertIn("[오류] 허용되지 않은 타입입니다", out)
        self.assertIn("[오류] 존재하지 않는 카테고리입니다", out)
        self.assertIn("[오류] 금액은 0보다 커야 합니다", out)
        self.assertIn("[저장 완료] id=TX-000001", out)


class TestList(CommandTestCase):
    def test_list_newest_first_with_limit(self) -> None:
        self.seed()
        code, out = self.run_cli("list", "--limit", "3")
        self.assertEqual(code, 0)
        ids = [line.split(" | ")[0] for line in out.strip().splitlines()]
        self.assertEqual(ids, ["TX-000001", "TX-000002", "TX-000003"])  # 11-15, 11-14, 11-12 (TX-000005 는 10월)


class TestSearch(CommandTestCase):
    def test_search_filters(self) -> None:
        self.seed()
        _, out = self.run_cli("search", "--type", "expense", "--category", "food")
        self.assertEqual([l.split(" | ")[0] for l in out.strip().splitlines()], ["TX-000001", "TX-000005"])
        _, out = self.run_cli("search", "--from", "2026-11-01", "--to", "2026-11-13")
        self.assertEqual([l.split(" | ")[0] for l in out.strip().splitlines()], ["TX-000003", "TX-000004"])
        _, out = self.run_cli("search", "--q", "월세")
        self.assertIn("TX-000004", out)
        _, out = self.run_cli("search", "--tag", "cafe")
        self.assertEqual(out.strip().split(" | ")[0], "TX-000005")

    def test_search_no_result(self) -> None:
        code, out = self.run_cli("search", "--q", "없음")
        self.assertEqual(code, 0)
        self.assertIn("[결과 없음]", out)


class TestSummary(CommandTestCase):
    def test_summary_with_budget(self) -> None:
        self.seed()
        self.assertEqual(self.run_cli("budget", "set", "--month", "2026-11", "--amount", "500000")[0], 0)
        code, out = self.run_cli("summary", "--month", "2026-11", "--top", "2")
        self.assertEqual(code, 0)
        self.assertIn("총 수입: 3000000원", out)
        self.assertIn("총 지출: 185000원", out)
        self.assertIn("잔액: 2815000원", out)
        self.assertIn("사용률 37.0%", out)
        self.assertIn("1) rent 150000원", out)
        self.assertIn("2) transport 20000원", out)
        self.assertNotIn("3)", out)

    def test_summary_budget_exceeded(self) -> None:
        self.seed()
        self.run_cli("budget", "set", "--month", "2026-11", "--amount", "100000")
        _, out = self.run_cli("summary", "--month", "2026-11")
        self.assertIn("[경고] 예산을 85000원 초과했습니다!", out)
        self.assertIn("[권장] 지출 1위 'rent' 부터 줄이거나, 예산 조정: budget set --month 2026-11", out)

    def test_summary_budget_caution(self) -> None:
        self.seed()  # 2026-11 지출 185000
        self.run_cli("budget", "set", "--month", "2026-11", "--amount", "200000")  # 92.5%
        _, out = self.run_cli("summary", "--month", "2026-11")
        self.assertIn("[주의] 예산의 92.5%를 사용했습니다. (남은 예산 15000원)", out)
        self.assertIn("[권장]", out)
        self.assertNotIn("[경고]", out)

    def test_summary_budget_ok_has_no_alert(self) -> None:
        self.seed()
        self.run_cli("budget", "set", "--month", "2026-11", "--amount", "500000")  # 37%
        _, out = self.run_cli("summary", "--month", "2026-11")
        self.assertNotIn("[주의]", out)
        self.assertNotIn("[경고]", out)
        self.assertNotIn("[권장]", out)

    def test_summary_no_data(self) -> None:
        code, out = self.run_cli("summary", "--month", "2026-09")
        self.assertEqual(code, 0)
        self.assertIn("[데이터 없음]", out)


class TestUpdate(CommandTestCase):
    def test_update_changes_only_given_fields(self) -> None:
        self.seed()
        code, out = self.run_cli("update", "--id", "TX-000003", "--amount", "25000", "--memo", "택시")
        self.assertEqual(code, 0)
        self.assertIn("[수정 완료] id=TX-000003", out)
        self.assertIn("TX-000003 | 2026-11-12 | expense | transport | 25000 | 택시", out)

    def test_update_missing_id(self) -> None:
        code, out = self.run_cli("update", "--id", "TX-999999", "--amount", "1")
        self.assertEqual(code, 1)
        self.assertIn("[오류] 없는 데이터입니다", out)


class TestDelete(CommandTestCase):
    def test_delete_then_missing(self) -> None:
        self.seed()
        code, out = self.run_cli("delete", "--id", "TX-000005")
        self.assertEqual(code, 0)
        self.assertIn("[삭제 완료] id=TX-000005", out)
        self.assertNotIn("TX-000005", self.run_cli("list")[1])
        code, out = self.run_cli("delete", "--id", "TX-000005")
        self.assertEqual(code, 1)
        self.assertIn("[오류] 없는 데이터입니다", out)


class TestImport(CommandTestCase):
    def test_import_counts_and_skips_invalid_rows(self) -> None:
        src = self.dir / "import.csv"
        src.write_text(
            "date,type,category,amount,memo,tags\n"
            "2026-11-14,income,salary,3000000,월급,\n"
            '2026-11-20,expense,food,30000,저녁,"meal,dinner"\n'
            "2026-11-21,expense,nope,1000,,\n",
            encoding="utf-8",
        )
        code, out = self.run_cli("import", "--from", str(src))
        self.assertEqual(code, 0)
        self.assertIn("[완료] imported=2, skipped=1 (id TX-000001 ~ TX-000002)", out)
        self.assertIn("[안내] 부분 적용", out)
        self.assertIn("TX-000002 | 2026-11-20 | expense | food | 30000 | 저녁 | meal,dinner",
                      self.run_cli("list")[1])


class TestImportAtomic(CommandTestCase):
    """import 의 부분 적용(기본) vs --atomic(전부 아니면 전무)."""

    def write_csv(self, *rows: str) -> Path:
        src = self.dir / "in.csv"
        src.write_text("date,type,category,amount\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
        return src

    def tx_text(self) -> str:
        return (self.data / "transactions.jsonl").read_text(encoding="utf-8")

    def test_atomic_rejects_whole_file_if_any_row_invalid(self) -> None:
        self.seed()
        before = self.tx_text()
        src = self.write_csv("2026-11-01,expense,food,100", "2026-11-02,expense,nope,100")
        code, out = self.run_cli("import", "--from", str(src), "--atomic")
        self.assertEqual(code, 1)
        self.assertIn("잘못된 행 1개가 있어 아무것도 가져오지 않았습니다", out)
        self.assertIn("3행: 존재하지 않는 카테고리입니다", out)
        self.assertEqual(self.tx_text(), before)  # 정상 행도 반영되지 않음

    def test_atomic_imports_all_when_valid(self) -> None:
        self.seed()
        src = self.write_csv("2026-11-01,expense,food,100", "2026-11-02,expense,rent,200")
        code, out = self.run_cli("import", "--from", str(src), "--atomic")
        self.assertEqual(code, 0, out)
        self.assertIn("[완료] imported=2, skipped=0 (id TX-000006 ~ TX-000007)", out)
        self.assertEqual(len(self.tx_text().splitlines()), 7)

    def test_atomic_interrupted_write_keeps_original(self) -> None:
        """쓰는 도중 중단(예: Ctrl+C)되면 원본 파일이 그대로 남는다."""
        self.seed()
        before = self.tx_text()
        src = self.write_csv(*["2026-11-01,expense,food,100"] * 5)
        original = Transaction.to_dict
        calls = {"n": 0}

        def flaky(tx: Transaction) -> dict[str, object]:
            if tx.id >= "TX-000006":  # 새 거래만 카운트
                calls["n"] += 1
                if calls["n"] == 3:
                    raise KeyboardInterrupt
            return original(tx)

        with mock.patch.object(Transaction, "to_dict", flaky):
            code, _ = self.run_cli("import", "--from", str(src), "--atomic")
        self.assertEqual(code, 130)
        self.assertEqual(self.tx_text(), before)
        self.assertEqual([p.name for p in self.data.glob("*.tmp")], [])  # 임시 파일 정리됨

    def test_default_interrupted_write_keeps_rows_written_so_far(self) -> None:
        """기본(부분 적용) 모드는 롤백이 없다: 중단 전까지 쓴 행은 남는다 (문서화된 동작)."""
        src = self.write_csv(*["2026-11-01,expense,food,100"] * 5)
        original = Transaction.to_dict
        calls = {"n": 0}

        def flaky(tx: Transaction) -> dict[str, object]:
            calls["n"] += 1
            if calls["n"] == 3:
                raise KeyboardInterrupt
            return original(tx)

        with mock.patch.object(Transaction, "to_dict", flaky):
            code, _ = self.run_cli("import", "--from", str(src))
        self.assertEqual(code, 130)
        self.assertEqual(len(self.tx_text().splitlines()), 2)


class TestExport(CommandTestCase):
    def test_export_month(self) -> None:
        self.seed()
        dst = self.dir / "export.csv"
        code, out = self.run_cli("export", "--out", str(dst), "--month", "2026-11")
        self.assertEqual(code, 0)
        self.assertIn("(4 records)", out)
        lines = dst.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "date,type,category,amount,memo,tags")
        self.assertEqual(len(lines), 5)

    def test_export_zero_records_still_writes_header(self) -> None:
        dst = self.dir / "empty.csv"
        code, out = self.run_cli("export", "--out", str(dst), "--month", "2026-09")
        self.assertEqual(code, 0)
        self.assertIn("(0 records)", out)
        self.assertEqual(dst.read_text(encoding="utf-8").splitlines(), ["date,type,category,amount,memo,tags"])

    def test_export_requires_period(self) -> None:
        code, out = self.run_cli("export", "--out", str(self.dir / "x.csv"))
        self.assertEqual(code, 1)
        self.assertIn("[오류] 내보낼 기간 조건이 없습니다", out)

    def test_export_then_import_roundtrip(self) -> None:
        self.seed()
        dst = self.dir / "export.csv"
        self.run_cli("export", "--out", str(dst), "--from", "2026-10-01", "--to", "2026-10-31")
        _, out = self.run_cli("import", "--from", str(dst))
        self.assertIn("[완료] imported=1, skipped=0", out)


class TestCategory(CommandTestCase):
    def test_category_add_list_remove(self) -> None:
        self.assertIn("[저장 완료] category=hobby", self.run_cli("category", "add", "--name", "hobby")[1])
        self.assertIn("- hobby", self.run_cli("category", "list")[1])
        self.assertIn("[삭제 완료] category=hobby", self.run_cli("category", "remove", "--name", "hobby")[1])
        self.assertNotIn("- hobby", self.run_cli("category", "list")[1])

    def test_remove_in_use_category_is_blocked(self) -> None:
        self.seed()
        code, out = self.run_cli("category", "remove", "--name", "food")
        self.assertEqual(code, 1)
        self.assertIn("[오류] 사용 중인 카테고리는 삭제할 수 없습니다", out)
        self.assertIn("--replace-with", out)

    def test_remove_with_replacement_moves_transactions(self) -> None:
        self.seed()
        code, out = self.run_cli("category", "remove", "--name", "food", "--replace-with", "etc")
        self.assertEqual(code, 0, out)
        self.assertIn("[이동 완료] food → etc (2건)", out)
        self.assertIn("[삭제 완료] category=food", out)
        self.assertNotIn("- food", self.run_cli("category", "list")[1])
        self.assertIn("[결과 없음]", self.run_cli("search", "--category", "food")[1])
        self.assertEqual(len(self.run_cli("search", "--category", "etc")[1].strip().splitlines()), 2)

    def test_remove_with_invalid_replacement(self) -> None:
        self.seed()
        code, out = self.run_cli("category", "remove", "--name", "food", "--replace-with", "nope")
        self.assertEqual(code, 1)
        self.assertIn("[오류] 존재하지 않는 카테고리입니다", out)
        self.assertIn("- food", self.run_cli("category", "list")[1])
        code, _ = self.run_cli("category", "remove", "--name", "food", "--replace-with", "food")
        self.assertEqual(code, 1)


class TestDecorators(unittest.TestCase):
    """관심사별 데코레이터를 각각 단독으로 검증한다."""

    def test_handle_errors_converts_exceptions_to_exit_codes(self) -> None:
        from budget_app.decorators import handle_errors
        from budget_app.models import AppError

        @handle_errors
        def ok() -> None:
            pass

        @handle_errors
        def fail() -> None:
            raise AppError("원인", "힌트")

        @handle_errors
        def cancel() -> None:
            raise EOFError

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual((ok(), fail(), cancel()), (0, 1, 130))
        self.assertIn("[오류] 원인\n[힌트] 힌트", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_log_call_logs_and_reraises(self) -> None:
        from budget_app.decorators import log_call

        @log_call
        def boom() -> None:
            raise ValueError("x")

        with self.assertLogs("budget_app", "INFO") as logs, self.assertRaises(ValueError):
            boom()
        self.assertTrue(any("boom 시작" in m for m in logs.output))
        self.assertTrue(any("boom 예외: ValueError" in m for m in logs.output))

    def test_timed_logs_elapsed_and_keeps_return_value(self) -> None:
        from budget_app.decorators import timed

        @timed
        def add(a: int, b: int) -> int:
            return a + b

        with self.assertLogs("budget_app", "INFO") as logs:
            self.assertEqual(add(1, 2), 3)
        self.assertRegex(logs.output[0], r"add 소요 \d+\.\dms")


class TestLock(CommandTestCase):
    """data/.lock 잠금: 쓰기 명령의 동시 실행 방지."""

    def lock_file(self, pid: int) -> Path:
        self.run_cli("list")  # data 폴더 생성
        lock = self.data / ".lock"
        lock.write_text(str(pid), encoding="utf-8")
        return lock

    def test_write_waits_then_fails_while_locked(self) -> None:
        lock = self.lock_file(os.getpid())  # 살아 있는 프로세스가 잡고 있는 잠금
        with mock.patch("budget_app.storage.LOCK_TIMEOUT", 0.3):
            code, out = self.run_cli("budget", "set", "--month", "2026-11", "--amount", "1000")
        self.assertEqual(code, 1)
        self.assertIn("[오류] 다른 budget_app 실행이 데이터를 수정 중입니다", out)
        self.assertIn(str(lock), out)  # 힌트에 잠금 파일 경로 안내
        self.assertTrue(lock.exists())  # 남의 잠금은 지우지 않음
        self.assertEqual((self.data / "budgets.jsonl").read_text(encoding="utf-8"), "")

    def test_read_commands_do_not_need_lock(self) -> None:
        self.lock_file(os.getpid())
        self.assertEqual(self.run_cli("list")[0], 0)
        self.assertEqual(self.run_cli("summary", "--month", "2026-11")[0], 0)

    @unittest.skipUnless(os.name == "posix", "stale 잠금 자동 정리는 POSIX 전용")
    def test_stale_lock_from_dead_process_is_removed(self) -> None:
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()  # 종료된 프로세스의 PID
        lock = self.lock_file(dead.pid)
        code, out = self.run_cli("budget", "set", "--month", "2026-11", "--amount", "1000")
        self.assertEqual(code, 0, out)
        self.assertFalse(lock.exists())  # 명령이 끝나면 잠금 해제

    def test_concurrent_imports_get_unique_ids(self) -> None:
        """프로세스 5개가 동시에 20건씩 import → 100건, id 중복 없음."""
        src = self.dir / "in.csv"
        src.write_text("date,type,category,amount\n" + "2026-11-01,expense,food,100\n" * 20, encoding="utf-8")
        self.run_cli("list")
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
        procs = [subprocess.Popen([sys.executable, "-m", "budget_app", "--data-dir", str(self.data),
                                   "import", "--from", str(src)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                 for _ in range(5)]
        self.assertEqual([p.wait() for p in procs], [0] * 5)
        ids = [json.loads(line)["id"] for line in
               (self.data / "transactions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(ids), 100)
        self.assertEqual(len(set(ids)), 100)
        self.assertFalse((self.data / ".lock").exists())


if __name__ == "__main__":
    unittest.main()
