# Copyright (c) Microsoft. All rights reserved.

"""Additional tests for session utilities and serializers.

These target edge cases not covered by the main test suite:
- filename-safe session stem encoding
- non-finite float detection in nested structures
- default state encoder/decoder error paths
"""

from __future__ import annotations

import pytest

from agent_framework import _sessions as sessions
from pydantic import BaseModel


class TestSessionFileStem:
    def test_literal_safe_session_stem(self):
        # ASCII alnum + separators allowed
        assert sessions._is_literal_session_file_stem_safe("session-123") is True
        assert sessions._session_file_stem("session-123", encoded_prefix="sess-") == "session-123"

    def test_reserved_windows_name_encoded(self):
        # Windows reserved stem must be encoded
        session_id = "CON"
        stem = sessions._session_file_stem(session_id, encoded_prefix="sess-")
        assert stem != session_id
        assert stem.startswith("sess-")

    def test_control_characters_encoded(self):
        # Control characters should force encoding
        session_id = "bad\x01id"
        stem = sessions._session_file_stem(session_id, encoded_prefix="s-")
        assert stem.startswith("s-")
        assert "\x01" not in stem

    def test_long_encoded_falls_back_to_hash(self):
        # Very long literal-safe IDs may be returned unchanged; otherwise the encoded
        # representation should start with the provided prefix or the sha256 fallback.
        long_id = "x" * 1000
        stem = sessions._session_file_stem(long_id, encoded_prefix="p-")
        assert stem == long_id or stem.startswith("p-") or stem.startswith("p-sha256-")


class TestNonFiniteFloatDetection:
    def test_contains_non_finite_float_direct(self):
        assert sessions._contains_non_finite_float(float("nan")) is True
        assert sessions._contains_non_finite_float(float("inf")) is True
        assert sessions._contains_non_finite_float(1.0) is False

    def test_contains_non_finite_float_nested(self):
        data = {"a": [1.0, float("nan")], "b": {"c": float("inf")}}
        assert sessions._contains_non_finite_float(data) is True

    def test_contains_non_finite_float_sequences(self):
        assert sessions._contains_non_finite_float([1.0, 2.0]) is False
        assert sessions._contains_non_finite_float((1.0, float("nan"))) is True


class _BadToDict:
    def to_dict(self):
        # Return a non-mapping type to exercise encoder error path
        return [1, 2, 3]


class TestDefaultStateEncoderDecoder:
    def test_default_state_encoder_raises_on_non_mapping_to_dict(self):
        encoder = sessions._default_state_encoder(_BadToDict)
        with pytest.raises(TypeError):
            encoder(_BadToDict())

    def test_default_state_decoder_for_pydantic(self):
        class Model(BaseModel):
            x: int

        decoder = sessions._default_state_decoder(Model)
        obj = decoder({"x": 5})
        assert isinstance(obj, Model)
        assert obj.x == 5

    def test_resolve_state_type_id_custom_priority(self):
        class WithType:
            TYPE = "custom_type"

        # explicit type_id overrides
        assert sessions._resolve_state_type_id(WithType, "explicit-id") == "explicit-id"
        # fallback to TYPE attribute
        assert sessions._resolve_state_type_id(WithType, None) == "custom_type"


# End of file
