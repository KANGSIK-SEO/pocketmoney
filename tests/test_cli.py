"""
Integration tests for CLI entrypoints and user interactions.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from budget_app.cli import main


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.common_args = ["--data-dir", self.test_dir]

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_cli(self, args: list, input_text: str = "") -> tuple:
        """Run CLI with arguments and optional standard input, capturing stdout and stderr."""
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        full_args = self.common_args + args
        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            with patch("sys.stdin", io.StringIO(input_text)):
                exit_code = main(full_args)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_cli_help(self):
        code, out, err = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("나만의 용돈 기입장", out)

    def test_cli_add_interactive_and_list(self):
        # Interactive inputs for add:
        # 날짜(YYYY-MM-DD): 2024-01-15
        # 타입(income/expense): expense
        # 카테고리: 식비
        # 금액(양수): 15000
        # 메모(선택): 점심
        # 태그(쉼표로 구분): meal
        inputs = "2024-01-15\nexpense\n식비\n15000\n점심\nmeal\n"
        code, out, err = self.run_cli(["add"], input_text=inputs)
        self.assertEqual(code, 0)
        self.assertIn("[저장 완료] id=TX-000001", out)

        # list
        code, out, err = self.run_cli(["list"])
        self.assertEqual(code, 0)
        self.assertIn("TX-000001", out)
        self.assertIn("15000", out)
        self.assertIn("식비", out)

    def test_cli_category_workflow(self):
        # Add category
        code, out, err = self.run_cli(["category", "add", "취미"])
        self.assertEqual(code, 0)
        self.assertIn("category=취미", out)

        # List category
        code, out, err = self.run_cli(["category", "list"])
        self.assertEqual(code, 0)
        self.assertIn("취미", out)

        # Remove category
        code, out, err = self.run_cli(["category", "remove", "취미"])
        self.assertEqual(code, 0)
        self.assertIn("[삭제 완료] category=취미", out)

    def test_cli_budget_and_summary(self):
        # Add income and expense
        inputs1 = "2024-01-10\nincome\n급여\n3000000\n급여\n\n"
        self.run_cli(["add"], input_text=inputs1)

        inputs2 = "2024-01-15\nexpense\n식비\n15000\n점심\n\n"
        self.run_cli(["add"], input_text=inputs2)

        # Set budget
        code, out, err = self.run_cli(["budget", "set", "--month", "2024-01", "--amount", "500000"])
        self.assertEqual(code, 0)
        self.assertIn("2024-01 예산 500000원", out)

        # Summary
        code, out, err = self.run_cli(["summary", "--month", "2024-01"])
        self.assertEqual(code, 0)
        self.assertIn("총 수입: 3000000원", out)
        self.assertIn("총 지출: 15000원", out)
        self.assertIn("예산: 500000원", out)
        self.assertIn("사용률", out)

    def test_cli_update_and_delete(self):
        inputs = "2024-01-15\nexpense\n식비\n15000\n점심\n\n"
        self.run_cli(["add"], input_text=inputs)

        # Option-based update
        code, out, err = self.run_cli(["update", "--id", "TX-000001", "--amount", "20000", "--memo", "저녁"])
        self.assertEqual(code, 0)
        self.assertIn("[수정 완료]", out)
        self.assertIn("20000원", out)

        # Delete
        code, out, err = self.run_cli(["delete", "--id", "TX-000001"])
        self.assertEqual(code, 0)
        self.assertIn("[삭제 완료] id=TX-000001", out)

        # Delete non-existent
        code, out, err = self.run_cli(["delete", "--id", "TX-999999"])
        self.assertEqual(code, 1)
        self.assertIn("[오류]", err)

    def test_cli_export_and_import(self):
        inputs = "2024-01-15\nexpense\n식비\n15000\n점심\n\n"
        self.run_cli(["add"], input_text=inputs)

        csv_path = os.path.join(self.test_dir, "export.csv")
        code, out, err = self.run_cli(["export", "--out", csv_path, "--month", "2024-01"])
        self.assertEqual(code, 0)
        self.assertIn("(1 records)", out)

        # Import into fresh dir
        new_data_dir = os.path.join(self.test_dir, "new_data")
        code, out, err = self.run_cli(["--data-dir", new_data_dir, "import", "--from", csv_path])
        self.assertEqual(code, 0)
        self.assertIn("imported=1", out)

    def test_cli_korean_aliases(self):
        # 1. 카테고리 추가 / 목록
        code, out, err = self.run_cli(["카테고리", "추가", "문화"])
        self.assertEqual(code, 0)
        self.assertIn("category=문화", out)

        code, out, err = self.run_cli(["카테고리 관리", "목록"])
        self.assertEqual(code, 0)
        self.assertIn("문화", out)

        # 2. 거래 추가 (한글 서브커맨드)
        inputs = "2024-02-10\nexpense\n문화\n30000\n영화\n\n"
        code, out, err = self.run_cli(["추가"], input_text=inputs)
        self.assertEqual(code, 0)
        self.assertIn("[저장 완료] id=TX-000001", out)

        # 3. 목록 조회 (한글 서브커맨드)
        code, out, err = self.run_cli(["목록"])
        self.assertEqual(code, 0)
        self.assertIn("영화", out)

        # 4. 검색 (한글 서브커맨드)
        code, out, err = self.run_cli(["검색", "--q", "영화"])
        self.assertEqual(code, 0)
        self.assertIn("영화", out)

        # 5. 예산 설정 (한글 서브커맨드)
        code, out, err = self.run_cli(["예산", "설정", "--month", "2024-02", "--amount", "200000"])
        self.assertEqual(code, 0)
        self.assertIn("2024-02 예산 200000원", out)

        # 6. 월별 요약 (한글 서브커맨드)
        code, out, err = self.run_cli(["월별", "요약", "--month", "2024-02"])
        self.assertEqual(code, 0)
        self.assertIn("총 지출: 30000원", out)
        self.assertIn("예산: 200000원", out)


if __name__ == "__main__":
    unittest.main()
