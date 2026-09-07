# Vector stores

Vector stores accept multiple model styles so applications can keep the data
representation that already fits their validation, memory, and interoperability
needs. When you own a model, annotate a dataclass, Pydantic model, msgspec
struct, or plain class. When another team or package owns it, register an
explicit definition and codecs. Dictionaries use a collection-specific
definition; DataFrames and other containers can convert to row dictionaries
before calling the batch API.

No database or credentials are needed for these examples.

| File | Demonstrates |
|------|--------------|
| [`vector_store_models.py`](vector_store_models.py) | Choosing among owned models, third-party model registration, and loose dictionary definitions. |
| [`optimized_data_formats.py`](optimized_data_formats.py) | Keeping NumPy vector fields and adapting pandas DataFrames to the batch record API. |

The first section shows the two equivalent custom-codec registration forms.
`@vectorstoremodel` derives the definition from annotations and registers it;
`register_vectorstoremodel` accepts an externally constructed definition.
Both produce the same internal model registration.

The sample order is informed by a small benchmark on Apple Silicon with
CPython 3.13. Each benchmark model had the same `id`, `text`, and `vector`
fields. Results are medians of seven warmed runs:

| Model style | 3-element vector | 1,566-element vector |
|-------------|-----------------:|---------------------:|
| Custom codecs | 2.60 μs | 7.01 μs |
| Dictionary | 2.39 μs | 6.60 μs |
| Plain class | 3.46 μs | 12.26 μs |
| msgspec `Struct` | 3.03 μs | 16.61 μs |
| Dataclass | 3.17 μs | 16.81 μs |
| Pydantic | 5.52 μs | 37.32 μs |

These results measure only the framework's internal record conversion path.
They do not include database SDK conversion, network I/O,
embedding generation, validation complexity, nested fields, alternate vector
representations, or memory allocation. Custom codecs are especially favorable
here because the benchmark codec returns the existing vector reference rather
than copying it. The middle ordering also changes with vector size, so treat
these timings as illustrative data, not a recommendation or performance
guarantee.

Array-like vector values, including NumPy arrays, are serialized through their
`tolist()` method without making NumPy a core dependency. If a model must
restore a NumPy array instead of a Python list, pass a custom `decoder` to
`@vectorstoremodel` or `register_vectorstoremodel` and call `numpy.array` or
`numpy.asarray` there.

Run the sample from the `python` directory:

```bash
uv run samples/02-agents/vector_stores/vector_store_models.py
uv run samples/02-agents/vector_stores/optimized_data_formats.py
```
