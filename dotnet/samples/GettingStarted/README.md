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

## 🔐 Configuration Setup

The samples use .NET User Secrets to securely store API keys and configuration. This prevents sensitive information from being committed to source control.

### Option 1: Interactive Setup (Recommended)

The **easiest way** to configure your API keys is using the built-in interactive setup:

1. **Run** the application:
   ```bash
   cd dotnet/samples/GettingStarted
   dotnet run --framework net9.0
   ```

2. **Follow the prompts**: The application will automatically detect missing configuration and guide you through setup with:
   - Clear descriptions for each setting
   - Contextual help and examples
   - Secure input for API keys

The interactive setup handles all the technical details and ensures your configuration is stored securely.

### Option 2: Manual Setup - Visual Studio

1. **Right-click** on the `GettingStarted` project in Solution Explorer
2. **Select** "Manage User Secrets"
3. **Add** your configuration in the opened `secrets.json` file:

```json
{
  "OpenAI:ApiKey": "sk-your-openai-api-key-here",
  "OpenAI:ChatModelId": "gpt-4o-mini",
  "AzureOpenAI:Endpoint": "https://your-resource.openai.azure.com/",
  "AzureOpenAI:DeploymentName": "gpt-4o-mini",
  "AzureOpenAI:ApiKey": "your-azure-openai-api-key",
  "AzureAI:Endpoint": "https://your-ai-foundry-project.cognitiveservices.azure.com/api/projects/your-project",
  "AzureAI:DeploymentName": "gpt-4o-mini"
}
```

### Option 3: Manual Setup - Command Line

Navigate to the GettingStarted directory and run these commands:

```bash
# Navigate to the project directory
cd dotnet/samples/GettingStarted

# Initialize user secrets (if not already done)
dotnet user-secrets init

# Configure OpenAI
dotnet user-secrets set "OpenAI:ApiKey" "sk-your-openai-api-key-here"
dotnet user-secrets set "OpenAI:ChatModelId" "gpt-4o-mini"

# Configure Azure OpenAI (alternative to OpenAI)
dotnet user-secrets set "AzureOpenAI:Endpoint" "https://your-resource.openai.azure.com/"
dotnet user-secrets set "AzureOpenAI:DeploymentName" "gpt-4o-mini"
dotnet user-secrets set "AzureOpenAI:ApiKey" "your-azure-openai-api-key"

# Configure Azure AI Foundry (optional)
dotnet user-secrets set "AzureAI:Endpoint" "https://your-ai-foundry-project.cognitiveservices.azure.com/api/projects/your-project"
dotnet user-secrets set "AzureAI:DeploymentName" "gpt-4o-mini"
```

### Option 4: Environment Variables (Alternative)

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

## 🚀 Running the Application

### Console/Terminal

Navigate to the project directory and run with framework specification:

```bash
cd dotnet/samples/GettingStarted

# Build the project
dotnet build

# Run the interactive test runner (recommended)
dotnet run --framework net9.0    # Best experience with .NET 9.0
dotnet run --framework net472     # Alternative with .NET Framework 4.7.2
```

**Note**: Framework specification is required for multi-targeting projects. Use `net9.0` for the optimal console experience.

### Visual Studio Code

1. **Open** the project folder in VS Code
2. **Use** the existing debug configuration:
   - Press `F5` or go to `Run and Debug` panel
   - Select **"C# GettingStarted"** configuration
   - Click the play button to start debugging

The launch configuration is pre-configured to run the interactive test runner with proper framework targeting.

### Visual Studio

1. **Open** the solution: `dotnet/agent-framework-dotnet.slnx`
2. **Set** `GettingStarted` as the startup project (right-click → Set as Startup Project)
3. **Press** `F5` or click **Debug > Start Debugging**
4. **Alternative**: Use Test Explorer (`Test > Test Explorer`) to run individual tests

## ✨ Key Features

### Configuration Management

The application provides an **interactive configuration system** that guides you through setting up your AI service credentials:

- **Automatic Detection**: Identifies missing configuration and prompts for setup
- **Secure Storage**: Uses .NET User Secrets to protect API keys and sensitive data
- **Multiple Providers**: Supports OpenAI, Azure OpenAI, and Azure AI Foundry services
- **User-Friendly Prompts**: Clear descriptions and contextual help for each setting
- **Real-Time Validation**: Immediate feedback on configuration status

### Sample Execution

The **interactive test runner** provides a comprehensive interface for discovering and executing samples:

- **Hierarchical Navigation**: Browse samples by category → class → method → parameters
- **Smart Discovery**: Automatically finds all available tests and organizes them logically
- **Rich Descriptions**: Each sample includes detailed explanations and context
- **Flexible Execution**: Run individual tests, test groups, or entire categories
- **Real-Time Output**: View test results and detailed execution logs
- **Error Handling**: Clear error messages and troubleshooting guidance

**Navigation Features:**
- **Category Browsing**: Explore samples by Steps, Orchestration, and Providers
- **Method Selection**: Choose specific test methods with parameter variations
- **Theory Parameters**: Run tests with different provider configurations
- **Back Navigation**: Easy return to previous menus and selections

## 📁 Project Organization

### Main Components

- **`/Steps`**: Progressive learning samples (Step01 through Step09)
- **`/Orchestration`**: Multi-agent coordination patterns
- **`/Providers`**: Service-specific end-to-end code integration examples
- **`/TestRunner`**: Interactive console application for sample execution

### TestRunner

The TestRunner is a convenience executable UI logic that provides an intuitive UI for exploring and running the framework samples. It handles configuration management, test discovery, and execution through an interactive console interface, making it easy to get started without complex command-line arguments.

## 🧪 Alternative Execution Methods

### Direct Test Execution

For advanced users, you can run tests directly using xUnit:

```bash
# Run all samples
dotnet test

# Run specific categories
dotnet test --filter "FullyQualifiedName~Steps"
dotnet test --filter "FullyQualifiedName~Orchestration"

# Run with detailed output
dotnet test --filter "FullyQualifiedName~Step01" --logger "console;verbosity=detailed"
```

### Command Line Arguments

Run specific tests via command line:

```bash
dotnet run --framework net9.0 -- --test "DisplayName=Steps.Step01_ChatClientAgent_Running.RunWithoutThread(provider: OpenAI)"
```

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