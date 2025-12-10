# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive tests for all confirmation strategies."""

import pytest

from agent_framework_ag_ui._confirmation_strategies import (
    ConfirmationStrategy,
    DefaultConfirmationStrategy,
    DocumentWriterConfirmationStrategy,
    RecipeConfirmationStrategy,
    TaskPlannerConfirmationStrategy,
)


@pytest.fixture
def sample_steps() -> list[dict[str, str]]:
    """Sample steps for testing approval messages."""
    return [
        {"description": "Step 1: Do something", "status": "enabled"},
        {"description": "Step 2: Do another thing", "status": "enabled"},
        {"description": "Step 3: Disabled step", "status": "disabled"},
    ]


@pytest.fixture
def all_enabled_steps() -> list[dict[str, str]]:
    """All steps enabled."""
    return [
        {"description": "Task A", "status": "enabled"},
        {"description": "Task B", "status": "enabled"},
        {"description": "Task C", "status": "enabled"},
    ]


@pytest.fixture
def empty_steps() -> list[dict[str, str]]:
    """Empty steps list."""
    return []


class TestDefaultConfirmationStrategy:
    """Tests for DefaultConfirmationStrategy."""

    def test_on_approval_accepted_with_enabled_steps(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_approval_accepted(sample_steps)

        assert "Executing 2 approved steps" in message
        assert "Step 1: Do something" in message
        assert "Step 2: Do another thing" in message
        assert "Step 3" not in message  # Disabled step shouldn't appear
        assert "All steps completed successfully!" in message

    def test_on_approval_accepted_with_all_enabled(self, all_enabled_steps: list[dict[str, str]]) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_approval_accepted(all_enabled_steps)

        assert "Executing 3 approved steps" in message
        assert "Task A" in message
        assert "Task B" in message
        assert "Task C" in message

    def test_on_approval_accepted_with_empty_steps(self, empty_steps: list[dict[str, str]]) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_approval_accepted(empty_steps)

        assert "Executing 0 approved steps" in message
        assert "All steps completed successfully!" in message

    def test_on_approval_rejected(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_approval_rejected(sample_steps)

        assert "No problem!" in message
        assert "What would you like me to change" in message

    def test_on_state_confirmed(self) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_state_confirmed()

        assert "Changes confirmed" in message
        assert "successfully" in message

    def test_on_state_rejected(self) -> None:
        strategy = DefaultConfirmationStrategy()
        message = strategy.on_state_rejected()

        assert "No problem!" in message
        assert "What would you like me to change" in message


class TestTaskPlannerConfirmationStrategy:
    """Tests for TaskPlannerConfirmationStrategy."""

    def test_on_approval_accepted_with_enabled_steps(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_approval_accepted(sample_steps)

        assert "Executing your requested tasks" in message
        assert "1. Step 1: Do something" in message
        assert "2. Step 2: Do another thing" in message
        assert "Step 3" not in message
        assert "All tasks completed successfully!" in message

    def test_on_approval_accepted_with_all_enabled(self, all_enabled_steps: list[dict[str, str]]) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_approval_accepted(all_enabled_steps)

        assert "Executing your requested tasks" in message
        assert "1. Task A" in message
        assert "2. Task B" in message
        assert "3. Task C" in message

    def test_on_approval_accepted_with_empty_steps(self, empty_steps: list[dict[str, str]]) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_approval_accepted(empty_steps)

        assert "Executing your requested tasks" in message
        assert "All tasks completed successfully!" in message

    def test_on_approval_rejected(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_approval_rejected(sample_steps)

        assert "No problem!" in message
        assert "revise the plan" in message

    def test_on_state_confirmed(self) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_state_confirmed()

        assert "Tasks confirmed" in message
        assert "ready to execute" in message

    def test_on_state_rejected(self) -> None:
        strategy = TaskPlannerConfirmationStrategy()
        message = strategy.on_state_rejected()

        assert "No problem!" in message
        assert "adjust the task list" in message


class TestRecipeConfirmationStrategy:
    """Tests for RecipeConfirmationStrategy."""

    def test_on_approval_accepted_with_enabled_steps(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_approval_accepted(sample_steps)

        assert "Updating your recipe" in message
        assert "1. Step 1: Do something" in message
        assert "2. Step 2: Do another thing" in message
        assert "Step 3" not in message
        assert "Recipe updated successfully!" in message

    def test_on_approval_accepted_with_all_enabled(self, all_enabled_steps: list[dict[str, str]]) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_approval_accepted(all_enabled_steps)

        assert "Updating your recipe" in message
        assert "1. Task A" in message
        assert "2. Task B" in message
        assert "3. Task C" in message

    def test_on_approval_accepted_with_empty_steps(self, empty_steps: list[dict[str, str]]) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_approval_accepted(empty_steps)

        assert "Updating your recipe" in message
        assert "Recipe updated successfully!" in message

    def test_on_approval_rejected(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_approval_rejected(sample_steps)

        assert "No problem!" in message
        assert "ingredients or steps" in message

    def test_on_state_confirmed(self) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_state_confirmed()

        assert "Recipe changes applied" in message
        assert "successfully" in message

    def test_on_state_rejected(self) -> None:
        strategy = RecipeConfirmationStrategy()
        message = strategy.on_state_rejected()

        assert "No problem!" in message
        assert "adjust in the recipe" in message


class TestDocumentWriterConfirmationStrategy:
    """Tests for DocumentWriterConfirmationStrategy."""

    def test_on_approval_accepted_with_enabled_steps(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_approval_accepted(sample_steps)

        assert "Applying your edits" in message
        assert "1. Step 1: Do something" in message
        assert "2. Step 2: Do another thing" in message
        assert "Step 3" not in message
        assert "Document updated successfully!" in message

    def test_on_approval_accepted_with_all_enabled(self, all_enabled_steps: list[dict[str, str]]) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_approval_accepted(all_enabled_steps)

        assert "Applying your edits" in message
        assert "1. Task A" in message
        assert "2. Task B" in message
        assert "3. Task C" in message

    def test_on_approval_accepted_with_empty_steps(self, empty_steps: list[dict[str, str]]) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_approval_accepted(empty_steps)

        assert "Applying your edits" in message
        assert "Document updated successfully!" in message

    def test_on_approval_rejected(self, sample_steps: list[dict[str, str]]) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_approval_rejected(sample_steps)

        assert "No problem!" in message
        assert "keep or modify" in message

    def test_on_state_confirmed(self) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_state_confirmed()

        assert "Document edits applied!" in message

    def test_on_state_rejected(self) -> None:
        strategy = DocumentWriterConfirmationStrategy()
        message = strategy.on_state_rejected()

        assert "No problem!" in message
        assert "change about the document" in message


class TestConfirmationStrategyInterface:
    """Tests for ConfirmationStrategy abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Verify ConfirmationStrategy is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            ConfirmationStrategy()  # type: ignore

    def test_all_strategies_implement_interface(self):
        """Verify all concrete strategies implement the full interface."""
        strategies = [
            DefaultConfirmationStrategy(),
            TaskPlannerConfirmationStrategy(),
            RecipeConfirmationStrategy(),
            DocumentWriterConfirmationStrategy(),
        ]

        sample_steps = [{"description": "Test", "status": "enabled"}]

        for strategy in strategies:
            # All should have these methods
            assert callable(strategy.on_approval_accepted)
            assert callable(strategy.on_approval_rejected)
            assert callable(strategy.on_state_confirmed)
            assert callable(strategy.on_state_rejected)

            # All should return strings
            assert isinstance(strategy.on_approval_accepted(sample_steps), str)
            assert isinstance(strategy.on_approval_rejected(sample_steps), str)
            assert isinstance(strategy.on_state_confirmed(), str)
            assert isinstance(strategy.on_state_rejected(), str)
