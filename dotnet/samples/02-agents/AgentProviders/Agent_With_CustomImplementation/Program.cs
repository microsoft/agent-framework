// Copyright (c) Microsoft. All rights reserved.

// This sample shows all the required steps to create a fully custom agent implementation.
// In this case the agent doesn't use AI at all, and simply parrots back the user input in upper case.
// You can however, build a fully custom agent that uses AI in any way you want.

using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
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

        public readonly ChatHistoryProvider ChatHistoryProvider = new InMemoryChatHistoryProvider();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new CustomAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            if (session is not CustomAgentSession typedSession)
            {
                throw new ArgumentException($"The provided session is not of type {nameof(CustomAgentSession)}.", nameof(session));
            }

            return new(JsonSerializer.SerializeToElement(typedSession, jsonSerializerOptions));
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(serializedState.Deserialize<CustomAgentSession>(jsonSerializerOptions)!);

        protected override async Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            // Create a session if the user didn't supply one.
            session ??= await this.CreateSessionAsync(cancellationToken);

            if (session is not CustomAgentSession typedSession)
            {
                throw new ArgumentException($"The provided session is not of type {nameof(CustomAgentSession)}.", nameof(session));
            }

            // Get existing messages from the store
            var invokingContext = new ChatHistoryProvider.InvokingContext(this, session, messages);
            var userAndChatHistoryMessages = await this.ChatHistoryProvider.InvokingAsync(invokingContext, cancellationToken);

            // Clone the input messages and turn them into response messages with upper case text.
            List<ChatMessage> responseMessages = CloneAndToUpperCase(messages, this.Name).ToList();

            // Notify the session of the input and output messages.
            var invokedContext = new ChatHistoryProvider.InvokedContext(this, session, userAndChatHistoryMessages, responseMessages);
            await this.ChatHistoryProvider.InvokedAsync(invokedContext, cancellationToken);

            return new AgentResponse
            {
                AgentId = this.Id,
                ResponseId = Guid.NewGuid().ToString("N"),
                Messages = responseMessages
            };
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            // Create a session if the user didn't supply one.
            session ??= await this.CreateSessionAsync(cancellationToken);

            if (session is not CustomAgentSession typedSession)
            {
                throw new ArgumentException($"The provided session is not of type {nameof(CustomAgentSession)}.", nameof(session));
            }

            // Get existing messages from the store
            var invokingContext = new ChatHistoryProvider.InvokingContext(this, session, messages);
            var userAndChatHistoryMessages = await this.ChatHistoryProvider.InvokingAsync(invokingContext, cancellationToken);

            // Clone the input messages and turn them into response messages with upper case text.
            List<ChatMessage> responseMessages = CloneAndToUpperCase(messages, this.Name).ToList();

            // Notify the session of the input and output messages.
            var invokedContext = new ChatHistoryProvider.InvokedContext(this, session, userAndChatHistoryMessages, responseMessages);
            await this.ChatHistoryProvider.InvokedAsync(invokedContext, cancellationToken);

            foreach (var message in responseMessages)
            {
                yield return new AgentResponseUpdate
                {
                    AgentId = this.Id,
                    AuthorName = message.AuthorName,
                    Role = ChatRole.Assistant,
                    Contents = message.Contents,
                    ResponseId = Guid.NewGuid().ToString("N"),
                    MessageId = Guid.NewGuid().ToString("N")
                };
            }
        }

        private static IEnumerable<ChatMessage> CloneAndToUpperCase(IEnumerable<ChatMessage> messages, string? agentName) => messages.Select(x =>
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
        /// A session type for our custom agent that only supports in memory storage of messages.
        /// </summary>
        internal sealed class CustomAgentSession : AgentSession
        {
            internal CustomAgentSession()
            {
            }

            [JsonConstructor]
            internal CustomAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
            {
            }
        }
    }
}
