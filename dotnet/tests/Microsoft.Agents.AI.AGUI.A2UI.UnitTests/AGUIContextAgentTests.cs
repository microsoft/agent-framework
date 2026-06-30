// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.A2UI.UnitTests;

/// <summary>
/// Unit tests for <see cref="AGUIContextAgent"/>: forwarded AG-UI context entries are
/// surfaced to the model as a leading system message, with the catalog schema entry
/// routed into the canonical <c>## Available Components</c> section.
/// </summary>
public sealed class AGUIContextAgentTests
{
    [Fact]
    public async Task RunAsync_WithForwardedContext_PrependsSystemMessageAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new AGUIContextAgent(inner);
        var options = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["ag_ui_context"] = new[]
                    {
                        new KeyValuePair<string, string>(A2UIConstants.A2UISchemaContextDescription, "{\"components\":{}}"),
                        new KeyValuePair<string, string>("Style guide", "use cards"),
                    },
                },
            },
        };

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], options: options);

        // Assert: one system message prepended, carrying both the canonical schema
        // section and the plain context section.
        Assert.NotNull(inner.LastMessages);
        Assert.Equal(2, inner.LastMessages!.Count);
        ChatMessage system = inner.LastMessages[0];
        Assert.Equal(ChatRole.System, system.Role);
        Assert.Contains("## Available Components", system.Text);
        Assert.Contains("{\"components\":{}}", system.Text);
        Assert.Contains("## Style guide", system.Text);
        Assert.Contains("use cards", system.Text);
        Assert.Equal(ChatRole.User, inner.LastMessages[1].Role);
    }

    [Fact]
    public async Task RunAsync_WithoutForwardedContext_PassesMessagesThroughAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new AGUIContextAgent(inner);
        var userMessage = new ChatMessage(ChatRole.User, "hi");

        // Act
        await agent.RunAsync([userMessage]);

        // Assert: untouched — same single message instance, no system prefix.
        Assert.NotNull(inner.LastMessages);
        ChatMessage only = Assert.Single(inner.LastMessages!);
        Assert.Same(userMessage, only);
    }

    [Fact]
    public async Task RunAsync_WithEmptyContextEntries_DoesNotPrependAsync()
    {
        // Arrange: entries that render to an empty prompt must not produce an
        // empty system message.
        var inner = new RecordingAgent();
        var agent = new AGUIContextAgent(inner);
        var options = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions
            {
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["ag_ui_context"] = Array.Empty<KeyValuePair<string, string>>(),
                },
            },
        };

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], options: options);

        // Assert
        Assert.NotNull(inner.LastMessages);
        ChatMessage only = Assert.Single(inner.LastMessages!);
        Assert.Equal(ChatRole.User, only.Role);
    }

    /// <summary>An inner agent that records the messages it was run with.</summary>
    private sealed class RecordingAgent : AIAgent
    {
        public List<ChatMessage>? LastMessages { get; private set; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.LastMessages = messages.ToList();
            return Task.FromResult(new AgentResponse());
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.LastMessages = messages.ToList();
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }
    }
}
