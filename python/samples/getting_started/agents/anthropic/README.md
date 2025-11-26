# Anthropic Examples

This folder contains examples demonstrating how to use Anthropic's Claude models with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`anthropic_basic.py`](anthropic_basic.py) | Demonstrates how to setup a simple agent using the AnthropicClient, with both streaming and non-streaming responses. |
| [`anthropic_advanced.py`](anthropic_advanced.py) | Shows advanced usage of the AnthropicClient, including hosted tools and `thinking`. |
| [`anthropic_skills.py`](anthropic_skills.py) | Illustrates how to use Anthropic-managed Skills with an agent, including the Code Interpreter tool and file generation and saving. |
| [`anthropic_foundry.py`](anthropic_foundry.py) | Example of using Foundry's Anthropic integration with the Agent Framework. |

## Environment Variables

Set the following environment variables before running the examples:

- `ANTHROPIC_API_KEY`: Your Anthropic API key (get one from [Anthropic Console](https://console.anthropic.com/))
- `ANTHROPIC_CHAT_MODEL_ID`: The Claude model to use (e.g., `claude-haiku-4-5`, `claude-sonnet-4-5-20250929`)

Or, for Foundry:
- `ANTHROPIC_FOUNDRY_API_KEY`: Your Foundry Anthropic API key
- `ANTHROPIC_FOUNDRY_ENDPOINT`: The endpoint URL for your Foundry Anthropic resource
- `ANTHROPIC_CHAT_MODEL_ID`: The Claude model to use in Foundry (e.g., `claude-haiku-4-5`)
