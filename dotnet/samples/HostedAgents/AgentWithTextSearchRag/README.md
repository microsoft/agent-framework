# What this sample demonstrates

This sample demonstrates how to use TextSearchProvider to add retrieval augmented generation (RAG) capabilities to an AI agent. The provider runs a search against an external knowledge base before each model invocation and injects the results into the model context.

Key features:
- Configuring TextSearchProvider with custom search behavior
- Running searches before AI invocations to provide relevant context
- Managing conversation memory with a rolling window approach
- Citing source documents in AI responses

## Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI endpoint configured
2. A deployment of a chat model (e.g., gpt-4o-mini)
3. Azure CLI installed and authenticated

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

## How It Works

The sample uses a mock search function that demonstrates the RAG pattern:

1. When the user asks a question, the TextSearchProvider intercepts it
2. The search function looks for relevant documents based on the query
3. Retrieved documents are injected into the model's context
4. The AI responds using both its training and the provided context
5. The agent can cite specific source documents in its answers

The mock search function returns pre-defined snippets for demonstration purposes. In a production scenario, you would replace this with actual searches against your knowledge base (e.g., Azure AI Search, vector database, etc.).
