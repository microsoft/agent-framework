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
    private readonly Func<AgentFunctionInvocationCallbackContext?, Func<AgentFunctionInvocationCallbackContext, Task>, Task> _callbackFunc;

    internal FunctionInvokingCallbackHandlerAgent(AIAgent innerAgent, Func<AgentFunctionInvocationCallbackContext?, Func<AgentFunctionInvocationCallbackContext, Task>, Task> callbackFunc) : base(innerAgent)
    {
        this._callbackFunc = callbackFunc;
    }

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, thread, this.WithAIFunctionMiddleware(options), cancellationToken);

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, thread, this.WithAIFunctionMiddleware(options), cancellationToken);

    // Decorate options to add the middleware function
    private AgentRunOptions? WithAIFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is ChatClientAgentRunOptions aco && aco.ChatOptions?.Tools is { Count: > 0 } tools)
        {
            // Clone the options to avoid modifying the original
            var chatOptions = aco.ChatOptions.Clone();
            chatOptions.Tools = [.. chatOptions.Tools!.Select(tool => tool is AIFunction aiFunction ? new MiddlewareFunction(this, aiFunction, this._callbackFunc) : tool)];

            return new ChatClientAgentRunOptions(chatOptions);
        }

        return options;
    }

    private sealed class MiddlewareFunction(AIAgent agent, AIFunction innerFunction, Func<AgentFunctionInvocationCallbackContext?, Func<AgentFunctionInvocationCallbackContext, Task>, Task> next) : DelegatingAIFunction(innerFunction)
    {
        protected async override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            if (FunctionInvokingChatClient.CurrentContext is null)
            {
                // If there's no current function invocation context, there's nothing to do.
                return null;
            }

            var context = new AgentFunctionInvocationCallbackContext(agent, FunctionInvokingChatClient.CurrentContext, cancellationToken);

            await next(context, CoreLogicAsync).ConfigureAwait(false);

            return context.Result;

            async Task CoreLogicAsync(AgentFunctionInvocationCallbackContext ctx)
            {
                var result = await base.InvokeCoreAsync(ctx.Arguments, ctx.CancellationToken).ConfigureAwait(false);

                ctx.Result = result;
            }
        }
    }
}
