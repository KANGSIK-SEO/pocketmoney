"""
Storage Layer for budget_app.
Implements file-based atomic persistence using JSONL and generator-based streaming.
Maintains 3+ separated persistent files: transactions.jsonl, categories.jsonl, budgets.jsonl, and recurring.jsonl.
"""

from datetime import datetime
import json
import os
import tempfile
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set

from budget_app.exceptions import BudgetAppException, ConflictError, NotFoundError
from budget_app.models import Budget, Category, RecurringRule, Transaction

DEFAULT_CATEGORIES = [
    "food",
    "transport",
    "rent",
    "salary",
    "allowance",
    "entertainment",
    "shopping",
    "medical",
    "etc",
    "식비",
    "교통",
    "주거/통신",
    "급여",
    "용돈",
    "문화/여가",
    "의료/건강",
    "기타",
]


def reverse_readline(file_path: str, buffer_size: int = 65536) -> Iterator[str]:
    """
    Generator streaming lines from the end of a file backwards.
    Memory complexity is O(1) with respect to file size.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return

    with open(file_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        remainder = b""
        pos = file_size

        while pos > 0:
            read_size = min(buffer_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size) + remainder
            lines = chunk.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                stripped = line.strip()
                if stripped:
                    yield stripped.decode("utf-8", errors="replace")

        stripped_remainder = remainder.strip()
        if stripped_remainder:
            yield stripped_remainder.decode("utf-8", errors="replace")


def forward_readline(file_path: str) -> Iterator[str]:
    """
    Generator streaming lines forwards line-by-line.
    Memory complexity is O(1).
    """
    if not os.path.exists(file_path):
        return

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                yield stripped


def atomic_write_jsonl(target_path: str, records: Iterable[Dict[str, Any]]) -> None:
    """
    Atomically write records to a target JSONL file.
    Writes to a temporary file in the target directory, calls fsync,
    and replaces the target file atomically via os.replace.
    """
    dir_name = os.path.dirname(os.path.abspath(target_path))
    os.makedirs(dir_name, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_budget_", suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


class TransactionRepository:
    """
    Persistent repository for transactions backed by transactions.jsonl.
    Supports atomic appends, atomic updates/deletions, and generator-based streaming.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                pass  # create empty file

    def stream_forward(self) -> Iterator[Transaction]:
        """Stream transactions chronologically from start to finish."""
        for line in forward_readline(self.file_path):
            try:
                data = json.loads(line)
                yield Transaction.from_dict(data)
            except Exception:
                continue

    def stream_reverse(self) -> Iterator[Transaction]:
        """
        Stream transactions reverse-chronologically (latest first).
        Reads lines backwards from EOF in chunks.
        """
        for line in reverse_readline(self.file_path):
            try:
                data = json.loads(line)
                yield Transaction.from_dict(data)
            except Exception:
                continue

    def get_by_id(self, tx_id: str) -> Optional[Transaction]:
        """Find a transaction by ID."""
        for tx in self.stream_reverse():
            if tx.id == tx_id:
                return tx
        return None

    def generate_next_id(self) -> str:
        """
        Generate a unique sequential transaction ID (e.g., TX-000001).
        Inspects existing transactions to determine the highest ID.
        """
        max_num = 0
        for tx in self.stream_reverse():
            if tx.id.startswith("TX-"):
                try:
                    num = int(tx.id[3:])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        return f"TX-{(max_num + 1):06d}"

    def append(self, tx: Transaction) -> None:
        """Append a single transaction to the end of transactions.jsonl."""
        self._ensure_file()
        line = json.dumps(tx.to_dict(), ensure_ascii=False) + "\n"
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def update(self, updated_tx: Transaction) -> bool:
        """
        Atomically update a transaction by rewriting the file safely via tempfile and rename.
        """
        found = False
        new_records: List[Dict[str, Any]] = []
        for tx in self.stream_forward():
            if tx.id == updated_tx.id:
                new_records.append(updated_tx.to_dict())
                found = True
            else:
                new_records.append(tx.to_dict())

        if not found:
            raise NotFoundError(
                f"ID '{updated_tx.id}'에 해당하는 거래를 찾을 수 없습니다.",
                hint="list 명령으로 존재하는 거래 ID를 확인해주세요.",
            )

        atomic_write_jsonl(self.file_path, new_records)
        return True

    def delete(self, tx_id: str) -> bool:
        """
        Atomically delete a transaction by ID.
        """
        found = False
        new_records: List[Dict[str, Any]] = []
        for tx in self.stream_forward():
            if tx.id == tx_id:
                found = True
            else:
                new_records.append(tx.to_dict())

        if not found:
            raise NotFoundError(
                f"ID '{tx_id}'에 해당하는 거래를 찾을 수 없습니다.",
                hint="list 명령으로 존재하는 거래 ID를 확인해주세요.",
            )

        atomic_write_jsonl(self.file_path, new_records)
        return True

    def batch_append(self, transactions: Iterable[Transaction]) -> int:
        """Append multiple transactions in order."""
        count = 0
        self._ensure_file()
        with open(self.file_path, "a", encoding="utf-8") as f:
            for tx in transactions:
                line = json.dumps(tx.to_dict(), ensure_ascii=False) + "\n"
                f.write(line)
                count += 1
            f.flush()
        return count


class CategoryRepository:
    """
    Persistent repository for categories backed by categories.jsonl.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file_and_defaults()

    def _ensure_file_and_defaults(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            # Plan A: Auto initialize default categories
            records = [
                Category(name=c, created_at=datetime.now().isoformat()).to_dict()
                for c in DEFAULT_CATEGORIES
            ]
            atomic_write_jsonl(self.file_path, records)

    def list_all(self) -> List[Category]:
        categories: List[Category] = []
        for line in forward_readline(self.file_path):
            try:
                data = json.loads(line)
                categories.append(Category.from_dict(data))
            except Exception:
                continue
        return categories

    def exists(self, name: str) -> bool:
        name_clean = name.strip().lower()
        return any(c.name.lower() == name_clean for c in self.list_all())

    def add(self, category: Category) -> None:
        if self.exists(category.name):
            raise ConflictError(
                f"이미 존재하는 카테고리입니다: '{category.name}'",
                hint="category list 명령으로 기존 목록을 조회해보세요.",
            )
        current = [c.to_dict() for c in self.list_all()]
        current.append(category.to_dict())
        atomic_write_jsonl(self.file_path, current)

    def remove(self, name: str) -> bool:
        name_clean = name.strip().lower()
        existing = self.list_all()
        found = False
        remaining: List[Dict[str, Any]] = []
        for c in existing:
            if c.name.lower() == name_clean:
                found = True
            else:
                remaining.append(c.to_dict())

        if not found:
            raise NotFoundError(
                f"존재하지 않는 카테고리입니다: '{name}'",
                hint="category list 명령으로 존재하는 카테고리 목록을 확인해주세요.",
            )

        atomic_write_jsonl(self.file_path, remaining)
        return True


class BudgetRepository:
    """
    Persistent repository for monthly budgets backed by budgets.jsonl.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                pass

    def list_all(self) -> List[Budget]:
        budgets: List[Budget] = []
        for line in forward_readline(self.file_path):
            try:
                data = json.loads(line)
                budgets.append(Budget.from_dict(data))
            except Exception:
                continue
        return budgets

    def get_by_month(self, month: str) -> Optional[Budget]:
        for b in self.list_all():
            if b.month == month:
                return b
        return None

    def set_budget(self, budget: Budget) -> None:
        """Upsert a budget for the given month."""
        all_budgets = self.list_all()
        updated = False
        records: List[Dict[str, Any]] = []
        for b in all_budgets:
            if b.month == budget.month:
                records.append(budget.to_dict())
                updated = True
            else:
                records.append(b.to_dict())

        if not updated:
            records.append(budget.to_dict())

        atomic_write_jsonl(self.file_path, records)


class RecurringRepository:
    """
    Persistent repository for recurring transaction rules backed by recurring.jsonl (Bonus feature).
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                pass

    def list_all(self) -> List[RecurringRule]:
        rules: List[RecurringRule] = []
        for line in forward_readline(self.file_path):
            try:
                data = json.loads(line)
                rules.append(RecurringRule.from_dict(data))
            except Exception:
                continue
        return rules

    def generate_next_id(self) -> str:
        max_num = 0
        for r in self.list_all():
            if r.id.startswith("REC-"):
                try:
                    num = int(r.id[4:])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        return f"REC-{(max_num + 1):04d}"

    def add(self, rule: RecurringRule) -> None:
        rules = [r.to_dict() for r in self.list_all()]
        rules.append(rule.to_dict())
        atomic_write_jsonl(self.file_path, rules)

    def remove(self, rule_id: str) -> bool:
        rules = self.list_all()
        found = False
        remaining: List[Dict[str, Any]] = []
        for r in rules:
            if r.id == rule_id:
                found = True
            else:
                remaining.append(r.to_dict())
        if not found:
            raise NotFoundError(
                f"존재하지 않는 반복 규칙입니다: '{rule_id}'",
                hint="recurring list 명령으로 등록된 규칙을 확인해주세요.",
            )
        atomic_write_jsonl(self.file_path, remaining)
        return True


class StorageManager:
    """
    Central storage manager that encapsulates all file repositories in a data directory.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        self.transactions_file = os.path.join(self.data_dir, "transactions.jsonl")
        self.categories_file = os.path.join(self.data_dir, "categories.jsonl")
        self.budgets_file = os.path.join(self.data_dir, "budgets.jsonl")
        self.recurring_file = os.path.join(self.data_dir, "recurring.jsonl")

        self.transactions = TransactionRepository(self.transactions_file)
        self.categories = CategoryRepository(self.categories_file)
        self.budgets = BudgetRepository(self.budgets_file)
        self.recurring = RecurringRepository(self.recurring_file)
