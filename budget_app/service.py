"""
Service Layer for budget_app.
Contains core domain business logic, validation enforcement, reporting, and file operations.
"""

from collections import Counter
import csv
from datetime import datetime
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple
import zipfile

from budget_app.exceptions import (
    CategoryInUseError,
    ConflictError,
    ImportExportError,
    NotFoundError,
    ValidationError,
)
from budget_app.models import (
    Budget,
    Category,
    RecurringRule,
    Transaction,
    validate_date_string,
    validate_month_string,
    validate_positive_amount,
    validate_transaction_type,
)
from budget_app.storage import StorageManager


class BudgetService:
    """
    Business logic coordinator for the budget application.
    """

    def __init__(self, storage_manager: StorageManager):
        self.storage = storage_manager

    # =========================================================================
    # 1. Transactions CRUD & Streaming
    # =========================================================================

    def add_transaction(
        self,
        date: str,
        tx_type: str,
        category: str,
        amount: int,
        memo: str = "",
        tags: Optional[List[str]] = None,
    ) -> Transaction:
        """
        Validate and create a new transaction with a sequential ID.
        """
        date = validate_date_string(date)
        tx_type = validate_transaction_type(tx_type)
        amount = validate_positive_amount(amount)
        cat_clean = category.strip()

        # Validate that category exists
        if not self.storage.categories.exists(cat_clean):
            valid_cats = [c.name for c in self.storage.categories.list_all()]
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: '{cat_clean}'",
                hint=f"현재 등록된 카테고리 목록: {', '.join(valid_cats)} (필요 시 'category add'로 추가)",
            )

        tx_id = self.storage.transactions.generate_next_id()
        tx = Transaction(
            id=tx_id,
            type=tx_type,
            date=date,
            amount=amount,
            category=cat_clean,
            memo=memo,
            tags=tags or [],
        )
        self.storage.transactions.append(tx)
        return tx

    def list_transactions(self, limit: Optional[int] = None) -> Iterator[Transaction]:
        """
        Stream transactions in reverse chronological order using generator.
        Limits output count if specified.
        """
        count = 0
        for tx in self.storage.transactions.stream_reverse():
            if limit is not None and count >= limit:
                break
            yield tx
            count += 1

    def search_transactions(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category: Optional[str] = None,
        tx_type: Optional[str] = None,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Transaction]:
        """
        Stream search matching transactions in reverse chronological order.
        """
        if from_date:
            validate_date_string(from_date)
        if to_date:
            validate_date_string(to_date)
        if tx_type:
            tx_type = validate_transaction_type(tx_type)

        keyword_lower = keyword.lower() if keyword else None
        tag_lower = tag.lower() if tag else None
        cat_lower = category.lower() if category else None

        count = 0
        for tx in self.storage.transactions.stream_reverse():
            if from_date and tx.date < from_date:
                continue
            if to_date and tx.date > to_date:
                continue
            if cat_lower and tx.category.lower() != cat_lower:
                continue
            if tx_type and tx.type != tx_type:
                continue
            if keyword_lower and not (
                keyword_lower in tx.memo.lower()
                or any(keyword_lower in t.lower() for t in tx.tags)
                or keyword_lower in tx.category.lower()
            ):
                continue
            if tag_lower and not any(tag_lower == t.lower() for t in tx.tags):
                continue

            if limit is not None and count >= limit:
                break

            yield tx
            count += 1

    def update_transaction(
        self,
        tx_id: str,
        date: Optional[str] = None,
        tx_type: Optional[str] = None,
        category: Optional[str] = None,
        amount: Optional[int] = None,
        memo: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Transaction:
        """
        Atomically update an existing transaction.
        """
        existing = self.storage.transactions.get_by_id(tx_id)
        if not existing:
            raise NotFoundError(
                f"ID '{tx_id}'에 해당하는 거래를 찾을 수 없습니다.",
                hint="list 명령으로 존재하는 거래 ID를 확인해주세요.",
            )

        new_date = validate_date_string(date) if date is not None else existing.date
        new_type = validate_transaction_type(tx_type) if tx_type is not None else existing.type
        new_amount = validate_positive_amount(amount) if amount is not None else existing.amount

        new_category = existing.category
        if category is not None:
            cat_clean = category.strip()
            if not self.storage.categories.exists(cat_clean):
                valid_cats = [c.name for c in self.storage.categories.list_all()]
                raise ValidationError(
                    f"등록되지 않은 카테고리입니다: '{cat_clean}'",
                    hint=f"등록된 카테고리: {', '.join(valid_cats)}",
                )
            new_category = cat_clean

        new_memo = memo if memo is not None else existing.memo
        new_tags = tags if tags is not None else existing.tags

        updated = Transaction(
            id=tx_id,
            type=new_type,
            date=new_date,
            amount=new_amount,
            category=new_category,
            memo=new_memo,
            tags=new_tags,
        )
        self.storage.transactions.update(updated)
        return updated

    def delete_transaction(self, tx_id: str) -> bool:
        """
        Delete a transaction by ID.
        """
        return self.storage.transactions.delete(tx_id)

    # =========================================================================
    # 2. Monthly Summary & Budget Verification
    # =========================================================================

    def get_monthly_summary(self, month: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Generate monthly financial summary with income/expense totals, balance,
        top expense categories, and budget comparison.
        """
        month = validate_month_string(month)
        top_n = max(1, top_n)

        total_income = 0
        total_expense = 0
        category_expenses: Counter[str] = Counter()
        tx_count = 0

        for tx in self.storage.transactions.stream_forward():
            if tx.date.startswith(month):
                tx_count += 1
                if tx.type == "income":
                    total_income += tx.amount
                elif tx.type == "expense":
                    total_expense += tx.amount
                    category_expenses[tx.category] += tx.amount

        balance = total_income - total_expense
        budget = self.storage.budgets.get_by_month(month)

        summary: Dict[str, Any] = {
            "month": month,
            "has_data": tx_count > 0,
            "transaction_count": tx_count,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": balance,
            "top_categories": category_expenses.most_common(top_n),
            "budget": budget,
        }

        if budget:
            usage_rate = (total_expense / budget.amount) * 100.0 if budget.amount > 0 else 0.0
            is_over = total_expense > budget.amount
            over_amount = max(0, total_expense - budget.amount)
            summary["budget_usage_rate"] = usage_rate
            summary["is_over_budget"] = is_over
            summary["over_amount"] = over_amount

        return summary

    def set_budget(self, month: str, amount: int) -> Budget:
        """Set or update the monthly expense budget."""
        month = validate_month_string(month)
        amount = validate_positive_amount(amount)
        budget = Budget(month=month, amount=amount)
        self.storage.budgets.set_budget(budget)
        return budget

    def list_budgets(self) -> List[Budget]:
        """List all configured monthly budgets sorted by month descending."""
        return sorted(self.storage.budgets.list_all(), key=lambda b: b.month, reverse=True)

    # =========================================================================
    # 3. Category Management
    # =========================================================================

    def list_categories(self) -> List[Category]:
        """List all registered categories."""
        return self.storage.categories.list_all()

    def add_category(self, name: str) -> Category:
        """Register a new category."""
        category = Category(name=name)
        self.storage.categories.add(category)
        return category

    def remove_category(self, name: str, replacement: Optional[str] = None) -> bool:
        """
        Delete a category. If currently used by transactions, blocks deletion
        unless a replacement category is specified.
        """
        name_clean = name.strip()
        if not self.storage.categories.exists(name_clean):
            raise NotFoundError(
                f"존재하지 않는 카테고리입니다: '{name_clean}'",
                hint="category list 명령으로 등록된 카테고리를 확인해주세요.",
            )

        # Check transactions referencing this category
        referencing_count = sum(
            1 for tx in self.storage.transactions.stream_forward()
            if tx.category.lower() == name_clean.lower()
        )

        if referencing_count > 0:
            if not replacement:
                raise CategoryInUseError(
                    f"카테고리 '{name_clean}'은(는) 현재 {referencing_count}건의 거래 내역에서 사용 중입니다.",
                    hint="해당 거래들을 먼저 수정/삭제하거나, --replace <새카테고리> 옵션을 사용해 대체하세요.",
                )
            replace_clean = replacement.strip()
            if replace_clean.lower() == name_clean.lower():
                raise ValidationError("대체 카테고리는 삭제할 카테고리와 달라야 합니다.")
            if not self.storage.categories.exists(replace_clean):
                raise NotFoundError(
                    f"대체 대상 카테고리 '{replace_clean}'이(가) 등록되어 있지 않습니다.",
                    hint="category list로 등록된 카테고리를 확인하세요.",
                )

            # Update all referencing transactions atomically
            for tx in self.storage.transactions.stream_forward():
                if tx.category.lower() == name_clean.lower():
                    self.storage.transactions.update(
                        Transaction(
                            id=tx.id,
                            type=tx.type,
                            date=tx.date,
                            amount=tx.amount,
                            category=replace_clean,
                            memo=tx.memo,
                            tags=tx.tags,
                        )
                    )

        return self.storage.categories.remove(name_clean)

    # =========================================================================
    # 4. Import / Export (CSV)
    # =========================================================================

    def import_csv(self, file_path: str) -> Tuple[int, int]:
        """
        Import transactions from a CSV file.
        Schema: date (Y), type (Y), category (Y), amount (Y), memo (N), tags (N)
        Returns (imported_count, skipped_count).
        """
        if not os.path.exists(file_path):
            raise ImportExportError(
                f"가져올 CSV 파일을 찾을 수 없습니다: '{file_path}'",
                hint="파일 경로를 다시 확인해주세요.",
            )

        imported = 0
        skipped = 0
        new_transactions: List[Transaction] = []

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                required_cols = {"date", "type", "category", "amount"}
                if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
                    raise ImportExportError(
                        "CSV 헤더 스키마가 일치하지 않습니다.",
                        hint="필수 컬럼: date, type, category, amount (선택: memo, tags)",
                    )

                for row_num, row in enumerate(reader, start=2):
                    try:
                        date_val = validate_date_string(row.get("date", "").strip())
                        type_val = validate_transaction_type(row.get("type", "").strip())
                        amt_val = validate_positive_amount(row.get("amount", "").strip())
                        cat_val = row.get("category", "").strip()
                        if not cat_val:
                            skipped += 1
                            continue

                        # Auto-register category if absent during CSV import
                        if not self.storage.categories.exists(cat_val):
                            self.storage.categories.add(Category(name=cat_val))

                        memo_val = row.get("memo", "").strip() if "memo" in row else ""
                        raw_tags = row.get("tags", "").strip() if "tags" in row else ""
                        if None in row and row[None]:
                            raw_tags = ",".join([raw_tags] + [str(x).strip() for x in row[None] if x])
                        tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()]

                        tx_id = self.storage.transactions.generate_next_id()
                        tx = Transaction(
                            id=tx_id,
                            type=type_val,
                            date=date_val,
                            amount=amt_val,
                            category=cat_val,
                            memo=memo_val,
                            tags=tag_list,
                        )
                        # Immediately append to repo so next ID advances
                        self.storage.transactions.append(tx)
                        imported += 1
                    except Exception:
                        skipped += 1
        except Exception as e:
            if isinstance(e, ImportExportError):
                raise
            raise ImportExportError(
                f"CSV 파일을 읽는 중 오류가 발생했습니다: {e}",
                hint="파일이 UTF-8 인코딩인지, 올바른 CSV 포맷인지 확인하세요.",
            ) from e

        return imported, skipped

    def export_csv(
        self,
        out_path: str,
        month: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> int:
        """
        Export transactions matching month or date range to CSV.
        Requires either --month OR (--from and --to).
        """
        if not month and not (from_date and to_date):
            raise ImportExportError(
                "내보내기 조건이 필요합니다.",
                hint="--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 조건을 입력하세요.",
            )

        if month:
            validate_month_string(month)
        if from_date:
            validate_date_string(from_date)
        if to_date:
            validate_date_string(to_date)

        records_to_export: List[Transaction] = []
        for tx in self.storage.transactions.stream_forward():
            if month and not tx.date.startswith(month):
                continue
            if from_date and tx.date < from_date:
                continue
            if to_date and tx.date > to_date:
                continue
            records_to_export.append(tx)

        out_dir = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(out_dir, exist_ok=True)

        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["date", "type", "category", "amount", "memo", "tags"],
                )
                writer.writeheader()
                for tx in records_to_export:
                    writer.writerow(tx.to_csv_row())
        except Exception as e:
            raise ImportExportError(
                f"CSV 내보내기 실패: {e}",
                hint="대상 파일 경로에 쓰기 권한이 있는지 확인하세요.",
            ) from e

        return len(records_to_export)

    # =========================================================================
    # 5. Bonus Features: Backup & Recurring Transactions
    # =========================================================================

    def create_backup(self, target_dir: Optional[str] = None) -> str:
        """
        Create a timestamped zip archive of all persistent data files.
        """
        backup_folder = target_dir or os.path.join(self.storage.data_dir, "..", "backups")
        backup_folder = os.path.abspath(backup_folder)
        os.makedirs(backup_folder, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"pocketmoney_backup_{timestamp}.zip"
        zip_filepath = os.path.join(backup_folder, zip_filename)

        with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(self.storage.data_dir):
                for file in files:
                    if file.endswith(".jsonl"):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.storage.data_dir)
                        zf.write(full_path, arcname=rel_path)

        return zip_filepath

    def add_recurring_rule(
        self,
        name: str,
        tx_type: str,
        day_of_month: int,
        amount: int,
        category: str,
        memo: str = "",
        tags: Optional[List[str]] = None,
    ) -> RecurringRule:
        """Register a recurring monthly transaction rule."""
        tx_type = validate_transaction_type(tx_type)
        amount = validate_positive_amount(amount)
        if not self.storage.categories.exists(category):
            raise ValidationError(f"등록되지 않은 카테고리입니다: '{category}'")

        rule_id = self.storage.recurring.generate_next_id()
        rule = RecurringRule(
            id=rule_id,
            name=name,
            type=tx_type,
            day_of_month=day_of_month,
            amount=amount,
            category=category,
            memo=memo,
            tags=tags or [],
        )
        self.storage.recurring.add(rule)
        return rule

    def list_recurring_rules(self) -> List[RecurringRule]:
        """List all registered recurring transaction rules."""
        return self.storage.recurring.list_all()

    def remove_recurring_rule(self, rule_id: str) -> bool:
        """Remove a recurring rule by ID."""
        return self.storage.recurring.remove(rule_id)

    def apply_recurring(self, month: str) -> int:
        """
        Apply recurring rules to generate transactions for the given month.
        """
        month = validate_month_string(month)
        year, month_num = map(int, month.split("-"))
        rules = self.storage.recurring.list_all()

        generated_count = 0
        for rule in rules:
            # Determine max days in month (handling leap years safely)
            if month_num in (1, 3, 5, 7, 8, 10, 12):
                max_day = 31
            elif month_num in (4, 6, 9, 11):
                max_day = 30
            else:
                is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
                max_day = 29 if is_leap else 28

            actual_day = min(rule.day_of_month, max_day)
            date_str = f"{year:04d}-{month_num:02d}-{actual_day:02d}"

            # Append transaction
            self.add_transaction(
                date=date_str,
                tx_type=rule.type,
                category=rule.category,
                amount=rule.amount,
                memo=f"[반복: {rule.name}] {rule.memo}".strip(),
                tags=rule.tags + ["recurring"],
            )
            generated_count += 1

        return generated_count
