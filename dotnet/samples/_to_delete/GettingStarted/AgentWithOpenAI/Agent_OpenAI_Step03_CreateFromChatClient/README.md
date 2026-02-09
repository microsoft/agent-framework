# Creating an Agent from a ChatClient

This sample demonstrates how to create an AI agent directly from an `OpenAI.Chat.ChatClient` instance using the `OpenAIChatClientAgent` class.

## What This Sample Shows

- **Direct ChatClient Creation**: Shows how to create an `OpenAI.Chat.ChatClient` from `OpenAI.OpenAIClient` and then use it to instantiate an agent
- **OpenAIChatClientAgent**: Demonstrates using the OpenAI SDK primitives instead of the ones from Microsoft.Extensions.AI and Microsoft.Agents.AI abstractions
- **Full Agent Capabilities**: Shows both regular and streaming invocation of the agent

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
