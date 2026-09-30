# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for data-URI parameter handling and media-type sniffing.

Covers two reported defects in agent_framework/_types.py:
- _validate_uri rejected RFC 2397 parameters such as charset=... and failed to
  take the media type from a data URI without parameters (#8905).
- detect_media_type_from_base64 misclassified plain "BM..." text as BMP, any
  XML document as SVG, missed MPEG-2/2.5 Layer III frames, and silently
  discarded invalid base64 characters (#8906).
"""

from __future__ import annotations

import base64

import pytest

from agent_framework import Content, detect_media_type_from_base64
from agent_framework.exceptions import ContentError


class TestDataUriParameters:
    def test_charset_parameter_accepted(self) -> None:
        content = Content.from_uri("data:text/plain;charset=utf-8,hello%20world")
        assert content.media_type == "text/plain"

    def test_media_type_extracted_without_parameters(self) -> None:
        content = Content.from_uri("data:text/plain,hello")
        assert content.media_type == "text/plain"

    def test_empty_media_type_defaults_to_text_plain(self) -> None:
        content = Content.from_uri("data:;base64,aGVsbG8=")
        assert content.media_type == "text/plain"

    def test_charset_and_base64_accepted(self) -> None:
        content = Content.from_uri("data:application/json;charset=utf-8;base64,e30=")
        assert content.media_type == "application/json"

    def test_unknown_bare_encoding_still_rejected(self) -> None:
        with pytest.raises(ContentError, match="Unsupported data URI encoding"):
            Content.from_uri("data:text/plain;gzip,hello")

    def test_explicit_media_type_wins_over_uri(self) -> None:
        content = Content.from_uri("data:text/plain;charset=utf-8,hello", media_type="text/csv")
        assert content.media_type == "text/csv"


class TestMediaTypeDetection:
    def test_plain_text_starting_with_bm_is_not_bmp(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"BMW is a car") is None

    @pytest.mark.parametrize("dib_size", [12, 40, 52, 56, 64, 108, 124])
    def test_real_bmp_header_detected(self, dib_size: int) -> None:
        bmp = b"BM" + b"\x00" * 12 + dib_size.to_bytes(4, "little") + b"\x00" * dib_size
        assert detect_media_type_from_base64(data_bytes=bmp) == "image/bmp"

    def test_xml_document_is_not_svg(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"<?xml version='1.0'?><rss/>") is None

    def test_svg_with_xml_prolog_detected(self) -> None:
        svg = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'></svg>"
        assert detect_media_type_from_base64(data_bytes=svg) == "image/svg+xml"

    def test_bare_svg_element_detected(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"<svg></svg>") == "image/svg+xml"

    @pytest.mark.parametrize("prefix", [b"  \n", b"\xef\xbb\xbf", b" \xef\xbb\xbf\n"])
    def test_svg_with_leading_whitespace_or_bom_detected(self, prefix: bytes) -> None:
        assert detect_media_type_from_base64(data_bytes=prefix + b"<svg/>") == "image/svg+xml"

    @pytest.mark.parametrize("prefix", [b"", b"<?xml version='1.0'?>"])
    def test_svg_named_prefix_is_not_svg(self, prefix: bytes) -> None:
        assert detect_media_type_from_base64(data_bytes=prefix + b"<svgish/>") is None

    def test_mpeg2_layer3_frame_sync_detected(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"\xff\xf2\x90\x00" + b"\0" * 20) == "audio/mpeg"

    def test_mpeg25_layer3_frame_sync_detected(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"\xff\xe3\x90\x00" + b"\0" * 20) == "audio/mpeg"

    def test_reserved_layer_not_mpeg(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"\xff\xf9\x90\x00" + b"\0" * 20) is None

    def test_reserved_version_not_mpeg(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"\xff\xeb\x90\x00" + b"\0" * 20) is None

    def test_invalid_base64_characters_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid base64 data provided."):
            detect_media_type_from_base64(data_str="iVBO!!!!Rw0KGgowMDAwMDAwMA==")

    def test_valid_signatures_unchanged(self) -> None:
        assert detect_media_type_from_base64(data_bytes=b"\x89PNG\r\n\x1a\n" + b"x" * 8) == "image/png"
        assert detect_media_type_from_base64(data_bytes=b"\xff\xd8\xff\xe0" + b"x" * 8) == "image/jpeg"
        assert detect_media_type_from_base64(data_bytes=b"GIF89a" + b"x" * 8) == "image/gif"
        assert detect_media_type_from_base64(data_bytes=b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"
        assert detect_media_type_from_base64(data_bytes=b"RIFF\x00\x00\x00\x00WAVE") == "audio/wav"
        assert detect_media_type_from_base64(data_bytes=b"ID3\x04\x00" + b"x" * 8) == "audio/mpeg"
        assert detect_media_type_from_base64(data_bytes=b"OggS" + b"x" * 8) == "audio/ogg"
        assert detect_media_type_from_base64(data_bytes=b"fLaC" + b"x" * 8) == "audio/flac"
        assert detect_media_type_from_base64(data_bytes=b"%PDF-1.7") == "application/pdf"
        assert (
            detect_media_type_from_base64(data_str=base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 8).decode())
            == "image/png"
        )
