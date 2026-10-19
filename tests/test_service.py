"""
Unit and integration tests for BudgetService.
Tests CRUD, streaming search, monthly summary, budget tracking, categories, CSV, and bonus features.
"""

import os
import shutil
import tempfile
import unittest

from budget_app.exceptions import CategoryInUseError, ValidationError
from budget_app.service import BudgetService
from budget_app.storage import StorageManager


class TestBudgetService(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage = StorageManager(data_dir=self.test_dir)
        self.service = BudgetService(self.storage)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_add_transaction_with_valid_category(self):
        tx = self.service.add_transaction(
            date="2024-01-15",
            tx_type="expense",
            category="식비",
            amount=15000,
            memo="점심",
            tags=["외식", "한식"],
        )
        self.assertEqual(tx.id, "TX-000001")
        self.assertEqual(tx.amount, 15000)

    def test_add_transaction_unregistered_category_fails(self):
        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                date="2024-01-15",
                tx_type="expense",
                category="미등록카테고리",
                amount=15000,
            )

    def test_list_transactions_streaming_and_limit(self):
        for i in range(1, 6):
            self.service.add_transaction(
                date=f"2024-01-0{i}",
                tx_type="expense",
                category="식비",
                amount=i * 1000,
            )

        # Reverse chronological check
        results = list(self.service.list_transactions(limit=3))
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].id, "TX-000005")
        self.assertEqual(results[1].id, "TX-000004")
        self.assertEqual(results[2].id, "TX-000003")

    def test_search_transactions(self):
        self.service.add_transaction(
            date="2024-01-10",
            tx_type="income",
            category="급여",
            amount=3000000,
            memo="1월 급여",
            tags=["월급"],
        )
        self.service.add_transaction(
            date="2024-01-15",
            tx_type="expense",
            category="식비",
            amount=15000,
            memo="점심 식사",
            tags=["식사"],
        )
        self.service.add_transaction(
            date="2024-01-20",
            tx_type="expense",
            category="교통",
            amount=20000,
            memo="지하철 정기권",
            tags=["교통비"],
        )

        # Search by date range
        res1 = list(self.service.search_transactions(from_date="2024-01-12", to_date="2024-01-25"))
        self.assertEqual(len(res1), 2)

        # Search by category
        res2 = list(self.service.search_transactions(category="식비"))
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0].memo, "점심 식사")

        # Search by type
        res3 = list(self.service.search_transactions(tx_type="income"))
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0].amount, 3000000)

        # Search by keyword
        res4 = list(self.service.search_transactions(keyword="지하철"))
        self.assertEqual(len(res4), 1)
        self.assertEqual(res4[0].category, "교통")

        # Search by tag
        res5 = list(self.service.search_transactions(tag="월급"))
        self.assertEqual(len(res5), 1)

    def test_monthly_summary_and_budget_tracking(self):
        # Empty month
        summary_empty = self.service.get_monthly_summary("2024-02")
        self.assertFalse(summary_empty["has_data"])

        # Add data for 2024-01
        self.service.add_transaction(
            date="2024-01-01", tx_type="income", category="급여", amount=3000000
        )
        self.service.add_transaction(
            date="2024-01-05", tx_type="expense", category="식비", amount=45000
        )
        self.service.add_transaction(
            date="2024-01-10", tx_type="expense", category="교통", amount=20000
        )
        self.service.add_transaction(
            date="2024-01-15", tx_type="expense", category="주거/통신", amount=150000
        )

        # Set budget 200,000 (total expense is 215,000 -> exceeds budget)
        self.service.set_budget(month="2024-01", amount=200000)

        summary = self.service.get_monthly_summary("2024-01", top_n=3)
        self.assertTrue(summary["has_data"])
        self.assertEqual(summary["total_income"], 3000000)
        self.assertEqual(summary["total_expense"], 215000)
        self.assertEqual(summary["balance"], 2785000)
        self.assertTrue(summary["is_over_budget"])
        self.assertEqual(summary["over_amount"], 15000)
        self.assertAlmostEqual(summary["budget_usage_rate"], 107.5, places=1)

        # TOP categories check
        top_cats = summary["top_categories"]
        self.assertEqual(top_cats[0][0], "주거/통신")
        self.assertEqual(top_cats[0][1], 150000)

    def test_category_management_in_use_protection_and_replacement(self):
        self.service.add_category("도서")
        self.assertTrue(self.storage.categories.exists("도서"))

        # Add transaction using '도서'
        self.service.add_transaction(
            date="2024-01-10",
            tx_type="expense",
            category="도서",
            amount=20000,
        )

        # Deleting without replacement must fail
        with self.assertRaises(CategoryInUseError):
            self.service.remove_category("도서")

        # Deleting with replacement to '기타' must succeed
        self.service.remove_category("도서", replacement="기타")
        self.assertFalse(self.storage.categories.exists("도서"))

        # Verify transaction category is now '기타'
        tx = self.service.storage.transactions.get_by_id("TX-000001")
        self.assertEqual(tx.category, "기타")

    def test_csv_import_export(self):
        # Create CSV file to import
        csv_file = os.path.join(self.test_dir, "import_test.csv")
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("date,type,category,amount,memo,tags\n")
            f.write("2024-01-10,income,급여,3000000,1월급여,월급\n")
            f.write("2024-01-15,expense,식비,15000,점심,외식,점심\n")
            f.write("2024-01-20,expense,신규카테고리,5000,기타비용,\n")

        imported, skipped = self.service.import_csv(csv_file)
        self.assertEqual(imported, 3)
        self.assertEqual(skipped, 0)
        self.assertTrue(self.storage.categories.exists("신규카테고리"))

        # Export by month
        export_file = os.path.join(self.test_dir, "export_test.csv")
        count = self.service.export_csv(out_path=export_file, month="2024-01")
        self.assertEqual(count, 3)
        self.assertTrue(os.path.exists(export_file))

    def test_backup_bonus(self):
        self.service.add_transaction(
            date="2024-01-01", tx_type="income", category="급여", amount=1000000
        )
        backup_zip = self.service.create_backup()
        self.assertTrue(os.path.exists(backup_zip))
        self.assertTrue(backup_zip.endswith(".zip"))

    def test_recurring_transactions_bonus(self):
        self.service.add_recurring_rule(
            name="월세",
            tx_type="expense",
            day_of_month=25,
            amount=500000,
            category="주거/통신",
            memo="매월 월세",
        )
        self.assertEqual(len(self.service.list_recurring_rules()), 1)

        # Apply to 2024-02
        gen_count = self.service.apply_recurring(month="2024-02")
        self.assertEqual(gen_count, 1)

        tx = self.storage.transactions.get_by_id("TX-000001")
        self.assertIsNotNone(tx)
        self.assertEqual(tx.date, "2024-02-25")
        self.assertEqual(tx.amount, 500000)


if __name__ == "__main__":
    unittest.main()
