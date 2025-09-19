// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add a basic custom memory component to an agent.
// The memory component subscribes to all messages added to the conversation and
// extracts the user's name and age if provided.
// The component adds a prompt to ask for this information if it is not already known
// and provides it to the model before each invocation if known.

using System;
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
using OpenAI.Chat;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

ChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName);

// Create the agent and provide a factory to add our custom memory component to
// all threads created by the agent. Here each new memory component will have its own
// user info object, so each thread will have its own memory.
// In real world applications/services, where the user info would be persisted in a database,
// and preferably shared between multiple threads used by the same user, ensure that the
// factory reads the user id from the current context and scopes the memory component
// and its storage to that user id.
AIAgent agent = chatClient.CreateAIAgent(new ChatClientAgentOptions()
{
    Instructions = "You are a friendly assistant. Always address the user by their name.",
    AIContextProviderFactory = ctx => new UserInfoMemory(chatClient.AsIChatClient(), ctx.SerializedState, ctx.JsonSerializerOptions)
});

// Create a new thread for the conversation.
AgentThread thread = agent.GetNewThread();

Console.WriteLine(">> Use thread with blank memory\n");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Hello, what is the square root of 9?", thread));
Console.WriteLine(await agent.RunAsync("My name is Ruaidhrí", thread));
Console.WriteLine(await agent.RunAsync("I am 20 years old", thread));

// We can serialize the thread. The serialized state will include the state of the memory component.
var threadElement = await thread.SerializeAsync();

Console.WriteLine("\n>> Use deserialized thread with previously created memories\n");

// Later we can deserialize the thread and continue the conversation with the previous memory component state.
var deserializedThread = agent.DeserializeThread(threadElement);
Console.WriteLine(await agent.RunAsync("What is my name and age?", deserializedThread));

Console.WriteLine("\n>> Read memories from memory component\n");

// It's possible to access the memory component via the thread's AIContextProvider property.
var userInfo = ((deserializedThread as ChatClientAgentThread)!.AIContextProvider as UserInfoMemory)!.UserInfo;

// Output the user info that was captured by the memory component.
Console.WriteLine($"MEMORY - User Name: {userInfo.UserName}");
Console.WriteLine($"MEMORY - User Age: {userInfo.UserAge}");

Console.WriteLine("\n>> Use new thread with previously created memories\n");

// It is also possible to set the memories in a memory component on an individual thread.
// This is useful if we want to start a new thread, but have it share the same memories as a previous thread.
// For this scenario, we have to know the underlying agent thread type and the memory component type.
var newThread = agent.GetNewThread();
((newThread as ChatClientAgentThread)!.AIContextProvider as UserInfoMemory)!.UserInfo = userInfo;

// Invoke the agent and output the text result.
// This time the agent should remember the user's name and use it in the response.
Console.WriteLine(await agent.RunAsync("What is my name and age?", newThread));

namespace SampleApp
{
    /// <summary>
    /// Sample memory component that can remember a user's name and age.
    /// </summary>
    internal sealed class UserInfoMemory : AIContextProvider
    {
        private readonly IChatClient _chatClient;

        public UserInfoMemory(IChatClient chatClient, UserInfo? userInfo = null)
        {
            this._chatClient = chatClient;
            this.UserInfo = userInfo ?? new UserInfo();
        }

        public UserInfoMemory(IChatClient chatClient, JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            this._chatClient = chatClient;

            this.UserInfo = serializedState.ValueKind == JsonValueKind.Object ?
                serializedState.Deserialize<UserInfo>(jsonSerializerOptions)! :
                new UserInfo();
        }

        public UserInfo UserInfo { get; set; }

        public override async ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            // Try and extract the user name and age from the message if we don't have it already and it's a user message.
            if ((this.UserInfo.UserName is null || this.UserInfo.UserAge is null) && context.RequestMessages.Any(x => x.Role == ChatRole.User))
            {
                var result = await this._chatClient.GetResponseAsync<UserInfo>(
                    context.RequestMessages,
                    new ChatOptions()
                    {
                        Instructions = "Extract the user's name and age from the message if present. If not present return nulls."
                    },
                    cancellationToken: cancellationToken);

                this.UserInfo.UserName ??= result.Result.UserName;
                this.UserInfo.UserAge ??= result.Result.UserAge;
            }
        }

        public override ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            StringBuilder instructions = new();

            // If we don't already know the user's name and age, add instructions to ask for them, otherwise just provide what we have to the context.
            instructions
                .AppendLine(
                    this.UserInfo.UserName is null ?
                        "Ask the user for their name and politely decline to answer any questions until they provide it." :
                        $"The user's name is {this.UserInfo.UserName}.")
                .AppendLine(
                    this.UserInfo.UserAge is null ?
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
            this.UserInfo = serializedState.Deserialize<UserInfo>(jsonSerializerOptions) ?? new UserInfo();
            return default;
        }
    }

    internal sealed class UserInfo
    {
        public string? UserName { get; set; }
        public int? UserAge { get; set; }
    }
}
