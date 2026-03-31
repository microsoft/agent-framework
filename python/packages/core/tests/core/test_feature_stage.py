# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import warnings
from enum import Enum
from typing import Protocol, runtime_checkable

import pytest

from agent_framework import ExperimentalFeature as PublicExperimentalFeature
from agent_framework import ReleaseCandidateFeature as PublicReleaseCandidateFeature
from agent_framework._feature_stage import (
    _WARNED_FEATURES,
    ExperimentalWarning,
    _feature_stage,
    experimental,
    release_candidate,
)
from agent_framework._feature_stage import (
    ExperimentalFeature as InternalExperimentalFeature,
)
from agent_framework._feature_stage import (
    ReleaseCandidateFeature as InternalReleaseCandidateFeature,
)


class AlternateExperimentalFeature(str, Enum):
    EXPERIMENTAL_FEATURE = "EXPERIMENTAL_FEATURE"
    SHARED_FEATURE = "SHARED_EXPERIMENTAL_FEATURE"
    ALTERNATE_FEATURE = "ALTERNATE_EXPERIMENTAL_FEATURE"


class InvalidStageFeature(str, Enum):
    LOWERCASE = "skills"


class NonStringFeature(Enum):
    INTEGER = 1


class HelperReleaseCandidateFeature(str, Enum):
    RC_FEATURE = "RC_FEATURE"


@pytest.fixture(autouse=True)
def clear_feature_warning_state() -> None:
    _WARNED_FEATURES.clear()
    yield
    _WARNED_FEATURES.clear()


def test_feature_enums_are_exposed_from_root() -> None:
    assert PublicExperimentalFeature is InternalExperimentalFeature
    assert PublicReleaseCandidateFeature is InternalReleaseCandidateFeature


def test_experimental_decorator_accepts_feature_enum() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
        def skill_function() -> None:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        skill_function()

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "skill_function" in str(caught[0].message)
    assert skill_function.__feature_id__ == AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value


def test_experimental_function_warns_on_call_and_not_on_definition() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
        def my_function(value: int) -> int:
            """Double the input.

            Args:
                value: Value to double.

            Returns:
                The doubled value.
            """
            return value * 2

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        assert my_function(3) == 6
        assert my_function(4) == 8

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "my_function" in str(caught[0].message)
    assert my_function.__feature_stage__ == "experimental"
    assert my_function.__feature_id__ == AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value
    assert my_function.__doc__ is not None
    lines = my_function.__doc__.splitlines()
    warning_index = next(i for i, line in enumerate(lines) if line == ".. warning:: Experimental")
    args_index = next(i for i, line in enumerate(lines) if line == "Args:")
    assert warning_index < args_index


def test_experimental_class_warns_on_instantiation_and_not_on_definition() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
        class ExperimentalClass:
            """An experimental class.

            Args:
                value: Value to store.
            """

            def __init__(self, value: int) -> None:
                self.value = value

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        instantiation_line = inspect.currentframe().f_lineno + 1
        instance = ExperimentalClass(4)
        second_instance = ExperimentalClass(5)

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "ExperimentalClass" in str(caught[0].message)
    assert caught[0].filename == __file__
    assert caught[0].lineno == instantiation_line
    assert instance.value == 4
    assert second_instance.value == 5
    assert ExperimentalClass.__feature_stage__ == "experimental"
    assert ExperimentalClass.__feature_id__ == AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value


def test_experimental_runtime_checkable_protocol_keeps_protocol_runtime_checks() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @runtime_checkable
        @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
        class ExampleProtocol(Protocol):
            """A protocol used for runtime checks.

            Returns:
                Nothing.
            """

            def __call__(self, value: int) -> int: ...

    assert not caught

    def implementation(value: int) -> int:
        return value

    assert isinstance(implementation, ExampleProtocol)
    assert ExampleProtocol.__doc__ is not None
    assert ".. warning:: Experimental" in ExampleProtocol.__doc__
    assert getattr(ExampleProtocol, "__feature_stage__", None) is None
    assert getattr(ExampleProtocol, "__feature_id__", None) is None


def test_experimental_warning_is_emitted_once_per_feature() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id=AlternateExperimentalFeature.SHARED_FEATURE)  # type: ignore[arg-type]
        def first() -> None:
            pass

        @experimental(feature_id=AlternateExperimentalFeature.SHARED_FEATURE)  # type: ignore[arg-type]
        class Second:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        first()
        Second()

    assert first is not None
    assert Second is not None
    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.SHARED_FEATURE.value}]" in str(caught[0].message)
    assert "first" in str(caught[0].message)


def test_release_candidate_internal_helper_adds_metadata_without_runtime_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @_feature_stage(
            stage="release_candidate",
            feature_id=HelperReleaseCandidateFeature.RC_FEATURE,
            docstring_block="""\
.. note:: Release candidate

    This API is in release-candidate stage and may receive
    minor refinements before it is considered generally available.
""",
            warning_category=None,
        )
        class ReleaseCandidateClass:
            """A release-candidate class.

            Args:
                value: Value to store.
            """

            def __init__(self, value: int) -> None:
                self.value = value

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        instance = ReleaseCandidateClass(5)

    assert instance.value == 5
    assert not caught
    assert ReleaseCandidateClass.__feature_stage__ == "release_candidate"
    assert ReleaseCandidateClass.__feature_id__ == HelperReleaseCandidateFeature.RC_FEATURE.value
    assert ReleaseCandidateClass.__doc__ is not None
    assert ".. note:: Release candidate" in ReleaseCandidateClass.__doc__


def test_experimental_property_warns_on_access_and_not_on_definition() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class Example:
            @property
            @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
            def value(self) -> int:
                """Return the value.

                Returns:
                    The stored value.
                """
                return 1

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        assert Example().value == 1
        assert Example().value == 1

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "Example.value" in str(caught[0].message)
    assert Example.value.__doc__ is not None
    lines = Example.value.__doc__.splitlines()
    warning_index = next(i for i, line in enumerate(lines) if line == ".. warning:: Experimental")
    returns_index = next(i for i, line in enumerate(lines) if line == "Returns:")
    assert warning_index < returns_index


def test_experimental_staticmethod_warns_when_decorator_wraps_descriptor() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class Example:
            @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
            @staticmethod
            def value() -> int:
                """Return the value.

                Returns:
                    The stored value.
                """
                return 1

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        assert Example.value() == 1
        assert Example.value() == 1

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "Example.value" in str(caught[0].message)
    assert Example.value.__feature_id__ == AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value
    assert Example.value.__doc__ is not None
    lines = Example.value.__doc__.splitlines()
    warning_index = next(i for i, line in enumerate(lines) if line == ".. warning:: Experimental")
    returns_index = next(i for i, line in enumerate(lines) if line == "Returns:")
    assert warning_index < returns_index


def test_experimental_classmethod_warns_when_decorator_wraps_descriptor() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class Example:
            @experimental(feature_id=AlternateExperimentalFeature.EXPERIMENTAL_FEATURE)  # type: ignore[arg-type]
            @classmethod
            def value(cls) -> int:
                """Return the value.

                Returns:
                    The stored value.
                """
                return 1

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        assert Example.value() == 1
        assert Example.value() == 1

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value}]" in str(caught[0].message)
    assert "Example.value" in str(caught[0].message)
    assert Example.value.__func__.__feature_id__ == AlternateExperimentalFeature.EXPERIMENTAL_FEATURE.value
    assert Example.value.__doc__ is not None
    lines = Example.value.__doc__.splitlines()
    warning_index = next(i for i, line in enumerate(lines) if line == ".. warning:: Experimental")
    returns_index = next(i for i, line in enumerate(lines) if line == "Returns:")
    assert warning_index < returns_index


def test_feature_id_allows_lowercase_values() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @_feature_stage(
            stage="experimental",
            feature_id=InvalidStageFeature.LOWERCASE,
            docstring_block=".. warning:: Experimental",
            warning_category=ExperimentalWarning,
        )
        def lowercase_feature() -> None:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        lowercase_feature()

    assert len(caught) == 1
    assert "[skills]" in str(caught[0].message)
    assert "lowercase_feature" in str(caught[0].message)
    assert lowercase_feature.__feature_id__ == "skills"


def test_experimental_decorator_allows_string_feature_id_at_runtime() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id="STRING_FEATURE")  # type: ignore[arg-type]
        def skill_function() -> None:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        skill_function()

    assert len(caught) == 1
    assert "[STRING_FEATURE]" in str(caught[0].message)
    assert "skill_function" in str(caught[0].message)
    assert skill_function.__feature_id__ == "STRING_FEATURE"


def test_experimental_decorator_allows_other_enum_values_at_runtime() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @experimental(feature_id=AlternateExperimentalFeature.ALTERNATE_FEATURE)  # type: ignore[arg-type]
        def my_function() -> None:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        my_function()

    assert len(caught) == 1
    assert f"[{AlternateExperimentalFeature.ALTERNATE_FEATURE.value}]" in str(caught[0].message)
    assert "my_function" in str(caught[0].message)
    assert my_function.__feature_id__ == AlternateExperimentalFeature.ALTERNATE_FEATURE.value


def test_release_candidate_decorator_allows_string_feature_id_at_runtime() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @release_candidate(feature_id="RC_FEATURE")  # type: ignore[arg-type]
        class ReleaseCandidateClass:
            """A release-candidate class."""

    assert not caught
    assert ReleaseCandidateClass.__feature_stage__ == "release_candidate"
    assert ReleaseCandidateClass.__feature_id__ == "RC_FEATURE"


def test_feature_id_stringifies_non_string_enum_values() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @_feature_stage(
            stage="experimental",
            feature_id=NonStringFeature.INTEGER,
            docstring_block=".. warning:: Experimental",
            warning_category=ExperimentalWarning,
        )
        def numeric_feature() -> None:
            pass

    assert not caught

    with warnings.catch_warnings(record=True) as caught:
        numeric_feature()

    assert len(caught) == 1
    assert "[1]" in str(caught[0].message)
    assert "numeric_feature" in str(caught[0].message)
    assert numeric_feature.__feature_id__ == "1"
