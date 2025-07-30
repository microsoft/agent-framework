# OpenTelemetry Aspire Demo

This demo showcases the integration of OpenTelemetry with the Microsoft Agent Framework using .NET Aspire Dashboard for telemetry visualization.

## Overview

The demo consists of two main components:

1. **Aspire Dashboard** - Provides a web-based interface to visualize OpenTelemetry data
2. **Console Application** - An interactive console application that demonstrates agent interactions with proper OpenTelemetry instrumentation

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Console App   │───▶│  Agent Framework │───▶│  OpenAI/Azure   │
│  (Interactive)  │    │  with OpenTel    │    │     OpenAI      │
│                 │    │  Instrumentation │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Aspire Dashboard                             │
│              (OpenTelemetry Visualization)                      │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- .NET 9.0 SDK or later
- An OpenAI API key OR Azure OpenAI endpoint configured

## Configuration

### Option 1: OpenAI
Set the following environment variable:
```bash
$env:OPENAI_API_KEY="your-openai-api-key-here"
```

### Option 2: Azure OpenAI
Set the following environment variables:
```bash
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Running the Demo

### Quick Start (Using Script)

The easiest way to run the demo is using the provided PowerShell script:

```powershell
.\start-demo.ps1
```

This script will automatically:
- ✅ Check prerequisites (Docker, API keys)
- 🔨 Build the console application
- 🐳 Start the Aspire Dashboard via Docker (with anonymous access)
- ⏳ Wait for dashboard to be ready (polls port until listening)
- 🌐 Open your browser with the dashboard
- 📊 Configure telemetry endpoints (http://localhost:4318)
- 🎯 Start the interactive console application

### Manual Setup (Step by Step)

If you prefer to run the components manually:

#### Step 1: Start the Aspire Dashboard via Docker

```bash
docker run -d --name aspire-dashboard -p 4318:18888 -p 4317:18889 -e DOTNET_DASHBOARD_UNSECURED_ALLOW_ANONYMOUS=true mcr.microsoft.com/dotnet/aspire-dashboard:9.0
```

#### Step 2: Access the Dashboard

Open your browser to: http://localhost:4317

#### Step 3: Run the Console Application

```bash
cd dotnet/demos/AgentOpenTelemetry
$env:OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
dotnet run
```

#### Interacting with the Console Application

You should see a welcome message like:

```
=== OpenTelemetry Aspire Demo ===
This demo shows OpenTelemetry integration with the Agent Framework.
Each agent interaction will be wrapped in a telemetry span.
You can view the telemetry data in the Aspire Dashboard.

Make sure the Aspire Dashboard is running first!
Type your message and press Enter. Type 'exit' to quit.

You:
```

1. Type your message and press Enter to interact with the AI agent
2. The agent will respond, and you can continue the conversation
3. Type `exit` to stop the application

**Note**: Make sure the Aspire Dashboard is running before starting the console application, as the telemetry data will be sent to the dashboard.

#### Step 4: Test the Integration

1. **Start the Aspire Dashboard** (if not already running)
2. **Run the Console Application** in a separate terminal
3. **Send a test message** like "Hello, how are you?"
4. **Check the Aspire Dashboard** - you should see:
   - New traces appearing in the **Traces** tab
   - Each trace showing the complete agent interaction flow
   - Metrics in the **Metrics** tab showing token usage and duration
   - Logs in the **Structured Logs** tab with detailed information

## Viewing Telemetry Data

### Traces
1. In the Aspire Dashboard, navigate to the **Traces** tab
2. You'll see traces for each agent interaction
3. Each trace contains:
   - An outer span for the entire agent interaction
   - Inner spans from the Agent Framework's OpenTelemetry instrumentation
   - Spans from HTTP calls to OpenAI/Azure OpenAI

### Metrics
1. Navigate to the **Metrics** tab
2. View metrics related to:
   - Agent execution duration
   - Token usage (input/output tokens)
   - Request counts

### Logs
1. Navigate to the **Structured Logs** tab
2. Filter by the console application to see detailed logs
3. Logs include information about user inputs, agent responses, and any errors

## Key Features Demonstrated

### OpenTelemetry Integration
- **Automatic instrumentation** of Agent Framework operations
- **Custom spans** for user interactions
- **Proper span lifecycle management** (create → execute → close)
- **Telemetry correlation** across the entire request flow

### Agent Framework Features
- **ChatClientAgent** with OpenAI/Azure OpenAI integration
- **OpenTelemetry wrapper** using `.WithOpenTelemetry()`
- **Conversation threading** for multi-turn conversations
- **Error handling** with telemetry correlation

### Aspire Dashboard Features
- **Real-time telemetry visualization**
- **Distributed tracing** across services
- **Metrics and logging** integration
- **Resource management** and monitoring

## Available Script

The demo includes a PowerShell script to make running the demo easy:

### `start-demo.ps1`
Complete demo startup script that handles everything automatically.

**Usage:**
```powershell
.\start-demo.ps1           # Full demo startup
.\start-demo.ps1 -SkipBuild # Skip building projects
.\start-demo.ps1 -Help     # Show help information
```

**Features:**
- **Automatic API key detection** - Checks for OpenAI or Azure OpenAI configuration
- **Project building** - Automatically builds projects before running
- **Error handling** - Provides clear error messages if something goes wrong
- **Multi-window support** - Opens dashboard in separate window for better experience
- **Browser auto-launch** - Automatically opens the Aspire Dashboard in your browser
- **Hardcoded endpoints** - Uses reliable, fixed endpoints for demo consistency

**Hardcoded Endpoints:**
- **Aspire Dashboard**: `https://localhost:17054`
- **OTLP Telemetry**: `https://localhost:21244` (from launchSettings.json)

## Troubleshooting

### Port Conflicts
If you encounter port binding errors, try:
1. Change the port in `Properties/launchSettings.json`
2. Or kill any processes using the conflicting ports

### Authentication Issues
- Ensure your OpenAI API key or Azure OpenAI endpoint is correctly configured
- Check that the environment variables are set in the correct terminal session

### Build Issues
- Ensure you're using .NET 9.0 SDK
- Run `dotnet restore` if you encounter package restore issues
- Check that all project references are correctly resolved

## Project Structure

```
AspireOpenTelemetry/
├── OpenTelemetryAspire.AppHost/          # Aspire orchestration host
│   ├── AppHost.cs                        # Main orchestration configuration
│   └── Properties/launchSettings.json    # Launch profiles
├── OpenTelemetryAspire.ServiceDefaults/  # Shared service configuration
│   └── Extensions.cs                     # OpenTelemetry configuration
├── OpenTelemetryAspire.ConsoleApp/       # Console application
│   └── Program.cs                        # Main application with agent integration
└── README.md                             # This file
```

## Next Steps

- Experiment with different prompts to see various telemetry patterns
- Explore the Aspire Dashboard's filtering and search capabilities
- Try modifying the OpenTelemetry configuration to add custom metrics or spans
- Integrate additional services to see distributed tracing in action
