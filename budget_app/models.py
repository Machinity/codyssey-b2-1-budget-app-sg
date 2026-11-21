"""모델 계층: 데이터 구조와 값 검증."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

TYPES = ("income", "expense")


class AppError(Exception):
    """사용자에게 보여줄 오류(원인 + 해결 힌트)."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class Transaction:
    """거래 1건 (불변 값 객체). 수정은 새 인스턴스를 만들어 교체한다."""

    id: str
    date: str  # YYYY-MM-DD
    type: str  # income / expense
    category: str
    amount: int  # 양수
    memo: str = ""
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags)  # JSON 저장용
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        return cls(
            id=str(data["id"]),
            date=str(data["date"]),
            type=str(data["type"]),
            category=str(data["category"]),
            amount=int(data["amount"]),
            memo=str(data.get("memo", "")),
            tags=tuple(data.get("tags", [])),
        )


def parse_date(text: str) -> str:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise AppError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).", "예: 2024-01-15") from None


def parse_month(text: str) -> str:
    try:
        return datetime.strptime(text.strip(), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise AppError("월 형식이 올바르지 않습니다 (YYYY-MM).", "예: 2024-01") from None


def parse_type(text: str) -> str:
    value = text.strip().lower()
    if value not in TYPES:
        raise AppError(f"허용되지 않은 타입입니다: {text!r}", "income 또는 expense 중 하나를 입력하세요.")
    return value


def parse_amount(text: str | int) -> int:
    try:
        value = int(str(text).strip())
    except ValueError:
        raise AppError(f"금액은 정수여야 합니다: {text!r}", "예: 15000") from None
    if value <= 0:
        raise AppError("금액은 0보다 커야 합니다.", "양수 정수를 입력하세요. 예: 15000")
    return value


def parse_tags(text: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in text.split(",") if t.strip())
