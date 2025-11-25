**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).
 
Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.
 
Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.
 
Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

# What this sample demonstrates

This sample demonstrates how to use AI agents as executors within a workflow, hosted using 
[Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme) and 
deploy it to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.

## How It Works

### Agents in Workflows

This sample demonstrates the integration of AI agents within a workflow pipeline. The workflow operates as follows:

1. **French Agent** - Receives input text and translates it to French
2. **Spanish Agent** - Takes the French translation and translates it to Spanish
3. **English Agent** - Takes the Spanish translation and translates it back to English

The agents are connected sequentially in a workflow, creating a translation chain that demonstrates:
- How AI-powered agents can be seamlessly integrated into workflow pipelines
- Sequential execution patterns where each agent's output becomes the next agent's input
- Composable agent architectures for multi-step processing

### Agent Hosting

The agent workflow is hosted using the [Azure AI AgentServer SDK](https://learn.microsoft.com/en-us/dotnet/api/overview/azure/ai.agentserver.agentframework-readme),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol. This allows interaction with the agent workflow using OpenAI Responses compatible clients.

### Agent Deployment

The hosted agent workflow can be seamlessly deployed to Microsoft Foundry using the Azure Developer CLI [ai agent](https://aka.ms/azdaiagent/docs) extension.
The extension builds a container image for the agent, deploys it to Azure Container Instances (ACI), and creates a hosted agent version and deployment on Foundry Agent Service.

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI endpoint configured
2. A deployment of a chat model (e.g., `gpt-4o-mini`)
3. Azure CLI installed and authenticated (`az login`)
4. .NET 9.0 SDK or later installed

### Environment Variables

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_OPENAI_DEPLOYMENT_NAME` - The deployment name for your chat model (optional, defaults to `gpt-4o-mini`)

**PowerShell:**
```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

### Running the Sample

To run the agent, execute the following command in your terminal:

```powershell
dotnet run
```

This will start the hosted agent workflow locally on `http://localhost:8080/`.

### Interacting with the Agent

You can interact with the agent workflow using:

- The `run-requests.http` file in this directory to test and prompt the agent
- Any OpenAI Responses compatible client by sending requests to `http://localhost:8080/`

Try providing text in English to see it translated through the workflow chain (English ? French ? Spanish ? English).

### Deploying the Agent to Microsoft Foundry

To deploy your agent to Microsoft Foundry, follow the comprehensive deployment guide at https://aka.ms/azdaiagent/docs