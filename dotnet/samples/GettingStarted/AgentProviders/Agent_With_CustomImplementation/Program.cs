// Copyright (c) Microsoft. All rights reserved.

// This sample shows all the required steps to create a fully custom agent implementation.
// In this case the agent doesn't use AI at all, and simply parrots back the user input in upper case.
// You can however, build a fully custom agent that uses AI in any way you want.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using SampleApp;

AIAgent agent = new UpperCaseParrotAgent();

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}

namespace SampleApp
{
    // Custom agent that parrot's the user input back in upper case.
    internal sealed class UpperCaseParrotAgent : AIAgent
    {
        public override string? Name => "UpperCaseParrotAgent";

        public override AgentThread GetNewThread()
            => new CustomAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new CustomAgentThread(serializedThread, jsonSerializerOptions);

        public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            // Create a thread if the user didn't supply one.
            thread ??= this.GetNewThread();

            if (thread is not CustomAgentThread typedThread)
            {
                throw new ArgumentException($"The provided thread is not of type {nameof(CustomAgentThread)}.", nameof(thread));
            }

            // Clone the input messages and turn them into response messages with upper case text.
            List<ChatMessage> responseMessages = CloneAndToUpperCase(messages, this.DisplayName).ToList();

            // Notify the thread of the input and output messages.
            await typedThread.MessageStore.AddMessagesAsync(messages.Concat(responseMessages), cancellationToken);

            return new AgentRunResponse
            {
                AgentId = this.Id,
                ResponseId = Guid.NewGuid().ToString("N"),
                Messages = responseMessages
            };
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            // Create a thread if the user didn't supply one.
            thread ??= this.GetNewThread();

            if (thread is not CustomAgentThread typedThread)
            {
                throw new ArgumentException($"The provided thread is not of type {nameof(CustomAgentThread)}.", nameof(thread));
            }

            // Clone the input messages and turn them into response messages with upper case text.
            List<ChatMessage> responseMessages = CloneAndToUpperCase(messages, this.DisplayName).ToList();

            // Notify the thread of the input and output messages.
            await typedThread.MessageStore.AddMessagesAsync(messages.Concat(responseMessages), cancellationToken);

            foreach (var message in responseMessages)
            {
                yield return new AgentRunResponseUpdate
                {
                    AgentId = this.Id,
                    AuthorName = this.DisplayName,
                    Role = ChatRole.Assistant,
                    Contents = message.Contents,
                    ResponseId = Guid.NewGuid().ToString("N"),
                    MessageId = Guid.NewGuid().ToString("N")
                };
            }
        }

        private static IEnumerable<ChatMessage> CloneAndToUpperCase(IEnumerable<ChatMessage> messages, string agentName) => messages.Select(x =>
            {
                // Clone the message and update its author to be the agent.
                var messageClone = x.Clone();
                messageClone.Role = ChatRole.Assistant;
                messageClone.MessageId = Guid.NewGuid().ToString("N");
                messageClone.AuthorName = agentName;

                // Clone and convert any text content to upper case.
                messageClone.Contents = x.Contents.Select(c => c switch
                {
                    TextContent tc => new TextContent(tc.Text.ToUpperInvariant())
                    {
                        AdditionalProperties = tc.AdditionalProperties,
                        Annotations = tc.Annotations,
                        RawRepresentation = tc.RawRepresentation
                    },
                    _ => c
                }).ToList();

                return messageClone;
            });

        /// <summary>
        /// A thread type for our custom agent that only supports in memory storage of messages.
        /// </summary>
        internal sealed class CustomAgentThread : InMemoryAgentThread
        {
            internal CustomAgentThread() { }

            internal CustomAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
                : base(serializedThreadState, jsonSerializerOptions) { }
        }
    }
}
