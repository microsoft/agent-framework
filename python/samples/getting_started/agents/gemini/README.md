# Gemini Examples

This folder contains examples demonstrating how to use Google Gemini models with the Agent Framework through the OpenAI Chat Client interface.

## Examples

| File | Description |
|------|-------------|
| [`gemini_with_openai_chat_client.py`](gemini_with_openai_chat_client.py) | Demonstrates how to configure OpenAI Chat Client to use Google Gemini models. Shows non-streaming responses with tool calling capabilities. |
| [`vertexai_with_openai_chat_client.py`](vertexai_with_openai_chat_client.py) | Demonstrates how to configure OpenAI Chat Client to use the Gemini API on Vertex AI. Shows non-streaming responses with tool calling capabilities. |

## Environment Variables

Set the following environment variables before running the examples:

- `GEMINI_MODEL`: The Gemini model to use (e.g., `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`)

- For the [Gemini Developer API](https://ai.google.dev/)
  - `GEMINI_API_KEY`: Your Gemini API key (get one from [Google AI Studio](https://aistudio.google.com/apikey))
- For [Gemini API on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs)
  - `GOOGLE_CLOUD_PROJECT`: Your Google Cloud Project ID
  - `GOOGLE_CLOUD_LOCATION`: Your Google Cloud Location (e.g., `global` or `us-central1`)
