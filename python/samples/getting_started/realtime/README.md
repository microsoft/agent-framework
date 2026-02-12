# Realtime Voice Agent Samples

These samples demonstrate how to use the Agent Framework's realtime voice capabilities for bidirectional audio streaming with LLM providers.

## Overview

The realtime voice agents enable natural voice conversations with AI models through WebSocket connections. Key features include:

- **Bidirectional audio streaming**: Send and receive audio in real-time
- **Voice Activity Detection (VAD)**: Automatic detection of when the user starts/stops speaking
- **Function calling**: Tools work seamlessly during voice conversations
- **Multiple providers**: Support for OpenAI Realtime, Azure OpenAI Realtime, and Azure Voice Live

## Prerequisites

### Required Dependencies

```bash
pip install agent-framework-core websockets
```

### For Microphone Samples

```bash
pip install pyaudio
```

### For FastAPI WebSocket Sample

```bash
pip install fastapi uvicorn
```

On macOS, you may need to install PortAudio first:
```bash
brew install portaudio
```

### Environment Variables

**OpenAI:**
```bash
export OPENAI_API_KEY="your-openai-api-key"
```

**Azure OpenAI:**
```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME="gpt-realtime"
```

**Azure Voice Live:**
```bash
export AZURE_VOICELIVE_ENDPOINT="https://your-resource.services.ai.azure.com"
export AZURE_VOICELIVE_API_KEY="your-api-key"
export AZURE_VOICELIVE_MODEL="gpt-realtime"
```

## Samples

| Sample | Description |
|--------|-------------|
| `realtime_with_microphone.py` | Voice conversation using your microphone and speakers |
| `realtime_with_tools.py` | Voice conversation with function calling (weather, time, math) |
| `realtime_with_multiple_agents.py` | Multiple agents with transfer via `update_session()` — single connection reused across agents |
| `realtime_fastapi_websocket.py` | WebSocket API server for web browser clients |
| `websocket_audio_client.py` | CLI client that connects to the FastAPI WebSocket endpoint with microphone/speaker |
| `audio_utils.py` | Shared audio utilities (microphone capture, speaker playback) |

## Configuring the Client Type

All samples support three realtime providers. Configure via:

**CLI argument** (microphone and tools samples):
```bash
python realtime_with_microphone.py --client-type azure_openai
python realtime_with_tools.py --client-type azure_voice_live
```

**Environment variable** (all samples):
```bash
export REALTIME_CLIENT_TYPE="openai"  # or "azure_openai" or "azure_voice_live"
```

**FastAPI sample** (env var only, since it runs via uvicorn):
```bash
REALTIME_CLIENT_TYPE=azure_openai uvicorn realtime_fastapi_websocket:app --reload
```

The default client type is `"openai"`. Each client reads its required credentials from environment variables automatically.

## Audio Format

All realtime clients use PCM16 audio format by default:
- **Sample rate**: 24kHz (OpenAI/Azure OpenAI) or configurable (Voice Live)
- **Channels**: Mono (1 channel)
- **Bit depth**: 16-bit signed integers

## Event Types

The `RealtimeEvent` class normalizes events across providers:

| Event Type | Description |
|------------|-------------|
| `audio` | Audio chunk from the model |
| `transcript` | Text transcript of model's speech |
| `input_transcript` | Transcript of user's speech input |
| `tool_call` | Function call request |
| `tool_result` | Result of a function call execution |
| `listening` | VAD detected user speech started |
| `speaking_done` | Model finished speaking |
| `session_update` | Session created or configuration updated (e.g. via `update_session()`) |
| `error` | Error occurred |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Audio Input   │────▶│  RealtimeAgent   │────▶│  Audio Output   │
│  (Microphone)   │     │                  │     │   (Speaker)     │
└─────────────────┘     │  ┌────────────┐  │     └─────────────────┘
                        │  │   Tools    │  │
                        │  └────────────┘  │
                        │                  │
                        │  ┌────────────┐  │
                        │  │  Client    │  │
                        │  │ (WebSocket)│  │
                        │  └────────────┘  │
                        └──────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │  LLM Provider    │
                        │ (OpenAI/Azure)   │
                        └──────────────────┘
```
