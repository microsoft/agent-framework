# Copyright (c) Microsoft. All rights reserved.

"""Confirmation strategies for human-in-the-loop approval flows.

Each agent can provide a custom confirmation strategy to generate domain-specific
messages when users approve or reject changes/actions.
"""

from abc import ABC, abstractmethod
from typing import Any


class ConfirmationStrategy(ABC):
    """Strategy for generating confirmation messages during human-in-the-loop flows.

    Subclasses must define the message properties. The methods use those properties
    by default, but can be overridden for complete customization.
    """

    @property
    @abstractmethod
    def approval_header(self) -> str:
        """Header for approval accepted message. Must be overridden."""
        ...

    @property
    @abstractmethod
    def approval_footer(self) -> str:
        """Footer for approval accepted message. Must be overridden."""
        ...

    @property
    @abstractmethod
    def rejection_message(self) -> str:
        """Message when user rejects. Must be overridden."""
        ...

    @property
    @abstractmethod
    def state_confirmed_message(self) -> str:
        """Message when state is confirmed. Must be overridden."""
        ...

    @property
    @abstractmethod
    def state_rejected_message(self) -> str:
        """Message when state is rejected. Must be overridden."""
        ...

    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        """Generate message when user approves function execution.

        Default implementation uses header/footer properties.
        Override for complete customization.

        Args:
            steps: List of approved steps with 'description', 'status', etc.

        Returns:
            Message to display to user
        """
        enabled_steps = [s for s in steps if s.get("status") == "enabled"]
        message_parts = [self.approval_header.format(count=len(enabled_steps))]
        for i, step in enumerate(enabled_steps, 1):
            message_parts.append(f"{i}. {step['description']}\n")
        message_parts.append(self.approval_footer)
        return "".join(message_parts)

    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        """Generate message when user rejects function execution.

        Args:
            steps: List of rejected steps

        Returns:
            Message to display to user
        """
        return self.rejection_message

    def on_state_confirmed(self) -> str:
        """Generate message when user confirms predictive state changes.

        Returns:
            Message to display to user
        """
        return self.state_confirmed_message

    def on_state_rejected(self) -> str:
        """Generate message when user rejects predictive state changes.

        Returns:
            Message to display to user
        """
        return self.state_rejected_message


class DefaultConfirmationStrategy(ConfirmationStrategy):
    """Generic confirmation messages suitable for most agents."""

    @property
    def approval_header(self) -> str:
        return "Executing {count} approved steps:\n\n"

    @property
    def approval_footer(self) -> str:
        return "\nAll steps completed successfully!"

    @property
    def rejection_message(self) -> str:
        return "No problem! What would you like me to change about the plan?"

    @property
    def state_confirmed_message(self) -> str:
        return "Changes confirmed and applied successfully!"

    @property
    def state_rejected_message(self) -> str:
        return "No problem! What would you like me to change?"


class TaskPlannerConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for task planning agents."""

    @property
    def approval_header(self) -> str:
        return "Executing your requested tasks:\n\n"

    @property
    def approval_footer(self) -> str:
        return "\nAll tasks completed successfully!"

    @property
    def rejection_message(self) -> str:
        return "No problem! Let me revise the plan. What would you like me to change?"

    @property
    def state_confirmed_message(self) -> str:
        return "Tasks confirmed and ready to execute!"

    @property
    def state_rejected_message(self) -> str:
        return "No problem! How should I adjust the task list?"


class RecipeConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for recipe agents."""

    @property
    def approval_header(self) -> str:
        return "Updating your recipe:\n\n"

    @property
    def approval_footer(self) -> str:
        return "\nRecipe updated successfully!"

    @property
    def rejection_message(self) -> str:
        return "No problem! What ingredients or steps should I change?"

    @property
    def state_confirmed_message(self) -> str:
        return "Recipe changes applied successfully!"

    @property
    def state_rejected_message(self) -> str:
        return "No problem! What would you like me to adjust in the recipe?"


class DocumentWriterConfirmationStrategy(ConfirmationStrategy):
    """Domain-specific confirmation messages for document writing agents."""

    @property
    def approval_header(self) -> str:
        return "Applying your edits:\n\n"

    @property
    def approval_footer(self) -> str:
        return "\nDocument updated successfully!"

    @property
    def rejection_message(self) -> str:
        return "No problem! Which changes should I keep or modify?"

    @property
    def state_confirmed_message(self) -> str:
        return "Document edits applied!"

    @property
    def state_rejected_message(self) -> str:
        return "No problem! What should I change about the document?"


def apply_confirmation_strategy(
    strategy: ConfirmationStrategy | None,
    accepted: bool,
    steps: list[dict[str, Any]],
) -> str:
    """Apply a confirmation strategy to generate a message.

    This helper consolidates the pattern used in multiple orchestrators.

    Args:
        strategy: Strategy to use, or None for default
        accepted: Whether the user approved
        steps: List of steps (may be empty for state confirmations)

    Returns:
        Generated message string
    """
    if strategy is None:
        strategy = DefaultConfirmationStrategy()

    if not steps:
        # State confirmation (no steps)
        return strategy.on_state_confirmed() if accepted else strategy.on_state_rejected()
    # Step-based approval
    return strategy.on_approval_accepted(steps) if accepted else strategy.on_approval_rejected(steps)
