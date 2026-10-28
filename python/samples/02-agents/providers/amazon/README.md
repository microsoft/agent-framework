# Bedrock Examples

This folder contains examples demonstrating how to use AWS Bedrock models with the Agent Framework. The sample
uses `BEDROCK_CHAT_MODEL`, `BEDROCK_REGION`, and AWS credentials (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`).

## Examples

| File | Description |
|------|-------------|
| [`bedrock_chat_client.py`](bedrock_chat_client.py) | Uses `BedrockChatClient` with a simple tool-enabled `Agent` to demonstrate direct Bedrock chat integration. |
| [`bedrock_kb_tool.py`](bedrock_kb_tool.py) | `BedrockKnowledgeBaseProvider` in **tool mode** (`mode="tool"`) — exposes a KB search tool the model calls on demand. |
| [`bedrock_kb_context_provider.py`](bedrock_kb_context_provider.py) | `BedrockKnowledgeBaseProvider` in **inject mode** (`mode="inject"`) — automatically injects KB context before every agent invocation. |

### Choosing a mode

`BedrockKnowledgeBaseProvider` is the single entry point for using an Amazon Bedrock managed Knowledge Base with an agent. Pick a `mode`:

- **`"inject"`**: KB context is retrieved and injected before every run. Best for single-purpose assistants that always need domain knowledge.
- **`"tool"`**: a KB search tool is exposed and the model decides *when* to search. Best for multi-tool agents where KB retrieval is one of several capabilities.
- **`"both"`** (default): does both.

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
            "Action": [
                "bedrock:Retrieve",
                "bedrock:GetDocumentContent"
            ],
            "Resource": "arn:aws:bedrock:*:*:knowledge-base/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:AgenticRetrieveStream",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": "*"
        }
    ]
}
```

> `bedrock:AgenticRetrieveStream` and `bedrock:InvokeModelWithResponseStream` have no resource-level permission type and must be granted with `Resource: "*"`; scoping `AgenticRetrieveStream` to a Knowledge Base ARN implicitly denies the agentic call and forces a fallback to standard retrieval, so query decomposition never runs. `bedrock:GetDocumentContent` is scoped to the Knowledge Base ARN and is required because agentic retrieval calls it during a `FullDocumentExpansion` step. This matches the [AWS agentic-retrieval permissions reference](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html). `AgenticRetrieveStream`/`GetDocumentContent`/`InvokeModelWithResponseStream` are only required when using `use_agentic_retrieval=True`.
