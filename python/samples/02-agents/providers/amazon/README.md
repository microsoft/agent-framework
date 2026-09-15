# Bedrock Examples

This folder contains examples demonstrating how to use AWS Bedrock models with the Agent Framework. The sample
uses `BEDROCK_CHAT_MODEL`, `BEDROCK_REGION`, and AWS credentials (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`).

## Examples

| File | Description |
|------|-------------|
| [`bedrock_chat_client.py`](bedrock_chat_client.py) | Uses `BedrockChatClient` with a simple tool-enabled `Agent` to demonstrate direct Bedrock chat integration. |
| [`bedrock_kb_tool.py`](bedrock_kb_tool.py) | Uses `BedrockKnowledgeBaseTool` as a `FunctionTool` — the agent calls it on demand to retrieve context from an Amazon Bedrock managed Knowledge Base. |
| [`bedrock_kb_context_provider.py`](bedrock_kb_context_provider.py) | Uses `BedrockKnowledgeBaseProvider` as a `ContextProvider` — automatically injects KB context before every agent invocation. |

### When to use the KB tool vs. the KB context provider

- **Tool pattern** (`BedrockKnowledgeBaseTool`): when the agent should decide *when* to search the KB. Best for multi-tool agents where KB retrieval is one of several capabilities.
- **Provider pattern** (`BedrockKnowledgeBaseProvider`): when KB context should *always* be available. Best for single-purpose assistants that always need domain knowledge.

## Environment Variables

- `BEDROCK_CHAT_MODEL`: Bedrock model ID (for example, `anthropic.claude-3-5-sonnet-20240620-v1:0`)
- `BEDROCK_REGION`: AWS region (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`)

## Required IAM Permissions (Knowledge Base samples)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "bedrock:Retrieve",
            "Resource": "arn:aws:bedrock:*:*:knowledge-base/*"
        },
        {
            "Effect": "Allow",
            "Action": "bedrock:AgenticRetrieveStream",
            "Resource": "*"
        }
    ]
}
```

> `bedrock:AgenticRetrieveStream` has no resource-level permission type and must be granted with `Resource: "*"`; scoping it to a Knowledge Base ARN implicitly denies the agentic call and forces a fallback to standard retrieval. `bedrock:AgenticRetrieveStream` is only required when using `use_agentic_retrieval=True`.
