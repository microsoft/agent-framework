# Copyright (c) Microsoft. All rights reserved.

"""Confirmation strategies for human-in-the-loop approval flows.

Each agent can provide a custom confirmation strategy to generate domain-specific
messages when users approve or reject changes/actions.
"""

from abc import ABC, abstractmethod
from typing import Any


class ConfirmationStrategy(ABC):
    """Strategy for generating confirmation messages during human-in-the-loop flows."""

    @abstractmethod
    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate message when user approves function execution.

        Args:
            steps: List of approved steps with 'description', 'status', etc.

        Returns:
            Message to display to user
        """
        ...

    @abstractmethod
    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate message when user rejects function execution.

        Args:
            steps: List of rejected steps

        Returns:
            Message to display to user
        """
        ...

    @abstractmethod
    def on_state_confirmed(self) -> str:
        """Generate message when user confirms predictive state changes.

        Returns:
            Message to display to user
        """
        ...

    @abstractmethod
    def on_state_rejected(self) -> str:
        """Generate message when user rejects predictive state changes.

        Returns:
            Message to display to user
        """
        ...


class DefaultConfirmationStrategy(ConfirmationStrategy):
    """Generic confirmation messages suitable for most agents.

    This preserves the original behavior from v1.
    """

    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate generic approval message with step list."""
        enabled_steps = [s for s in steps if s.get("status") == "enabled"]

        message_parts = [f"Executing {len(enabled_steps)} approved steps:\n\n"]

        for i, step in enumerate(enabled_steps, 1):
            message_parts.append(f"{i}. {step['description']}\n")

        message_parts.append("\nAll steps completed successfully!")

        return "".join(message_parts)

    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate generic rejection message."""
        return "No problem! What would you like me to change about the plan?"

    def on_state_confirmed(self) -> str:
        """Generate generic state confirmation message."""
        return "Changes confirmed and applied successfully!"

    def on_state_rejected(self) -> str:
        """Generate generic state rejection message."""
        return "No problem! What would you like me to change?"


class TaskPlannerConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for task planning agents."""

    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate task-specific approval message."""
        enabled_steps = [s for s in steps if s.get("status") == "enabled"]

        message_parts = ["Executing your requested tasks:\n\n"]

        for i, step in enumerate(enabled_steps, 1):
            message_parts.append(f"{i}. {step['description']}\n")

        message_parts.append("\nAll tasks completed successfully!")

        return "".join(message_parts)

    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate task-specific rejection message."""
        return "No problem! Let me revise the plan. What would you like me to change?"

    def on_state_confirmed(self) -> str:
        """Task planners typically don't use state confirmation."""
        return "Tasks confirmed and ready to execute!"

    def on_state_rejected(self) -> str:
        """Task planners typically don't use state confirmation."""
        return "No problem! How should I adjust the task list?"


class RecipeConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for recipe agents."""

    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate recipe-specific approval message."""
        enabled_steps = [s for s in steps if s.get("status") == "enabled"]

        message_parts = ["Updating your recipe:\n\n"]

        for i, step in enumerate(enabled_steps, 1):
            message_parts.append(f"{i}. {step['description']}\n")

        message_parts.append("\nRecipe updated successfully!")

        return "".join(message_parts)

    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate recipe-specific rejection message."""
        return "No problem! What ingredients or steps should I change?"

    def on_state_confirmed(self) -> str:
        """Generate recipe-specific state confirmation message."""
        return "Recipe changes applied successfully!"

    def on_state_rejected(self) -> str:
        """Generate recipe-specific state rejection message."""
        return "No problem! What would you like me to adjust in the recipe?"


class DocumentWriterConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for document writing agents."""

    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate document-specific approval message."""
        enabled_steps = [s for s in steps if s.get("status") == "enabled"]

        message_parts = ["Applying your edits:\n\n"]

        for i, step in enumerate(enabled_steps, 1):
            message_parts.append(f"{i}. {step['description']}\n")

        message_parts.append("\nDocument updated successfully!")

        return "".join(message_parts)

    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate document-specific rejection message."""
        return "No problem! Which changes should I keep or modify?"

    def on_state_confirmed(self) -> str:
        """Generate document-specific state confirmation message."""
        return "Document edits applied!"

    def on_state_rejected(self) -> str:
        """Generate document-specific state rejection message."""
        return "No problem! What should I change about the document?"
