// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
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

        var gate = new object();
        var pendingApprovalsByParentCallId = new Dictionary<string, PendingAgentToolApproval>(StringComparer.Ordinal);

        [Description("Invoke an agent to retrieve some information.")]
        async Task<string> InvokeAgentAsync(
            [Description("Input query to invoke the agent.")] string query,
            CancellationToken cancellationToken)
        {
            // Get the parent function call context.
            var functionInvocationContext = FunctionInvokingChatClient.CurrentContext;
            var parentFunctionCall = functionInvocationContext?.CallContent;

            // Propagate any additional properties from the parent agent's run to the child agent if the parent is using a FunctionInvokingChatClient.
            AgentRunOptions? agentRunOptions = functionInvocationContext?.Options?.AdditionalProperties is AdditionalPropertiesDictionary dict
                ? new AgentRunOptions { AdditionalProperties = dict }
                : null;

            PendingAgentToolApproval? pendingApproval = null;
            if (parentFunctionCall is not null)
            {
                lock (gate)
                {
                    if (pendingApprovalsByParentCallId.TryGetValue(parentFunctionCall.CallId, out pendingApproval))
                    {
                        pendingApprovalsByParentCallId.Remove(parentFunctionCall.CallId);
                    }
                }
            }

            AgentResponse response;
            if (pendingApproval is not null)
            {
                var approved = GetApprovalForParentCall(functionInvocationContext, parentFunctionCall);
                var approvalResponseMessages = CreateChildApprovalResponseMessages(pendingApproval, approved);
                response = await agent.RunAsync(approvalResponseMessages, session: pendingApproval.Session, options: agentRunOptions, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            else
            {
                AgentSession? invocationSession = session ?? await TryCreateSessionAsync(agent, cancellationToken).ConfigureAwait(false);
                response = await agent.RunAsync(query, session: invocationSession, options: agentRunOptions, cancellationToken: cancellationToken).ConfigureAwait(false);

                if (parentFunctionCall is not null)
                {
                    var childApprovalRequests = response.Messages
                        .SelectMany(static message => message.Contents)
                        .OfType<ToolApprovalRequestContent>()
                        .ToList();

                    if (childApprovalRequests.Count > 0)
                    {
                        lock (gate)
                        {
                            pendingApprovalsByParentCallId[parentFunctionCall.CallId] =
                                new PendingAgentToolApproval(invocationSession, childApprovalRequests);
                        }

                        var parentApprovalRequest = new ToolApprovalRequestContent(
                            childApprovalRequests[0].RequestId,
                            parentFunctionCall);

                        ToolApprovalRequestPropagator.Attach(parentFunctionCall, [parentApprovalRequest]);

                        if (functionInvocationContext is not null)
                        {
                            functionInvocationContext.Terminate = true;
                        }
                    }
                }
            }

            return response.Text;
        }

        options ??= new();
        options.Name ??= SanitizeAgentName(agent.Name);
        options.Description ??= agent.Description;

        return AIFunctionFactory.Create(InvokeAgentAsync, options);
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

    private static async ValueTask<AgentSession?> TryCreateSessionAsync(AIAgent agent, CancellationToken cancellationToken)
    {
        try
        {
            return await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (NotImplementedException)
        {
            return null;
        }
        catch (NotSupportedException)
        {
            return null;
        }
    }

    private static ToolApprovalResponseContent? GetApprovalForParentCall(FunctionInvocationContext? context, FunctionCallContent? parentFunctionCall)
    {
        if (context?.Messages is null || parentFunctionCall is null)
        {
            return null;
        }

        return context.Messages
            .SelectMany(static message => message.Contents)
            .OfType<ToolApprovalResponseContent>()
            .LastOrDefault(response => response.ToolCall is FunctionCallContent functionCall &&
                string.Equals(functionCall.CallId, parentFunctionCall.CallId, StringComparison.Ordinal));
    }

    private static List<ChatMessage> CreateChildApprovalResponseMessages(
        PendingAgentToolApproval pendingApproval,
        ToolApprovalResponseContent? parentApproval)
    {
        bool approved = parentApproval?.Approved ?? true;
        string? reason = parentApproval?.Reason;

        return
        [
            new(ChatRole.User, [.. pendingApproval.ChildApprovalRequests.Select(request => request.CreateResponse(approved, reason))])
        ];
    }

    private sealed class PendingAgentToolApproval(
        AgentSession? session,
        IReadOnlyList<ToolApprovalRequestContent> childApprovalRequests)
    {
        public AgentSession? Session { get; } = session;

        public IReadOnlyList<ToolApprovalRequestContent> ChildApprovalRequests { get; } = childApprovalRequests;
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
