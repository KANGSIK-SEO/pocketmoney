"""
Domain Exceptions for budget_app.
Contains structured exception types providing human-readable causes and actionable hints.
"""

from typing import Optional


class BudgetAppException(Exception):
    """Base exception class for all budget application domain errors."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message} (힌트: {self.hint})"
        return self.message


class ValidationError(BudgetAppException):
    """Raised when user input or data record fails validation rules."""
    pass


class NotFoundError(BudgetAppException):
    """Raised when a requested resource (transaction, category, budget) does not exist."""
    pass


class CategoryInUseError(BudgetAppException):
    """Raised when attempting to delete a category currently referenced by transactions."""
    pass


class ConflictError(BudgetAppException):
    """Raised when an entity already exists (e.g., duplicate category name)."""
    pass


class ImportExportError(BudgetAppException):
    """Raised during CSV import or export failures."""
    pass
