"""
Unit tests for storage layer and atomic operations.
"""

import os
import shutil
import tempfile
import unittest

from budget_app.models import Budget, Category, Transaction
from budget_app.storage import (
    BudgetRepository,
    CategoryRepository,
    StorageManager,
    TransactionRepository,
    atomic_write_jsonl,
    forward_readline,
    reverse_readline,
)


class TestStorage(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage = StorageManager(data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_reverse_and_forward_readline(self):
        file_path = os.path.join(self.test_dir, "test_lines.txt")
        lines = [f"line_{i}" for i in range(1, 20)]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Forward
        fwd = list(forward_readline(file_path))
        self.assertEqual(fwd, lines)

        # Reverse
        rev = list(reverse_readline(file_path))
        self.assertEqual(rev, list(reversed(lines)))

    def test_atomic_write(self):
        file_path = os.path.join(self.test_dir, "atomic.jsonl")
        data = [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]
        atomic_write_jsonl(file_path, data)

        self.assertTrue(os.path.exists(file_path))
        lines = list(forward_readline(file_path))
        self.assertEqual(len(lines), 2)

    def test_transaction_repository_crud(self):
        repo = self.storage.transactions
        self.assertEqual(repo.generate_next_id(), "TX-000001")

        tx1 = Transaction(
            id="TX-000001",
            type="expense",
            date="2024-01-01",
            amount=10000,
            category="식비",
        )
        repo.append(tx1)

        self.assertEqual(repo.generate_next_id(), "TX-000002")

        tx2 = Transaction(
            id="TX-000002",
            type="income",
            date="2024-01-02",
            amount=20000,
            category="급여",
        )
        repo.append(tx2)

        # Stream reverse check
        reversed_txs = list(repo.stream_reverse())
        self.assertEqual(len(reversed_txs), 2)
        self.assertEqual(reversed_txs[0].id, "TX-000002")
        self.assertEqual(reversed_txs[1].id, "TX-000001")

        # Update
        updated_tx1 = Transaction(
            id="TX-000001",
            type="expense",
            date="2024-01-01",
            amount=15000,
            category="식비",
            memo="수정됨",
        )
        repo.update(updated_tx1)
        fetched = repo.get_by_id("TX-000001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.amount, 15000)
        self.assertEqual(fetched.memo, "수정됨")

        # Delete
        repo.delete("TX-000001")
        self.assertIsNone(repo.get_by_id("TX-000001"))
        self.assertEqual(len(list(repo.stream_forward())), 1)

    def test_category_repository_defaults(self):
        cat_repo = self.storage.categories
        cats = cat_repo.list_all()
        # Default categories auto-generated (Plan A)
        self.assertTrue(len(cats) > 0)
        self.assertTrue(cat_repo.exists("식비"))

        # Add new
        cat_repo.add(Category(name="자기계발"))
        self.assertTrue(cat_repo.exists("자기계발"))

        # Remove
        cat_repo.remove("자기계발")
        self.assertFalse(cat_repo.exists("자기계발"))

    def test_budget_repository(self):
        budget_repo = self.storage.budgets
        budget_repo.set_budget(Budget(month="2024-01", amount=500000))
        fetched = budget_repo.get_by_month("2024-01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.amount, 500000)

        # Upsert
        budget_repo.set_budget(Budget(month="2024-01", amount=600000))
        fetched2 = budget_repo.get_by_month("2024-01")
        self.assertEqual(fetched2.amount, 600000)


if __name__ == "__main__":
    unittest.main()
