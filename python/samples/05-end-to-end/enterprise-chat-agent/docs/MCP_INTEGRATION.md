# Microsoft Docs MCP Server Integration

## Overview

This document explains how to integrate the Microsoft Docs MCP server into the Enterprise Chat Agent, enabling real-time access to official Microsoft and Azure documentation.

## What is MCP?

**Model Context Protocol (MCP)** is a standard for connecting AI applications to external data sources and tools. The Microsoft Docs MCP server provides access to:
- Official Microsoft Learn documentation
- Azure service documentation
- Code samples and examples
- API references

## Current Status

The chat agent includes two MCP-ready tools:
- `search_microsoft_docs` - Search documentation content
- `search_microsoft_code_samples` - Find code examples

**Status:** Tools are defined but MCP integration requires VS Code/Copilot Chat environment or custom MCP client implementation.

## Integration Options

### Option 1: Use in VS Code with GitHub Copilot (Recommended)

The MCP server is already available in your VS Code environment. The tools can be used directly when the agent runs in a Copilot-enabled context.

**No additional code needed** - the MCP functions are available via the Copilot extension.

### Option 2: Direct HTTP API Integration (Azure Functions)

For standalone Azure Functions deployment, replace MCP calls with direct REST API calls to Microsoft Learn search:

```python
import httpx

async def search_microsoft_docs(query: str, max_results: int = 5) -> list[dict]:
    """Search Microsoft docs via REST API."""
    # Microsoft Learn has a public search endpoint
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://learn.microsoft.com/api/search",
            params={
                "search": query,
                "locale": "en-us",
                "$top": max_results,
            }
        )
        results = response.json()

    return [
        {
            "title": result["title"],
            "content": result["description"],
            "url": result["url"],
        }
        for result in results.get("results", [])
    ]
```

### Option 3: Use Azure Cognitive Search on Microsoft Learn Index

For production deployments, use Azure Cognitive Search with a pre-built index of Microsoft documentation:

```python
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential

async def search_microsoft_docs(query: str, max_results: int = 5) -> list[dict]:
    """Search using Azure Cognitive Search."""
    credential = DefaultAzureCredential()
    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name="microsoft-docs-index",
        credential=credential,
    )

    results = search_client.search(
        search_text=query,
        top=max_results,
        select=["title", "content", "url"],
    )

    return [
        {
            "title": doc["title"],
            "content": doc["content"],
            "url": doc["url"],
        }
        for doc in results
    ]
```

## Example Usage

Once integrated, users can ask:

```
User: "How do I configure partition keys in Azure Cosmos DB?"
→ Agent calls: search_microsoft_docs("Cosmos DB partition keys")
→ Returns: Official docs with best practices, examples, and guidance
```

```
User: "Show me Python code for Azure OpenAI chat completion"
→ Agent calls: search_microsoft_code_samples("Azure OpenAI chat completion", language="python")
→ Returns: Official code examples from Microsoft Learn
```

## Implementation Steps

### Quick Test (Local with VS Code)

1. The MCP server is already available in your VS Code environment
2. Tools are defined and ready
3. Test with Copilot Chat to verify MCP integration

### Production Deployment (Azure Functions)

1. Choose integration method (Option 2 or 3 above)
2. Update `tools/microsoft_docs.py` with real implementation
3. Add required dependencies to `requirements.txt`:
   ```
   httpx>=0.24.0  # For REST API option
   # OR
   azure-search-documents>=11.4.0  # For Azure Search option
   ```
4. Add environment variables:
   ```json
   {
     "AZURE_SEARCH_ENDPOINT": "https://your-search.search.windows.net",
     "MICROSOFT_LEARN_API_KEY": "optional-if-using-api"
   }
   ```
5. Deploy with `azd up`

## Benefits

✅ **Authoritative Information**: Official Microsoft documentation
✅ **Always Current**: Latest product updates and features
✅ **Code Examples**: Real, tested code samples
✅ **Better Support**: Answer Azure questions with confidence
✅ **Reduced Hallucination**: Grounded in actual documentation

## Example Queries the Agent Can Now Handle

- "What are Azure Functions hosting options?"
- "How do I implement retry policies in Azure?"
- "Show me code for Azure Cosmos DB bulk operations"
- "What's the difference between Azure App Service and Container Apps?"
- "How do I configure CORS for Azure Functions?"
- "Best practices for Azure OpenAI rate limiting"

## Next Steps

1. **Test locally**: Run agent and ask Azure-related questions
2. **Choose production integration**: REST API or Azure Search
3. **Implement real search**: Replace placeholder with actual calls
4. **Deploy and monitor**: Track which docs are most helpful

For questions about MCP, see:
- [Model Context Protocol Specification](https://modelcontextprotocol.io)
- [Microsoft MCP Servers](https://github.com/microsoft/mcp-servers)
