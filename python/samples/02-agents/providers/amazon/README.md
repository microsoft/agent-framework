# Bedrock Examples

This folder contains examples demonstrating how to use AWS Bedrock models with the Agent Framework. The sample
uses `BEDROCK_CHAT_MODEL_ID`, `BEDROCK_REGION`, and AWS credentials (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`).

## Examples

| File | Description |
|------|-------------|
| [`bedrock_chat_client.py`](bedrock_chat_client.py) | Uses `BedrockChatClient` with a simple tool-enabled `Agent` to demonstrate direct Bedrock chat integration. |

## Environment Variables

- `BEDROCK_CHAT_MODEL_ID`: Bedrock model ID (for example, `anthropic.claude-3-5-sonnet-20240620-v1:0`)
- `BEDROCK_REGION`: AWS region (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`)
