# Managing Conversation State with OpenAI

This sample demonstrates how to maintain conversation state across multiple turns using the Agent Framework with OpenAI's Conversation API.

## What This Sample Shows

- **Conversation State Management**: Shows how to use `ConversationClient` and `AgentThread` to maintain conversation context across multiple agent invocations
- **Multi-turn Conversations**: Demonstrates follow-up questions that rely on context from previous messages in the conversation
- **Server-Side Storage**: Uses OpenAI's Conversation API to manage conversation history server-side, allowing the model to access previous messages without resending them
- **Conversation Lifecycle**: Demonstrates creating, retrieving, and deleting conversations

## Key Concepts

### ConversationClient for Server-Side Storage

The `ConversationClient` manages conversations on OpenAI's servers:

```csharp
// Create a ConversationClient from OpenAIClient
OpenAIClient openAIClient = new(apiKey);
ConversationClient conversationClient = openAIClient.GetConversationClient();

// Create a new conversation
ClientResult createConversationResult = await conversationClient.CreateConversationAsync(BinaryContent.Create(BinaryData.FromString("{}")));
```

### AgentThread for Conversation State

The `AgentThread` works with `ChatClientAgentRunOptions` to link the agent to a server-side conversation:

```csharp
// Set up agent run options with the conversation ID
ChatClientAgentRunOptions agentRunOptions = new() { ChatOptions = new ChatOptions() { ConversationId = conversationId } };

// Create a thread for the conversation
AgentThread thread = agent.GetNewThread();

// First call links the thread to the conversation
ChatCompletion firstResponse = await agent.RunAsync([firstMessage], thread, agentRunOptions);

// Subsequent calls use the thread without needing to pass options again
ChatCompletion secondResponse = await agent.RunAsync([secondMessage], thread);
```

### Retrieving Conversation History

You can retrieve the full conversation history from the server:

```csharp
CollectionResult getConversationItemsResults = conversationClient.GetConversationItems(conversationId);
foreach (ClientResult result in getConversationItemsResults.GetRawPages())
{
    // Process conversation items
}
```

### How It Works

1. **Create an OpenAI Client**: Initialize an `OpenAIClient` with your API key
2. **Create a Conversation**: Use `ConversationClient` to create a server-side conversation
3. **Create an Agent**: Initialize an `OpenAIResponseClientAgent` with the desired model and instructions
4. **Create a Thread**: Call `agent.GetNewThread()` to create a new conversation thread
5. **Link Thread to Conversation**: Pass `ChatClientAgentRunOptions` with the `ConversationId` on the first call
6. **Send Messages**: Subsequent calls to `agent.RunAsync()` only need the thread - context is maintained
7. **Cleanup**: Delete the conversation when done using `conversationClient.DeleteConversation()`

## Running the Sample

1. Set the required environment variables:
   ```powershell
   $env:OPENAI_API_KEY = "your_api_key_here"
   $env:OPENAI_MODEL = "gpt-4o-mini"
   ```

2. Run the sample:
   ```powershell
   dotnet run
   ```

## Expected Output

The sample demonstrates a three-turn conversation where each follow-up question relies on context from previous messages:

1. First question asks about the capital of France
2. Second question asks about landmarks "there" - requiring understanding of the previous answer
3. Third question asks about "the most famous one" - requiring context from both previous turns

After the conversation, the sample retrieves and displays the full conversation history from the server, then cleans up by deleting the conversation.

This demonstrates that the conversation state is properly maintained across multiple agent invocations using OpenAI's server-side conversation storage.
