# Azure AI Video Translation Agent

This sample demonstrates how to build an AI agent that helps users translate videos from one language to another using Azure AI Speech's Video Translation services. The agent handles video uploads, long-running translation operations, and status monitoring with a conversational interface.

## Files

| File | Description |
|------|-------------|
| [`agent.py`](agent/src/azure_ai_video_translation.py) | Main agent implementation with video translation tools including upload, download, translation, and status checking functionality. Demonstrates long-running operation handling with pull-based status updates. |
| [`video_translation_client.py`](agent/src/video_translation_client.py) | API client for Azure Video Translation service with methods for creating, listing, and managing translations. |
| [`video_translation_dataclass.py`](agent/src/video_translation_dataclass.py) | Data models for API request and response structures. |
| [`video_translation_enum.py`](agent/src/video_translation_enum.py) | Enumerations for voice kinds, WebVTT file types, and translation status values. |
| [`video_translation_util.py`](agent/src/video_translation_util.py) | Utility functions for API interactions and data processing. |

## Environment Variables

Make sure to set the following environment variables before running the example:

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your Azure AI model deployment (e.g., `gpt-4`)
- `COGNITIVE_SERVICES_ENDPOINT`: Your Azure Cognitive Services endpoint for video translation
- `AZURE_STORAGE_ACCOUNT_NAME`: Your Azure Storage account name (for uploading video files)

You can set these in a `.env` file in the `agent/src` directory (copy from `.env.sample`).

## Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the example, or replace `AzureCliCredential` with your preferred authentication method.

## Additional Resources

For more information about Azure Video Translation and related services, see:
- [Azure Video Translation Overview](https://learn.microsoft.com/azure/ai-services/speech-service/video-translation-overview)
- [Azure Video Translation Language Support](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=video-translation)