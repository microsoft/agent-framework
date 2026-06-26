// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Agent that returns a single assistant message carrying mixed content — reasoning, a function call, a
/// function result, and final text — so the channel's rich output-item rendering can be exercised.
/// </summary>
internal sealed class RichContentAgent : AIAgent
{
    public const string ReasoningText = "thinking about it";
    public const string CallId = "call_1";
    public const string ToolName = "get_weather";
    public const string FinalText = "It is sunny.";

    protected override string? IdCore => "rich-agent";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new RichSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(new RichSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(JsonSerializer.SerializeToElement(new { }));

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var content = new List<AIContent>
        {
            new TextReasoningContent(ReasoningText),
            new FunctionCallContent(CallId, ToolName, new Dictionary<string, object?> { ["city"] = "Seattle" }),
            new FunctionResultContent(CallId, "sunny in Seattle"),
            new TextContent(FinalText),
        };
        return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, content)));
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new AgentResponseUpdate { Role = ChatRole.Assistant, Contents = [new TextContent(FinalText)] };
        await Task.Yield();
    }

    private sealed class RichSession : AgentSession
    {
        public RichSession()
        {
        }

        public RichSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
