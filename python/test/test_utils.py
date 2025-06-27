# Copyright (c) Microsoft. All rights reserved.
import ast
import inspect
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any, Tuple, get_type_hints


class CallTracker:
    """A class to track calls invocations by id."""

    def __init__(self):
        """Initialize the call tracker."""
        self.calls: set[int] = set()
        self.last_id: int | None = None
        self.available_ids: set[int] = set()

    class CallNotifier:
        """A class to notify when a call is made."""

        def __init__(self, tracker: "CallTracker", id_: int):
            """Initialize the notifier with a tracker and an id."""
            self.tracker = tracker
            self.id = id_

        def __call__(self, *args, **kwargs) -> None:
            """Notify the tracker of the call."""
            self.tracker.calls.add(self.id)
            self.tracker.last_id = self.id

    def create_notifier(self, id_: int | None = None) -> "CallTracker.CallNotifier":
        """Create a notifier for a call with the given id. If id_ is None, a new id will be generated.

        Args:
            id_: Optional[int] - The id for the notifier. If None, a new id will be generated.

        Raises:
            ValueError: If the id is already in use.

        Returns:
            CallTracker.CallNotifier: A notifier that can be called to track the call.
        """
        if id_ is None:
            if self.available_ids:
                id_ = self.available_ids.pop()
            else:
                self.last_id = self.last_id + 1 if self.last_id is not None else 0
                id_ = self.last_id
        else:
            if id_ not in self.available_ids:
                raise ValueError(f"Id {id_} is already in use or not yet available.")

            self.available_ids.remove(id_)

        return self.CallNotifier(self, id_)

    def reset(self, ids: set[int] | None = None) -> None:
        """Reset the call tracker, optionally filtering by ids.

        Args:
            ids: Optional set of ids to reset. If None, all calls are reset.
        """
        if ids is None:
            self.calls.clear()
            self.last_id = None
        else:
            self.calls.difference_update(ids)
            self.available_ids.update(ids)

    def __contains__(self, id_: int | set[int]) -> bool:
        """Check if the tracker contains a call with the given id."""
        if isinstance(id_, set):
            return not self.calls.issuperset(id_)

        if isinstance(id_, int):
            return id_ in self.calls

        raise TypeError(f"Expected int or set[int], got {type(id_).__name__}")


def next_(it) -> Tuple[bool, Any | None]:
    """Get the next item from an iterator, returning a tuple of (has_next, item)."""
    try:
        return True, next(it)
    except StopIteration:
        return False, None


class Assertions:
    """A collection of assertions for testing graph components."""

    @staticmethod
    def check_annotations(
        func: Callable,
        params: OrderedDict[str, type] | dict[str, type],
        returns: type | None = None,
        is_async: bool = False,
    ) -> None:
        """Assert that the function's annotations match the expected annotations."""
        assert isinstance(func, Callable), "Function must be callable"  # noqa: S101
        assert hasattr(func, "__annotations__"), "Function must have annotations"  # noqa: S101

        #signature = inspect.signature(func)  # Ensure the function can be inspected
        type_hints = get_type_hints(func)

        if "return" in type_hints and returns is None:
            assert type_hints["return"] is type(None), "Function should not have a return annotation if returns is None"  # noqa: S101
            returns = type(None)

        actual_params_iter = iter(type_hints.items())
        expected_params_iter = iter((*params.items(), ("return", returns) if returns is not None else ()))

        while True:
            has_next, actual = next_(actual_params_iter)
            if not has_next:
                has_next, _ = next_(expected_params_iter)
                assert not has_next, "Actual parameters exhausted before expected parameters"  # noqa: S101
                break


            expect_next, expected = next_(expected_params_iter)
            if not expect_next:
                assert not has_next, "Expected parameters exhausted before actual parameters"  # noqa: S101
                # This line should be unreachable if the function is well-defined
                break

            actual_name, actual_type = actual
            expected_name, expected_type = expected

            # if isinstance(actual_param, str):
            #     actual_param = ast.literal_eval(actual_param)
            # if isinstance(expected_param, str):
            #     expected_param = ast.literal_eval(expected_param)

            # assert actual_param.kind == expected_param.kind, (  # noqa: S101
            #     f"Parameter kind mismatch for {actual_param.name}: {actual_param.kind} != {expected_param.kind}"
            # )
            assert actual_name == expected_name, (  # noqa: S101
                f"Parameter name mismatch: {actual_name} != {expected_name}"
            )
            assert actual_type == expected_type, (  # noqa: S101
                f"Parameter annotation mismatch for {actual_name}: {actual_type} != {expected_type}"  # noqa: E501
            )

    def check(
        condition: bool,
        message: str | None = None,
    ):
        """Assert that a condition is true, with an optional message."""
        # This only exists because Ruff gets annoyed by "assert" statements for some reason
        if message is not None:
            assert condition, message  # noqa: S101
        else:
            assert condition  # noqa: S101

