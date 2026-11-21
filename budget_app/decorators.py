"""공통 관심사 데코레이터: 예외 처리 + 실행 로그/시간 측정."""
from __future__ import annotations

import functools
import logging
import sys
import time
from typing import Callable

from .models import AppError

logger = logging.getLogger("budget_app")


def cli_command(func: Callable[..., None]) -> Callable[..., int]:
    """명령 함수를 감싸 종료 코드(int)를 돌려준다.

    - AppError 는 스택트레이스 없이 [오류]/[힌트] 로 출력하고 1 반환
    - 정상 종료 시 0 반환
    - 실행 시간을 로그(--verbose)로 남김
    """

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> int:
        start = time.perf_counter()
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
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("%s 종료 code=%d (%.1fms)", func.__name__, code, elapsed)
        return code

    return wrapper
