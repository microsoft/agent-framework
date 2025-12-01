# Bedrock Chat Client Sample

This sample shows how to call Amazon Bedrock models through the Microsoft Agent Framework chat abstractions.

## Prerequisites

Set the following environment variables before running the sample:

- `BEDROCK_REGION`: The AWS region that hosts Bedrock (for example, `us-east-1`).
- `BEDROCK_CHAT_MODEL_ID`: The target model ID (for example, `anthropic.claude-3-sonnet-20240229-v1:0`).
- `BEDROCK_ACCESS_KEY` and `BEDROCK_SECRET_KEY`: AWS credentials that have access to the Bedrock runtime APIs.
- `BEDROCK_SESSION_TOKEN`: Optional session token if you rely on temporary credentials.

Install the provider package in editable mode from the repository root:

```bash
uv pip install -e python/packages/bedrock
```

## Run the Sample

From the repository root:

```bash
cd python/samples/bedrock_chatclient
uv run python main.py
```

The script registers a simple weather tool, lets Bedrock request it, injects the mocked tool result back into the conversation, and prints the assistant's final response.