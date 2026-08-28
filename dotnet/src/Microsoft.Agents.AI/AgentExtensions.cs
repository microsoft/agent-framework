// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extensions for <see cref="AIAgent"/>.
/// </summary>
public static partial class AIAgentExtensions
{
    /// <summary>
    /// Creates a new <see cref="AIAgentBuilder"/> using the specified agent as the foundation for the builder pipeline.
    /// </summary>
    /// <param name="innerAgent">The <see cref="AIAgent"/> instance to use as the inner agent.</param>
    /// <returns>A new <see cref="AIAgentBuilder"/> instance configured with the specified inner agent.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This method provides a convenient way to convert an existing <see cref="AIAgent"/> instance into
    /// a builder pattern, enabling easily wrapping the agent in layers of additional functionality.
    /// It is functionally equivalent to using the <see cref="AIAgentBuilder(AIAgent)"/> constructor directly,
    /// but provides a more fluent API when working with existing agent instances.
    /// </remarks>
    public static AIAgentBuilder AsBuilder(this AIAgent innerAgent)
    {
        _ = Throw.IfNull(innerAgent);

        return new AIAgentBuilder(innerAgent);
    }

    /// <summary>
    /// Creates an <see cref="AIFunction"/> that runs the provided <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent"/> to be represented as an invocable function.</param>
    /// <param name="options">
    /// Optional metadata to customize the function representation, such as name and description.
    /// If not provided, defaults will be inferred from the agent's properties.
    /// </param>
    /// <param name="session">
    /// Optional <see cref="AgentSession"/> to use for function invocations. If not provided, a new session
    /// will be created for each function call, which may not preserve conversation context.
    /// </param>
    /// <returns>
    /// An <see cref="AIFunction"/> that can be used as a tool by other agents or AI models to invoke this agent.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This extension method enables agents to participate in function calling scenarios, where they can be
    /// invoked as tools by other agents or AI models. The resulting function accepts a query string as input and
    /// returns the agent's response as a string, making it compatible with standard function calling interfaces
    /// used by AI models.
    /// </para>
    /// <para>
    /// The resulting <see cref="AIFunction"/> is stateful, referencing both the <paramref name="agent"/> and the optional
    /// <paramref name="session"/>. Especially if a specific session is provided, avoid using the resulting function concurrently
    /// in multiple conversations or in requests where the parallel function calls may result in concurrent usage of the session,
    /// as that could lead to undefined and unpredictable behavior.
    /// </para>
    /// </remarks>
    public static AIFunction AsAIFunction(this AIAgent agent, AIFunctionFactoryOptions? options = null, AgentSession? session = null)
    {
        Throw.IfNull(agent);

        [Description("Invoke an agent to retrieve some information.")]
        async Task<string> InvokeAgentAsync(
            [Description("Input query to invoke the agent.")] string query,
            CancellationToken cancellationToken)
        {
            // Propagate any additional properties from the parent agent's run to the child agent if the parent is using a FunctionInvokingChatClient.
            AgentRunOptions? agentRunOptions = FunctionInvokingChatClient.CurrentContext?.Options?.AdditionalProperties is AdditionalPropertiesDictionary dict
                ? new AgentRunOptions { AdditionalProperties = dict }
                : null;

            var response = await agent.RunAsync(query, session: session, options: agentRunOptions, cancellationToken: cancellationToken).ConfigureAwait(false);
            return response.Text;
        }

        options ??= new();
        options.Name ??= SanitizeAgentName(agent.Name);
        options.Description ??= agent.Description;

        return AIFunctionFactory.Create(InvokeAgentAsync, options);
    }

    /// <summary>
    /// Creates an <see cref="IChatClient"/> that delegates its operations to the provided <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent"/> to be represented as an <see cref="IChatClient"/>.</param>
    /// <param name="session">
    /// Optional <see cref="AgentSession"/> to use for every request made through the returned client. If not provided,
    /// each request is made without a session and the caller is responsible for supplying the conversation history.
    /// The agent would also not be able to retain any state or memories across invocations.
    /// </param>
    /// <param name="conversationId">
    /// Optional conversation id for the returned client to report on its responses, representing the active session.
    /// May only be supplied together with a <paramref name="session"/>, and must not be empty or whitespace; if
    /// omitted, but a session is supplied, an id unique to the returned client is generated. Supply one when the id
    /// has to be recognizable outside the process, for example when it is persisted or routed on.
    /// </param>
    /// <returns>
    /// An <see cref="IChatClient"/> that can be used anywhere the <see cref="IChatClient"/> abstraction is consumed,
    /// such as in a <see cref="ChatClientBuilder"/> pipeline.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">
    /// <paramref name="conversationId"/> is non-<see langword="null"/> and no <paramref name="session"/> is supplied,
    /// or <paramref name="conversationId"/> is empty, whitespace, or a framework reserved value.
    /// </exception>
    /// <remarks>
    /// <para>
    /// By default the returned client is stateless: no <see cref="AgentSession"/> is used, so every call must supply the
    /// full conversation history, just as when calling an <see cref="IChatClient"/> directly. Nothing about the
    /// conversation id is interpreted in this mode; it is the caller's to set and flows through untouched in both
    /// directions.
    /// </para>
    /// <para>
    /// If a <paramref name="session"/> is provided, the returned client is stateful, referencing both the
    /// <paramref name="agent"/> and the <paramref name="session"/>. The session stores the history, which is exactly
    /// what a non-null <see cref="ChatResponse.ConversationId"/> signals under the <see cref="IChatClient"/> contract,
    /// so the returned client reports one on every response. Callers should follow it: send only the new messages on
    /// each subsequent call, along with the reported id, rather than resending a history the session is already
    /// accumulating. The reported id is <paramref name="conversationId"/>, or the generated one when that was omitted,
    /// and it never changes for the life of the client — the same value on every response and every streamed update,
    /// from both entry points, whatever the underlying service does with its own ids. Echoing it back is accepted: it
    /// is stripped before the agent sees it, which restores the as-if-absent semantics of the first turn, and a fixed
    /// bound session cannot fork, so the conversation simply continues. Any other conversation id is rejected with an
    /// <see cref="InvalidOperationException"/>, which for <see cref="IChatClient.GetStreamingResponseAsync"/> surfaces
    /// from the call itself rather than when the returned sequence is enumerated.
    /// </para>
    /// <para>
    /// So that the conversation id is reported even when there is nothing else to report, a session-bound stream that
    /// produces no updates still yields a single update carrying only that id. Aggregating such a stream with
    /// <see cref="ChatResponseExtensions.ToChatResponse(System.Collections.Generic.IEnumerable{ChatResponseUpdate})"/>
    /// therefore produces one empty assistant message rather than an empty message list.
    /// </para>
    /// <para>
    /// A session-bound client supports one in-flight request at a time. Concurrent calls over the same bound session
    /// race on its history state, which is not synchronized, so the caller must serialize them. In particular, do not
    /// register a session-bound client as a shared or singleton service that serves multiple users: concurrent use is
    /// unsupported, and every caller appends to and reads from the same conversation, so history bleeds across them.
    /// </para>
    /// <para>
    /// Service-side conversation ids are not surfaced in this mode at all. A response or streamed update that arrives
    /// carrying one is copied and re-stamped with the client's id, so the id the service minted is replaced rather than
    /// forwarded, and the <paramref name="session"/>'s own id is not reported either. The service's id is consequently
    /// not accepted as input: only the id this client hands out is. The <paramref name="session"/> tracks the service
    /// conversation internally, so callers that need to address a specific service conversation should bind a session
    /// obtained from <see cref="ChatClientAgent.CreateSessionAsync(string, CancellationToken)"/>.
    /// </para>
    /// <para>
    /// Any <see cref="ChatOptions"/> supplied to the returned client are passed to the agent as
    /// <see cref="ChatClientAgentRunOptions"/>. Agents that understand that type, such as <see cref="ChatClientAgent"/>,
    /// honor those options; other agent implementations may ignore them. The exception is
    /// <see cref="ChatOptions.ResponseFormat"/>, which is additionally copied to <see cref="AgentRunOptions.ResponseFormat"/>
    /// and so may be honored by any agent implementation. Except where a conversation id has to be stripped, the
    /// caller's <see cref="ChatOptions"/> instance is handed to the agent by reference rather than copied.
    /// <see cref="ChatClientAgent"/> clones it before use, but a custom <see cref="AIAgent"/> receives the caller's own
    /// object and must treat it as read-only.
    /// </para>
    /// <para>
    /// For agents that honor <see cref="ChatClientAgentRunOptions"/>, this means a caller supplying
    /// <see cref="ChatOptions"/> can add tools to those configured on the agent and append to its instructions; the
    /// collections are unioned and the instructions concatenated rather than replaced. <see cref="ChatOptions.ConversationId"/>
    /// deserves the same care: a stateless client forwards it verbatim, so an untrusted caller could name a service-side
    /// conversation of its choosing and have the agent read and extend it under the host's credentials. When requests
    /// originate from an untrusted caller, do not pass caller-supplied <see cref="ChatOptions"/> through unfiltered. Follow the
    /// default-closed pattern used by the <c>Microsoft.Agents.AI.Hosting.OpenAI</c> package, whose
    /// <c>RunOptionsFactory</c> defaults to <c>RejectRequestSettings</c> and rejects caller-supplied settings unless the
    /// host explicitly maps the ones it chooses to honor.
    /// </para>
    /// <para>
    /// Background and continuation responses are not supported through the returned client. A continuation token
    /// obtained from a <see cref="ChatResponse"/> is the underlying service's raw token rather than the agent's wrapped
    /// token, so it does not round-trip: passing it back via <see cref="ChatOptions.ContinuationToken"/> causes
    /// <see cref="ChatClientAgent"/> to reject it during token validation.
    /// </para>
    /// <para>
    /// Some option combinations cause the underlying agent to throw an <see cref="InvalidOperationException"/> at run
    /// time. With <see cref="ChatClientAgent"/>, requesting <see cref="ChatOptions.AllowBackgroundResponses"/> without a
    /// bound <paramref name="session"/> throws. To converse over an existing service conversation, bind a session
    /// obtained from <see cref="ChatClientAgent.CreateSessionAsync(string, CancellationToken)"/> rather than passing its
    /// id through <see cref="ChatOptions.ConversationId"/>.
    /// </para>
    /// <para>
    /// Calling this method on a <see cref="ChatClientAgent"/> returns an adapter over the full agent pipeline, including
    /// its instructions, tools, chat history management, and any middleware. An unkeyed
    /// <see cref="IChatClient.GetService"/> request for <see cref="IChatClient"/> returns the adapter itself, not the
    /// agent's inner client. Keyed requests, and requests for other service types, are forwarded to
    /// <see cref="AIAgent.GetService(Type, object?)"/> and may therefore return the inner client.
    /// </para>
    /// <para>
    /// The returned client does not own the lifetime of the <paramref name="agent"/> or the <paramref name="session"/>;
    /// disposing it does not dispose either of them.
    /// </para>
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public static IChatClient AsIChatClient(this AIAgent agent, AgentSession? session = null, string? conversationId = null)
    {
        Throw.IfNull(agent);

        if (conversationId is not null)
        {
            if (session is null)
            {
                // Without a session the caller owns the history, so there is no stored conversation for an id to name.
                Throw.ArgumentException(
                    nameof(conversationId),
                    $"A conversation id is only meaningful for a session-bound client, so it may not be supplied without a {nameof(session)}.");
            }

            // An empty or whitespace id is reported verbatim on every response, where callers that test it with
            // string.IsNullOrEmpty read it as "no stored history" and resend the full history the session already has.
            _ = Throw.IfNullOrWhitespace(conversationId);

            if (conversationId == PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId)
            {
                // The framework stamps this value to mark history as handled in process. Reporting it as this
                // client's conversation id would make an internal marker indistinguishable from a real conversation.
                Throw.ArgumentException(
                    nameof(conversationId),
                    $"The conversation id '{conversationId}' is reserved for internal use and cannot be used as a client-supplied conversation id.");
            }
        }

        return new AIAgentChatClient(agent, session, conversationId);
    }

    /// <summary>
    /// Removes characters from AI agent name that shouldn't be used in an AI function name.
    /// </summary>
    /// <param name="agentName">The AI agent name to sanitize.</param>
    /// <returns>
    /// The sanitized agent name with invalid characters replaced by underscores, or <c>null</c> if the input is <c>null</c>.
    /// </returns>
    private static string? SanitizeAgentName(string? agentName)
    {
        return agentName is null
            ? agentName
            : InvalidNameCharsRegex().Replace(agentName, "_");
    }

    /// <summary>Regex that flags any character other than ASCII digits or letters.</summary>
#if NET
    [GeneratedRegex("[^0-9A-Za-z]+")]
    private static partial Regex InvalidNameCharsRegex();
#else
    private static Regex InvalidNameCharsRegex() => s_invalidNameCharsRegex;
    private static readonly Regex s_invalidNameCharsRegex = new("[^0-9A-Za-z]+", RegexOptions.Compiled);
#endif
}
