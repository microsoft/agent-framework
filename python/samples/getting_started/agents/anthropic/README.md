# Anthropic Examples

This folder contains examples demonstrating how to use Anthropic's Claude models with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`anthropic_with_openai_chat_client.py`](anthropic_with_openai_chat_client.py) | Demonstrates how to configure OpenAI Chat Client to use Anthropic's Claude models. Shows both streaming and non-streaming responses with tool calling capabilities. |

## Environment Variables

Set the following environment variables before running the examples:

- `ANTHROPIC_API_KEY`: Your Anthropic API key (get one from [Anthropic Console](https://console.anthropic.com/))
- `ANTHROPIC_MODEL`: The Claude model to use (e.g., `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`)

