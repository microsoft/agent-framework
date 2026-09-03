# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "numpy>=2,<3",
#     "pandas>=2,<4",
# ]
#
# [tool.uv.sources]
# agent-framework-core = { path = "../../../packages/core" }
# ///

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

# Run with: uv run samples/02-agents/vector_stores/optimized_data_formats.py
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, cast

import numpy as np
import pandas as pd  # pyright: ignore[reportMissingImports]
from agent_framework import (
    VectorStoreCollectionDefinition,
    VectorStoreField,
    vectorstoremodel,
)
from numpy.typing import NDArray

"""This sample demonstrates optimized vector data formats.

When optimized formats already fit the application, Agent Framework should not
force conversion at the model boundary. NumPy arrays reduce the in-memory
footprint of large vectors, while pandas DataFrames can preserve an existing
tabular data pipeline.

NumPy vectors are encoded through ``tolist()`` without making NumPy a core
dependency. A model decoder restores the array after retrieval. DataFrames are
converted to ordinary row dictionaries before using the vector store batch API
and reconstructed after retrieval. Agent Framework does not need
container-specific behavior or a pandas dependency.

These formats are choices, not requirements. A plain class or other application
model may be simpler and entirely appropriate. For all standard model and
third-party registration options, see
[vector_store_models.py](vector_store_models.py).
"""

DIMENSIONS = 1566


# 1. Use a NumPy array as a vector field.
def decode_numpy_record(record: Mapping[str, Any]) -> NumpyRecord:
    """Restore a NumPy vector after storage returned an ordinary list."""
    return NumpyRecord(
        record_id=cast(str, record["record_id"]),
        vector=np.asarray(record["vector"], dtype=np.float32),
    )


@vectorstoremodel(collection_name="numpy-records", decoder=decode_numpy_record)
@dataclass
class NumpyRecord:
    record_id: Annotated[str, VectorStoreField("key")]
    vector: Annotated[
        NDArray[np.float32],
        VectorStoreField("vector", dimensions=DIMENSIONS, type_="float"),
    ]


# 2. Convert a pandas DataFrame to and from ordinary row dictionaries.
dataframe_definition = VectorStoreCollectionDefinition(
    [
        VectorStoreField("key", name="id"),
        VectorStoreField("data", name="text", is_full_text_indexed=True),
        VectorStoreField("vector", name="vector", dimensions=3),
    ],
    collection_name="dataframe-records",
)


def main() -> None:
    """Convert NumPy and DataFrame values at the vector store boundary."""
    numpy_vector = np.arange(DIMENSIONS, dtype=np.float32) / np.float32(DIMENSIONS)
    serialized_numpy = {"record_id": "numpy-1", "vector": numpy_vector.tolist()}
    restored_numpy = decode_numpy_record(serialized_numpy)

    print(f"Serialized vector type: {type(serialized_numpy['vector']).__name__}")
    print(f"Restored vector type: {type(restored_numpy.vector).__name__} ({restored_numpy.vector.dtype})")

    frame = pd.DataFrame({
        "id": ["one", "two"],
        "text": ["First record", "Second record"],
        "vector": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    })
    dataframe_rows = cast(list[dict[str, Any]], frame.to_dict(orient="records"))
    restored_frame = pd.DataFrame.from_records(dataframe_rows)

    print(f"Rows passed to batch upsert: {dataframe_rows}")
    print("Restored DataFrame:")
    print(restored_frame)


if __name__ == "__main__":
    main()


"""
Sample output:
Serialized vector type: list
Restored vector type: ndarray (float32)
Rows passed to batch upsert: [
    {'id': 'one', 'text': 'First record', 'vector': [0.1, 0.2, 0.3]},
    {'id': 'two', 'text': 'Second record', 'vector': [0.4, 0.5, 0.6]}
]
Restored DataFrame:
    id           text           vector
0  one   First record  [0.1, 0.2, 0.3]
1  two  Second record  [0.4, 0.5, 0.6]
"""
