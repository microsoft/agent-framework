// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
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
    ///Provides a global registry for tracking pending agent tool approvals.
    /// Maps approval request IDs to clean up records that contain weak references
    /// back to per-function pending approval dictionaries, enabling external
    /// code (e.g., <see cref="ClearRejectedAgentToolApprovals"/>) to locate and remove
    /// approval entries from closure-local state.
    /// </summary>
    private static readonly ConcurrentDictionary<string, PendingAgentToolApprovalCleanup> s_pendingAgentToolApprovalCleanups = [];

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

        // PendingAgentToolApproval object used to store sub-agents awaiting approval
        ConcurrentDictionary<string, PendingAgentToolApproval> pendingApprovals = [];

        [Description("Invoke an agent to retrieve some information.")]
        async Task<string> InvokeAgentMetadataAsync(
            [Description("Input query to invoke the agent.")] string query,
            CancellationToken cancellationToken)
        {
            return await InvokeAgentAsync(query, cancellationToken).ConfigureAwait(false) as string ?? string.Empty;
        }

        async Task<object?> InvokeAgentAsync(string query, CancellationToken cancellationToken)
        {
            // Retrieve the current function call context in case this agent is being invoked as a tool by a parent agent.
            var parentFunctionContext = FunctionInvokingChatClient.CurrentContext;

            // Determine if the current invocation matches a parent function call.
            // A match means this agent was invoked as a tool by a parent agent via FunctionInvokingChatClient.
            // The name comparison ensures we're matching the correct tool when the same agent is
            // registered under multiple names.
            FunctionCallContent? parentToolCall =
                parentFunctionContext?.CallContent is { } callContent &&
                string.Equals(callContent.Name, options?.Name, StringComparison.Ordinal)
                    ? CloneFunctionCall(callContent)
                    : null;

            // Propagate any additional properties from the parent agent's run to the child agent if the parent is using a FunctionInvokingChatClient.
            AgentRunOptions? agentRunOptions = FunctionInvokingChatClient.CurrentContext?.Options?.AdditionalProperties is AdditionalPropertiesDictionary dict
                ? new AgentRunOptions { AdditionalProperties = dict }
                : null;

            AgentSession? agentSession = session;
            IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, query)];

            // Resolve the session and input messages for the child agent invocation.
            //
            // Two scenarios are handled when invoked via a parent tool call:
            //  1) Re-invocation after approval: A pending approval record exists for this CallId.
            //     Restore the previous session and convert approval requests into "approved" messages
            //     so the child agent can continue from where it left off.
            //  2) First invocation with no session: No session was provided and there is no
            //     pending approval. Create a fresh session to maintain conversation state across
            //     future re-invocations of this agent-as-tool.
            if (parentToolCall is not null &&
                pendingApprovals.TryRemove(parentToolCall.CallId, out PendingAgentToolApproval? pendingApproval))
            {
                s_pendingAgentToolApprovalCleanups.TryRemove(CreateAgentToolApprovalRequestId(parentToolCall.CallId), out _);

                agentSession = pendingApproval.Session;
                inputMessages = pendingApproval.ApprovalRequests.ConvertAll(
                    request => new ChatMessage(ChatRole.User, [request.CreateResponse(approved: true)]));
            }
            else if (parentToolCall is not null && agentSession is null)
            {
                agentSession = await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            }

            var response = await agent.RunAsync(inputMessages, session: agentSession, options: agentRunOptions, cancellationToken: cancellationToken).ConfigureAwait(false);

            // After running the child agent, check if it requires human approval (HITL).
            // If so, store the approval requests in persistent state keyed by the parent tool call's CallId,
            // and return a special result that surfaces the approval request back to the parent agent's
            // HITL pipeline rather than treating it as a regular tool output.
            if (parentToolCall is not null &&
                agentSession is not null &&
                response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList() is { Count: > 0 } approvalRequests)
            {
                pendingApprovals[parentToolCall.CallId] = new PendingAgentToolApproval(agentSession, approvalRequests);
                string approvalRequestId = CreateAgentToolApprovalRequestId(parentToolCall.CallId);
                s_pendingAgentToolApprovalCleanups[approvalRequestId] = new(parentToolCall.CallId, new(pendingApprovals));

                // Agent-as-tool must surface the child agent's normal HITL pipeline; otherwise
                // ToolApprovalRequestContent from the child would be flattened into a tool result.
                return new AgentToolApprovalRequestResult(
                    new ToolApprovalRequestContent(approvalRequestId, parentToolCall));
            }

            return response.Text;
        }

        options ??= new();
        options.Name ??= SanitizeAgentName(agent.Name);
        options.Description ??= agent.Description;

        return new AgentAIFunction(AIFunctionFactory.Create(InvokeAgentMetadataAsync, options), InvokeAgentAsync);
    }

    internal static bool TryExtractAgentToolApprovalRequests(IList<ChatMessage> messages, out List<ToolApprovalRequestContent> approvalRequests)
    {
        approvalRequests = [];

        foreach (var message in messages)
        {
            foreach (var content in message.Contents)
            {
                if (content is FunctionResultContent { Result: AgentToolApprovalRequestResult result })
                {
                    approvalRequests.Add(result.ApprovalRequest);
                }
            }
        }

        return approvalRequests.Count > 0;
    }

    /// <summary>
    /// Cleans up pending agent tool approvals that have been rejected.
    /// </summary>
    /// <remarks>
    /// When a child agent invoked as a tool requests human approval (HITL), the approval state
    /// is stored in closure-local dictionaries. If the user rejects the approval, those entries
    /// must be cleaned up to prevent stale state from interfering with future invocations.
    /// <para>
    /// This method traverses the messages for rejected <see cref="ToolApprovalResponseContent"/>,
    /// looks up the corresponding entry in <see cref="s_pendingAgentToolApprovalCleanups"/>,
    /// and uses the stored <see cref="WeakReference{T}"/> to reach back into the closure-local
    /// <c>pendingApprovals</c> dictionary and remove the stale approval record.
    /// </para>
    /// </remarks>
    /// <param name="messages">The messages to scan for rejected approval responses.</param>
    internal static void ClearRejectedAgentToolApprovals(IEnumerable<ChatMessage> messages)
    {
        foreach (ToolApprovalResponseContent approvalResponse in messages.SelectMany(m => m.Contents).OfType<ToolApprovalResponseContent>())
        {
            if (!approvalResponse.Approved &&
                s_pendingAgentToolApprovalCleanups.TryRemove(approvalResponse.RequestId, out PendingAgentToolApprovalCleanup? cleanup) &&
                cleanup.PendingApprovals.TryGetTarget(out ConcurrentDictionary<string, PendingAgentToolApproval>? pendingApprovals))
            {
                pendingApprovals.TryRemove(cleanup.CallId, out _);
            }
        }
    }

    private static FunctionCallContent? CloneFunctionCall(FunctionCallContent? functionCall)
    {
        if (functionCall is null)
        {
            return null;
        }

        return functionCall.Arguments is null
            ? new FunctionCallContent(functionCall.CallId, functionCall.Name)
            : new FunctionCallContent(functionCall.CallId, functionCall.Name, new Dictionary<string, object?>(functionCall.Arguments));
    }

    private static string CreateAgentToolApprovalRequestId(string callId) => $"agent_tool_{callId}";

    private sealed record PendingAgentToolApproval(
        AgentSession Session,
        List<ToolApprovalRequestContent> ApprovalRequests);

    private sealed record PendingAgentToolApprovalCleanup(
        string CallId,
        WeakReference<ConcurrentDictionary<string, PendingAgentToolApproval>> PendingApprovals);

    internal sealed record AgentToolApprovalRequestResult(
        ToolApprovalRequestContent ApprovalRequest);

    /// <summary>
    /// A delegating <see cref="AIFunction"/> that separates metadata from execution.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <paramref name="metadataFunction"/> (derived from <c>InvokeAgentMetadataAsync</c>) provides
    /// the AI-visible schema — name, description, and parameter definitions with
    /// <see cref="DescriptionAttribute"/> annotations — while <paramref name="invokeAsync"/>
    /// (the real <c>InvokeAgentAsync</c>) performs the actual agent invocation.
    /// </para>
    /// <para>
    /// This indirection is necessary because <c>InvokeAgentAsync</c> returns <see cref="object"/>,
    /// which can be either a <see cref="string"/> result or an
    /// <see cref="AgentToolApprovalRequestResult"/> for HITL approval. By overriding
    /// <see cref="InvokeCoreAsync"/> and calling <paramref name="invokeAsync"/> directly,
    /// we preserve the original return type rather than letting the base class serialize
    /// it, ensuring <see cref="AgentToolApprovalRequestResult"/> passes through intact.
    /// </para>
    /// </remarks>
    /// <param name="metadataFunction">The function providing AI-visible metadata and schema.</param>
    /// <param name="invokeAsync">The delegate that performs the actual agent invocation.</param>
    private sealed class AgentAIFunction(
        AIFunction metadataFunction,
        Func<string, CancellationToken, Task<object?>> invokeAsync) : DelegatingAIFunction(metadataFunction)
    {
        protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            if (!arguments.TryGetValue("query", out object? queryValue) || queryValue is null)
            {
                throw new ArgumentException("The required 'query' argument was not provided.", nameof(arguments));
            }

            string query = queryValue is JsonElement { ValueKind: JsonValueKind.String } jsonString
                ? jsonString.GetString()!
                : queryValue.ToString() ?? string.Empty;

            return await invokeAsync(query, cancellationToken).ConfigureAwait(false);
        }
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
