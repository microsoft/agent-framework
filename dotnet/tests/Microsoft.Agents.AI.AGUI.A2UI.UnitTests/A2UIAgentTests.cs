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
    public async Task RunStreamingAsync_InjectsGenerateA2UIToolIntoRunOptionsAsync()
    {
        // Arrange
        var inner = new RecordingAgent();
        var agent = new A2UIAgent(inner, new ScriptedChatClient(_ => s_validRenderArgs));

        // Act: the streaming entry point goes through the same per-run preparation.
        await foreach (AgentResponseUpdate _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "hi")]))
        {
        }

        // Assert
        ChatClientAgentRunOptions options = Assert.IsType<ChatClientAgentRunOptions>(inner.LastOptions);
        AITool tool = Assert.Single(options.ChatOptions?.Tools ?? []);
        Assert.Equal(A2UIConstants.GenerateA2UIToolName, tool.Name);
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

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
