# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for ``_make_powerfx_safe``.

PowerFx (via pythonnet) only accepts plain primitives, dicts, and lists.
``Enum`` instances - especially ``str``- and ``int``-subclass enums like
MAF's ``MessageRole`` - silently pass ``isinstance(v, str)`` /
``isinstance(v, int)`` checks but blow up later inside pythonnet with
``'<EnumName>' value cannot be converted to System.<X>``. These tests
pin down the Enum coercion branch so we don't regress that interop fix.
"""

from enum import Enum, IntEnum

from agent_framework_declarative._workflows._declarative_base import _make_powerfx_safe


class _StrRole(str, Enum):
    USER = "user"
    SYSTEM = "system"


class _IntCode(IntEnum):
    ONE = 1
    TWO = 2


class _PlainEnum(Enum):
    X = "x"
    Y = 42


def test_str_subclass_enum_reduces_to_str():
    assert _make_powerfx_safe(_StrRole.USER) == "user"
    assert type(_make_powerfx_safe(_StrRole.USER)) is str


def test_int_subclass_enum_reduces_to_int():
    assert _make_powerfx_safe(_IntCode.ONE) == 1
    assert type(_make_powerfx_safe(_IntCode.ONE)) is int


def test_plain_enum_reduces_to_underlying_value():
    assert _make_powerfx_safe(_PlainEnum.X) == "x"
    assert _make_powerfx_safe(_PlainEnum.Y) == 42


def test_enum_inside_dict_is_coerced():
    safe = _make_powerfx_safe({"role": _StrRole.USER, "code": _IntCode.TWO})
    assert safe == {"role": "user", "code": 2}
    assert type(safe["role"]) is str
    assert type(safe["code"]) is int


def test_enum_inside_list_is_coerced():
    safe = _make_powerfx_safe([_StrRole.USER, _IntCode.ONE])
    assert safe == ["user", 1]
    assert type(safe[0]) is str
    assert type(safe[1]) is int
