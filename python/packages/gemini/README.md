# Get Started with Microsoft Agent Framework Gemini

Install the provider package:

```bash
pip install agent-framework-gemini --pre
```

## Gemini Integration

The Gemini integration uses Google's current `google-genai` SDK for chat and text embeddings
through the Gemini Developer API or Gemini Enterprise Agent Platform (formerly Vertex AI).
Chat supports streaming, tool/function calling, and structured output.

## Gemini Embeddings

`GeminiEmbeddingClient` defaults to the stable [Gemini Embedding 2](https://ai.google.dev/gemini-api/docs/embeddings)
model (`gemini-embedding-2`). It also accepts `gemini-embedding-2-preview` via
`GOOGLE_EMBEDDING_MODEL` or `model=`; older embedding models are not supported.
It produces one embedding per input: a text string, a Google SDK media `Part`, or
a `google.genai.types.Content` aggregating text and media. Text strings **require**
a `task_type` in each `get_embeddings` call; the client does not choose one by default.

```python
from agent_framework.gemini import GeminiEmbeddingClient

client = GeminiEmbeddingClient()
try:
    document = await client.get_embeddings(
        ["Agent Framework helps build AI agents."],
        options={"task_type": "RETRIEVAL_DOCUMENT", "dimensions": 768, "title": "Agent Framework"},
    )
    query = await client.get_embeddings(
        ["How do I build an AI agent?"],
        options={"task_type": "RETRIEVAL_QUERY", "dimensions": 768},
    )
finally:
    await client.close()
```

The client maps Google's [Embedding 2 task instructions](https://ai.google.dev/gemini-api/docs/embeddings).
Use `RETRIEVAL_DOCUMENT` to index documents; pair it with `RETRIEVAL_QUERY` for search,
or `QUESTION_ANSWERING`, `FACT_VERIFICATION`, or `CODE_RETRIEVAL_QUERY` for those specialized
queries. For `CLASSIFICATION`, `CLUSTERING`, or `SEMANTIC_SIMILARITY`, use the same task on
all inputs; `SEMANTIC_SIMILARITY` is not intended for retrieval. Use the same model and
dimensions for indexing and searching. `title` applies to every text in a call, so embed
documents with different titles separately. Generic vector-store embedding generators do
not infer a task type: configure `GeminiEmbeddingClient` as the collection's
`embedding_generator`, pass `embeddings_options={"task_type": "RETRIEVAL_DOCUMENT"}`
to each text upsert, and set `embeddings_options={"task_type": "RETRIEVAL_QUERY"}`
on `create_vector_search_tool`. Core supplies the selected vector field's
dimensions, rejecting a conflicting value. See the
[agent search example](../../samples/02-agents/providers/gemini/gemini_search_agent.py).

For image, audio, video, PDF, or combined text-and-media input, pass a Google SDK
`Part` or `Content` with at least one media part. The client preserves its parts without
a task prefix, as [Google recommends for multimodal aggregates](https://ai.google.dev/gemini-api/docs/embeddings):

```python
from google.genai import types

with open("picture.png", "rb") as image:
    image_part = types.Part.from_bytes(data=image.read(), mime_type="image/png")
mixed = types.Content(parts=[types.Part.from_text(text="A landscape photo"), image_part])
client = GeminiEmbeddingClient()
try:
    result = await client.get_embeddings([mixed], options={"dimensions": 768})
finally:
    await client.close()
```

Text-only `Part`/`Content` values are rejected: use a string with `task_type` instead.
If a call mixes text strings with media, its `task_type` applies only to the strings;
media content is never prefixed. On Enterprise, Embedding 2 accepts one content per
request, so the client sends multiple inputs as separate, ordered requests.
See the [image search Agent sample](../../samples/02-agents/providers/gemini/gemini_image_search_agent.py)
for cross-modal text-to-image retrieval. Images are embedded without a text task
and upserted with `generate_vectors=False`; the search tool uses
`RETRIEVAL_QUERY` through its `embeddings_options`.

For chat and embeddings on Enterprise, use the current SDK setting
`GOOGLE_GENAI_USE_ENTERPRISE=true` (or pass `enterprise=True`) together with
`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`. The older
`GOOGLE_GENAI_USE_VERTEXAI=true` / `vertexai=True` setting remains supported.
An injected `google.genai.Client` can also provide either authentication mode.

## Structured Output

Gemini structured output can be configured with either a Pydantic model in `response_format`, a JSON schema mapping in `response_format`, or a Gemini-specific `response_schema`. Declarative agents that define `outputSchema` pass that schema through `response_format`.

## Authentication

The connector supports both `google-genai` authentication modes.

### Gemini Developer API

Obtain an API key from [Google AI Studio](https://aistudio.google.com/apikey) and set the connector's environment variables:

```bash
export GOOGLE_API_KEY="your-api-key"
export GOOGLE_MODEL="gemini-2.5-flash-lite"
```

The connector no longer reads `GEMINI_API_KEY`, `GEMINI_MODEL`, or
`GEMINI_EMBEDDING_MODEL`. Rename those variables to their `GOOGLE_*` equivalents,
or pass the API key and model explicitly. An injected `google.genai.Client` retains
the Google SDK's own authentication behavior.

### Gemini Enterprise Agent Platform (Vertex AI)

Set the standard Enterprise environment variables used by `google-genai`:

```bash
export GOOGLE_GENAI_USE_ENTERPRISE=true
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="global"
export GOOGLE_MODEL="gemini-2.5-flash-lite"
```

The older `GOOGLE_GENAI_USE_VERTEXAI=true` setting remains supported.

## Examples

See the [Google Gemini samples](../../samples/02-agents/providers/gemini/) for runnable end-to-end scripts covering:

- Basic agent with tool calling and streaming
- Extended thinking with `ThinkingConfig`
- Google Search grounding
- Google Maps grounding
- Built-in code execution
- Text embeddings for document indexing and query retrieval
