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
internal sealed class FunctionCallMiddlewareAgent : DelegatingAIAgent
{
    private readonly Func<AgentFunctionInvocationContext?, Func<AgentFunctionInvocationContext, Task>, Task> _callbackFunc;

    internal FunctionCallMiddlewareAgent(AIAgent innerAgent, Func<AgentFunctionInvocationContext?, Func<AgentFunctionInvocationContext, Task>, Task> callbackFunc) : base(innerAgent)
    {
        this._callbackFunc = callbackFunc;
    }

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, thread, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, thread, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    // Decorate options to add the middleware function
    private AgentRunOptions? AgentRunOptionsWithFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is ChatClientAgentRunOptions aco && aco.ChatOptions?.Tools is { Count: > 0 } tools)
        {
            // Creates an immutable agent run options 
            var newAgentOptions = new ChatClientAgentRunOptions(aco.ChatOptions.Clone());

            if (aco.AIToolsTransformer is null)
            {
                newAgentOptions.AIToolsTransformer = LocalTransformerImpl;
            }
            else
            {
                var original = aco.AIToolsTransformer;

                newAgentOptions.AIToolsTransformer = tools => LocalTransformerImpl(original(tools));
            }

            return newAgentOptions;

            IList<AITool>? LocalTransformerImpl(IList<AITool>? tools)
                => tools?.Select(tool => tool is AIFunction aiFunction
                    ? new MiddlewareEnabledFunction(this, aiFunction, this._callbackFunc)
                    : tool)
                .ToList();
        }

        return options;
    }

    private sealed class MiddlewareEnabledFunction(AIAgent agent, AIFunction innerFunction, Func<AgentFunctionInvocationContext?, Func<AgentFunctionInvocationContext, Task>, Task> next) : DelegatingAIFunction(innerFunction)
    {
        protected async override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            if (FunctionInvokingChatClient.CurrentContext is null)
            {
                // If there's no current function invocation context, there's nothing to do.
                return null;
            }

            var context = new AgentFunctionInvocationContext(agent, FunctionInvokingChatClient.CurrentContext, cancellationToken);

            await next(context, CoreLogicAsync).ConfigureAwait(false);

            return context.FunctionResult;

            async Task CoreLogicAsync(AgentFunctionInvocationContext ctx)
            {
                var result = await base.InvokeCoreAsync(ctx.Arguments, ctx.CancellationToken).ConfigureAwait(false);

                ctx.FunctionResult = result;
            }
        }
    }
}
