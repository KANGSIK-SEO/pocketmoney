"""
Domain Data Models for budget_app.
Defined as strongly typed dataclasses with serialization and validation logic.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, List, Optional

from budget_app.exceptions import ValidationError

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_REGEX = re.compile(r"^\d{4}-\d{2}$")


def validate_date_string(date_str: str) -> str:
    """Validate that date_str matches YYYY-MM-DD and represents a valid calendar day."""
    if not isinstance(date_str, str) or not DATE_REGEX.match(date_str):
        raise ValidationError(
            "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).",
            hint="예: 2024-01-15",
        )
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValidationError(
            "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).",
            hint="예: 2024-01-15",
        ) from e
    return date_str


def validate_month_string(month_str: str) -> str:
    """Validate that month_str matches YYYY-MM and represents a valid calendar month."""
    if not isinstance(month_str, str) or not MONTH_REGEX.match(month_str):
        raise ValidationError(
            f"월 형식이 올바르지 않습니다: '{month_str}' (YYYY-MM 필요)",
            hint="예: 2024-01",
        )
    try:
        datetime.strptime(month_str, "%Y-%m")
    except ValueError as e:
        raise ValidationError(
            f"유효하지 않은 월입니다: '{month_str}'",
            hint="01부터 12 사이의 월을 입력해주세요 (예: 2024-05)",
        ) from e
    return month_str


def validate_transaction_type(tx_type: str) -> str:
    """Validate that tx_type is either 'income' or 'expense'."""
    normalized = tx_type.strip().lower()
    if normalized not in ("income", "expense"):
        raise ValidationError(
            f"거래 타입이 올바르지 않습니다: '{tx_type}'",
            hint="'income'(수입) 또는 'expense'(지출) 중 하나를 입력하세요.",
        )
    return normalized


def validate_positive_amount(amount: Any) -> int:
    """Validate that amount is a positive integer greater than zero."""
    try:
        amt = int(amount)
    except (ValueError, TypeError) as e:
        raise ValidationError(
            f"금액은 숫자여야 합니다: '{amount}'",
            hint="정수 숫자로 입력하세요 (예: 15000)",
        ) from e
    if amt <= 0:
        raise ValidationError(
            f"금액은 0보다 큰 양수여야 합니다: {amt}",
            hint="0원 초과의 금액을 입력해주세요.",
        )
    return amt


@dataclass(slots=True)
class Transaction:
    """
    Represents an individual income or expense record.
    """
    id: str
    type: str  # 'income' | 'expense'
    date: str  # 'YYYY-MM-DD'
    amount: int  # Positive integer
    category: str
    memo: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValidationError("거래 ID는 비어있을 수 없습니다.")
        self.type = validate_transaction_type(self.type)
        self.date = validate_date_string(self.date)
        self.amount = validate_positive_amount(self.amount)
        if not self.category or not self.category.strip():
            raise ValidationError("카테고리는 필수 입력값입니다.", hint="category list로 등록된 카테고리를 확인하세요.")
        self.category = self.category.strip()
        self.memo = self.memo.strip() if self.memo else ""
        if isinstance(self.tags, str):  # in case a single comma-separated string passed
            self.tags = [t.strip() for t in self.tags.split(",") if t.strip()]
        else:
            self.tags = [str(t).strip() for t in self.tags if str(t).strip()]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            date=str(data["date"]),
            amount=int(data["amount"]),
            category=str(data["category"]),
            memo=str(data.get("memo", "")),
            tags=list(data.get("tags", [])),
        )

    def to_csv_row(self) -> Dict[str, str]:
        """Convert transaction into standard CSV columns according to spec."""
        return {
            "date": self.date,
            "type": self.type,
            "category": self.category,
            "amount": str(self.amount),
            "memo": self.memo,
            "tags": ",".join(self.tags),
        }


@dataclass(slots=True)
class Category:
    """Represents a budget/transaction category."""
    name: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationError("카테고리명은 공백일 수 없습니다.")
        self.name = self.name.strip()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Category":
        return cls(
            name=str(data["name"]),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )


@dataclass(slots=True)
class Budget:
    """Represents a monthly expense budget limit."""
    month: str  # YYYY-MM
    amount: int  # Positive integer
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        self.month = validate_month_string(self.month)
        self.amount = validate_positive_amount(self.amount)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Budget":
        return cls(
            month=str(data["month"]),
            amount=int(data["amount"]),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
        )


@dataclass(slots=True)
class RecurringRule:
    """Represents a recurring monthly income or expense rule (Bonus feature)."""
    id: str
    name: str
    type: str  # 'income' | 'expense'
    day_of_month: int  # 1-31
    amount: int
    category: str
    memo: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValidationError("반복 규칙 ID는 필수입니다.")
        if not self.name or not self.name.strip():
            raise ValidationError("반복 규칙명은 필수입니다.")
        self.name = self.name.strip()
        self.type = validate_transaction_type(self.type)
        self.amount = validate_positive_amount(self.amount)
        if not 1 <= int(self.day_of_month) <= 31:
            raise ValidationError(
                f"반복 일자는 1일에서 31일 사이여야 합니다: {self.day_of_month}",
                hint="매월 생성될 일자를 지정하세요 (예: 25)",
            )
        self.day_of_month = int(self.day_of_month)
        self.category = self.category.strip()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecurringRule":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            type=str(data["type"]),
            day_of_month=int(data["day_of_month"]),
            amount=int(data["amount"]),
            category=str(data["category"]),
            memo=str(data.get("memo", "")),
            tags=list(data.get("tags", [])),
        )
