// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add a basic custom memory component to an agent.
// The memory component subscribes to all messages added to the conversation and
// extracts the user's name and age if provided.
// The component adds a prompt to ask for this information if it is not already known
// and provides it to the model before each invocation if known.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

OpenAI.Chat.ChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName);

// Create the agent and provide a factory to add our custom memory component to
// all threads created by the agent. Here we are using the same user info object for all threads, which
// means this agent instance shouldn't be used with multiple users or it will leak user info between them.
AIAgent agent = chatClient.CreateAIAgent(new ChatClientAgentOptions()
{
    Instructions = "You are a friendly assistant. Always address the user by their name.",
    AIContextProviderFactory = () => new SampleApp.UserInfoMemory(chatClient.AsIChatClient())
});

// Create a new thread for the conversation.
AgentThread thread = agent.GetNewThread();

// It is also possible to add the memory component to an individual thread only instead of
// via the factory above. This allows you to have different user info objects for different threads.
// thread.AIContextProvider = new SampleApp.UserInfoMemory(chatClient.AsIChatClient(), userInfo);

Console.WriteLine(">> Thread with blank memory\n");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Hello, what is the square root of 9?", thread));
Console.WriteLine(await agent.RunAsync("My name is Ruaidhrí", thread));
Console.WriteLine(await agent.RunAsync("I am 20 years old", thread));

// We can serialize the thread. The serialized state will include the state of the memory component.
var threadElement = await thread.SerializeAsync();

Console.WriteLine("\n>> Deserialized Thread with previously created memories\n");

// Later we can deserialize the thread and continue the conversation with the previous memory component state.
var deserializedThread = await agent.DeserializeThreadAsync(threadElement);
Console.WriteLine(await agent.RunAsync("What is my name and age?", deserializedThread));

Console.WriteLine("\n>> Memories from memory component\n");

// It's possible to access the memory component via the thread's AIContextProvider property.
var userInfo = ((UserInfoMemory)deserializedThread.AIContextProvider!).UserInfo;

// Output the user info that was captured by the memory component.
Console.WriteLine($"MEMORY - User Name: {userInfo.UserName}");
Console.WriteLine($"MEMORY - User Age: {userInfo.UserAge}");

Console.WriteLine("\n>> New Thread with previously created memories\n");

// Create a new thread.
thread = agent.GetNewThread();

// We can attach the same user info object to this thread, meaning that this thread shares the same memories as the previous thread.
((UserInfoMemory)thread.AIContextProvider!).UserInfo = userInfo;

// Invoke the agent and output the text result.
// This time the agent should remember the user's name and use it in the response.
Console.WriteLine(await agent.RunAsync("What is my name and age?", thread));

namespace SampleApp
{
    /// <summary>
    /// Sample memory component that can remember a user's name and age.
    /// </summary>
    internal sealed class UserInfoMemory(IChatClient chatClient, UserInfo? userInfo = null) : AIContextProvider
    {
        public UserInfo UserInfo { get; set; } = userInfo ?? new();

        public override async ValueTask MessagesAddingAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
        {
            // Try and extract the user name and age from the message if we don't have it already and it's a user message.
            if ((this.UserInfo.UserName == null || this.UserInfo.UserAge == null) && newMessages.Any(x => x.Role == ChatRole.User))
            {
                var result = await chatClient.GetResponseAsync<UserInfo>(
                    newMessages,
                    new ChatOptions()
                    {
                        Instructions = "Extract the user's name and age from the message if present. If not present return nulls."
                    },
                    cancellationToken: cancellationToken);

                this.UserInfo.UserName ??= result.Result.UserName;
                this.UserInfo.UserAge ??= result.Result.UserAge;
            }
        }

        public override ValueTask<AIContext> InvokingAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
        {
            StringBuilder instructions = new();

            // Add the user name and age to the instructions if we have them, otherwise ask for them.
            instructions.AppendLine(
                this.UserInfo.UserName == null ?
                "Ask the user for their name and politely decline to answer any questions until they provide it." :
                $"The user's name is {this.UserInfo.UserName}.");

            instructions.AppendLine(
                this.UserInfo.UserAge == null ?
                "Ask the user for their age and politely decline to answer any questions until they provide it." :
                $"The user's age is {this.UserInfo.UserAge}.");

            return new ValueTask<AIContext>(new AIContext
            {
                Instructions = instructions.ToString()
            });
        }

        public override ValueTask<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return new ValueTask<JsonElement?>(JsonSerializer.SerializeToElement(this.UserInfo, jsonSerializerOptions));
        }

        public override ValueTask DeserializeAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            this.UserInfo = JsonSerializer.Deserialize<UserInfo>(serializedState, jsonSerializerOptions) ?? new UserInfo();
            return default;
        }
    }

    internal sealed class UserInfo
    {
        public string? UserName { get; set; }
        public int? UserAge { get; set; }
    }
}
