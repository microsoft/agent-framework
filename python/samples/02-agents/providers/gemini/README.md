# Google Gemini Examples

This folder contains examples demonstrating how to use Google Gemini models with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`gemini_basic.py`](gemini_basic.py) | Basic agent with a weather tool, demonstrating both streaming and non-streaming responses. |
| [`gemini_advanced.py`](gemini_advanced.py) | Extended thinking via `ThinkingConfig` for reasoning-heavy questions (Gemini 2.5+). |
| [`gemini_with_google_search.py`](gemini_with_google_search.py) | Google Search grounding for up-to-date answers. |
| [`gemini_with_google_maps.py`](gemini_with_google_maps.py) | Google Maps grounding for location and mapping information. |
| [`gemini_with_code_execution.py`](gemini_with_code_execution.py) | Built-in code execution tool for computing precise answers in a sandboxed environment. |
| [`gemini_embeddings.py`](gemini_embeddings.py) | Per-call document and query text embeddings with stable Gemini Embedding 2. |
| [`gemini_search_agent.py`](gemini_search_agent.py) | Document upsert and `create_vector_search_tool` with distinct per-operation embedding options. |
| [`gemini_image_search_agent.py`](gemini_image_search_agent.py) | Cross-modal image indexing and Agent text-to-image search with query embedding options. |

Run the image search example with two or more local PNG/JPEG files:

```bash
uv run samples/02-agents/providers/gemini/gemini_image_search_agent.py \
  --query "Which image shows a dog?" photos/dog.jpg photos/cat.png
```

Image embeddings are generated without a task prefix. The search tool uses
`RETRIEVAL_QUERY` for text queries and shares the image index's 768 dimensions.

## Environment Variables

- `GOOGLE_MODEL`: The Gemini chat model to use (for example,
  `gemini-2.5-flash-lite` or `gemini-2.5-pro`)
- For Gemini Developer API: `GOOGLE_API_KEY`
- For Gemini Enterprise Agent Platform (chat and embeddings): `GOOGLE_GENAI_USE_ENTERPRISE=true`,
  `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`. The older
  `GOOGLE_GENAI_USE_VERTEXAI=true` setting remains supported.
- `GOOGLE_EMBEDDING_MODEL`: Optional `gemini-embedding-2-preview` override (defaults to `gemini-embedding-2`)
