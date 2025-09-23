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
/// Internal agent decorator that adds run middleware logic.
/// </summary>
internal sealed class RunDelegatingAgent : DelegatingAIAgent
{
    private readonly Func<AgentRunContext, Func<AgentRunContext, Task>, Task> _delegateFunc;

    internal RunDelegatingAgent(AIAgent innerAgent, Func<AgentRunContext, Func<AgentRunContext, Task>, Task> delegateFunc) : base(innerAgent)
    {
        this._delegateFunc = Throw.IfNull(delegateFunc);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var context = new AgentRunContext(this, messages, thread, options, isStreaming: false, cancellationToken);

        async Task CoreLogicAsync(AgentRunContext ctx)
        {
            var response = await this.InnerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken).ConfigureAwait(false);

            ctx.SetRunResponse(response);
        }

        await this._delegateFunc(context, CoreLogicAsync).ConfigureAwait(false);

        return context.RunResponse!;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var context = new AgentRunContext(this, messages, thread, options, isStreaming: true, cancellationToken);

        Task CoreLogicAsync(AgentRunContext ctx)
        {
            var enumerable = this.InnerAgent.RunStreamingAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken);
            ctx.SetRunStreamingResponse(enumerable);

            return Task.CompletedTask;
        }

        await this._delegateFunc(context, CoreLogicAsync).ConfigureAwait(false);

        await foreach (var update in context.RunStreamingResponse!.ConfigureAwait(false))
        {
            yield return update;
        }
    }
}
