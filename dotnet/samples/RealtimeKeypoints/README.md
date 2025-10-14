# Realtime Transcription with Key Points and Q&A

This sample demonstrates how to connect the Agent Framework to the Azure OpenAI GPT-Realtime audio API to capture speech from the default microphone, transcribe it in real time, extract concise key points, and answer questions detected in the conversation. Three agents work in parallel for low-latency, highly available processing:

- **RealtimeTranscriptionAgent** (Priority: HIGHEST) – captures PCM audio through NAudio, streams it to Azure OpenAI GPT-Realtime over WebSocket, and produces structured transcript segments using server-side Voice Activity Detection (VAD). This agent has the highest priority and must never be interrupted.
- **RealtimeKeypointAgent** – maintains a rolling transcript window with in-memory storage, calls a chat deployment for intelligent summarization, and emits newly discovered key points without repeating earlier ones.
- **RealtimeQuestionAnswerAgent** – monitors transcripts for questions, detects them using AI, and answers them with support for tool calling (e.g., web search for current information). Each question is processed in parallel to avoid blocking.

The `Program` entry point orchestrates parallel execution using channels with a broadcast pattern:

1. **Audio capture thread** – continuously streams microphone input to GPT-Realtime (zero interruption guaranteed)
2. **Broadcast thread** – distributes transcripts to multiple consumers without blocking
3. **Display and memory thread** – shows transcripts (yellow) and stores them in `TranscriptMemoryStore`
4. **Keypoint extraction thread** – processes transcript batches, extracts key points (green with 💡), leverages memory for context
5. **Q&A detection thread** – monitors for questions and answers them (magenta/cyan with ❓ and 💬), uses tool calling for web search

This architecture ensures zero interruption to audio capture while providing intelligent, batched keypoint extraction and real-time question answering with tool support.

## Prerequisites

- .NET 9 SDK (RC or later).
- An Azure OpenAI resource with:
  - A **realtime** deployment that supports `gpt-4o-realtime-preview` (or later) for audio transcription.
  - A **chat** deployment (for example `gpt-4o-mini`) that will be used to extract key points.
- An API key with access to both deployments.
- A working microphone on the machine running the sample.

> [!TIP]
> The realtime deployment must have the 2024-09-01-preview API enabled. You can re-use the same deployment name for both transcription and key point extraction by setting `AZURE_OPENAI_CHAT_DEPLOYMENT` to the realtime deployment name.

## Environment variables

Configure these environment variables before running the sample:

| Variable | Description |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Base endpoint for the Azure OpenAI resource (e.g. `https://contoso.openai.azure.com/`). |
| `AZURE_OPENAI_API_KEY` | API key authorised for both deployments. |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT` | Deployment name for the GPT-Realtime audio model. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Deployment name used for key point extraction. Optional – defaults to the realtime deployment. |

### PowerShell

```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://your-endpoint.openai.azure.com/"
$env:AZURE_OPENAI_API_KEY = "<your-api-key>"
$env:AZURE_OPENAI_REALTIME_DEPLOYMENT = "gpt-realtime"
$env:AZURE_OPENAI_CHAT_DEPLOYMENT = "gpt-4o-mini"
```

### Bash

```bash
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
export AZURE_OPENAI_API_KEY="<your-api-key>"
export AZURE_OPENAI_REALTIME_DEPLOYMENT="gpt-realtime"
export AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o-mini"
```

## Run the sample

Speak into your microphone. You'll see:

- **Yellow text**: Finalised transcript turns as they are received from the realtime session
- **Green text with 💡**: Key points extracted by the summarisation agent (decisions, action items, notable facts)
- **Magenta text with ❓**: Detected questions from your speech
- **Cyan text with 💬**: AI-generated answers to your questions (with tool calling support for web search)

Press Ctrl+C to stop the capture.

## Key components

- `Audio/MicrophoneAudioSource.cs` – wraps NAudio to expose microphone audio as a `Channel<byte[]>`.
- `Realtime/AzureRealtimeClient.cs` – low-level WebSocket client that handles GPT-Realtime session management, audio buffering, and response streaming.
- `Memory/TranscriptMemoryStore.cs` – in-memory store that deduplicates transcripts using GPT embeddings and cosine similarity.
- `Agents/RealtimeTranscriptionAgent.cs` – turns microphone audio into transcript segments consumable by other agents.
- `Agents/RealtimeKeypointAgent.cs` – maintains transcript context, calls a chat deployment via `IChatClient`, and filters out duplicate key points.
- `Agents/RealtimeQuestionAnswerAgent.cs` – monitors transcripts for questions, detects them using AI, and answers them with tool calling support (e.g., web_search).
- `Program.cs` – orchestrates all three agents and renders console output with a broadcast pattern.

## Customisation ideas

- Tune the audio commit interval in `AzureRealtimeClient` if you need more/less frequent transcription updates.
- Adjust the `RealtimeKeypointAgent` system prompt to focus on specific insight types (risks, questions, action items, etc.).
- Replace the simulated `web_search` tool in `RealtimeQuestionAnswerAgent` with a real web search API (e.g., Bing Search, Google Custom Search) for live web results.
- Swap the chat deployment for a local or hosted model that implements the `IChatClient` interface.
- Extend the console app to push transcripts, key points, and Q&A to a UI, dashboard, or storage service.
- Add additional agents that consume the transcript channel for other purposes (sentiment analysis, entity extraction, etc.).

## Troubleshooting

- **No audio captured** – ensure that the application has microphone access and that the default input device matches your recording device.
- **401/403 errors** – verify the API key and deployment names, and confirm the key has access to both the realtime and chat deployments.
- **High latency** – reduce the `commitInterval` passed to `AzureRealtimeClient` or lower the sampling rate in `MicrophoneAudioSource`.

## License

This sample is provided under the [MIT License](../../../LICENSE).
