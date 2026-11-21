"""공통 관심사 데코레이터 (관심사 하나당 데코레이터 하나).

- handle_errors : 예외 처리 → [오류]/[힌트] 출력 + 종료 코드
- log_call      : 실행 로그 (시작/종료/예외)
- timed         : 실행 시간 측정
- locked        : 쓰기 작업 동시 실행 방지 (data/.lock)
"""
from __future__ import annotations

import functools
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from .models import AppError
from .storage import FileLock

logger = logging.getLogger("budget_app")
T = TypeVar("T")


def locked(method: Callable[..., T]) -> Callable[..., T]:
    """데이터를 바꾸는 서비스 메서드를 data 폴더 잠금(data/.lock) 안에서 실행한다.

    self.data_dir 를 가진 객체의 메서드에 쓴다. 동시에 두 명령이 쓰기를 하면
    한쪽은 잠금이 풀릴 때까지 기다린다(최대 storage.LOCK_TIMEOUT 초).
    """

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> T:
        data_dir: Path = self.data_dir
        with FileLock(data_dir / ".lock"):
            return method(self, *args, **kwargs)

    return wrapper


def timed(func: Callable[..., T]) -> Callable[..., T]:
    """[시간 측정] 호출 소요 시간을 INFO 로그로 남긴다. 예외가 나도 측정한다."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            logger.info("%s 소요 %.1fms", func.__qualname__, (time.perf_counter() - start) * 1000)

    return wrapper


def log_call(func: Callable[..., T]) -> Callable[..., T]:
    """[실행 로그] 호출 시작/정상 종료/예외를 로그로 남기고, 예외는 그대로 다시 던진다."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        logger.info("%s 시작", func.__qualname__)
        try:
            result = func(*args, **kwargs)
        except BaseException as e:
            logger.info("%s 예외: %s", func.__qualname__, type(e).__name__)
            raise
        logger.info("%s 정상 종료", func.__qualname__)
        return result

    return wrapper


def handle_errors(func: Callable[..., None]) -> Callable[..., int]:
    """[예외 처리] 예외를 스택트레이스 없이 [오류]/[힌트] 로 출력하고 종료 코드(int)로 바꾼다.

    정상 0 / AppError·OSError 1 / KeyboardInterrupt·EOFError(입력 취소) 130
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> int:
        code = 0
        try:
            func(*args, **kwargs)
        except AppError as e:
            print(f"[오류] {e.message}", file=sys.stderr)
            if e.hint:
                print(f"[힌트] {e.hint}", file=sys.stderr)
            code = 1
        except OSError as e:
            print(f"[오류] 파일 처리 실패: {e.strerror} ({e.filename})", file=sys.stderr)
            print("[힌트] 경로와 권한을 확인하세요.", file=sys.stderr)
            code = 1
        except (KeyboardInterrupt, EOFError):
            print("\n[중단] 입력이 취소되었습니다.", file=sys.stderr)
            code = 130
        logger.info("%s 종료 코드 %d", func.__qualname__, code)
        return code

    return wrapper
