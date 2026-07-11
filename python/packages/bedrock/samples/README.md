# Bedrock Knowledge Base Examples

This folder contains examples demonstrating how to use Amazon Bedrock Knowledge Bases with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`bedrock_kb_tool.py`](bedrock_kb_tool.py) | Using `BedrockKnowledgeBaseTool` as a FunctionTool — agent calls it on-demand when it needs knowledge base context. |
| [`bedrock_kb_context_provider.py`](bedrock_kb_context_provider.py) | Using `BedrockKnowledgeBaseProvider` as a ContextProvider — automatically injects KB context before every agent invocation. |

## When to use each pattern

- **Tool pattern** (`BedrockKnowledgeBaseTool`): When the agent should decide *when* to search the KB. Best for multi-tool agents where KB retrieval is one of several capabilities.
- **Provider pattern** (`BedrockKnowledgeBaseProvider`): When KB context should *always* be available. Best for single-purpose assistants that always need domain knowledge.

## Environment Variables

- `AWS_DEFAULT_REGION`: AWS region where your Knowledge Base is deployed
- AWS credentials: Configure via environment variables, IAM role, or AWS profiles

## Required IAM Permissions

```json
{
    "Effect": "Allow",
    "Action": [
        "bedrock:Retrieve",
        "bedrock:AgenticRetrieveStream"
    ],
    "Resource": "arn:aws:bedrock:*:*:knowledge-base/*"
}
```
