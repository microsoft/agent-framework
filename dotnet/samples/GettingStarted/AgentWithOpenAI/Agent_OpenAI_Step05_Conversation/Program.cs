// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to maintain conversation state using the ChatClientAgent's
// server-side conversation storage. By creating a thread with a ConversationId, subsequent
// messages in the conversation will have access to the full conversation history without
// needing to send previous messages with each request.

using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Create a ChatClient directly from OpenAIClient
ChatClient chatClient = new OpenAIClient(apiKey).GetChatClient(model);

// Create an agent directly from the ChatClient using OpenAIChatClientAgent
OpenAIChatClientAgent agent = new(chatClient, instructions: "You are a helpful assistant.", name: "ConversationAgent");

// Create a thread for the conversation - this enables conversation state management
AgentThread thread = agent.GetNewThread();

Console.WriteLine("=== Multi-turn Conversation Demo ===\n");

// First turn: Ask about a topic
Console.WriteLine("User: What is the capital of France?");
UserChatMessage firstMessage = new("What is the capital of France?");
ChatCompletion firstResponse = await agent.RunAsync([firstMessage], thread);
Console.WriteLine($"Assistant: {firstResponse.Content.Last().Text}\n");

// Second turn: Follow-up question that relies on conversation context
Console.WriteLine("User: What famous landmarks are located there?");
UserChatMessage secondMessage = new("What famous landmarks are located there?");
ChatCompletion secondResponse = await agent.RunAsync([secondMessage], thread);
Console.WriteLine($"Assistant: {secondResponse.Content.Last().Text}\n");

// Third turn: Another follow-up that demonstrates context continuity
Console.WriteLine("User: How tall is the most famous one?");
UserChatMessage thirdMessage = new("How tall is the most famous one?");
ChatCompletion thirdResponse = await agent.RunAsync([thirdMessage], thread);
Console.WriteLine($"Assistant: {thirdResponse.Content.Last().Text}\n");

Console.WriteLine("=== End of Conversation ===");
