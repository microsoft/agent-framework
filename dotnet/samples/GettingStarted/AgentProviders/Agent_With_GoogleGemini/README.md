# Creating an AIAgent with Google Gemini

This sample demonstrates how to create an AIAgent using Google Gemini models as the underlying inference service.

The sample showcases two different `IChatClient` implementations:

1. **Google GenAI** - Using the official [Google.GenAI](https://www.nuget.org/packages/Google.GenAI) package
2. **Mscc.GenerativeAI.Microsoft** - Using the community-driven [Mscc.GenerativeAI.Microsoft](https://www.nuget.org/packages/Mscc.GenerativeAI.Microsoft) package

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- Google AI Studio API key (get one at [Google AI Studio](https://aistudio.google.com/apikey))

Set the following environment variables:

```powershell
$env:GOOGLE_GENAI_API_KEY="your-google-api-key"  # Replace with your Google AI Studio API key
$env:GOOGLE_GENAI_MODEL="gemini-2.5-fast"  # Optional, defaults to gemini-2.5-fast
```

## Package Options

### Google GenAI (Official)

The official Google GenAI package provides direct access to Google's Generative AI models. This sample uses an extension method to convert the Google client to an `IChatClient`.

> [!NOTE]
> Until PR [googleapis/dotnet-genai#81](https://github.com/googleapis/dotnet-genai/pull/81) is merged, this option requires the additional `GeminiChatClient.cs` and `GoogleGenAIExtensions.cs` files included in this sample.
>
> We appreciate any community push by liking and commenting in the above PR to get it merged and release as part of official Google GenAI package.

### Mscc.GenerativeAI.Microsoft (Community)

The community-driven Mscc.GenerativeAI.Microsoft package provides a ready-to-use `IChatClient` implementation for Google Gemini models through the `GeminiChatClient` class.
