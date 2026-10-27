# NVIDIA samples

`nvidia_embeddings.py` generates single and batched embeddings, then indexes two
notes in an in-memory collection and retrieves the closer one. Stored notes are
embedded with `input_type="passage"` and the search text with `input_type="query"`,
which asymmetric models such as `nvidia/nemotron-3-embed-1b` embed differently.

Set `NVIDIA_API_KEY` to a key from [build.nvidia.com](https://build.nvidia.com/).
See the [package README](../README.md) for the other settings and for choosing a
model.
