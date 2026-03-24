# Agent Implementation Guide

## What Was Implemented

### 1. ChatAgent Service with CosmosHistoryProvider (`services/agent_service.py`)

Created a new service module that:
- Initializes a singleton `ChatAgent` instance
- Configures `CosmosHistoryProvider` for automatic conversation persistence
- Configures Azure OpenAI client with Azure AD authentication
- Registers 5 tools: `get_weather`, `calculate`, `search_knowledge_base`, `search_microsoft_docs`, `search_microsoft_code_samples`
- Defines system instructions for the agent

**Key Features:**
```python
from agent_framework_azure_cosmos import CosmosHistoryProvider

# History provider automatically loads/stores conversation history
history_provider = CosmosHistoryProvider(
    source_id="enterprise_chat_agent",
    endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
    database_name="chat_db",
    container_name="messages",
    credential=DefaultAzureCredential(),
    load_messages=True,   # Auto-load history before each run
    store_inputs=True,    # Auto-store user messages
    store_outputs=True,   # Auto-store assistant responses
)

# Agent uses history provider as context provider
agent = ChatAgent(
    chat_client=client,
    instructions="You are a helpful enterprise chat assistant...",
    tools=[get_weather, calculate, search_knowledge_base, ...],
    context_providers=[history_provider],  # Auto-persist history!
    name="EnterpriseAssistant",
)
```

### 2. Tool Updates

All tools use the `@ai_function` decorator:

```python
from agent_framework.ai import ai_function

@ai_function
def get_weather(location: str) -> dict:
    """Get current weather for a location."""
    ...

@ai_function
def search_microsoft_docs(query: str) -> list[dict]:
    """Search official Microsoft documentation."""
    ...
```

This decorator enables the agent to:
- Discover and call tools automatically
- Generate proper function call schemas
- Handle tool execution and response parsing

### 3. Simplified Message Route (`routes/messages.py`)

**Before (Manual storage):**
```python
# Store user message manually
await store.add_message(thread_id, user_message_id, "user", content)

# Load history manually
message_history = await store.get_messages(thread_id)
chat_messages = convert_messages_to_chat_messages(message_history)

# Run agent
response = await agent.run(chat_messages)

# Store response manually
await store.add_message(thread_id, assistant_message_id, "assistant", response.content)
```

**After (With CosmosHistoryProvider):**
```python
# Get agent (configured with CosmosHistoryProvider)
agent = get_agent()

# Run agent - history is loaded and stored automatically!
response = await agent.run(content, session_id=thread_id)
```

The `CosmosHistoryProvider` handles all message persistence automatically:
- Loads conversation history before each `agent.run()`
- Stores user input after each run
- Stores assistant response after each run
- Uses `session_id` as the Cosmos DB partition key

## How It Works

### Flow Diagram

```
User Request
    ↓
POST /api/threads/{thread_id}/messages
    ↓
1. Validate thread exists
    ↓
2. agent.run(content, session_id=thread_id)
    ↓
   ┌─────────────────────────────────────────┐
   │  CosmosHistoryProvider (automatic):     │
   │  • Load previous messages from Cosmos   │
   │  • Add to agent context                 │
   └─────────────────────────────────────────┘
    ↓
3. Agent analyzes context and decides tools
    ↓
4. Agent automatically calls tools as needed:
   - get_weather("Seattle")
   - calculate("85 * 0.15")
   - search_microsoft_docs("Azure Functions")
    ↓
   ┌─────────────────────────────────────────┐
   │  CosmosHistoryProvider (automatic):     │
   │  • Store user message to Cosmos         │
   │  • Store assistant response to Cosmos   │
   └─────────────────────────────────────────┘
    ↓
5. Return response to user
```

### Example Interactions

**Weather Query:**
```
User: "What's the weather in Tokyo?"
→ Agent calls: get_weather("Tokyo")
→ Response: "The weather in Tokyo is 72°F with partly cloudy conditions."
```

**Multi-tool Query:**
```
User: "What's the weather in Paris and what's 18% tip on €75?"
→ Agent calls: get_weather("Paris") AND calculate("75 * 0.18")
→ Response: "The weather in Paris is 65°F with light rain. An 18% tip on €75 is €13.50."
```

**Microsoft Docs Query:**
```
User: "How do I deploy Azure Functions with Python?"
→ Agent calls: search_microsoft_docs("Azure Functions Python deployment")
→ Response: "To deploy Azure Functions with Python, you can use..."
```

**No Tools Needed:**
```
User: "Tell me a joke"
→ Agent responds directly (no tools called)
→ Response: "Why did the programmer quit? Because they didn't get arrays!"
```

## Environment Variables Required

Make sure your `local.settings.json` includes:

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_MODEL": "gpt-4o",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
    "AZURE_COSMOS_ENDPOINT": "https://your-cosmos.documents.azure.com:443/",
    "AZURE_COSMOS_DATABASE_NAME": "chat_db",
    "AZURE_COSMOS_CONTAINER_NAME": "messages",
    "AZURE_COSMOS_THREADS_CONTAINER_NAME": "threads"
  }
}
```

**Note:** Two containers are used:
- `AZURE_COSMOS_CONTAINER_NAME` - Messages (managed by `CosmosHistoryProvider`)
- `AZURE_COSMOS_THREADS_CONTAINER_NAME` - Thread metadata (managed by `CosmosConversationStore`)

## Next Steps

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Start the function app
func start

# Test with demo.http or curl
curl -X POST http://localhost:7071/api/threads
curl -X POST http://localhost:7071/api/threads/{thread_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "What is the weather in Seattle?"}'
```

### Deploy to Azure
```bash
azd auth login
azd up
```

## Key Benefits of This Implementation

1. **Intelligent Tool Selection**: The LLM decides which tools to use based on context
2. **Multi-tool Coordination**: Can call multiple tools in one response
3. **Automatic History Persistence**: `CosmosHistoryProvider` handles message storage automatically
4. **Simplified Code**: No manual message load/store - just `agent.run(content, session_id=...)`
5. **Production Ready**: Includes error handling, observability, and security
6. **Scalable**: Serverless Azure Functions with serverless Cosmos DB
7. **Observable**: OpenTelemetry spans for all operations

## Architecture Pattern

This implementation demonstrates the **Agent with Tools** pattern:
- Single AI agent (not a workflow)
- Dynamic tool selection by LLM
- Suitable for chat-based RAG applications
- Simple, maintainable, and efficient

For complex multi-agent orchestration, consider using [Microsoft Agent Framework Workflows](https://learn.microsoft.com/agent-framework/user-guide/workflows/overview).
