// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
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
    // Bare acknowledgement returned as the inner render_a2ui tool result; the painted
    // surface rides the streamed arguments, so the result only has to balance the call.
    private const string RenderAcknowledgement = "{\"status\":\"rendered\"}";

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

    /// <summary>
    /// The cap on planner rounds (model turn → generation → result fed back) per run,
    /// guarding against a planner that keeps requesting surfaces without terminating.
    /// </summary>
    internal const int MaxPlannerRounds = 8;

    /// <inheritdoc/>
    /// <remarks>
    /// The streaming path runs the <c>generate_a2ui</c> invocation loop at the agent level
    /// instead of through automatic function invocation: the tool is advertised as a
    /// schema-only declaration so the planner's call surfaces on the update stream, the
    /// render subagent is then run with a streaming chat call, and its raw updates are
    /// forwarded so hosting layers can emit the tool-call argument fragments incrementally
    /// (progressive surface rendering). The envelope is fed back to the planner and the
    /// conversation continues — the same wire shape the LangGraph adapters produce.
    /// </remarks>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        List<ChatMessage> history = messages.ToList();

        ChatClientAgentRunOptions runOptions = CloneRunOptions(options);
        ChatOptions chatOptions = runOptions.ChatOptions ?? new ChatOptions();
        runOptions.ChatOptions = chatOptions;

        A2UIAgentState state = ReadAgentState(chatOptions.AdditionalProperties);

        var generateTool = new GenerateA2UIToolDeclaration(this._parameters.ToolName, this._parameters.ToolDescription);
        chatOptions.Tools = (chatOptions.Tools ?? Enumerable.Empty<AITool>())
            .Where(t => !string.Equals(t.Name, generateTool.Name, StringComparison.Ordinal))
            .Append(generateTool)
            .ToList();

        // Round 1 carries the caller's session so inner-agent bookkeeping still happens;
        // later rounds resend the manually grown history without the session to avoid
        // double-recording the same messages in session-aware inner agents.
        List<ChatMessage> pending = history;
        AgentSession? pendingSession = session;
        for (int round = 1; round <= MaxPlannerRounds; round++)
        {
            List<FunctionCallContent> generateCalls = [];
            await foreach (AgentResponseUpdate update in this.InnerAgent
                .RunStreamingAsync(pending, pendingSession, runOptions, cancellationToken)
                .ConfigureAwait(false))
            {
                foreach (AIContent content in update.Contents)
                {
                    if (content is FunctionCallContent call &&
                        string.Equals(call.Name, generateTool.Name, StringComparison.Ordinal))
                    {
                        generateCalls.Add(call);
                    }
                }

                yield return update;
            }

            if (generateCalls.Count == 0)
            {
                yield break;
            }

            List<AIContent> results = [];
            foreach (FunctionCallContent call in generateCalls)
            {
                var envelopeBox = new StrongBox<JsonElement>();
                await foreach (AgentResponseUpdate update in this
                    .RunGenerateStreamingAsync(call, history, state, envelopeBox, cancellationToken)
                    .ConfigureAwait(false))
                {
                    yield return update;
                }

                results.Add(new FunctionResultContent(call.CallId, envelopeBox.Value));
            }

            // Surface the tool results on the wire and feed them back to the planner.
            var toolMessage = new ChatMessage(ChatRole.Tool, results);
            yield return new AgentResponseUpdate(ChatRole.Tool, results);

            history.Add(new ChatMessage(ChatRole.Assistant, [.. generateCalls]));
            history.Add(toolMessage);
            pending = history;
            pendingSession = null;
        }

        // The planner kept requesting generations through the round cap. Give it one final
        // turn to consume the last tool result and narrate, with the generate tool withheld
        // so it cannot request another surface — otherwise the run would end on an
        // unanswered tool result with no closing assistant message.
        chatOptions.Tools = (chatOptions.Tools ?? Enumerable.Empty<AITool>())
            .Where(t => !string.Equals(t.Name, generateTool.Name, StringComparison.Ordinal))
            .ToList();
        await foreach (AgentResponseUpdate update in this.InnerAgent
            .RunStreamingAsync(history, pendingSession, runOptions, cancellationToken)
            .ConfigureAwait(false))
        {
            yield return update;
        }
    }

    /// <summary>
    /// Runs one <c>generate_a2ui</c> invocation with the validate-and-retry loop, streaming
    /// the render subagent's updates (each retry is a fresh, visible subagent call) and
    /// depositing the final envelope — operations, request error, or recovery-exhausted —
    /// into <paramref name="envelopeBox"/>.
    /// </summary>
    private async IAsyncEnumerable<AgentResponseUpdate> RunGenerateStreamingAsync(
        FunctionCallContent call,
        IReadOnlyList<ChatMessage> conversation,
        A2UIAgentState state,
        StrongBox<JsonElement> envelopeBox,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string? intent = GetStringArgument(call.Arguments, "intent");
        string? targetSurfaceId = GetStringArgument(call.Arguments, "target_surface_id");
        string? changes = GetStringArgument(call.Arguments, "changes");

        List<A2UIHistoryMessage> history = conversation.Select(ToHistoryMessage).ToList();
        A2UIPreparedRequest prep = A2UIToolkit.PrepareA2UIRequest(
            intent, targetSurfaceId, changes, history, state, this._parameters.Guidelines);
        if (prep.Error is not null)
        {
            envelopeBox.Value = ParseEnvelope(A2UIToolkit.WrapErrorEnvelope(prep.Error));
            yield break;
        }

        // The streaming twin of A2UIGenerationRecovery.RunAsync: same attempt semantics,
        // but each subagent call streams so its updates can be forwarded between attempts.
        int maxAttempts = this._parameters.Recovery?.MaxAttempts ?? A2UIConstants.MaxA2UIAttempts;
        List<A2UIAttemptRecord> attempts = [];
        IReadOnlyList<A2UIValidationError> lastErrors = [];
        for (int attempt = 1; attempt <= maxAttempts; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            string prompt = A2UIGenerationRecovery.AugmentPromptWithValidationErrors(prep.Prompt, lastErrors);

            // Forward every update so the hosting layer can paint the render_a2ui argument
            // fragments progressively, while accumulating them to coalesce the complete
            // tool call afterward. Reading arguments off a single update is unsafe: a chat
            // client may stream a tool call's arguments as fragments across updates, and
            // only the coalesced response carries the full arguments (this mirrors the
            // non-streaming path, which reads the already-coalesced ChatResponse).
            List<ChatResponseUpdate> attemptUpdates = [];
            await foreach (ChatResponseUpdate update in this._subagentChatClient
                .GetStreamingResponseAsync(BuildSubagentMessages(prompt, conversation), CreateSubagentOptions(), cancellationToken)
                .ConfigureAwait(false))
            {
                attemptUpdates.Add(update);
                yield return new AgentResponseUpdate(update);
            }

            FunctionCallContent? renderCall = attemptUpdates.ToChatResponse().Messages
                .SelectMany(m => m.Contents)
                .OfType<FunctionCallContent>()
                .FirstOrDefault(c => string.Equals(c.Name, A2UIConstants.RenderA2UIToolName, StringComparison.Ordinal));
            JsonObject? renderArgs = renderCall?.Arguments is { } renderArguments ? ToJsonObject(renderArguments) : null;

            // The subagent's render_a2ui call is forwarded onto the wire so the hosting
            // layer can paint its argument fragments progressively — but that means it
            // becomes part of the persisted conversation. Emit a matching tool result so
            // the assistant tool call is balanced; an unanswered tool call would make the
            // next turn's history invalid (e.g. OpenAI rejects it). The painted surface
            // comes from the streamed arguments, so this result is a bare acknowledgement.
            if (renderCall is not null)
            {
                yield return new AgentResponseUpdate(
                    ChatRole.Tool,
                    [new FunctionResultContent(renderCall.CallId, ParseEnvelope(RenderAcknowledgement))]);
            }

            // Validation and attempt accounting are shared with the non-streaming recovery
            // loop so the two paths cannot drift on attempt semantics.
            A2UIAttemptRecord record = A2UIGenerationRecovery.ValidateAttempt(attempt, renderArgs, this._parameters.Catalog);
            attempts.Add(record);
            this._parameters.OnAttempt?.Invoke(record);

            if (record.Ok)
            {
                envelopeBox.Value = ParseEnvelope(A2UIToolkit.BuildA2UIEnvelope(
                    renderArgs!,
                    prep.IsUpdate,
                    targetSurfaceId,
                    prep.Prior,
                    this._parameters.DefaultSurfaceId,
                    this._parameters.DefaultCatalogId));
                yield break;
            }

            lastErrors = record.Errors;
        }

        envelopeBox.Value = ParseEnvelope(A2UIGenerationRecovery.WrapRecoveryExhaustedEnvelope(maxAttempts, attempts));
    }

    /// <summary>Reads a string argument from a function call's argument dictionary.</summary>
    private static string? GetStringArgument(IDictionary<string, object?>? arguments, string name) =>
        arguments is not null && arguments.TryGetValue(name, out object? value)
            ? value switch
            {
                string text => text,
                JsonElement element when element.ValueKind == JsonValueKind.String => element.GetString(),
                JsonValue jsonValue when jsonValue.TryGetValue(out string? text) => text,
                _ => null,
            }
            : null;

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

        ChatClientAgentRunOptions runOptions = CloneRunOptions(options);
        ChatOptions chatOptions = runOptions.ChatOptions ?? new ChatOptions();
        runOptions.ChatOptions = chatOptions;

        AIFunction generateTool = this.CreateGenerateA2UIFunction(messageList, ReadAgentState(chatOptions.AdditionalProperties));
        chatOptions.Tools = (chatOptions.Tools ?? Enumerable.Empty<AITool>())
            .Where(t => !string.Equals(t.Name, generateTool.Name, StringComparison.Ordinal))
            .Append(generateTool)
            .ToList();

        return (messageList, runOptions);
    }

    /// <summary>
    /// Clones the caller's run options into a <see cref="ChatClientAgentRunOptions"/> so the
    /// base <see cref="AgentRunOptions"/> members (continuation token, background-response
    /// opt-in, additional properties, response format) survive the per-run
    /// <see cref="ChatOptions"/> augmentation rather than being dropped.
    /// </summary>
    private static ChatClientAgentRunOptions CloneRunOptions(AgentRunOptions? options) =>
        options switch
        {
            ChatClientAgentRunOptions chatRunOptions => (ChatClientAgentRunOptions)chatRunOptions.Clone(),
            not null => new ChatClientAgentRunOptions
            {
                ContinuationToken = options.ContinuationToken,
                AllowBackgroundResponses = options.AllowBackgroundResponses,
                AdditionalProperties = options.AdditionalProperties?.Clone(),
                ResponseFormat = options.ResponseFormat,
            },
            null => new ChatClientAgentRunOptions(),
        };

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
        ChatResponse response = await this._subagentChatClient
            .GetResponseAsync(BuildSubagentMessages(prompt, messages), CreateSubagentOptions(), cancellationToken)
            .ConfigureAwait(false);

        FunctionCallContent? call = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionCallContent>()
            .FirstOrDefault(c => string.Equals(c.Name, A2UIConstants.RenderA2UIToolName, StringComparison.Ordinal));

        return call?.Arguments is { } arguments ? ToJsonObject(arguments) : null;
    }

    /// <summary>Builds the render subagent's message list: the generation prompt plus the conversation.</summary>
    private static List<ChatMessage> BuildSubagentMessages(string prompt, IReadOnlyList<ChatMessage> messages) =>
        [new ChatMessage(ChatRole.System, prompt), .. messages];

    /// <summary>Builds the render subagent's chat options: a forced <c>render_a2ui</c> structured call.</summary>
    private static ChatOptions CreateSubagentOptions() => new()
    {
        Tools = [new RenderA2UIToolDeclaration()],
        ToolMode = ChatToolMode.RequireSpecific(A2UIConstants.RenderA2UIToolName),
    };

    /// <summary>
    /// Reads the AG-UI state slice from the additional properties stamped by the AG-UI
    /// hosting layer: forwarded context entries plus the A2UI component catalog entry
    /// injected by the A2UI middleware.
    /// </summary>
    internal static A2UIAgentState ReadAgentState(AdditionalPropertiesDictionary? properties)
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
            // A message can carry multiple tool results (parallel calls); use the first
            // one with usable textual content rather than only the first item.
            foreach (FunctionResultContent result in message.Contents.OfType<FunctionResultContent>())
            {
                content = result.Result switch
                {
                    string text => text,
                    JsonElement { ValueKind: JsonValueKind.String } element => element.GetString(),
                    JsonElement element => element.GetRawText(),
                    JsonValue value when value.TryGetValue(out string? text) => text,
                    JsonNode node => node.ToJsonString(),
                    _ => null,
                };

                if (!string.IsNullOrEmpty(content))
                {
                    break;
                }
            }
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
    /// The schema-only declaration of the planner-facing <c>generate_a2ui</c> tool, used on
    /// the streaming path so the planner's call surfaces on the update stream instead of
    /// being invoked by the automatic function-invocation layer.
    /// </summary>
    private sealed class GenerateA2UIToolDeclaration : AIFunctionDeclaration
    {
        private static readonly JsonElement s_schema = ParseSchema();

        private readonly string _name;
        private readonly string _description;

        public GenerateA2UIToolDeclaration(string name, string description)
        {
            this._name = name;
            this._description = description;
        }

        private static JsonElement ParseSchema()
        {
            var schema = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject
                {
                    ["intent"] = new JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = A2UIToolDefinitions.IntentArgumentDescription,
                    },
                    ["target_surface_id"] = new JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = A2UIToolDefinitions.TargetSurfaceIdArgumentDescription,
                    },
                    ["changes"] = new JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = A2UIToolDefinitions.ChangesArgumentDescription,
                    },
                },
            };
            using var document = JsonDocument.Parse(schema.ToJsonString());
            return document.RootElement.Clone();
        }

        public override string Name => this._name;

        public override string Description => this._description;

        public override JsonElement JsonSchema => s_schema;
    }

    /// <summary>
    /// The schema-only declaration of the inner <c>render_a2ui</c> structured-output tool.
    /// The subagent is forced to call it; the adapter reads the arguments instead of invoking it.
    /// </summary>
    private sealed class RenderA2UIToolDeclaration : AIFunctionDeclaration
    {
        // Name, description, and schema all derive from the canonical tool definition so
        // the declaration cannot drift from what other A2UI hosts advertise.
        private static readonly (string Description, JsonElement Schema) s_definition = ParseDefinition();

        private static (string Description, JsonElement Schema) ParseDefinition()
        {
            JsonNode function = A2UIToolDefinitions.CreateRenderA2UIToolDefinition()["function"]!;
            using var document = JsonDocument.Parse(function["parameters"]!.ToJsonString());
            return (function["description"]!.GetValue<string>(), document.RootElement.Clone());
        }

        public override string Name => A2UIConstants.RenderA2UIToolName;

        public override string Description => s_definition.Description;

        public override JsonElement JsonSchema => s_definition.Schema;
    }
}
