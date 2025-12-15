// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to maintain conversation state using the OpenAIResponseClientAgent
// and AgentThread. By passing the same thread to multiple agent invocations, the agent
// automatically maintains the conversation history, allowing the AI model to understand
// context from previous exchanges.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;
using OpenAI.Conversations;

string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Create a ConversationClient directly from OpenAIClient
OpenAIClient openAIClient = new(apiKey);
ConversationClient conversationClient = openAIClient.GetConversationClient();

// Create an agent directly from the OpenAIResponseClient using OpenAIResponseClientAgent
ChatClientAgent agent = new(openAIClient.GetOpenAIResponseClient(model).AsIChatClient(), instructions: "You are a helpful assistant.", name: "ConversationAgent");

ClientResult createConversationResult = await conversationClient.CreateConversationAsync(BinaryContent.Create(BinaryData.FromString("{}")));

using JsonDocument createConversationResultAsJson = JsonDocument.Parse(createConversationResult.GetRawResponse().Content.ToString());
string conversationId = createConversationResultAsJson.RootElement.GetProperty("id"u8)!.GetString()!;

// Create a thread for the conversation - this enables conversation state management for subsequent turns
AgentThread thread = agent.GetNewThread(conversationId);

Console.WriteLine("=== Multi-turn Conversation Demo ===\n");

// First turn: Ask about a topic
Console.WriteLine("User: What is the capital of France?");
UserChatMessage firstMessage = new("What is the capital of France?");

// After this call, the conversation state associated in the options is stored in 'thread' and used in subsequent calls
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

// Show full conversation history
Console.WriteLine("Full Conversation History:");
ClientResult getConversationResult = await conversationClient.GetConversationAsync(conversationId);

Console.WriteLine("Conversation created.");
Console.WriteLine($"    Conversation ID: {conversationId}");
Console.WriteLine();

CollectionResult getConversationItemsResults = conversationClient.GetConversationItems(conversationId);
foreach (ClientResult result in getConversationItemsResults.GetRawPages())
{
    Console.WriteLine("Message contents retrieved. Order is most recent first by default.");
    using JsonDocument getConversationItemsResultAsJson = JsonDocument.Parse(result.GetRawResponse().Content.ToString());
    foreach (JsonElement element in getConversationItemsResultAsJson.RootElement.GetProperty("data").EnumerateArray())
    {
        string messageId = element.GetProperty("id"u8).ToString();
        string messageRole = element.GetProperty("role"u8).ToString();
        Console.WriteLine($"    Message ID: {messageId}");
        Console.WriteLine($"    Message Role: {messageRole}");

        foreach (var content in element.GetProperty("content").EnumerateArray())
        {
            string messageContentText = content.GetProperty("text"u8).ToString();
            Console.WriteLine($"    Message Text: {messageContentText}");
        }
        Console.WriteLine();
    }
}

ClientResult deleteConversationResult = conversationClient.DeleteConversation(conversationId);
using JsonDocument deleteConversationResultAsJson = JsonDocument.Parse(deleteConversationResult.GetRawResponse().Content.ToString());
bool deleted = deleteConversationResultAsJson.RootElement
    .GetProperty("deleted"u8)
    .GetBoolean();

Console.WriteLine("Conversation deleted.");
Console.WriteLine($"    Deleted: {deleted}");
Console.WriteLine();
