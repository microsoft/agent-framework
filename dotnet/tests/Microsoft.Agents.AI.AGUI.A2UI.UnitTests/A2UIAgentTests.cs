// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.A2UI.UnitTests;

/// <summary>
/// Unit tests for <see cref="A2UIAgent"/>: per-run <c>generate_a2ui</c> tool injection and
/// the tool's end-to-end behavior over a scripted subagent chat client.
/// </summary>
public sealed class A2UIAgentTests
{
    private static readonly JsonObject s_validRenderArgs = new()
    {
        ["surfaceId"] = "s1",
        ["components"] = new JsonArray(
            new JsonObject
            {
                ["id"] = "root",
                ["component"] = "Row",
                ["children"] = new JsonObject { ["componentId"] = "card", ["path"] = "/items" },
            },
            new JsonObject
            {
                ["id"] = "card",
                ["component"] = "HotelCard",
                ["name"] = new JsonObject { ["path"] = "name" },
            }),
        ["data"] = new JsonObject
        {
            ["items"] = new JsonArray(new JsonObject { ["name"] = "Ritz" }),
        },
    };

    [Fact]
    public async Task RunAsync_InjectsGenerateA2UIToolIntoRunOptionsAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")]);

        // Assert
        ChatClientAgentRunOptions options = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        AITool tool = Assert.Single(options.ChatOptions?.Tools ?? []);
        Assert.Equal(A2UIConstants.GenerateA2UIToolName, tool.Name);
        Assert.Equal(A2UIToolDefinitions.GenerateA2UIToolDescription, tool.Description);
    }

    [Fact]
    public async Task RunStreamingAsync_InjectsGenerateA2UIDeclarationIntoRunOptionsAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));

        // Act
        await foreach (AgentResponseUpdate _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "hi")]))
        {
        }

        // Assert: the streaming path advertises a schema-only declaration so the planner's
        // call surfaces on the update stream instead of being auto-invoked.
        ChatClientAgentRunOptions options = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        AITool tool = Assert.Single(options.ChatOptions?.Tools ?? []);
        Assert.Equal(A2UIConstants.GenerateA2UIToolName, tool.Name);
        Assert.IsNotType<AIFunction>(tool, exactMatch: false);
        Assert.IsType<AIFunctionDeclaration>(tool, exactMatch: false);
    }

    [Fact]
    public async Task RunStreamingAsync_GenerateCall_StreamsSubagentAndFeedsResultBackAsync()
    {
        // Arrange: round 1 the planner calls generate_a2ui; round 2 it narrates. The
        // subagent streams its forced render_a2ui call across several updates.
        var inner = new ScriptedPlannerAgent(generateArguments: new() { ["intent"] = "create" });
        var subagent = new ScriptedChatClient(_ => s_validRenderArgs) { StreamingChunks = 3 };
        var agent = new A2UIAgent(inner, subagent);

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "show hotels")]))
        {
            updates.Add(update);
        }

        // Assert: the subagent's streamed updates were forwarded on the agent stream.
        Assert.Equal(3, updates.Count(u => u.Contents.Any(c => c is TextContent text && text.Text == "chunk")));
        FunctionCallContent renderCall = Assert.Single(
            updates.SelectMany(u => u.Contents).OfType<FunctionCallContent>(),
            c => c.Name == A2UIConstants.RenderA2UIToolName);

        // The forwarded render_a2ui call is balanced with a tool result so the persisted
        // conversation stays valid for the next turn.
        FunctionResultContent renderResult = Assert.Single(
            updates.SelectMany(u => u.Contents).OfType<FunctionResultContent>(),
            r => r.CallId == renderCall.CallId);
        Assert.Equal("rendered", Assert.IsType<JsonElement>(renderResult.Result).GetProperty("status").GetString());

        // The generate call's result rides the stream as a valid operations envelope.
        FunctionResultContent result = Assert.Single(
            updates.SelectMany(u => u.Contents).OfType<FunctionResultContent>(),
            r => r.CallId == "call-g1");
        JsonElement envelope = Assert.IsType<JsonElement>(result.Result);
        Assert.True(envelope.TryGetProperty(A2UIConstants.A2UIOperationsKey, out JsonElement ops));
        Assert.Equal(3, ops.GetArrayLength());

        // The planner's second round received the tool-call/result pair and narrated.
        Assert.Equal(2, inner.Runs.Count);
        IReadOnlyList<ChatMessage> secondRoundMessages = inner.Runs[1];
        Assert.Contains(secondRoundMessages, m =>
            m.Role == ChatRole.Assistant && m.Contents.OfType<FunctionCallContent>().Any(c => c.CallId == "call-g1"));
        Assert.Contains(secondRoundMessages, m =>
            m.Role == ChatRole.Tool && m.Contents.OfType<FunctionResultContent>().Any(c => c.CallId == "call-g1"));
        Assert.Contains(updates, u => u.Text == "done");
    }

    [Fact]
    public async Task RunStreamingAsync_InvalidFirstAttempt_RetriesWithVisibleSecondSubagentCallAsync()
    {
        // Arrange: attempt 1 returns a dangling child reference, attempt 2 is valid.
        int calls = 0;
        var invalidArgs = new JsonObject
        {
            ["surfaceId"] = "s1",
            ["components"] = new JsonArray(
                new JsonObject
                {
                    ["id"] = "root",
                    ["component"] = "Row",
                    ["children"] = new JsonObject { ["componentId"] = "ghost", ["path"] = "/items" },
                }),
        };
        var inner = new ScriptedPlannerAgent(generateArguments: new() { ["intent"] = "create" });
        var subagent = new ScriptedChatClient(_ => ++calls == 1 ? invalidArgs : s_validRenderArgs) { StreamingChunks = 1 };
        var agent = new A2UIAgent(inner, subagent);

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "show hotels")]))
        {
            updates.Add(update);
        }

        // Assert: both attempts streamed (two visible render calls), and every forwarded
        // render call is balanced with its own tool result so the next turn's history is valid.
        List<FunctionCallContent> renderCalls = updates
            .SelectMany(u => u.Contents)
            .OfType<FunctionCallContent>()
            .Where(c => c.Name == A2UIConstants.RenderA2UIToolName)
            .ToList();
        Assert.Equal(2, renderCalls.Count);
        List<FunctionResultContent> resultContents = updates
            .SelectMany(u => u.Contents)
            .OfType<FunctionResultContent>()
            .ToList();
        foreach (FunctionCallContent renderCall in renderCalls)
        {
            Assert.Contains(resultContents, r => r.CallId == renderCall.CallId);
        }

        // The generate call's final envelope is the valid second attempt.
        FunctionResultContent result = Assert.Single(resultContents, r => r.CallId == "call-g1");
        JsonElement envelope = Assert.IsType<JsonElement>(result.Result);
        Assert.True(envelope.TryGetProperty(A2UIConstants.A2UIOperationsKey, out _));
        Assert.False(envelope.TryGetProperty("code", out _));
    }

    [Fact]
    public async Task RunStreamingAsync_SubagentNeverCallsTool_ReturnsRecoveryExhaustedEnvelopeAsync()
    {
        // Arrange: the subagent never calls render_a2ui, so every attempt fails.
        int attempts = 0;
        var inner = new ScriptedPlannerAgent(generateArguments: new() { ["intent"] = "create" });
        var subagent = new ScriptedChatClient(_ => null);
        var agent = new A2UIAgent(
            inner,
            subagent,
            new A2UIToolParams { OnAttempt = _ => attempts++ });

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "show hotels")]))
        {
            updates.Add(update);
        }

        // Assert: OnAttempt fired once per attempt, and the generate result is the
        // structured hard-failure envelope — matching the non-streaming path.
        Assert.Equal(A2UIConstants.MaxA2UIAttempts, attempts);
        FunctionResultContent result = Assert.Single(
            updates.SelectMany(u => u.Contents).OfType<FunctionResultContent>(),
            r => r.CallId == "call-g1");
        JsonElement envelope = Assert.IsType<JsonElement>(result.Result);
        Assert.Equal("a2ui_recovery_exhausted", envelope.GetProperty("code").GetString());
    }

    [Fact]
    public async Task RunStreamingAsync_UpdateWithPriorRenderInHistory_ReturnsInPlaceUpdateAsync()
    {
        // Arrange: a prior render envelope rides in a tool-result message, the way the
        // persisted conversation carries it back on a later turn. The streaming update
        // intent must find it through ToHistoryMessage + FindPriorSurface.
        string priorEnvelope = A2UIToolkit.WrapAsOperationsEnvelope(
        [
            A2UIOperationBuilder.CreateSurface("s1", "https://example.test/catalog.json"),
            A2UIOperationBuilder.UpdateComponents("s1", s_validRenderArgs["components"]!.AsArray()),
        ]);
        using JsonDocument priorDocument = JsonDocument.Parse(priorEnvelope);
        var inner = new ScriptedPlannerAgent(generateArguments: new()
        {
            ["intent"] = "update",
            ["target_surface_id"] = "s1",
        });
        var subagent = new ScriptedChatClient(_ => s_validRenderArgs) { StreamingChunks = 1 };
        var agent = new A2UIAgent(inner, subagent);

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(
        [
            new ChatMessage(ChatRole.User, "show hotels"),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call-0", priorDocument.RootElement.Clone())]),
            new ChatMessage(ChatRole.User, "make the cards bigger"),
        ]))
        {
            updates.Add(update);
        }

        // Assert: an in-place update — no createSurface for the existing surface.
        FunctionResultContent result = Assert.Single(
            updates.SelectMany(u => u.Contents).OfType<FunctionResultContent>(),
            r => r.CallId == "call-g1");
        JsonElement envelope = Assert.IsType<JsonElement>(result.Result);
        JsonElement ops = envelope.GetProperty(A2UIConstants.A2UIOperationsKey);
        Assert.Equal(2, ops.GetArrayLength());
        Assert.DoesNotContain(
            ops.EnumerateArray(),
            op => op.TryGetProperty("createSurface", out _));
    }

    [Fact]
    public async Task RunStreamingAsync_PlannerExhaustsRounds_ClosesWithGenerateToolWithheldAsync()
    {
        // Arrange: a planner that requests a generation every round, so the round cap is hit.
        var inner = new ScriptedPlannerAgent(generateArguments: new() { ["intent"] = "create" })
        {
            AlwaysGenerate = true,
        };
        var subagent = new ScriptedChatClient(_ => s_validRenderArgs) { StreamingChunks = 1 };
        var agent = new A2UIAgent(inner, subagent);

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "show hotels")]))
        {
            updates.Add(update);
        }

        // Assert: one final planner turn beyond the cap, and that final turn had the
        // generate tool withheld so the planner could only narrate (no dangling tool result).
        Assert.Equal(A2UIAgent.MaxPlannerRounds + 1, inner.Runs.Count);
        IReadOnlyList<string> finalTurnTools = inner.ToolsPerRun[^1];
        Assert.DoesNotContain(A2UIConstants.GenerateA2UIToolName, finalTurnTools);
        Assert.Contains(updates, u => u.Text == "done");
    }

    [Fact]
    public async Task RunAsync_CustomToolName_IsHonoredAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(
            inner,
            new ScriptedChatClient(_ => s_validRenderArgs),
            new A2UIToolParams { ToolName = "custom_a2ui" });

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")]);

        // Assert
        ChatClientAgentRunOptions options = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        Assert.Contains(options.ChatOptions?.Tools ?? [], t => t.Name == "custom_a2ui");
    }

    [Fact]
    public async Task RunAsync_PreservesCallerToolsAndRunOptionsAsync()
    {
        // Arrange: a caller-supplied options object carrying chat tools and base
        // AgentRunOptions members, plus a stale generate_a2ui entry that must be
        // replaced rather than duplicated.
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));
        AIFunction callerTool = AIFunctionFactory.Create(() => "weather", "get_weather");
        AIFunction staleGenerateTool = AIFunctionFactory.Create(() => "stale", A2UIConstants.GenerateA2UIToolName);
        Func<IChatClient, IChatClient> factory = client => client;
        var callerOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions { Tools = [callerTool, staleGenerateTool] },
            ChatClientFactory = factory,
            AllowBackgroundResponses = true,
            ResponseFormat = ChatResponseFormat.Json,
            AdditionalProperties = new AdditionalPropertiesDictionary { ["run-key"] = "run-value" },
        };

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], options: callerOptions);

        // Assert: caller tool retained, generate tool replaced (no duplicate), base
        // run-option members and the chat client factory all survive.
        ChatClientAgentRunOptions forwarded = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        IList<AITool> tools = forwarded.ChatOptions?.Tools ?? [];
        Assert.Contains(tools, t => t.Name == "get_weather");
        AITool generateTool = Assert.Single(tools, t => t.Name == A2UIConstants.GenerateA2UIToolName);
        Assert.NotSame(staleGenerateTool, generateTool);
        Assert.Same(factory, forwarded.ChatClientFactory);
        Assert.True(forwarded.AllowBackgroundResponses);
        Assert.Same(ChatResponseFormat.Json, forwarded.ResponseFormat);
        Assert.Equal("run-value", forwarded.AdditionalProperties?["run-key"]);

        // The caller's options object is not mutated.
        Assert.Equal(2, callerOptions.ChatOptions!.Tools!.Count);
        Assert.Same(staleGenerateTool, callerOptions.ChatOptions.Tools[1]);
    }

    [Fact]
    public async Task RunAsync_PlainAgentRunOptions_BaseMembersSurviveAsync()
    {
        // Arrange: a caller passing the base options type still gets its members forwarded.
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));
        var callerOptions = new AgentRunOptions
        {
            AllowBackgroundResponses = true,
            ResponseFormat = ChatResponseFormat.Json,
            AdditionalProperties = new AdditionalPropertiesDictionary { ["run-key"] = "run-value" },
        };

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], options: callerOptions);

        // Assert
        ChatClientAgentRunOptions forwarded = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        Assert.True(forwarded.AllowBackgroundResponses);
        Assert.Same(ChatResponseFormat.Json, forwarded.ResponseFormat);
        Assert.Equal("run-value", forwarded.AdditionalProperties?["run-key"]);
        Assert.Contains(forwarded.ChatOptions?.Tools ?? [], t => t.Name == A2UIConstants.GenerateA2UIToolName);
    }

    [Fact]
    public async Task GenerateA2UITool_CreateIntent_ReturnsOperationsEnvelopeAsync()
    {
        // Arrange
        ChatOptions? subagentOptions = null;
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(options =>
        {
            subagentOptions = options;
            return s_validRenderArgs;
        }));
        await agent.RunAsync([new ChatMessage(ChatRole.User, "show hotels")]);

        // Act
        string envelope = await InvokeGenerateToolAsync(inner, new() { ["intent"] = "create" });

        // Assert
        JsonObject parsed = Assert.IsType<JsonObject>(JsonNode.Parse(envelope));
        JsonArray ops = Assert.IsType<JsonArray>(parsed[A2UIConstants.A2UIOperationsKey]);
        Assert.Equal(3, ops.Count);
        // The subagent is forced to call render_a2ui.
        Assert.NotNull(subagentOptions);
        Assert.Equal(
            ChatToolMode.RequireSpecific(A2UIConstants.RenderA2UIToolName),
            subagentOptions!.ToolMode);
        AITool renderTool = Assert.Single(subagentOptions.Tools ?? []);
        Assert.Equal(A2UIConstants.RenderA2UIToolName, renderTool.Name);
    }

    [Fact]
    public async Task GenerateA2UITool_UpdateWithoutPrior_ReturnsErrorEnvelopeAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));
        await agent.RunAsync([new ChatMessage(ChatRole.User, "update it")]);

        // Act
        string envelope = await InvokeGenerateToolAsync(
            inner, new() { ["intent"] = "update", ["target_surface_id"] = "missing" });

        // Assert
        JsonObject parsed = Assert.IsType<JsonObject>(JsonNode.Parse(envelope));
        Assert.Contains("no prior render", (string?)parsed["error"]);
    }

    [Fact]
    public async Task GenerateA2UITool_UpdateWithPriorRenderInHistory_ReturnsUpdateOpsAsync()
    {
        // Arrange: a prior render envelope rides in a tool-result message, the way a real
        // conversation history carries it. The update intent must find it through
        // ToHistoryMessage + FindPriorSurface and emit in-place update operations.
        string priorEnvelope = A2UIToolkit.WrapAsOperationsEnvelope(
        [
            A2UIOperationBuilder.CreateSurface("s1", "https://example.test/catalog.json"),
            A2UIOperationBuilder.UpdateComponents("s1", s_validRenderArgs["components"]!.AsArray()),
        ]);
        using JsonDocument priorDocument = JsonDocument.Parse(priorEnvelope);
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));
        await agent.RunAsync(
        [
            new ChatMessage(ChatRole.User, "show hotels"),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("call-0", priorDocument.RootElement.Clone())]),
            new ChatMessage(ChatRole.User, "make the cards bigger"),
        ]);

        // Act
        string envelope = await InvokeGenerateToolAsync(
            inner, new() { ["intent"] = "update", ["target_surface_id"] = "s1" });

        // Assert: no createSurface for an in-place update; the ops target the prior surface.
        JsonObject parsed = Assert.IsType<JsonObject>(JsonNode.Parse(envelope));
        JsonArray ops = Assert.IsType<JsonArray>(parsed[A2UIConstants.A2UIOperationsKey]);
        Assert.Equal(2, ops.Count);
        Assert.DoesNotContain(ops, op => op is JsonObject obj && obj.ContainsKey("createSurface"));
        JsonObject updateComponents = Assert.IsType<JsonObject>(ops[0]?["updateComponents"]);
        Assert.Equal("s1", (string?)updateComponents["surfaceId"]);
    }

    [Fact]
    public async Task GenerateA2UITool_SubagentNeverCallsTool_ReturnsRecoveryExhaustedEnvelopeAsync()
    {
        // Arrange
        int calls = 0;
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ =>
        {
            calls++;
            return null; // no render_a2ui call
        }));
        await agent.RunAsync([new ChatMessage(ChatRole.User, "show hotels")]);

        // Act
        string envelope = await InvokeGenerateToolAsync(inner, []);

        // Assert
        JsonObject parsed = Assert.IsType<JsonObject>(JsonNode.Parse(envelope));
        Assert.Equal("a2ui_recovery_exhausted", (string?)parsed["code"]);
        Assert.Equal(A2UIConstants.MaxA2UIAttempts, calls);
    }

    [Fact]
    public async Task GenerateA2UITool_JsonElementArguments_ReturnsOperationsEnvelopeAsync()
    {
        // Arrange: real chat clients deliver FunctionCallContent.Arguments values as
        // JsonElement — exercise that marshalling arm rather than pre-built JsonNodes.
        using JsonDocument argsDocument = JsonDocument.Parse(s_validRenderArgs.ToJsonString());
        var elementArgs = new Dictionary<string, object?>
        {
            ["surfaceId"] = argsDocument.RootElement.GetProperty("surfaceId").Clone(),
            ["components"] = argsDocument.RootElement.GetProperty("components").Clone(),
            ["data"] = argsDocument.RootElement.GetProperty("data").Clone(),
        };
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => null) { RawArguments = elementArgs });
        await agent.RunAsync([new ChatMessage(ChatRole.User, "show hotels")]);

        // Act
        string envelope = await InvokeGenerateToolAsync(inner, new() { ["intent"] = "create" });

        // Assert
        JsonObject parsed = Assert.IsType<JsonObject>(JsonNode.Parse(envelope));
        JsonArray ops = Assert.IsType<JsonArray>(parsed[A2UIConstants.A2UIOperationsKey]);
        Assert.Equal(3, ops.Count);
    }

    [Fact]
    public async Task ReadAgentState_RoutesSchemaEntryIntoAvailableComponentsAsync()
    {
        // Arrange: the hosting layer forwards context entries; the catalog schema entry
        // must land in the prompt's canonical "## Available Components" section and the
        // plain entry under its own heading.
        string? subagentPrompt = null;
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(options => s_validRenderArgs)
        {
            OnMessages = messages => subagentPrompt = messages.FirstOrDefault(m => m.Role == ChatRole.System)?.Text,
        });
        var runOptions = new ChatClientAgentRunOptions
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
        await agent.RunAsync([new ChatMessage(ChatRole.User, "show hotels")], options: runOptions);

        // Act
        await InvokeGenerateToolAsync(inner, new() { ["intent"] = "create" });

        // Assert
        Assert.NotNull(subagentPrompt);
        Assert.Contains("## Available Components", subagentPrompt);
        Assert.Contains("{\"components\":{}}", subagentPrompt);
        Assert.Contains("## Style guide", subagentPrompt);
        Assert.DoesNotContain($"## {A2UIConstants.A2UISchemaContextDescription}", subagentPrompt);
    }

    /// <summary>
    /// Pulls the injected <c>generate_a2ui</c> function from the recorded run options and
    /// invokes it the way a function-invoking chat client would.
    /// </summary>
    private static async Task<string> InvokeGenerateToolAsync(RecordingAgent inner, Dictionary<string, object?> arguments)
    {
        ChatClientAgentRunOptions options = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        AIFunction function = Assert.IsType<AIFunction>(
            (options.ChatOptions?.Tools ?? []).Single(t => t is AIFunction),
            exactMatch: false);

        object? result = await function.InvokeAsync(new AIFunctionArguments(arguments));
        return result switch
        {
            string text => text,
            JsonElement element when element.ValueKind == JsonValueKind.String => element.GetString()!,
            JsonElement element => element.GetRawText(),
            _ => result?.ToString() ?? string.Empty,
        };
    }

    /// <summary>An inner agent that records the options it was run with and returns an empty response.</summary>
    private sealed class RecordingAgent : AIAgent
    {
        public AgentRunOptions? LastOptions { get; private set; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.LastOptions = options;
            return Task.FromResult(new AgentResponse());
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.LastOptions = options;
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }
    }

    /// <summary>
    /// A chat client scripted per call: returns a <c>render_a2ui</c> function call with the
    /// supplied arguments, or a plain text message when the script yields <see langword="null"/>.
    /// </summary>
    private sealed class ScriptedChatClient : IChatClient
    {
        private readonly Func<ChatOptions?, JsonObject?> _script;

        public ScriptedChatClient(Func<ChatOptions?, JsonObject?> script) => this._script = script;

        /// <summary>When set, the function call carries these raw argument values verbatim.</summary>
        public IDictionary<string, object?>? RawArguments { get; init; }

        /// <summary>Observes the messages each subagent invocation receives.</summary>
        public Action<IEnumerable<ChatMessage>>? OnMessages { get; init; }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.OnMessages?.Invoke(messages);
            IDictionary<string, object?>? arguments = this.RawArguments;
            if (arguments is null)
            {
                JsonObject? args = this._script(options);
                arguments = args?.ToDictionary(p => p.Key, object? (p) => p.Value?.DeepClone());
            }

            ChatMessage message = arguments is null
                ? new ChatMessage(ChatRole.Assistant, "no tool call")
                : new ChatMessage(ChatRole.Assistant,
                [
                    new FunctionCallContent("call-1", A2UIConstants.RenderA2UIToolName, arguments),
                ]);
            return Task.FromResult(new ChatResponse(message));
        }

        /// <summary>Text chunks streamed before the function call on the streaming path.</summary>
        public int StreamingChunks { get; init; }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.OnMessages?.Invoke(messages);
            for (int i = 0; i < this.StreamingChunks; i++)
            {
                yield return new ChatResponseUpdate(ChatRole.Assistant, "chunk");
            }

            IDictionary<string, object?>? arguments = this.RawArguments;
            if (arguments is null)
            {
                JsonObject? args = this._script(options);
                arguments = args?.ToDictionary(p => p.Key, object? (p) => p.Value?.DeepClone());
            }

            // Real streaming chat clients coalesce the call's fragments and attach the
            // typed FunctionCallContent on a trailing update.
            yield return arguments is null
                ? new ChatResponseUpdate(ChatRole.Assistant, "no tool call")
                : new ChatResponseUpdate(ChatRole.Assistant,
                [
                    new FunctionCallContent($"render-call-{Guid.NewGuid():N}", A2UIConstants.RenderA2UIToolName, arguments),
                ]);
            await Task.CompletedTask.ConfigureAwait(false);
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// A planner agent scripted for the streaming invocation loop: the first run emits a
    /// <c>generate_a2ui</c> tool call, subsequent runs emit a closing narration.
    /// </summary>
    private sealed class ScriptedPlannerAgent : AIAgent
    {
        private readonly Dictionary<string, object?> _generateArguments;

        public ScriptedPlannerAgent(Dictionary<string, object?> generateArguments)
            => this._generateArguments = generateArguments;

        /// <summary>When set, emit a <c>generate_a2ui</c> call on every run instead of narrating after the first.</summary>
        public bool AlwaysGenerate { get; init; }

        public List<IReadOnlyList<ChatMessage>> Runs { get; } = [];

        /// <summary>The tool names advertised on each run, in order.</summary>
        public List<IReadOnlyList<string>> ToolsPerRun { get; } = [];

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.Runs.Add(messages.ToList());
            this.ToolsPerRun.Add((options as ChatClientAgentRunOptions)?.ChatOptions?.Tools?.Select(t => t.Name).ToList() ?? []);

            // A generate_a2ui call is only possible when the tool is still advertised; once
            // the agent withholds it (the round-cap final turn), fall back to narration.
            bool generateAdvertised = this.ToolsPerRun[^1].Contains(A2UIConstants.GenerateA2UIToolName);
            if (generateAdvertised && (this.AlwaysGenerate || this.Runs.Count == 1))
            {
                yield return new AgentResponseUpdate(ChatRole.Assistant,
                [
                    new FunctionCallContent($"call-g{this.Runs.Count}", A2UIConstants.GenerateA2UIToolName, this._generateArguments),
                ]);
            }
            else
            {
                yield return new AgentResponseUpdate(ChatRole.Assistant, "done");
            }

            await Task.CompletedTask.ConfigureAwait(false);
        }
    }
}
