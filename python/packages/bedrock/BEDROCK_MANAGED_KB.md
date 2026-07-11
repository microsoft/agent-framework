# Bedrock Managed Knowledge Base Support

## Overview
Adds an Agent Framework tool that queries Amazon Bedrock Knowledge Bases for managed retrieval within agent pipelines.

## Usage
```python
from agent_framework import Agent
from agent_framework_bedrock import BedrockKnowledgeBaseTool

tool = BedrockKnowledgeBaseTool(
    knowledge_base_id="YOUR_KB_ID",
    region_name="us-east-1",
)

# As a FunctionTool, pass directly to an Agent:
agent = Agent(tools=[tool])

# Or invoke directly for testing:
import asyncio
result = asyncio.run(tool.invoke(arguments={"query": "What are the compliance requirements?"}))
print(result)  # List of Content items with retrieval results
```

## Configuration

All configuration is via constructor parameters:

| Parameter | Description | Default |
|---|---|---|
| `knowledge_base_id` | Bedrock Knowledge Base ID (required) | — |
| `region_name` | AWS region for the KB | `us-east-1` |
| `number_of_results` | Maximum retrieval results | `5` |
| `use_agentic_retrieval` | Enable agentic multi-hop retrieval | `True` |
| `client` | Pre-configured boto3 client (optional) | Auto-created |

## Features
- Managed search (no vector store needed)
- **BedrockKnowledgeBaseTool**: Agentic retrieval with query decomposition + reranking, automatic fallback to standard Retrieve
- **BedrockKnowledgeBaseProvider**: Standard managed retrieval injected as context before each agent run
- Multi-source support (S3, Web, Confluence, SharePoint)
- Compatible with Agent Framework FunctionTool and ContextProvider interfaces

## SDK Requirements
- boto3 >= 1.43.32

## Required IAM Permissions
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:Retrieve",
    "bedrock:AgenticRetrieveStream"
  ],
  "Resource": "arn:aws:bedrock:<region>:<account-id>:knowledge-base/<kb-id>"
}
```

## References
- [Build a Managed Knowledge Base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- [Retrieve API](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html)
- [Agentic Retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic.html)
