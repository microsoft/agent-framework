// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Streams a single update carrying mixed content (text, reasoning, a function call, and an image URI) so the
/// channel's rich streaming SSE rendering can be exercised. No live model.
/// </summary>
internal sealed class MultimodalStreamAgent : AIAgent
{
    public const string Caption = "caption";
    public const string Reasoning = "thinking";
    public const string ToolName = "lookup";
    public const string ImageUrl = "https://example.com/cat.png";

    protected override string? IdCore => "multimodal-stream-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new MultimodalSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new MultimodalSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in this.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var contents = new List<AIContent>
        {
            new TextContent(Caption),
            new TextReasoningContent(Reasoning),
            new FunctionCallContent("call_1", ToolName, new Dictionary<string, object?> { ["city"] = "Seattle" }),
            new UriContent(ImageUrl, "image/png"),
        };
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = contents };
        await Task.Yield();
    }

    private sealed class MultimodalSession : AgentSession
    {
        public MultimodalSession()
        {
        }

        public MultimodalSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
