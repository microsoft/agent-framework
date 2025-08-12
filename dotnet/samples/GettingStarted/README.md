# Getting Started with Microsoft Agent Framework for .NET

This project contains comprehensive samples demonstrating how to build AI agents using the Microsoft Agent Framework. The samples are organized into progressive steps and categories to help you learn the framework from basic concepts to advanced orchestration patterns.

## 📋 Project Overview

The Getting Started samples demonstrate:

- **Basic Agent Creation**: Creating and running chat agents with different providers
- **Tool Integration**: Using function tools, code interpreter, and file search capabilities  
- **Agent Orchestration**: Sequential, concurrent, group chat, and handoff patterns
- **Provider Integration**: Working with OpenAI, Azure OpenAI, and Azure AI Agents
- **Advanced Features**: Dependency injection, telemetry, structured outputs, and thread management

## 🛠️ Prerequisites

### Required Software

- **.NET SDK 9.0** or later (recommended)
  - Also supports .NET 8.0, .NET Framework 4.7.2, and .NET Standard 2.0
  - Download from: https://dotnet.microsoft.com/download
- **Visual Studio 2022** (17.8+) or **Visual Studio Code** with C# extension
- **Git** for cloning the repository

### API Keys and Services

You'll need access to at least one of the following AI services:

- **OpenAI**: API key from https://platform.openai.com/account/api-keys
- **Azure OpenAI**: Endpoint URL and API key or Azure CLI authentication
- **Azure AI Agents**: Azure subscription with AI services enabled

## 🔐 User Secrets Configuration

The samples use .NET User Secrets to securely store API keys and configuration. This prevents sensitive information from being committed to source control.

### Option 1: Using Visual Studio

1. **Right-click** on the `GettingStarted` project in Solution Explorer
2. **Select** "Manage User Secrets"
3. **Add** your configuration in the opened `secrets.json` file:

```json
{
  "OpenAI": {
    "ApiKey": "sk-your-openai-api-key-here",
    "ChatModelId": "gpt-4o-mini"
  },
  "AzureOpenAI": {
    "Endpoint": "https://your-resource.openai.azure.com/",
    "DeploymentName": "gpt-4o-mini",
    "ApiKey": "your-azure-openai-api-key"
  }
}
```

### Option 2: Using Visual Studio Code

1. **Open** the integrated terminal (`Ctrl+`` ` or `View > Terminal`)
2. **Navigate** to the samples directory:
   ```bash
   cd dotnet/samples/GettingStarted
   ```
3. **Initialize** user secrets:
   ```bash
   dotnet user-secrets init
   ```
4. **Set** your secrets using the commands below

### Option 3: Using Command Line

Navigate to the GettingStarted directory and run these commands:

```bash
# Navigate to the project directory
cd dotnet/samples/GettingStarted

# Initialize user secrets (if not already done)
dotnet user-secrets init

# Configure OpenAI (choose one model)
dotnet user-secrets set "OpenAI:ApiKey" "sk-your-openai-api-key-here"
dotnet user-secrets set "OpenAI:ChatModelId" "gpt-4o-mini"

# Configure Azure OpenAI (alternative to OpenAI)
dotnet user-secrets set "AzureOpenAI:Endpoint" "https://your-resource.openai.azure.com/"
dotnet user-secrets set "AzureOpenAI:DeploymentName" "gpt-4o-mini"
dotnet user-secrets set "AzureOpenAI:ApiKey" "your-azure-openai-api-key"

# Optional: Configure Azure AI Agents
dotnet user-secrets set "AzureAI:Endpoint" "https://your-ai-foundry-project.cognitiveservices.azure.com/"
dotnet user-secrets set "AzureAI:DeploymentName" "gpt-4o-mini"
```

### Environment Variables (Alternative)

If you prefer environment variables over user secrets, use these names:

```bash
# OpenAI Configuration
OpenAI__ApiKey=sk-your-openai-api-key-here
OpenAI__ChatModelId=gpt-4o-mini

# Azure OpenAI Configuration  
AzureOpenAI__Endpoint=https://your-resource.openai.azure.com/
AzureOpenAI__DeploymentName=gpt-4o-mini
AzureOpenAI__ApiKey=your-azure-openai-api-key

# Azure AI Configuration
AzureAI__Endpoint=https://your-ai-foundry-project.cognitiveservices.azure.com/
AzureAI__DeploymentName=gpt-4o-mini
```

## 🚀 Setup and Execution Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework
```

### 2. Navigate to the Samples Directory

```bash
cd dotnet/samples/GettingStarted
```

### 3. Build the Project & Restore Dependencies

```bash
dotnet build
```

### 4. Run the Samples

#### Option A: Interactive Console Interface (Recommended)

The project includes an interactive console interface that makes it easy to discover and run specific tests:

```bash
# Run the interactive console (requires framework specification)
dotnet run --framework net9.0    # Recommended - uses .NET 9.0
dotnet run --framework net472     # Alternative - uses .NET Framework 4.7.2
```

**Note**: Since this is a multi-targeting project, you must specify the `--framework` parameter when using `dotnet run`. The `--framework net9.0` option is recommended for the best console experience.

The interactive console provides:
- **Test Discovery**: Automatically finds all test classes, methods, and theory parameters
- **Configuration Management**: View, add, update, and remove API keys and configuration settings
- **Hierarchical Navigation**: Browse tests by folder → class → method → theory parameters
- **Easy Execution**: Run individual tests or groups with simple menu selections



#### Option B: Direct Test Execution

You can also run tests directly using xUnit:

```bash
# Run all samples
dotnet test

# Run a specific sample category
dotnet test --filter "FullyQualifiedName~Steps"
dotnet test --filter "FullyQualifiedName~Orchestration"
dotnet test --filter "FullyQualifiedName~Providers"

# Run a specific sample class
dotnet test --filter "FullyQualifiedName~Step01_ChatClientAgent_Running"

# Run a specific test method (all theory variations)
dotnet test --filter "FullyQualifiedName~Step01_ChatClientAgent_Running.RunWithoutThread" --logger "console;verbosity=detailed"

# Run only a specific theory case (e.g., just Azure OpenAI provider)
dotnet test --filter "DisplayName=Steps.Step01_ChatClientAgent_Running.RunWithoutThread(provider: AzureOpenAI)" --logger "console;verbosity=detailed"
```

#### Option C: Command Line Test Execution

You can also run specific tests via command line arguments:

```bash
# Run a specific test using the console interface
dotnet run --framework net9.0 -- --test "DisplayName=Steps.Step01_ChatClientAgent_Running.RunWithoutThread(provider: AzureOpenAI)"
```

### 5. Run Samples in Visual Studio

1. **Open** the solution file: `dotnet/agent-framework-dotnet.slnx`
2. **Set** the `GettingStarted` project as the startup project
3. **Open** Test Explorer (`Test > Test Explorer`)
4. **Run** individual tests or test categories

## 📚 Sample Categories

### 📖 Steps (Progressive Learning)
- **Step01**: Basic chat agent creation and interaction
- **Step02**: Adding function tools to agents
- **Step03**: Using code interpreter tools
- **Step04**: Dependency injection patterns
- **Step05**: Telemetry and observability
- **Step06**: Structured outputs
- **Step07**: File search capabilities
- **Step08**: Thread suspension and resumption
- **Step09**: Third-party thread storage

### 🔄 Orchestration (Multi-Agent Patterns)
- **Sequential**: Chain agents in sequence
- **Concurrent**: Run multiple agents simultaneously
- **Group Chat**: Multi-agent conversations
- **Handoff**: Transfer conversations between agents

### 🔌 Providers (Service Integration)
- **OpenAI**: Direct OpenAI API integration
- **Azure OpenAI**: Azure-hosted OpenAI models
- **Azure AI Agents**: Azure AI Foundry integration
- **OpenAI Responses**: Advanced response handling

## 🔧 Troubleshooting

### Common Issues

**Issue**: `InvalidOperationException: TestConfiguration must be initialized`
**Solution**: Ensure user secrets are properly configured with the required API keys and endpoints.

**Issue**: `Unauthorized` or `401` errors
**Solution**: Verify your API keys are correct and have sufficient permissions/credits.

**Issue**: `Model not found` errors  
**Solution**: Check that your model deployment names match the configured values in user secrets.

**Issue**: Build errors related to target frameworks
**Solution**: Ensure you have .NET 9.0 SDK installed. You can check with `dotnet --version`.

**Issues**: Test fails using Structured Output with Azure AI Foundry. `Azure.RequestFailedException : Invalid parameter: 'response_format' of type 'json_schema' is not supported with model version ''.`
**Solution**: This is a known issue with Azure AI Foundry when attempting to use models that don't support custom schemas for response-formats, attempting to latest generation models like `gpt-4.1` should resolve this.

### Getting Help

- **Documentation**: https://github.com/microsoft/agent-framework/tree/main/docs
- **Issues**: https://github.com/microsoft/agent-framework/issues
- **Discussions**: https://github.com/microsoft/agent-framework/discussions