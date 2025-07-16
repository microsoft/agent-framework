// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

public abstract partial class AgentOrchestration<TInput, TOutput>
{
    /// <summary>
    /// Actor responsible for receiving final message and transforming it into the output type.
    /// </summary>
    private sealed class RequestActor : OrchestrationActor
    {
        private readonly Func<TInput, JsonSerializerOptions?, CancellationToken, ValueTask<IEnumerable<ChatMessage>>> _transform;
        private readonly Func<IEnumerable<ChatMessage>, ValueTask> _action;
        private readonly TaskCompletionSource<TOutput> _completionSource;

        /// <summary>
        /// Initializes a new instance of the <see cref="AgentOrchestration{TInput, TOutput}"/> class.
        /// </summary>
        /// <param name="id">The unique identifier of the agent.</param>
        /// <param name="runtime">The runtime associated with the agent.</param>
        /// <param name="context">The orchestration context.</param>
        /// <param name="transform">A function that transforms an input of type TInput into a source type TSource.</param>
        /// <param name="completionSource">Optional TaskCompletionSource to signal orchestration completion.</param>
        /// <param name="action">An asynchronous function that processes the resulting source.</param>
        /// <param name="logger">The logger to use for the actor</param>
        public RequestActor(
            ActorId id,
            IAgentRuntime runtime,
            OrchestrationContext context,
            Func<TInput, JsonSerializerOptions?, CancellationToken, ValueTask<IEnumerable<ChatMessage>>> transform,
            TaskCompletionSource<TOutput> completionSource,
            Func<IEnumerable<ChatMessage>, ValueTask> action,
            ILogger<RequestActor>? logger = null)
            : base(id, runtime, context, $"{id.Type}_Actor", logger)
        {
            this._transform = transform;
            this._action = action;
            this._completionSource = completionSource;

            this.RegisterMessageHandler<TInput>(this.HandleAsync);
        }

        /// <summary>
        /// Handles the incoming message by transforming the input and executing the corresponding action asynchronously.
        /// </summary>
        /// <param name="item">The input message of type TInput.</param>
        /// <param name="messageContext">The context of the message, providing additional details.</param>
        /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
        /// <returns>A ValueTask representing the asynchronous operation.</returns>
        private async ValueTask HandleAsync(TInput item, MessageContext messageContext, CancellationToken cancellationToken)
        {
            this.Logger.LogOrchestrationRequestInvoke(this.Context.Orchestration, this.Id);
            try
            {
                IEnumerable<ChatMessage> input = await this._transform.Invoke(item, messageContext.SerializerOptions, cancellationToken).ConfigureAwait(false);
                var task = this._action.Invoke(input);
                this.Logger.LogOrchestrationStart(this.Context.Orchestration, this.Id);
                await task.ConfigureAwait(false);
            }
            catch (Exception exception)
            {
                // Log exception details and allow orchestration to fail
                this.Logger.LogOrchestrationRequestFailure(this.Context.Orchestration, this.Id, exception);
                this._completionSource.SetException(exception);
                throw;
            }
        }
    }
}
