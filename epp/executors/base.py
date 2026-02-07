"""
Base executor interface for EPP.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel

from ..models import Envelope


class ExecutionResult(BaseModel):
    """Result of executing an accepted envelope."""

    success: bool
    executor_name: str
    result_data: Dict[str, Any] = {}
    error_message: Optional[str] = None


class Executor(ABC):
    """
    Abstract base class for EPP executors.

    Executors process accepted envelopes and perform actions
    based on the prompt and context.
    """

    @abstractmethod
    def name(self) -> str:
        """Return the name of this executor."""
        pass

    @abstractmethod
    def execute(self, envelope: Envelope) -> ExecutionResult:
        """
        Execute an accepted envelope.

        Args:
            envelope: The accepted EPP envelope

        Returns:
            Execution result with success status and optional data
        """
        pass
