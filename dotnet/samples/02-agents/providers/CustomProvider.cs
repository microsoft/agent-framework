// Copyright (c) Microsoft. All rights reserved.

// Provider: Custom Implementation
// Build a fully custom agent by extending AIAgent.
// This example creates a parrot agent that echoes input in uppercase.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/providers

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using SampleApp;

// <use_custom_agent>
AIAgent agent = new UpperCaseParrotAgent();

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.Write(update);
}
Console.WriteLine();
// </use_custom_agent>

namespace SampleApp
{
    // <custom_agent>
    internal sealed class UpperCaseParrotAgent : AIAgent
    {
        public override string? Name => "UpperCaseParrotAgent";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new InMemoryAgentSession());

        protected override JsonElement SerializeSessionCore(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
            => JsonSerializer.SerializeToElement(new { });

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new InMemoryAgentSession());

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            List<ChatMessage> responseMessages = messages.Select(m =>
            {
                var clone = m.Clone();
                clone.Role = ChatRole.Assistant;
                clone.AuthorName = Name;
                clone.Contents = m.Contents.Select(c => c switch
                {
                    TextContent tc => new TextContent(tc.Text.ToUpperInvariant()),
                    _ => c
                }).ToList();
                return clone;
            }).ToList();

            return Task.FromResult(new AgentResponse
            {
                AgentId = Id,
                ResponseId = Guid.NewGuid().ToString("N"),
                Messages = responseMessages
            });
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var response = await RunCoreAsync(messages, session, options, cancellationToken);
            foreach (var message in response.Messages)
            {
                yield return new AgentResponseUpdate
                {
                    AgentId = Id,
                    AuthorName = message.AuthorName,
                    Role = ChatRole.Assistant,
                    Contents = message.Contents,
                    ResponseId = Guid.NewGuid().ToString("N"),
                    MessageId = Guid.NewGuid().ToString("N")
                };
            }
        }
    }
    // </custom_agent>
}
