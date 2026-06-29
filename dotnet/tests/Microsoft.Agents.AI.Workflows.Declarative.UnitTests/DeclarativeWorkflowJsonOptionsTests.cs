// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

public sealed partial class DeclarativeWorkflowJsonOptionsTests(ITestOutputHelper output)
    : WorkflowTest(output)
{
    [Theory]
    [InlineData(typeof(ActionExecutorResult))]
    [InlineData(typeof(ExternalInputRequest))]
    [InlineData(typeof(ExternalInputResponse))]
    [InlineData(typeof(UnassignedValue))]
    [InlineData(typeof(List<string>))]
    // Internal approval-snapshot types: catches source-gen regressions from rename/move of the nested types.
    [InlineData(typeof(InvokeFunctionToolExecutor.ApprovalSnapshot))]
    [InlineData(typeof(Dictionary<string, InvokeFunctionToolExecutor.ApprovalSnapshot>))]
    [InlineData(typeof(InvokeMcpToolExecutor.ApprovalSnapshot))]
    [InlineData(typeof(Dictionary<string, InvokeMcpToolExecutor.ApprovalSnapshot>))]
    public void DefaultOptions_HasTypeInfoForRegisteredType(Type type)
    {
        Assert.True(
            DeclarativeWorkflowJsonOptions.Default.TryGetTypeInfo(type, out _),
            $"Default should resolve JsonTypeInfo for {type.FullName}.");
    }

    [Fact]
    public void ActionExecutorResult_RoundTrip_NullResult()
    {
        ActionExecutorResult copy = RoundTrip(new ActionExecutorResult("exec-1"));

        Assert.Equal("exec-1", copy.ExecutorId);
        Assert.Null(copy.Result);
    }

    [Fact]
    public void ExternalInputRequest_RoundTrip_WithApprovalAndFunctionCallContent()
    {
        ChatMessage requestMessage = new(
            ChatRole.Assistant,
            [
                new ToolApprovalRequestContent("call1", new FunctionCallContent("call1", "do-something")),
                new FunctionCallContent("call2", "do-other"),
            ]);
        ExternalInputRequest copy = RoundTrip(new ExternalInputRequest(new AgentResponse(requestMessage)));

        ChatMessage messageCopy = Assert.Single(copy.AgentResponse.Messages);
        Assert.Equal(2, messageCopy.Contents.Count);
        Assert.Contains(messageCopy.Contents, c => c is ToolApprovalRequestContent);
        Assert.Contains(messageCopy.Contents, c => c is FunctionCallContent);

        // GetInnerRequestContent prefers ToolApprovalRequestContent over FunctionCallContent.
        AIContent? inner = ((IExternalRequestEnvelope)copy).GetInnerRequestContent();
        Assert.IsType<ToolApprovalRequestContent>(inner);
    }

    [Fact]
    public void ExternalInputResponse_RoundTrip()
    {
        ExternalInputResponse copy = RoundTrip(new ExternalInputResponse(new ChatMessage(ChatRole.User, "ok")));

        ChatMessage messageCopy = Assert.Single(copy.Messages);
        Assert.Equal(ChatRole.User, messageCopy.Role);
        Assert.Equal("ok", messageCopy.Text);
    }

    [Fact]
    public void UnassignedValue_RoundTrip()
    {
        Assert.NotNull(RoundTrip(UnassignedValue.Instance));
    }

    // Proves declarative types fail under a source-gen-only resolver that lacks the declarative
    // context. Mirrors AOT runtime behavior in a non-AOT test project.
    [Fact]
    public void Serialization_WithoutDeclarativeChain_FailsOnDeclarativeType()
    {
        ActionExecutorResult source = new("exec-1");
        JsonSerializerOptions bareOptions = new() { TypeInfoResolver = EmptyJsonContext.Default };

        Assert.False(
            bareOptions.TryGetTypeInfo(typeof(ActionExecutorResult), out _),
            $"Test is meaningless if the bare resolver already covers {nameof(ActionExecutorResult)}.");

        NotSupportedException ex = Assert.Throws<NotSupportedException>(
            () => JsonSerializer.Serialize(source, bareOptions));

        Assert.Contains(nameof(ActionExecutorResult), ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Serialization_WithDeclarativeChain_SucceedsOnDeclarativeType()
    {
        string text = JsonSerializer.Serialize(new ActionExecutorResult("exec-1"), DeclarativeWorkflowJsonOptions.Default);

        Assert.Contains("exec-1", text, StringComparison.Ordinal);
    }

    // Mirrors the documented public usage: CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default).
    [Fact]
    public void CheckpointManager_CreateJson_WithDefault_SmokeTest()
    {
        InMemoryJsonStore store = new();

        CheckpointManager manager = CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default);

        Assert.NotNull(manager);
    }

    // Empty context for the negative test; `string` is harmless filler required for a valid context.
    [JsonSerializable(typeof(string))]
    internal sealed partial class EmptyJsonContext : JsonSerializerContext;

    private sealed class InMemoryJsonStore : JsonCheckpointStore
    {
        private readonly Dictionary<CheckpointInfo, JsonElement> _store = [];

        public override ValueTask<CheckpointInfo> CreateCheckpointAsync(
            string sessionId, JsonElement value, CheckpointInfo? parent = null)
        {
            CheckpointInfo key = new(sessionId, Guid.NewGuid().ToString("N"));
            this._store[key] = value;
            return new(key);
        }

        public override ValueTask<JsonElement> RetrieveCheckpointAsync(
            string sessionId, CheckpointInfo key)
            => new(this._store[key]);

        public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(
            string sessionId, CheckpointInfo? withParent = null)
        {
            List<CheckpointInfo> matches = [];
            foreach (CheckpointInfo k in this._store.Keys)
            {
                if (k.SessionId == sessionId)
                {
                    matches.Add(k);
                }
            }
            return new(matches);
        }
    }

    private static T RoundTrip<T>(T source) where T : notnull
    {
        JsonSerializerOptions options = DeclarativeWorkflowJsonOptions.Default;
        string text = JsonSerializer.Serialize(source, options);
        T? copy = JsonSerializer.Deserialize<T>(text, options);
        Assert.NotNull(copy);
        return copy!;
    }
}
