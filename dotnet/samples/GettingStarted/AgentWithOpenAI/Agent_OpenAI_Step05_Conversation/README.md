# Managing Conversation State with OpenAI

This sample demonstrates how to maintain conversation state across multiple turns using the Agent Framework with OpenAI.

## What This Sample Shows

- **Conversation State Management**: Shows how to create a thread that maintains conversation context across multiple agent invocations
- **Multi-turn Conversations**: Demonstrates follow-up questions that rely on context from previous messages in the conversation
- **Server-Side Storage**: Uses the agent's thread mechanism to manage conversation history, allowing the model to access previous messages without resending them

## Key Concepts

### AgentThread for Conversation State

The `AgentThread` is the primary mechanism for maintaining conversation state:

```csharp
// Create a thread for the conversation
AgentThread thread = agent.GetNewThread();

// Pass the thread to each agent invocation to maintain context
ChatCompletion response = await agent.RunAsync([message], thread);
```

When you pass the same thread to multiple invocations, the agent automatically maintains the conversation history, enabling the AI model to understand context from previous exchanges.

### How It Works

1. **Create an Agent**: Initialize an `OpenAIChatClientAgent` with the desired model and instructions
2. **Create a Thread**: Call `agent.GetNewThread()` to create a new conversation thread
3. **Send Messages**: Pass messages to `agent.RunAsync()` along with the thread
4. **Context is Maintained**: Subsequent messages automatically have access to the full conversation history

## Running the Sample

1. Set the required environment variables:
   ```bash
   set OPENAI_API_KEY=your_api_key_here
   set OPENAI_MODEL=gpt-4o-mini
   ```

2. Run the sample:
   ```bash
   dotnet run
   ```

## Expected Output

The sample demonstrates a three-turn conversation where each follow-up question relies on context from previous messages:

1. First question asks about the capital of France
2. Second question asks about landmarks "there" - requiring understanding of the previous answer
3. Third question asks about "the most famous one" - requiring context from both previous turns

This demonstrates that the conversation state is properly maintained across multiple agent invocations.
