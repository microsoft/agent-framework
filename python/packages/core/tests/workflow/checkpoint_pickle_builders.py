# Copyright (c) Microsoft. All rights reserved.

"""Reusable pickle payload builders for checkpoint-deserialization tests."""

from __future__ import annotations


def _short_unicode(text: str) -> bytes:
    data = text.encode("utf-8")
    return b"\x8c" + bytes([len(data)]) + data


def _stack_global(module: str, name: str) -> bytes:
    return _short_unicode(module) + _short_unicode(name) + b"\x93"


def dynamic_dict_subclass_pickle(
    class_global_module: str, class_global_name: str, dynamic_qualname: str, items: dict[str, str]
) -> bytes:
    """Hand-assemble a protocol-4 pickle equivalent to:
    ``<class_global>(dynamic_qualname, (dict,), {"__module__": ..., "__qualname__": ...})(items)``.

    Exercises the primitive the checkpoint-restore allowlist must reject: calling an allowlisted
    class factory (``type``, or a module attribute that resolves to it) via ``REDUCE`` to construct
    a new ``dict`` subclass whose ``__module__``/``__qualname__`` are chosen by the payload, then
    instantiating it with caller-supplied data.
    """
    class_dict = (
        b"}("
        + _short_unicode("__module__")
        + _short_unicode(class_global_module)
        + _short_unicode("__qualname__")
        + _short_unicode(dynamic_qualname)
        + b"u"
    )
    payload_items = b"}(" + b"".join(_short_unicode(k) + _short_unicode(v) for k, v in items.items()) + b"u"
    return (
        b"\x80\x04"
        + _stack_global(class_global_module, class_global_name)
        + _short_unicode(dynamic_qualname)
        + _stack_global("builtins", "dict")
        + b"\x85"  # TUPLE1 -> (dict,)
        + class_dict
        + b"\x87R"  # TUPLE3, REDUCE -> constructed class
        + payload_items
        + b"\x85R."  # TUPLE1, REDUCE -> constructed instance, STOP
    )


def metaclass_via_builtin_type_pickle(
    already_allowed_class_global: tuple[str, str], dynamic_qualname: str, items: dict[str, str]
) -> bytes:
    """Hand-assemble a protocol-4 pickle that recovers the bare ``type`` metaclass from a restricted
    single-argument ``type(x)`` call, then reuses that recovered value -- not a ``find_class``
    lookup -- as the callable of a second ``REDUCE`` to construct an arbitrary class.

    Every ordinary class (``dict``, ``list``, any class without a custom metaclass) is itself an
    instance of ``type``, so ``type(<already_allowed_class_global>)`` would legitimately return the
    bare ``type`` object under a restriction that only checks argument count/kind. Pickle's
    ``REDUCE`` opcode calls whatever object is on top of the stack; it does not re-resolve that
    object through ``find_class``, so a value computed by one ``REDUCE`` can be memoized
    (``PUT``/``GET``) and reused as the callable of a *later* ``REDUCE`` with different arguments.
    This checks that a single-argument ``type(x)`` restriction also rejects ``x`` being a class,
    which is the only way ``type(x)`` can itself return a metaclass.
    """
    class_dict = (
        b"}("
        + _short_unicode("__module__")
        + _short_unicode("builtins")
        + _short_unicode("__qualname__")
        + _short_unicode(dynamic_qualname)
        + b"u"
    )
    payload_items = b"}(" + b"".join(_short_unicode(k) + _short_unicode(v) for k, v in items.items()) + b"u"
    return (
        b"\x80\x04"
        + _stack_global("builtins", "type")
        + _stack_global(*already_allowed_class_global)
        + b"\x85R"  # TUPLE1, REDUCE -> type(already_allowed_class_global) -- recovers bare `type`
        + b"q\x00"  # BINPUT 0 -- memoize the recovered `type` object
        + b"h\x00"  # BINGET 0 -- reuse it as the callable of the next REDUCE, without going through find_class
        + _short_unicode(dynamic_qualname)
        + _stack_global("builtins", "dict")
        + b"\x85"  # TUPLE1 -> (dict,)
        + class_dict
        + b"\x87R"  # TUPLE3, REDUCE -> type(qualname, (dict,), {...}) -- constructed class
        + payload_items
        + b"\x85R."  # TUPLE1, REDUCE -> constructed instance, STOP
    )
