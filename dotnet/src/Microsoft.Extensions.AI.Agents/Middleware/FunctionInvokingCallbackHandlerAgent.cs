// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Internal agent decorator that adds function invocation callback middleware logic.
/// </summary>
internal sealed class FunctionInvokingCallbackHandlerAgent : DelegatingAIAgent
{
    private readonly Func<FunctionInvocationContext?, Func<AIFunctionArguments, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> _func;

    internal FunctionInvokingCallbackHandlerAgent(AIAgent innerAgent, Func<FunctionInvocationContext?, Func<AIFunctionArguments, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> func) : base(innerAgent)
    {
        this._func = func;
    }

    public override Task<AgentRunResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, thread, this.WithAIFunctionMiddleware(options), cancellationToken);

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, thread, this.WithAIFunctionMiddleware(options), cancellationToken);

    // Decorate options to add the middleware function
    private AgentRunOptions? WithAIFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is ChatClientAgentRunOptions aco && aco.ChatOptions?.Tools is { Count: > 0 } tools)
        {
            // Clone the options to avoid modifying the original
            var chatOptions = aco.ChatOptions.Clone();
            chatOptions.Tools = [.. chatOptions.Tools!.Select(tool => tool is AIFunction aiFunction ? new MiddlewareFunction(aiFunction, this._func) : tool)];

            return new ChatClientAgentRunOptions(chatOptions);
        }

        return options;
    }

    private sealed class MiddlewareFunction(AIFunction innerFunction, Func<FunctionInvocationContext?, Func<AIFunctionArguments, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> next) : DelegatingAIFunction(innerFunction)
    {
        protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
            => next(FunctionInvokingChatClient.CurrentContext, base.InvokeCoreAsync, cancellationToken);
    }
}
