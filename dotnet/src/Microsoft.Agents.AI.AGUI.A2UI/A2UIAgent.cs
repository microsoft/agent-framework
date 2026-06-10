// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Wraps an agent with A2UI surface-generation support: every run gets a
/// <c>generate_a2ui</c> tool that delegates UI generation to a subagent chat client
/// and returns a validated A2UI operations envelope as its tool result.
/// </summary>
/// <remarks>
/// <para>
/// This is the Agent Framework adapter over the framework-agnostic toolkit
/// (<see cref="A2UIToolkit"/>, <see cref="A2UIGenerationRecovery"/>), mirroring the
/// LangGraph adapters' <c>getA2UITools</c>/<c>get_a2ui_tools</c> factories. The tool
/// must be constructed per run because it reads the run's conversation history (for
/// prior-surface lookup) and the AG-UI context forwarded by the hosting layer (for the
/// component catalog) — hence the agent wrapper rather than a static tool.
/// </para>
/// <para>
/// The component catalog is read from the <c>ag_ui_context</c> additional property that
/// <c>MapAGUI</c> stamps onto <see cref="ChatOptions.AdditionalProperties"/>, using the
/// schema context entry injected by the AG-UI A2UI middleware.
/// </para>
/// </remarks>
public sealed class A2UIAgent : DelegatingAIAgent
{
    private readonly IChatClient _subagentChatClient;
    private readonly A2UIResolvedToolParams _parameters;

    /// <summary>
    /// Initializes a new instance of the <see cref="A2UIAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The agent to wrap.</param>
    /// <param name="subagentChatClient">
    /// The chat client used to run the UI-generation subagent. Must be a raw client
    /// (no automatic function invocation) — the adapter reads the forced
    /// <c>render_a2ui</c> call's arguments directly.
    /// </param>
    /// <param name="parameters">Behavior knobs; defaults are filled per the shared toolkit rules.</param>
    public A2UIAgent(AIAgent innerAgent, IChatClient subagentChatClient, A2UIToolParams? parameters = null)
        : base(innerAgent)
    {
        this._subagentChatClient = Throw.IfNull(subagentChatClient);
        this._parameters = A2UIToolDefinitions.ResolveA2UIToolParams(parameters);
    }

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        (List<ChatMessage> messageList, AgentRunOptions runOptions) = this.PrepareRun(messages, options);
        return this.InnerAgent.RunAsync(messageList, session, runOptions, cancellationToken);
    }

    /// <inheritdoc/>
    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        (List<ChatMessage> messageList, AgentRunOptions runOptions) = this.PrepareRun(messages, options);
        return this.InnerAgent.RunStreamingAsync(messageList, session, runOptions, cancellationToken);
    }

    /// <summary>
    /// Builds the per-run options: clones the incoming chat options and appends a
    /// freshly constructed <c>generate_a2ui</c> tool that captures this run's
    /// conversation history and AG-UI state.
    /// </summary>
    private (List<ChatMessage> Messages, AgentRunOptions Options) PrepareRun(
        IEnumerable<ChatMessage> messages,
        AgentRunOptions? options)
    {
        List<ChatMessage> messageList = messages.ToList();

        ChatClientAgentRunOptions? original = options as ChatClientAgentRunOptions;
        ChatOptions chatOptions = original?.ChatOptions?.Clone() ?? new ChatOptions();

        AIFunction generateTool = this.CreateGenerateA2UIFunction(messageList, ReadAgentState(chatOptions.AdditionalProperties));
        chatOptions.Tools = (chatOptions.Tools ?? Enumerable.Empty<AITool>())
            .Where(t => !string.Equals(t.Name, generateTool.Name, StringComparison.Ordinal))
            .Append(generateTool)
            .ToList();

        var runOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = chatOptions,
            ChatClientFactory = original?.ChatClientFactory,
        };

        return (messageList, runOptions);
    }

    /// <summary>
    /// Builds the per-run <c>generate_a2ui</c> tool with the run's conversation history and
    /// AG-UI state captured in its closure.
    /// </summary>
    private AIFunction CreateGenerateA2UIFunction(IReadOnlyList<ChatMessage> messages, A2UIAgentState state)
    {
        List<A2UIHistoryMessage> history = messages.Select(ToHistoryMessage).ToList();

        // The tool returns the parsed envelope (not the JSON string): a string result
        // would be JSON-serialized a second time on its way into the AG-UI tool-result
        // event, and the A2UI middleware would have to undo the double encoding.
        async Task<JsonElement> GenerateA2UIAsync(
            [Description(A2UIToolDefinitions.IntentArgumentDescription)] string? intent = null,
            [Description(A2UIToolDefinitions.TargetSurfaceIdArgumentDescription)] string? target_surface_id = null,
            [Description(A2UIToolDefinitions.ChangesArgumentDescription)] string? changes = null,
            CancellationToken cancellationToken = default)
        {
            A2UIPreparedRequest prep = A2UIToolkit.PrepareA2UIRequest(
                intent, target_surface_id, changes, history, state, this._parameters.Guidelines);
            if (prep.Error is not null)
            {
                return ParseEnvelope(A2UIToolkit.WrapErrorEnvelope(prep.Error));
            }

            A2UIRecoveryResult result = await A2UIGenerationRecovery.RunAsync(
                prep.Prompt,
                (prompt, attempt, ct) => this.InvokeRenderSubagentAsync(prompt, messages, ct),
                args => A2UIToolkit.BuildA2UIEnvelope(
                    args,
                    prep.IsUpdate,
                    target_surface_id,
                    prep.Prior,
                    this._parameters.DefaultSurfaceId,
                    this._parameters.DefaultCatalogId),
                this._parameters.Catalog,
                this._parameters.Recovery,
                this._parameters.OnAttempt,
                cancellationToken).ConfigureAwait(false);

            return ParseEnvelope(result.Envelope);
        }

        return AIFunctionFactory.Create(
            GenerateA2UIAsync,
            this._parameters.ToolName,
            this._parameters.ToolDescription);
    }

    /// <summary>
    /// Runs the UI-generation subagent with a forced <c>render_a2ui</c> tool call and
    /// returns the call's structured arguments, or <see langword="null"/> when the model
    /// did not call the tool (a retryable failure in the recovery loop).
    /// </summary>
    private async ValueTask<JsonObject?> InvokeRenderSubagentAsync(
        string prompt,
        IReadOnlyList<ChatMessage> messages,
        CancellationToken cancellationToken)
    {
        List<ChatMessage> subagentMessages = [new ChatMessage(ChatRole.System, prompt), .. messages];
        var subagentOptions = new ChatOptions
        {
            Tools = [new RenderA2UIToolDeclaration()],
            ToolMode = ChatToolMode.RequireSpecific(A2UIConstants.RenderA2UIToolName),
        };

        ChatResponse response = await this._subagentChatClient
            .GetResponseAsync(subagentMessages, subagentOptions, cancellationToken)
            .ConfigureAwait(false);

        FunctionCallContent? call = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionCallContent>()
            .FirstOrDefault(c => string.Equals(c.Name, A2UIConstants.RenderA2UIToolName, StringComparison.Ordinal));

        return call?.Arguments is { } arguments ? ToJsonObject(arguments) : null;
    }

    /// <summary>
    /// Reads the AG-UI state slice from the additional properties stamped by the AG-UI
    /// hosting layer: forwarded context entries plus the A2UI component catalog entry
    /// injected by the A2UI middleware.
    /// </summary>
    private static A2UIAgentState ReadAgentState(AdditionalPropertiesDictionary? properties)
    {
        if (properties is null ||
            !properties.TryGetValue("ag_ui_context", out object? contextValue) ||
            contextValue is not IEnumerable<KeyValuePair<string, string>> entries)
        {
            return new A2UIAgentState();
        }

        List<A2UIContextEntry> context = [];
        string? schema = null;
        foreach (KeyValuePair<string, string> entry in entries)
        {
            if (string.Equals(entry.Key, A2UIConstants.A2UISchemaContextDescription, StringComparison.Ordinal))
            {
                schema = entry.Value;
            }
            else
            {
                context.Add(new A2UIContextEntry(entry.Key, entry.Value));
            }
        }

        return new A2UIAgentState { Context = context, A2UISchema = schema };
    }

    /// <summary>
    /// Maps a chat message onto the toolkit's history shape: the role name plus the
    /// message's textual content (for tool results, the function result payload).
    /// </summary>
    private static A2UIHistoryMessage ToHistoryMessage(ChatMessage message)
    {
        string? content = message.Text;
        if (string.IsNullOrEmpty(content) && message.Role == ChatRole.Tool)
        {
            FunctionResultContent? result = message.Contents.OfType<FunctionResultContent>().FirstOrDefault();
            content = result?.Result switch
            {
                string text => text,
                JsonElement { ValueKind: JsonValueKind.String } element => element.GetString(),
                JsonElement element => element.GetRawText(),
                _ => null,
            };
        }

        return new A2UIHistoryMessage(message.Role.Value, content);
    }

    private static JsonElement ParseEnvelope(string envelope)
    {
        using var document = JsonDocument.Parse(envelope);
        return document.RootElement.Clone();
    }

    private static JsonObject ToJsonObject(IDictionary<string, object?> arguments)
    {
        var result = new JsonObject();
        foreach (KeyValuePair<string, object?> argument in arguments)
        {
            result[argument.Key] = argument.Value switch
            {
                null => null,
                JsonNode node => node.DeepClone(),
                JsonElement element => JsonNode.Parse(element.GetRawText()),
                string text => JsonValue.Create(text),
                bool flag => JsonValue.Create(flag),
                int number => JsonValue.Create(number),
                long number => JsonValue.Create(number),
                double number => JsonValue.Create(number),
                _ => JsonNode.Parse(JsonSerializer.Serialize(argument.Value, AIJsonUtilities.DefaultOptions.GetTypeInfo(argument.Value.GetType()))),
            };
        }

        return result;
    }

    /// <summary>
    /// The schema-only declaration of the inner <c>render_a2ui</c> structured-output tool.
    /// The subagent is forced to call it; the adapter reads the arguments instead of invoking it.
    /// </summary>
    private sealed class RenderA2UIToolDeclaration : AIFunctionDeclaration
    {
        private static readonly JsonElement s_schema = ParseSchema();

        private static JsonElement ParseSchema()
        {
            using var document = JsonDocument.Parse(
                A2UIToolDefinitions.CreateRenderA2UIToolDefinition()["function"]!["parameters"]!.ToJsonString());
            return document.RootElement.Clone();
        }

        public override string Name => A2UIConstants.RenderA2UIToolName;

        public override string Description =>
            "Render a dynamic A2UI v0.9 surface. The root component must have " +
            "id 'root'. Use components from the available catalog only.";

        public override JsonElement JsonSchema => s_schema;
    }
}
