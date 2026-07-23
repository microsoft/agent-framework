# Bedrock Managed Knowledge Base Support

## Overview
Adds an Agent Framework tool that queries Amazon Bedrock Knowledge Bases for managed retrieval within agent pipelines.

## Usage
```python
from agent_framework_bedrock import BedrockKnowledgeBaseTool
import asyncio

tool = BedrockKnowledgeBaseTool(
    knowledge_base_id="YOUR_KB_ID",
    region_name="us-east-1",
)
results = asyncio.run(tool.run(query="What are the compliance requirements?"))
for result in results:
    print(result["content"], result["score"])
```

## Configuration
| Variable | Description | Default |
|---|---|---|
| KNOWLEDGE_BASE_ID | Bedrock Knowledge Base ID | None |
| AWS_REGION | AWS region for the KB | us-east-1 |
| AWS_PROFILE | AWS credentials profile | None |
| USE_AGENTIC_RETRIEVAL | Enable agentic retrieval | true |
| MAX_RESULTS | Maximum retrieval results (use `number_of_results` constructor param) | 5 |

## Features
- Managed search (no vector store needed)
- Agentic retrieval with query decomposition + reranking
- Automatic fallback to plain Retrieve if agentic fails
- Multi-source support (S3, Web, Confluence, SharePoint)
- Compatible with Agent Framework tool interface

## SDK Requirements
- boto3 >= 1.43

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
