// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
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
    /// </param>
    /// <returns>
    /// An <see cref="IChatClient"/> that can be used anywhere the <see cref="IChatClient"/> abstraction is consumed,
    /// such as in a <see cref="ChatClientBuilder"/> pipeline.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// By default the returned client is stateless: no <see cref="AgentSession"/> is used, so every call must supply the
    /// full conversation history, just as when calling an <see cref="IChatClient"/> directly.
    /// </para>
    /// <para>
    /// If a <paramref name="session"/> is provided, the returned client is stateful, referencing both the
    /// <paramref name="agent"/> and the <paramref name="session"/>. Avoid using such a client concurrently in multiple
    /// conversations or in requests where parallel calls may result in concurrent usage of the session, as that could
    /// lead to undefined and unpredictable behavior. In particular, do not register a session-bound client as a shared
    /// or singleton service that serves multiple users: concurrent use is unsupported, and every caller appends to and
    /// reads from the same conversation, so history bleeds across them. Because a bound session already accumulates the
    /// conversation history, callers should send only the new messages on each call rather than the full history, which
    /// would otherwise be duplicated.
    /// </para>
    /// <para>
    /// Any <see cref="ChatOptions"/> supplied to the returned client are passed to the agent as
    /// <see cref="ChatClientAgentRunOptions"/>. Agents that understand that type, such as <see cref="ChatClientAgent"/>,
    /// honor those options; other agent implementations may ignore them. The exception is
    /// <see cref="ChatOptions.ResponseFormat"/>, which is additionally copied to <see cref="AgentRunOptions.ResponseFormat"/>
    /// and so may be honored by any agent implementation.
    /// </para>
    /// <para>
    /// For agents that honor <see cref="ChatClientAgentRunOptions"/>, this means a caller supplying
    /// <see cref="ChatOptions"/> can add tools to those configured on the agent and append to its instructions; the
    /// collections are unioned and the instructions concatenated rather than replaced. When requests originate from an
    /// untrusted caller, do not pass caller-supplied <see cref="ChatOptions"/> through unfiltered. Follow the
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
    /// bound <paramref name="session"/> throws, as does supplying a <see cref="ChatOptions.ConversationId"/> that
    /// differs from the conversation id already held by a bound <paramref name="session"/>.
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
    public static IChatClient AsIChatClient(this AIAgent agent, AgentSession? session = null)
    {
        Throw.IfNull(agent);

        return new AIAgentChatClient(agent, session);
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
