// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents the context for a callback during the invocation of an agent function.
/// </summary>
/// <remarks>This context provides information about the agent and the function invocation, as well as a
/// cancellation token to monitor for cancellation requests during the callback execution. It is intended for use within
/// the lifecycle of an agent function invocation.</remarks>
public class AgentFunctionInvocationCallbackContext : CallbackContext
{
    internal AgentFunctionInvocationCallbackContext(AIAgent agent, FunctionInvocationContext functionInvocationContext, CancellationToken cancellationToken) : base(agent, cancellationToken)
    {
        this._functionInvocationContext = functionInvocationContext;
    }

    /// <summary>
    /// A nop function used to allow <see cref="Function"/> to be non-nullable. Default instances of
    /// <see cref="FunctionInvocationContext"/> start with this as the target function.
    /// </summary>
    private readonly FunctionInvocationContext _functionInvocationContext;

    /// <summary>Gets or sets the AI function to be invoked.</summary>
    public AIFunction Function
    {
        get => this._functionInvocationContext.Function;
        set => this._functionInvocationContext.Function = Throw.IfNull(value);
    }

    /// <summary>Gets or sets the arguments associated with this invocation.</summary>
    public AIFunctionArguments Arguments
    {
        get => this._functionInvocationContext.Arguments;
        set => this._functionInvocationContext.Arguments = Throw.IfNull(value);
    }

    /// <summary>Gets or sets the function call content information associated with this invocation.</summary>
    public FunctionCallContent CallContent
    {
        get => this._functionInvocationContext.CallContent;
        set => this._functionInvocationContext.CallContent = Throw.IfNull(value);
    }

    /// <summary>Gets or sets the chat contents associated with the operation that initiated this function call request.</summary>
    public IList<ChatMessage> Messages
    {
        get => this._functionInvocationContext.Messages;
        set => this._functionInvocationContext.Messages = Throw.IfNull(value);
    }

    /// <summary>Gets or sets the chat options associated with the operation that initiated this function call request.</summary>
    public ChatOptions? Options
    {
        get => this._functionInvocationContext.Options;
        set => this._functionInvocationContext.Options = value;
    }

    /// <summary>Gets or sets the number of this iteration with the underlying client.</summary>
    /// <remarks>
    /// The initial request to the client that passes along the chat contents provided to the <see cref="FunctionInvokingChatClient"/>
    /// is iteration 1. If the client responds with a function call request, the next request to the client is iteration 2, and so on.
    /// </remarks>
    public int Iteration
    {
        get => this._functionInvocationContext.Iteration;
        set => this._functionInvocationContext.Iteration = value;
    }

    /// <summary>Gets or sets the index of the function call within the iteration.</summary>
    /// <remarks>
    /// The response from the underlying client may include multiple function call requests.
    /// This index indicates the position of the function call within the iteration.
    /// </remarks>
    public int FunctionCallIndex
    {
        get => this._functionInvocationContext.FunctionCallIndex;
        set => this._functionInvocationContext.FunctionCallIndex = value;
    }

    /// <summary>Gets or sets the total number of function call requests within the iteration.</summary>
    /// <remarks>
    /// The response from the underlying client might include multiple function call requests.
    /// This count indicates how many there were.
    /// </remarks>
    public int FunctionCount
    {
        get => this._functionInvocationContext.FunctionCount;
        set => this._functionInvocationContext.FunctionCount = value;
    }

    /// <summary>Gets or sets a value indicating whether to terminate the request.</summary>
    /// <remarks>
    /// In response to a function call request, the function might be invoked, its result added to the chat contents,
    /// and a new request issued to the wrapped client. If this property is set to <see langword="true"/>, that subsequent request
    /// will not be issued and instead the loop immediately terminated rather than continuing until there are no
    /// more function call requests in responses.
    /// <para>
    /// If multiple function call requests are issued as part of a single iteration (a single response from the inner <see cref="IChatClient"/>),
    /// setting <see cref="Terminate" /> to <see langword="true" /> may also prevent subsequent requests within that same iteration from being processed.
    /// </para>
    /// </remarks>
    public bool Terminate
    {
        get => this._functionInvocationContext.Terminate;
        set => this._functionInvocationContext.Terminate = value;
    }

    /// <summary>
    /// Gets or sets a value indicating whether the function invocation is occurring as part of a
    /// <see cref="IChatClient.GetStreamingResponseAsync"/> call as opposed to a <see cref="IChatClient.GetResponseAsync"/> call.
    /// </summary>
    public bool IsStreaming
    {
        get => this._functionInvocationContext.IsStreaming;
        set => this._functionInvocationContext.IsStreaming = value;
    }

    /// <summary>
    /// Gets or sets the result of the function invocation.
    /// </summary>
    public object? Result { get; set; }
}
