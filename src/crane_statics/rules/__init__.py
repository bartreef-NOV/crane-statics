"""Classification-rule support (ABS/DNV). Pure: no Qt, no UI."""

from .validation import RulesValidationError, validate_rules_document

__all__ = ["RulesValidationError", "validate_rules_document"]
