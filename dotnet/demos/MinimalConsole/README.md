# Minimal Console Application

This demo shows a very basic console application, that uses the agent framework with Azure OpenAI and function calling.

## Overview

## Prerequisites

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

## Configuration

### Azure OpenAI Setup
Set the following environment variables:
```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource.

## Running the Demo

```powershell
cd dotnet/demos/MinimalConsole
dotnet build
dotnet run --no-build
```
