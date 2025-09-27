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
/// Internal agent decorator that adds function invocation middleware logic.
/// </summary>
internal sealed class FunctionInvocationDelegatingAgent : DelegatingAIAgent
{
    private readonly Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> _delegateFunc;

    internal FunctionInvocationDelegatingAgent(AIAgent innerAgent, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> delegateFunc) : base(innerAgent)
    {
        this._delegateFunc = delegateFunc;
    }

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, thread, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, thread, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    // Decorate options to add the middleware function
    private AgentRunOptions? AgentRunOptionsWithFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is ChatClientAgentRunOptions aco)
        {
            // Creates an immutable agent run options 
            var newAgentOptions = new ChatClientAgentRunOptions(aco.ChatOptions?.Clone());

            if (aco.AIToolsTransformer is null)
            {
                newAgentOptions.AIToolsTransformer = LocalTransformer;
            }
            else
            {
                var original = aco.AIToolsTransformer;

                newAgentOptions.AIToolsTransformer = tools => LocalTransformer(original(tools));
            }

            return newAgentOptions;

            IList<AITool>? LocalTransformer(IList<AITool>? tools)
                => tools?.Select(tool => tool is AIFunction aiFunction
                    ? aiFunction is ApprovalRequiredAIFunction approvalRequiredAiFunction
                    ? new ApprovalRequiredAIFunction(new MiddlewareEnabledFunction(this, approvalRequiredAiFunction, this._delegateFunc))
                    : new MiddlewareEnabledFunction(this.InnerAgent, aiFunction, this._delegateFunc)
                    : tool)
                .ToList();
        }

        return options;
    }

    private sealed class MiddlewareEnabledFunction(AIAgent innerAgent, AIFunction innerFunction, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> next) : DelegatingAIFunction(innerFunction)
    {
        protected async override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            if (FunctionInvokingChatClient.CurrentContext is null)
            {
                // If there's no current function invocation context, there's nothing to do.
                return null;
            }

            var context = FunctionInvokingChatClient.CurrentContext;

            return await next(innerAgent, context, CoreLogicAsync, cancellationToken).ConfigureAwait(false);

            ValueTask<object?> CoreLogicAsync(FunctionInvocationContext ctx, CancellationToken cancellationToken)
                => base.InvokeCoreAsync(ctx.Arguments, cancellationToken);
        }
    }
}
