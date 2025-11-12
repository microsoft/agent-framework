// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Base class for workflow agent providers.
/// </summary>
public abstract class WorkflowAgentProvider
{
    /// <summary>
    /// Gets or sets a collection of additional tools an agent is able to automatically invoke.
    /// If an agent is configured with a function tool that is not available, a <see cref="RequestPort"/> is executed
    /// that provides an <see cref="ExternalInputRequest"/> that describes the function calls requested.  The caller may
    /// then respond with a corrsponding <see cref="ExternalInputResponse"/> that includes the results of the function calls.
    /// </summary>
    /// <remarks>
    /// These will not impact the requests sent to the model by the <see cref="FunctionInvokingChatClient"/>.
    /// </remarks>
    public IEnumerable<AIFunction>? Functions { get; init; }

    /// <summary>
    /// Gets or sets a value indicating whether to allow concurrent invocation of functions.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if multiple function calls can execute in parallel.
    /// <see langword="false"/> if function calls are processed serially.
    /// The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// An individual response from the inner client might contain multiple function call requests.
    /// By default, such function calls are processed serially. Set <see cref="AllowConcurrentInvocation"/> to
    /// <see langword="true"/> to enable concurrent invocation such that multiple function calls can execute in parallel.
    /// </remarks>
    public bool AllowConcurrentInvocation { get; init; }

    /// <summary>
    /// Gets or sets a flag to indicate whether a single response is allowed to include multiple tool calls.
    /// If <see langword="false"/>, the <see cref="IChatClient"/> is asked to return a maximum of one tool call per request.
    /// If <see langword="true"/>, there is no limit.
    /// If <see langword="null"/>, the provider may select its own default.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When used with function calling middleware, this does not affect the ability to perform multiple function calls in sequence.
    /// It only affects the number of function calls within a single iteration of the function calling loop.
    /// </para>
    /// <para>
    /// The underlying provider is not guaranteed to support or honor this flag. For example it may choose to ignore it and return multiple tool calls regardless.
    /// </para>
    /// </remarks>
    public bool AllowMultipleToolCalls { get; init; }

    /// <summary>
    /// Asynchronously creates a new conversation and returns its unique identifier.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The conversation identifier</returns>
    public abstract Task<string> CreateConversationAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Creates a new message in the specified conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="conversationMessage">The message being added.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public abstract Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a specific message from a conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="messageId">The identifier of the target message.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The requested message</returns>
    public abstract Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Asynchronously retrieves an AI agent by its unique identifier.
    /// </summary>
    /// <param name="agentId">The unique identifier of the AI agent to retrieve. Cannot be null or empty.</param>
    /// <param name="agentVersion">An optional agent version.</param>
    /// <param name="conversationId">Optional identifier of the target conversation.</param>
    /// <param name="messages">The messages to include in the invocation.</param>
    /// <param name="inputArguments">Optional input arguments for agents that provide support.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>Asynchronous set of <see cref="AgentRunResponseUpdate"/>.</returns>
    public abstract IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(
        string agentId,
        string? agentVersion,
        string? conversationId,
        IEnumerable<ChatMessage>? messages,
        IDictionary<string, object?>? inputArguments,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a set of messages from a conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="limit">A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.</param>
    /// <param name="after">A cursor for use in pagination. after is an object ID that defines your place in the list.</param>
    /// <param name="before">A cursor for use in pagination. before is an object ID that defines your place in the list.</param>
    /// <param name="newestFirst">Provide records in descending order when true.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The requested messages</returns>
    public abstract IAsyncEnumerable<ChatMessage> GetMessagesAsync(
        string conversationId,
        int? limit = null,
        string? after = null,
        string? before = null,
        bool newestFirst = false,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Utility method to convert a dictionary of input arguments to a JsonNode.
    /// </summary>
    /// <param name="inputArguments">The dictionary of input arguments.</param>
    /// <returns>A JsonNode representing the input arguments.</returns>
    protected static JsonNode ConvertDictionaryToJson(IDictionary<string, object?> inputArguments)
    {
        return inputArguments.ToFormula().ToJson();
    }
}
