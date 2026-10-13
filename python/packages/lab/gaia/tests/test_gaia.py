# Copyright (c) Microsoft. All rights reserved.

"""Tests for GAIA benchmark implementation."""

import pytest

from agent_framework_lab_gaia import gaia_scorer


class TestGAIAScorer:
    """Test the GAIA scoring function."""

    def test_numeric_exact_match(self):
        """Test numeric exact matching."""
        assert gaia_scorer("42", "42") is True
        assert gaia_scorer("42.0", "42") is True
        assert gaia_scorer("42", "42.0") is True
        assert gaia_scorer("42", "43") is False

    def test_string_normalization(self):
        """Test string normalization and matching."""
        assert gaia_scorer("Hello World", "hello world") is True
        assert gaia_scorer("Hello, World!", "helloworld") is True
        assert gaia_scorer("test", "TEST") is True
        assert gaia_scorer("test", "different") is False

    def test_list_matching(self):
        """Test list matching with comma/semicolon separation."""
        assert gaia_scorer("1,2,3", "1,2,3") is True
        assert gaia_scorer("1; 2; 3", "1,2,3") is True
        assert gaia_scorer("apple,banana", "apple,banana") is True
        assert gaia_scorer("1,2,3", "1,2,4") is False
        assert gaia_scorer("1,2", "1,2,3") is False

    def test_none_handling(self):
        """Test handling of None values."""
        assert gaia_scorer("None", "test") is False
        assert gaia_scorer("", "test") is False


class TestEnsureData:
    """Test local data detection in GAIA._ensure_data."""

    def test_parquet_only_data_dir_is_accepted(self, tmp_path):
        """A data dir in the parquet layout _load_gaia_local supports must not force a download (#9337)."""
        pytest.importorskip("pyarrow")
        from agent_framework_lab_gaia.gaia import GAIA

        validation = tmp_path / "2023" / "validation"
        validation.mkdir(parents=True)
        rows = [
            {
                "task_id": "v1",
                "Question": "What is 2+2?",
                "Final answer": "4",
                "Level": 1,
                "file_name": "",
                "Annotator Metadata": "{}",
            }
        ]
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist(rows), validation / "metadata-00000-of-00001.parquet")

        runner = GAIA(data_dir=str(tmp_path))
        assert runner._ensure_data() == tmp_path
