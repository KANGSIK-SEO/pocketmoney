"""
Decorators for cross-cutting concerns: error handling, execution time measurement, and logging.
"""

from functools import wraps
import logging
import os
import sys
import time
from typing import Any, Callable, Optional, TypeVar

from budget_app.exceptions import BudgetAppException

F = TypeVar("F", bound=Callable[..., Any])

# Configure budget logger
logger = logging.getLogger("budget_app")


def handle_cli_errors(func: F) -> F:
    """
    Decorator for CLI command entrypoints.
    Intercepts domain exceptions and prints formatted error and hint messages
    without raw stack traces, returning non-zero exit codes.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> int:
        try:
            result = func(*args, **kwargs)
            if isinstance(result, int):
                return result
            return 0
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BudgetAppException as e:
            print(f"[오류] {e.message}", file=sys.stderr)
            if e.hint:
                print(f"[힌트] {e.hint}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\n[안내] 작업이 사용자에 의해 중단되었습니다.", file=sys.stderr)
            return 130
        except Exception as e:
            # Fallback safe error handler for unanticipated system errors
            print(f"[오류] 예기치 못한 시스템 오류가 발생했습니다: {e}", file=sys.stderr)
            print("[힌트] 입력 파라미터 및 파일 시스템 권한을 확인해주세요.", file=sys.stderr)
            return 1

    return wrapper  # type: ignore[return-value]


def measure_time(func: F) -> F:
    """
    Decorator to measure function execution time in milliseconds.
    If verbose flag or environment variable is active, prints timing information to stderr.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            # Check if verbose mode is requested in args/kwargs or env
            verbose = os.environ.get("BUDGET_APP_VERBOSE", "0") == "1"
            if not verbose and args and hasattr(args[0], "verbose"):
                verbose = getattr(args[0], "verbose", False)
            if verbose:
                print(f"[성능] {func.__name__} 실행 소요 시간: {elapsed_ms:.2f}ms", file=sys.stderr)

    return wrapper  # type: ignore[return-value]


def log_audit(action_name: str) -> Callable[[F], F]:
    """
    Decorator to log actions into an audit log file when available.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            logger.debug("Action '%s' completed successfully.", action_name)
            return result
        return wrapper  # type: ignore[return-value]
    return decorator
