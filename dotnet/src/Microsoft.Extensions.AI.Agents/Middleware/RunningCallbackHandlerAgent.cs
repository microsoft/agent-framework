// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Internal agent decorator that adds function invocation callback middleware logic.
/// </summary>
internal sealed class RunningCallbackHandlerAgent : DelegatingAIAgent
{
    private readonly Func<AgentInvokeCallbackContext, Func<AgentInvokeCallbackContext, Task>, Task> _callbackFunc;

    internal RunningCallbackHandlerAgent(AIAgent innerAgent, Func<AgentInvokeCallbackContext, Func<AgentInvokeCallbackContext, Task>, Task> callbackFunc) : base(innerAgent)
    {
        this._callbackFunc = Throw.IfNull(callbackFunc);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var context = new AgentInvokeCallbackContext(this, messages, thread, options, isStreaming: false, cancellationToken);

        async Task CoreLogicAsync(AgentInvokeCallbackContext ctx)
        {
            var response = await this.InnerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken).ConfigureAwait(false);

            ctx.SetRawResponse(response);
        }

        await this._callbackFunc(context, CoreLogicAsync).ConfigureAwait(false);

        return context.RunResponse!;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var context = new AgentInvokeCallbackContext(this, messages, thread, options, isStreaming: true, cancellationToken);

        Task CoreLogic(AgentInvokeCallbackContext ctx)
        {
            var enumerable = this.InnerAgent.RunStreamingAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken);
            ctx.SetRawResponse(enumerable);

            return Task.CompletedTask;
        }

        await this._callbackFunc(context, CoreLogic).ConfigureAwait(false);

        await foreach (var update in context.RunStreamingResponse!.ConfigureAwait(false))
        {
            yield return update;
        }
    }
}
