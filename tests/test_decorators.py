"""
Unit tests for decorators.
"""

import io
import os
import sys
import unittest

from budget_app.decorators import handle_cli_errors, measure_time
from budget_app.exceptions import BudgetAppException, ValidationError


class TestDecorators(unittest.TestCase):

    def test_handle_cli_errors_normal(self):
        @handle_cli_errors
        def successful_func():
            return 0

        self.assertEqual(successful_func(), 0)

    def test_handle_cli_errors_domain_exception(self):
        @handle_cli_errors
        def failing_func():
            raise ValidationError("테스트 유효성 오류입니다.", hint="이렇게 해결하세요.")

        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            code = failing_func()
        finally:
            sys.stderr = old_stderr

        self.assertEqual(code, 1)
        output = stderr_capture.getvalue()
        self.assertIn("[오류] 테스트 유효성 오류입니다.", output)
        self.assertIn("[힌트] 이렇게 해결하세요.", output)

    def test_handle_cli_errors_keyboard_interrupt(self):
        @handle_cli_errors
        def interrupted_func():
            raise KeyboardInterrupt()

        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            code = interrupted_func()
        finally:
            sys.stderr = old_stderr

        self.assertEqual(code, 130)
        self.assertIn("작업이 사용자에 의해 중단되었습니다", stderr_capture.getvalue())

    def test_measure_time(self):
        @measure_time
        def sample_action():
            return 42

        os.environ["BUDGET_APP_VERBOSE"] = "1"
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            result = sample_action()
        finally:
            sys.stderr = old_stderr
            os.environ.pop("BUDGET_APP_VERBOSE", None)

        self.assertEqual(result, 42)
        self.assertIn("[성능]", stderr_capture.getvalue())


if __name__ == "__main__":
    unittest.main()
