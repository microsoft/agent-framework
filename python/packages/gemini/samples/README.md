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

## Environment Variables

- `GOOGLE_MODEL` or `GEMINI_MODEL`: The Gemini model to use (for example,
  `gemini-2.5-flash-lite` or `gemini-2.5-pro`)
- For Gemini Developer API: `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- For Vertex AI: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION`
