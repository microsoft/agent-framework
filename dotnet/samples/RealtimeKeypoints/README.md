# Realtime Transcription with Key Points and Q&A

This sample demonstrates how to use the **Agent Framework Workflows** to orchestrate multiple agents for real-time speech processing. The application captures speech from the microphone, transcribes it using Azure OpenAI GPT-Realtime, extracts key points, and answers questions—all running concurrently and independently.

## Architecture

The sample uses **concurrent independent executors** coordinated through shared memory to create three agents that process audio in parallel:

### Executors

- **TranscriptionExecutor** – Continuously captures PCM audio and streams to Azure OpenAI GPT-Realtime API. Stores final transcript segments to the shared `TranscriptMemoryStore`.

- **KeypointProcessorExecutor** – Polls the memory store every 3 seconds for new transcripts. Extracts key points using the Keypoint Agent and emits concise, deduplicated insights.

- **QuestionAnsweringExecutor** – Polls the memory store every 2 seconds for new transcripts. Detects questions and answers them in parallel background tasks with tool calling support.

### Concurrency Model

All three executors run concurrently via `Task.WhenAll`:

```csharp
var stubContext = new StubWorkflowContext();
var transcriptionTask = transcriptionExecutor.HandleAsync(new object(), stubContext, cancellationToken);
var keypointTask = keypointProcessorExecutor.HandleAsync(new object(), stubContext, cancellationToken);
var qaTask = questionAnsweringExecutor.HandleAsync(new object(), stubContext, cancellationToken);

await Task.WhenAll(transcriptionTask.AsTask(), keypointTask.AsTask(), qaTask.AsTask());
```

**Key Benefits:**

- ✅ **Independent Coordination** – Each executor runs independently and coordinates through shared memory
- ✅ **Asynchronous Processing** – All three agents execute concurrently without blocking each other
- ✅ **Shared State** – `TranscriptMemoryStore` is the single source of truth for transcripts
- ✅ **Scalability** – Easy to add more executors (e.g., Sentiment Analysis, Summarization) using the same pattern

### Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                      Task.WhenAll (Main)                        │
└─────────────────────────────────────────────────────────────────┘
         ↓                           ↓                       ↓
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Transcription    │    │ Keypoint         │    │ Question         │
│ Executor         │    │ Processor        │    │ Answering        │
│                  │    │ Executor         │    │ Executor         │
│ • Continuous     │    │ • Polls every 3s │    │ • Polls every 2s │
│   audio capture  │    │ • Detects new    │    │ • Detects new    │
│ • Streams to     │    │   transcripts    │    │   transcripts    │
│   GPT-Realtime   │    │ • Extracts       │    │ • Answers        │
│ • Stores in      │    │   keypoints      │    │   questions      │
│   memory         │    │ • Displays 💡    │    │ • Displays ❓❓💬 │
└──────────────────┘    └──────────────────┘    └──────────────────┘
         ↓                           ↓                       ↓
         └───────────────┬──────────────────┬────────────────┘
                         ↓
         ┌────────────────────────────────────┐
         │   TranscriptMemoryStore (Shared)   │
         │ • Circular buffer (5000 entries)   │
         │ • Deduplication via embeddings     │
         │ • Time-windowed queries            │
         └────────────────────────────────────┘
```

## Directory Structure

```text
RealtimeKeypoints/
├── Program.cs                           # Entry point with Workflow orchestration
├── Agents/                              # Individual agents
│   ├── RealtimeTranscriptionAgent.cs   # Captures audio and streams transcripts
│   ├── RealtimeKeypointAgent.cs        # Extracts key points from transcripts
│   └── RealtimeQuestionAnswerAgent.cs  # Detects and answers questions
├── Executors/                           # Workflow executors (NEW)
│   ├── TranscriptionExecutor.cs        # Wraps transcription in workflow executor
│   ├── KeypointProcessorExecutor.cs    # Wraps keypoint extraction in workflow executor
│   └── QuestionAnsweringExecutor.cs    # Wraps Q&A in workflow executor
├── Memory/                              # Shared state management
│   ├── TranscriptMemoryStore.cs        # In-memory transcript storage
│   └── InMemoryVectorStore.cs          # Vector storage for embeddings
├── Audio/                               # Audio processing
│   └── MicrophoneAudioSource.cs        # Microphone input via NAudio
└── Realtime/                            # Real-time API integration
    ├── AzureRealtimeClient.cs          # Azure GPT-Realtime client
    └── RealtimeTranscriptSegment.cs    # Transcript data model
```

## Prerequisites

- .NET 9 SDK (RC or later).
- An Azure OpenAI resource with:
  - A **realtime** deployment that supports `gpt-4o-realtime-preview` (or later) for audio transcription.
  - A **chat** deployment (for example `gpt-4o-mini`) that will be used to extract key points and answer questions.
- A working microphone on the machine running the sample.

> [!TIP]
> The realtime deployment must have the 2024-09-01-preview API enabled. You can re-use the same deployment name for both transcription and key point extraction by setting `AZURE_OPENAI_CHAT_DEPLOYMENT` to the realtime deployment name.

## Environment variables

Configure these environment variables before running the sample:

| Variable | Description |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Base endpoint for the Azure OpenAI resource (e.g. `https://contoso.openai.azure.com/`). |
| `AZURE_OPENAI_REALTIME_DEPLOYMENT` | Deployment name for the GPT-Realtime audio model. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Deployment name used for key point extraction. Optional – defaults to the realtime deployment. |

### PowerShell

```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://your-endpoint.openai.azure.com/"
$env:AZURE_OPENAI_REALTIME_DEPLOYMENT = "gpt-realtime"
$env:AZURE_OPENAI_CHAT_DEPLOYMENT = "gpt-4o-mini"
```

### Bash

```bash
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
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

## Execution Flow

### How Concurrent Execution Works

The three executors coordinate through the shared `TranscriptMemoryStore`:

1. **TranscriptionExecutor** (Primary)
   - Continuously captures audio and stores transcript segments to memory
   - Runs continuously without blocking
   - Updates to memory trigger polling in other executors

2. **KeypointProcessorExecutor** (Concurrent)
   - Polls memory store every 3 seconds for new transcripts
   - Tracks processed transcripts to avoid redundant processing
   - Sends unprocessed transcripts to Keypoint Agent
   - Extracts and displays key points

3. **QuestionAnsweringExecutor** (Concurrent)
   - Polls memory store every 2 seconds for new transcripts
   - Detects questions in transcript segments
   - Answers questions in parallel background tasks
   - Supports tool calling for extended capabilities

### Shared State Management

All executors read from and write to a single `TranscriptMemoryStore` instance that:
- Maintains a circular buffer of recent transcripts (5000 entries)
- Deduplicates transcripts using embeddings
- Provides time-windowed queries for context-aware processing

## Key Components

- `Executors/TranscriptionExecutor.cs` – Captures audio and stores transcripts
- `Executors/KeypointProcessorExecutor.cs` – Polls and extracts key points
- `Executors/QuestionAnsweringExecutor.cs` – Polls and answers questions
- `Agents/RealtimeTranscriptionAgent.cs` – Audio-to-text via GPT-Realtime
- `Agents/RealtimeKeypointAgent.cs` – Key point extraction from transcripts
- `Agents/RealtimeQuestionAnswerAgent.cs` – Question detection and answering
- `Memory/TranscriptMemoryStore.cs` – Shared in-memory transcript storage with deduplication
- `Audio/MicrophoneAudioSource.cs` – Microphone capture via NAudio
- `Realtime/AzureRealtimeClient.cs` – WebSocket client for GPT-Realtime API

## Customisation Ideas

- **Add more agents**: Use the Executor pattern to add new agents (Sentiment Analysis, Entity Extraction, Summarization) that poll the memory store independently
- **Adjust polling intervals**: Change the polling intervals in executors to optimize for your use case
- **Tune the keypoint system prompt**: Modify the system prompt in `RealtimeKeypointAgent` to focus on specific insight types
- **Implement real web search**: Replace the simulated `web_search` tool in `QuestionAnsweringExecutor` with a real API (Bing Search, Google Custom Search)
- **Change chat models**: Swap the chat deployment for a local or hosted model implementing `IChatClient`
- **Export results**: Push transcripts, key points, and Q&A to a UI, dashboard, or storage service
- **Customize memory store**: Replace `TranscriptMemoryStore` with a persistent database or vector store for longer retention

## Learning Resources

- [Azure OpenAI Service Documentation](https://learn.microsoft.com/azure/ai-services/openai/)
- [Azure OpenAI Chat Completions API](https://learn.microsoft.com/azure/ai-services/openai/reference)
- [GPT-4o Realtime Audio API Guide](https://learn.microsoft.com/azure/ai-services/openai/concepts/realtime-audio-sdk)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)

## Troubleshooting

- **No audio captured** – ensure that the application has microphone access and that the default input device matches your recording device.
- **401/403 errors** – verify the API key and deployment names, and confirm the key has access to both the realtime and chat deployments.
- **High latency** – reduce the commit interval in `AzureRealtimeClient` or lower the sampling rate in `MicrophoneAudioSource`.
- **Workflow not starting** – ensure the Workflows package is properly installed via the updated .csproj file.

## License

This sample is provided under the [MIT License](../../../LICENSE).
