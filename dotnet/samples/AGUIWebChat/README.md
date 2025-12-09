# AGUI WebChat Sample

This sample demonstrates a Blazor-based web chat application using the AG-UI protocol to communicate with an AI agent server.

The sample consists of two projects:

1. **Server** - An ASP.NET Core server that hosts a simple chat agent using the AG-UI protocol
2. **Client** - A Blazor Server application with a rich chat UI for interacting with the agent

## Prerequisites

### Azure OpenAI Configuration

The server requires Azure OpenAI credentials. Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="your-deployment-name"  # e.g., "gpt-4o"
```

The server uses `DefaultAzureCredential` for authentication. Ensure you are logged in using one of the following methods:

- Azure CLI: `az login`
- Azure PowerShell: `Connect-AzAccount`
- Visual Studio or VS Code with Azure extensions
- Environment variables with service principal credentials

## Running the Sample

### Step 1: Start the Server

Open a terminal and navigate to the Server directory:

```powershell
cd Server
dotnet run
```

The server will start on `http://localhost:5100` and expose the AG-UI endpoint at `/ag-ui`.

### Step 2: Start the Client

Open a new terminal and navigate to the Client directory:

```powershell
cd Client
dotnet run
```

The client will start on `http://localhost:5000`. Open your browser and navigate to `http://localhost:5000` to access the chat interface.

### Step 3: Chat with the Agent

Type your message in the text box at the bottom of the page and press Enter or click the send button. The assistant will respond with streaming text that appears in real-time.

Features:
- **Streaming responses**: Watch the assistant's response appear word by word
- **Conversation suggestions**: The assistant may offer follow-up questions after responding
- **New chat**: Click the "New chat" button to start a fresh conversation
- **Auto-scrolling**: The chat automatically scrolls to show new messages

## How It Works

### Server (AG-UI Host)

The server (`Server/Program.cs`) creates a simple chat agent:

```csharp
// Create Azure OpenAI client
AzureOpenAIClient azureOpenAIClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential());

ChatClient chatClient = azureOpenAIClient.GetChatClient(deploymentName);

// Create AI agent
ChatClientAgent agent = chatClient.AsIChatClient().CreateAIAgent(
    name: "ChatAssistant",
    instructions: "You are a helpful assistant.");

// Map AG-UI endpoint
app.MapAGUI("/ag-ui", agent);
```

The server exposes the agent via the AG-UI protocol at `http://localhost:5100/ag-ui`.

### Client (Blazor Web App)

The client (`Client/Program.cs`) configures an `AGUIChatClient` to connect to the server:

```csharp
string serverUrl = builder.Configuration["SERVER_URL"] ?? "http://localhost:5100";

builder.Services.AddHttpClient("aguiserver", httpClient => httpClient.BaseAddress = new Uri(serverUrl));

builder.Services.AddChatClient(sp => new AGUIChatClient(
    sp.GetRequiredService<IHttpClientFactory>().CreateClient("aguiserver"), "ag-ui"));
```

The Blazor UI (`Client/Components/Pages/Chat/Chat.razor`) uses the `IChatClient` to:
- Send user messages to the agent
- Stream responses back in real-time
- Maintain conversation history
- Display messages with appropriate styling

### UI Components

The chat interface is built from several Blazor components:

- **Chat.razor** - Main chat page coordinating the conversation flow
- **ChatHeader.razor** - Header with "New chat" button
- **ChatMessageList.razor** - Scrollable list of messages with auto-scroll
- **ChatMessageItem.razor** - Individual message rendering (user vs assistant)
- **ChatInput.razor** - Text input with auto-resize and keyboard shortcuts
- **ChatSuggestions.razor** - AI-generated follow-up question suggestions
- **LoadingSpinner.razor** - Animated loading indicator during streaming

## Configuration

### Server Configuration

The server URL and port are configured in `Server/Properties/launchSettings.json`:

```json
{
  "profiles": {
    "http": {
      "applicationUrl": "http://localhost:5100"
    }
  }
}
```

### Client Configuration

The client connects to the server URL specified in `Client/Properties/launchSettings.json`:

```json
{
  "profiles": {
    "http": {
      "applicationUrl": "http://localhost:5000",
      "environmentVariables": {
        "SERVER_URL": "http://localhost:5100"
      }
    }
  }
}
```

To change the server URL, modify the `SERVER_URL` environment variable in the client's launch settings or provide it at runtime:

```powershell
$env:SERVER_URL="http://your-server:5100"
dotnet run
```

## Customization

### Changing the Agent Instructions

Edit the instructions in `Server/Program.cs`:

```csharp
ChatClientAgent agent = chatClient.AsIChatClient().CreateAIAgent(
    name: "ChatAssistant",
    instructions: "You are a helpful coding assistant specializing in C# and .NET.");
```

### Styling the UI

The chat interface uses CSS files colocated with each Razor component. Key styles:

- `wwwroot/app.css` - Global styles, buttons, color scheme
- `Components/Pages/Chat/Chat.razor.css` - Chat container layout
- `Components/Pages/Chat/ChatMessageItem.razor.css` - Message bubbles and icons
- `Components/Pages/Chat/ChatInput.razor.css` - Input box styling

### Disabling Suggestions

To disable the AI-generated follow-up suggestions, comment out the suggestions component in `Chat.razor`:

```razor
@* <ChatSuggestions OnSelected="@AddUserMessageAsync" @ref="@chatSuggestions" /> *@
```
