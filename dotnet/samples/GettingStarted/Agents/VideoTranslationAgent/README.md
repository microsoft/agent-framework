# Video Translation Agent Sample

This sample demonstrates how to create an AI agent that can translate videos using Azure AI Speech's Video Translation service. The agent provides tools to upload videos to Azure Blob Storage, translate videos, list translations, get details, and delete translations.

## Overview

The Video Translation Agent integrates multiple Azure services:

- **Azure OpenAI**: Powers the AI agent with natural language understanding
- **Azure Video Translation**: Translates videos from one language to another
- **Azure Blob Storage**: Stores video files for translation
- **Azure Identity**: Provides authentication across services

## Prerequisites

Before you begin, ensure you have the following:

- .NET 9.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure Video Translation service endpoint
- Azure Storage account with a container for video uploads
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource
- User has appropriate permissions for Video Translation and Storage services

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to all required Azure resources.

## Setup

### 1. Set Environment Variables

Set the following environment variables:

#### Windows (PowerShell)
```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4"  # Optional, defaults to gpt-4
$env:VIDEO_TRANSLATION_ENDPOINT="https://your-region.api.cognitive.microsoft.com/"
$env:VIDEO_TRANSLATION_API_VERSION="2024-05-20-preview"  # Optional
$env:AZURE_STORAGE_ACCOUNT_NAME="yourstorageaccount"
$env:AZURE_STORAGE_CONTAINER_NAME="videos"
```

#### Linux/macOS (Bash)
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4"  # Optional, defaults to gpt-4
export VIDEO_TRANSLATION_ENDPOINT="https://your-region.api.cognitive.microsoft.com/"
export VIDEO_TRANSLATION_API_VERSION="2024-05-20-preview"  # Optional
export AZURE_STORAGE_ACCOUNT_NAME="yourstorageaccount"
export AZURE_STORAGE_CONTAINER_NAME="videos"
```

### 2. Authenticate with Azure CLI

```bash
az login
```

Ensure your account has the necessary permissions for:
- Azure OpenAI (Cognitive Services OpenAI Contributor role)
- Azure Video Translation service
- Azure Storage (Storage Blob Data Contributor role)

## Running the Sample

Navigate to the sample directory:

```bash
cd dotnet/samples/GettingStarted/Agents/VideoTranslationAgent
```

Build and run:

```bash
dotnet run
```

Or build separately:

```bash
dotnet build
dotnet run --no-build
```

## Features

The agent provides the following capabilities:

### 1. Upload Video to Blob Storage
Uploads a local video file to Azure Blob Storage for translation.

### 2. Download and Upload Video
Downloads a video from a public URL and uploads it to Azure Blob Storage.

### 3. Translate Video
Translates a video to a target language. Supports full locale codes such as:
- `fr-FR` (French)
- `es-ES` (Spanish)
- `de-DE` (German)
- `en-US` (English)

### 4. List Translations
Lists all video translations in your account.

### 5. Get Translation Details
Retrieves detailed information about a specific translation.

### 6. Delete Translation
Deletes a translation and its associated resources.

### 7. List Iterations
Lists all iterations for a specific translation.

## Example Usage

The sample includes a default query that demonstrates translating a video to French:

```csharp
var query = "Translate this video \"[video-url]\" to French.";
var result = await agent.RunAsync(query);
```

You can modify the query in `Program.cs` to test different scenarios:

```csharp
// List all translations
var query = "List all my video translations";

// Get details about a specific translation
var query = "Get details for translation 12092024123456_en-US_fr-FR_PlatformVoice";

// Delete a translation
var query = "Delete the translation with ID 12092024123456_en-US_fr-FR_PlatformVoice";
```

## Architecture

### Components

1. **VideoTranslationEnums.cs**: Defines enums for voice kinds, operation statuses, and file types
2. **VideoTranslationModels.cs**: Contains data models for translations, iterations, and operations
3. **VideoTranslationClient.cs**: HTTP client for Azure Video Translation API
4. **Program.cs**: Main application that creates the AI agent with all tools

### Tool Functions

Each tool is implemented as a C# function with the `Description` attribute:

- `UploadVideoToBlob`: Uploads videos to Azure Blob Storage
- `DownloadAndUploadVideo`: Downloads and uploads videos
- `TranslateVideo`: Translates videos using Azure Video Translation
- `ListTranslations`: Lists all translations
- `GetTranslationDetails`: Gets details about a translation
- `DeleteTranslation`: Deletes a translation
- `ListIterations`: Lists iterations for a translation

## Troubleshooting

### Authentication Issues

If you encounter authentication errors:
1. Ensure you're logged in with `az login`
2. Verify you have the correct roles assigned
3. Check that environment variables are set correctly

### Video Translation Errors

If translation fails:
1. Verify the video URL is accessible from Azure
2. Check that the target language locale is valid (e.g., `fr-FR`, not just `fr`)
3. Ensure your Video Translation service endpoint is correct

### Storage Issues

If blob upload fails:
1. Verify your storage account name and container name
2. Check that the container exists
3. Ensure you have `Storage Blob Data Contributor` role

## Additional Resources

- [Azure Video Translation Documentation](https://learn.microsoft.com/azure/ai-services/speech-service/video-translation-overview)
- [Azure Blob Storage Documentation](https://learn.microsoft.com/azure/storage/blobs/)
- [Microsoft Extensions AI Documentation](https://learn.microsoft.com/dotnet/ai/)
