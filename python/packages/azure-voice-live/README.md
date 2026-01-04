# Azure Voice Live Agent

Real-time voice conversation support for Microsoft Agent Framework using Azure Voice Live SDK.

## Features

- **Real-time Voice Streaming**: Bidirectional audio streaming with PCM16 @ 24kHz
- **Server-side VAD**: Automatic voice activity detection for natural turn-taking
- **Function Calling**: Tool invocation during voice conversations with automatic execution
- **Multi-Agent Support**: Voice agent can delegate complex queries to text-based agents
- **Interruption Support**: User can interrupt agent responses naturally
- **Audio + Text**: Support for voice input/output with automatic transcription
- **Web Integration**: WebSocket support for browser-based voice interfaces
- **Streaming Responses**: Stream audio and text transcripts in real-time

## Installation

```bash
pip install agent-framework-azure-voice-live
```

For web support:
```bash
pip install agent-framework-azure-voice-live[web]
```

## License

MIT License - Copyright (c) Microsoft Corporation

