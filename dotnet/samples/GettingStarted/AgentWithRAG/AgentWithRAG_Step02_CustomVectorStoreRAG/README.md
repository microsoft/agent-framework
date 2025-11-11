# Agent Framework Retrieval Augmented Generation (RAG) with an external Vector Store with a custom schema

This sample demonstrates how to create and run an agent that uses Retrieval Augmented Generation (RAG) with an external vector store.
It also uses a custom schema for the documents stored in the vector store.
This sample uses Qdrant for the vector store, but this can easily be swapped out for any vector store that has a Microsoft.Extensions.VectorStore implementation.

## Prerequisites

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint
- Both a chat completion and embedding deployment configured in the Azure OpenAI resource
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource.
- An existing Qdrant instance. You can use a managed service or run a local instance using Docker, but the sample assumes the instance is running locally.

**Note**: These samples use Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource and have the `Cognitive Services OpenAI Contributor` role. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Running the sample from the console

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME="text-embedding-3-large"  # Optional, defaults to text-embedding-3-large
```

If the variables are not set, you will be prompted for the values when running the samples.

To use Qdrant in docker locally, start your Qdrant instance using the default port mappings.

```powershell
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest
```

Execute the following command to build the sample:

```powershell
dotnet build
```

Execute the following command to run the sample:

```powershell
dotnet run --no-build
```

Or just build and run in one step:

```powershell
dotnet run
```

## Running the sample from Visual Studio

Open the solution in Visual Studio and set the sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.
