"""
Unit tests for domain models and validation logic.
"""

import unittest

from budget_app.exceptions import ValidationError
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


class TestModels(unittest.TestCase):

    def test_valid_transaction(self):
        tx = Transaction(
            id="TX-000001",
            type="expense",
            date="2024-01-15",
            amount=15000,
            category="식비",
            memo="점심 식사",
            tags=["점심", "한식"],
        )
        self.assertEqual(tx.id, "TX-000001")
        self.assertEqual(tx.type, "expense")
        self.assertEqual(tx.amount, 15000)
        self.assertEqual(tx.tags, ["점심", "한식"])

        # Dict conversion
        d = tx.to_dict()
        self.assertEqual(d["id"], "TX-000001")
        self.assertEqual(d["amount"], 15000)

        # Reconstructed from dict
        reconstructed = Transaction.from_dict(d)
        self.assertEqual(reconstructed.id, tx.id)
        self.assertEqual(reconstructed.memo, tx.memo)

    def test_invalid_transaction_date(self):
        with self.assertRaises(ValidationError):
            Transaction(
                id="TX-1",
                type="expense",
                date="2024-13-40",
                amount=1000,
                category="식비",
            )

        with self.assertRaises(ValidationError):
            validate_date_string("invalid-date")

    def test_invalid_transaction_type(self):
        with self.assertRaises(ValidationError):
            Transaction(
                id="TX-1",
                type="unknown",
                date="2024-01-01",
                amount=1000,
                category="식비",
            )

    def test_invalid_transaction_amount(self):
        with self.assertRaises(ValidationError):
            Transaction(
                id="TX-1",
                type="income",
                date="2024-01-01",
                amount=-500,
                category="급여",
            )
        with self.assertRaises(ValidationError):
            validate_positive_amount(0)

    def test_empty_category(self):
        with self.assertRaises(ValidationError):
            Transaction(
                id="TX-1",
                type="income",
                date="2024-01-01",
                amount=5000,
                category="   ",
            )

    def test_csv_row_conversion(self):
        tx = Transaction(
            id="TX-000002",
            type="income",
            date="2024-01-10",
            amount=3000000,
            category="급여",
            memo="1월 급여",
            tags=["월급", "본업"],
        )
        csv_row = tx.to_csv_row()
        self.assertEqual(csv_row["date"], "2024-01-10")
        self.assertEqual(csv_row["type"], "income")
        self.assertEqual(csv_row["category"], "급여")
        self.assertEqual(csv_row["amount"], "3000000")
        self.assertEqual(csv_row["tags"], "월급,본업")

    def test_budget_model(self):
        b = Budget(month="2024-01", amount=500000)
        self.assertEqual(b.month, "2024-01")
        self.assertEqual(b.amount, 500000)

        with self.assertRaises(ValidationError):
            Budget(month="2024-13", amount=1000)

        with self.assertRaises(ValidationError):
            Budget(month="2024-01", amount=-100)

    def test_category_model(self):
        cat = Category(name="외식")
        self.assertEqual(cat.name, "외식")
        with self.assertRaises(ValidationError):
            Category(name="   ")

    def test_recurring_rule_model(self):
        r = RecurringRule(
            id="REC-0001",
            name="월세",
            type="expense",
            day_of_month=25,
            amount=500000,
            category="주거",
            memo="매월 월세",
        )
        self.assertEqual(r.id, "REC-0001")
        self.assertEqual(r.day_of_month, 25)

        with self.assertRaises(ValidationError):
            RecurringRule(
                id="REC-0002",
                name="잘못된일자",
                type="expense",
                day_of_month=32,
                amount=1000,
                category="주거",
            )


if __name__ == "__main__":
    unittest.main()
