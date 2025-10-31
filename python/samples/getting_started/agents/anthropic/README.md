# Anthropic Examples

This folder contains examples demonstrating how to use Anthropic's Claude models with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`anthropic_basic.py`](anthropic_basic.py) | Demonstrates how to setup a simple agent using the AnthropicClient, with both streaming and non-streaming responses. |
| [`anthropic_advanced.py`](anthropic_advanced.py) | Shows advanced usage of the AnthropicClient, including hosted tools and `thinking`. |

## Environment Variables

Set the following environment variables before running the examples:

- `ANTHROPIC_API_KEY`: Your Anthropic API key (get one from [Anthropic Console](https://console.anthropic.com/))
- `ANTHROPIC_MODEL`: The Claude model to use (e.g., `claude-haiku-4-5`, `claude-sonnet-4-5-20250929`)
