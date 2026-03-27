# Copyright (c) Microsoft. All rights reserved.

from agent_framework._docstrings import apply_layered_docstring, build_layered_docstring

# -- Helpers: stub functions with various docstring shapes --


def _source_with_full_docstring(x: int) -> int:
    """Do something useful.

    Args:
        x: The input value.

    Keyword Args:
        timeout: Max seconds to wait.

    Returns:
        The computed result.
    """
    return x


def _source_with_args_only(x: int) -> int:
    """Do something useful.

    Args:
        x: The input value.

    Returns:
        The computed result.
    """
    return x


def _source_no_sections() -> None:
    """A plain summary with no Google-style sections."""


def _source_no_docstring() -> None:
    pass


def _target_stub() -> None:
    pass


# -- build_layered_docstring tests --


def test_build_returns_none_when_source_has_no_docstring() -> None:
    result = build_layered_docstring(_source_no_docstring)
    assert result is None


def test_build_returns_original_when_no_extra_kwargs() -> None:
    result = build_layered_docstring(_source_with_full_docstring)
    assert result is not None
    assert "Do something useful." in result
    assert "Keyword Args:" in result


def test_build_returns_original_when_extra_kwargs_empty() -> None:
    result = build_layered_docstring(_source_with_full_docstring, extra_keyword_args={})
    assert result is not None
    assert result == build_layered_docstring(_source_with_full_docstring)


def test_build_appends_to_existing_keyword_args_section() -> None:
    result = build_layered_docstring(
        _source_with_full_docstring,
        extra_keyword_args={"retries": "Number of retries."},
    )
    assert result is not None
    assert "timeout: Max seconds to wait." in result
    assert "retries: Number of retries." in result
    # Both should be under Keyword Args
    lines = result.splitlines()
    kw_index = next(i for i, line in enumerate(lines) if line == "Keyword Args:")
    ret_index = next(i for i, line in enumerate(lines) if line == "Returns:")
    retries_index = next(i for i, line in enumerate(lines) if "retries:" in line)
    assert kw_index < retries_index < ret_index


def test_build_inserts_keyword_args_after_args_section() -> None:
    result = build_layered_docstring(
        _source_with_args_only,
        extra_keyword_args={"verbose": "Enable verbose output."},
    )
    assert result is not None
    assert "Keyword Args:" in result
    assert "verbose: Enable verbose output." in result
    lines = result.splitlines()
    args_index = next(i for i, line in enumerate(lines) if line == "Args:")
    kw_index = next(i for i, line in enumerate(lines) if line == "Keyword Args:")
    ret_index = next(i for i, line in enumerate(lines) if line == "Returns:")
    assert args_index < kw_index < ret_index


def test_build_inserts_keyword_args_in_docstring_with_no_sections() -> None:
    result = build_layered_docstring(
        _source_no_sections,
        extra_keyword_args={"debug": "Enable debug mode."},
    )
    assert result is not None
    assert "A plain summary" in result
    assert "Keyword Args:" in result
    assert "debug: Enable debug mode." in result


def test_build_handles_multiline_descriptions() -> None:
    result = build_layered_docstring(
        _source_with_args_only,
        extra_keyword_args={
            "config": "The configuration object.\nMust be a valid mapping.\nDefaults to empty.",
        },
    )
    assert result is not None
    lines = result.splitlines()
    config_line = next(line for line in lines if "config:" in line)
    assert "The configuration object." in config_line
    # Continuation lines should be indented
    config_idx = lines.index(config_line)
    assert "Must be a valid mapping." in lines[config_idx + 1]
    assert "Defaults to empty." in lines[config_idx + 2]


def test_build_preserves_multiple_extra_kwargs_order() -> None:
    result = build_layered_docstring(
        _source_with_args_only,
        extra_keyword_args={
            "alpha": "First.",
            "beta": "Second.",
            "gamma": "Third.",
        },
    )
    assert result is not None
    lines = result.splitlines()
    alpha_idx = next(i for i, line in enumerate(lines) if "alpha:" in line)
    beta_idx = next(i for i, line in enumerate(lines) if "beta:" in line)
    gamma_idx = next(i for i, line in enumerate(lines) if "gamma:" in line)
    assert alpha_idx < beta_idx < gamma_idx


# -- apply_layered_docstring tests --


def test_apply_sets_docstring_on_target() -> None:
    def target() -> None:
        pass

    apply_layered_docstring(target, _source_with_full_docstring)
    assert target.__doc__ is not None
    assert "Do something useful." in target.__doc__


def test_apply_with_extra_kwargs() -> None:
    def target() -> None:
        pass

    apply_layered_docstring(
        target,
        _source_with_args_only,
        extra_keyword_args={"flag": "A boolean flag."},
    )
    assert target.__doc__ is not None
    assert "flag: A boolean flag." in target.__doc__
    assert "Keyword Args:" in target.__doc__


def test_apply_sets_none_when_source_has_no_docstring() -> None:
    def target() -> None:
        """Original."""

    apply_layered_docstring(target, _source_no_docstring)
    assert target.__doc__ is None
