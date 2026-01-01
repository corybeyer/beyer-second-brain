"""Structured logging utilities.

Provides JSON-formatted logs per System Behavior observability spec.
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """Logger that outputs structured JSON for observability."""

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize structured logger.

        Args:
            logger: Python logger to use (defaults to root logger)
        """
        self.logger = logger or logging.getLogger()
        self._context: dict[str, Any] = {}

    def set_context(self, **kwargs: Any) -> None:
        """Set persistent context fields for all subsequent logs.

        Args:
            **kwargs: Context fields (e.g., source_id, file_path)
        """
        self._context.update(kwargs)

    def clear_context(self) -> None:
        """Clear all context fields."""
        self._context = {}

    def _format_log(
        self,
        level: str,
        step: str,
        message: str,
        duration_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Format a structured log entry.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            step: Pipeline step (validate, parse, chunk, extract, store)
            message: Human-readable message
            duration_ms: Operation duration in milliseconds
            **kwargs: Additional fields

        Returns:
            JSON-formatted log string
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "step": step,
            "message": message,
            **self._context,
            **kwargs,
        }

        if duration_ms is not None:
            entry["duration_ms"] = duration_ms

        return json.dumps(entry)

    def info(
        self,
        step: str,
        message: str,
        duration_ms: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log info-level structured message.

        Args:
            step: Pipeline step
            message: Human-readable message
            duration_ms: Operation duration in milliseconds
            **kwargs: Additional fields
        """
        self.logger.info(self._format_log("INFO", step, message, duration_ms, **kwargs))

    def warning(
        self,
        step: str,
        message: str,
        duration_ms: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log warning-level structured message.

        Args:
            step: Pipeline step
            message: Human-readable message
            duration_ms: Operation duration in milliseconds
            **kwargs: Additional fields
        """
        self.logger.warning(
            self._format_log("WARNING", step, message, duration_ms, **kwargs)
        )

    def error(
        self,
        step: str,
        message: str,
        duration_ms: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log error-level structured message.

        Args:
            step: Pipeline step
            message: Human-readable message
            duration_ms: Operation duration in milliseconds
            **kwargs: Additional fields
        """
        self.logger.error(
            self._format_log("ERROR", step, message, duration_ms, **kwargs)
        )

    @contextmanager
    def timed_operation(self, step: str, message: str, **kwargs: Any):
        """Context manager for timing operations.

        Args:
            step: Pipeline step
            message: Message to log on completion
            **kwargs: Additional fields

        Yields:
            dict that can be updated with additional fields during operation
        """
        start_time = time.time()
        extra_fields: dict[str, Any] = {}

        try:
            yield extra_fields
            duration_ms = int((time.time() - start_time) * 1000)
            self.info(step, message, duration_ms=duration_ms, **kwargs, **extra_fields)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.error(
                step,
                f"{message} - FAILED: {e!s}",
                duration_ms=duration_ms,
                error=str(e),
                **kwargs,
                **extra_fields,
            )
            raise


# Global logger instance
structured_logger = StructuredLogger()
