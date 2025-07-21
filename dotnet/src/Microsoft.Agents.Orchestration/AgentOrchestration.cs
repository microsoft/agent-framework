// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.AI.Agents.Runtime.InProcess;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CA2000 // Dispose objects before losing scope

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Base class for multi-agent agent orchestration patterns.
/// </summary>
/// <typeparam name="TInput">The type of the input to the orchestration.</typeparam>
/// <typeparam name="TOutput">The type of the result output by the orchestration.</typeparam>
public abstract partial class AgentOrchestration<TInput, TOutput>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentOrchestration{TInput, TOutput}"/> class.
    /// </summary>
    /// <param name="members">Specifies the member agents or orchestrations participating in this orchestration.</param>
    protected AgentOrchestration(params AIAgent[] members)
    {
        _ = Throw.IfNull(members);

        // Capture orchestration root name without generic parameters for use in
        // agent type and topic formatting as well as logging.
        string name = this.GetType().Name;
        int pos = name.IndexOf('`');
        if (pos > 0)
        {
            name = name.Substring(0, pos);
        }
        this.OrchestrationLabel = name;

        this.Members = members;
    }

    /// <summary>
    /// Gets the description of the orchestration.
    /// </summary>
    public string Description { get; init; } = string.Empty;

    /// <summary>
    /// Gets the name of the orchestration.
    /// </summary>
    public string Name { get; init; } = string.Empty;

    /// <summary>
    /// Gets the associated logger.
    /// </summary>
    public ILoggerFactory LoggerFactory { get; init; } = NullLoggerFactory.Instance;

    /// <summary>
    /// Transforms the orchestration input into a source input suitable for processing.
    /// </summary>
    public Func<TInput, JsonSerializerOptions?, CancellationToken, ValueTask<IEnumerable<ChatMessage>>>? InputTransform { get; set; }

    /// <summary>
    /// Transforms the processed result into the final output form.
    /// </summary>
    public Func<IList<ChatMessage>, JsonSerializerOptions?, CancellationToken, ValueTask<TOutput>>? ResultTransform { get; set; }

    /// <summary>
    /// Optional callback that is invoked for every agent response.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, ValueTask>? ResponseCallback { get; set; }

    /// <summary>
    /// Optional callback that is invoked for every agent update.
    /// </summary>
    public Func<AgentRunResponseUpdate, ValueTask>? StreamingResponseCallback { get; set; }

    /// <summary>
    /// Gets the list of member targets involved in the orchestration.
    /// </summary>
    protected IReadOnlyList<AIAgent> Members { get; }

    /// <summary>
    /// Orchestration identifier without generic parameters for use in
    /// agent type and topic formatting as well as logging.
    /// </summary>
    protected string OrchestrationLabel { get; }

    /// <summary>
    /// Initiates processing of the orchestration.
    /// </summary>
    /// <param name="input">The input message.</param>
    /// <param name="runtime">The runtime associated with the orchestration.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    public async ValueTask<OrchestrationResult<TOutput>> InvokeAsync(
        TInput input,
        IAgentRuntime? runtime = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(input, nameof(input));

        cancellationToken.ThrowIfCancellationRequested();

        TopicId topic = new($"{this.OrchestrationLabel}_{Guid.NewGuid():N}");

        CancellationTokenSource orchestrationCancelSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cancellationToken = orchestrationCancelSource.Token;

        OrchestrationContext context =
            new(this.OrchestrationLabel,
                topic,
                this.ResponseCallback,
                this.StreamingResponseCallback,
                this.LoggerFactory,
                cancellationToken);

        ILogger logger = this.LoggerFactory.CreateLogger(this.GetType());

        TaskCompletionSource<TOutput> completion = new();

        InProcessRuntime? temporaryRuntime = null;
        runtime ??= temporaryRuntime = InProcessRuntime.StartNew();

        ActorType orchestrationType = await this.RegisterAsync(runtime, context, completion, handoff: null).ConfigureAwait(false);

        logger.LogOrchestrationInvoke(this.OrchestrationLabel, topic);

        Task task = runtime.PublishMessageAsync(input, orchestrationType, cancellationToken).AsTask();

        logger.LogOrchestrationYield(this.OrchestrationLabel, topic);

        return new OrchestrationResult<TOutput>(context, completion, orchestrationCancelSource, logger, temporaryRuntime);
    }

    /// <summary>
    /// Initiates processing according to the orchestration pattern.
    /// </summary>
    /// <param name="runtime">The runtime associated with the orchestration.</param>
    /// <param name="topic">The unique identifier for the orchestration session.</param>
    /// <param name="input">The input to be transformed and processed.</param>
    /// <param name="entryAgent">The initial agent type used for starting the orchestration.</param>
    protected abstract ValueTask StartAsync(IAgentRuntime runtime, TopicId topic, IEnumerable<ChatMessage> input, ActorType? entryAgent);

    /// <summary>
    /// Orchestration specific registration, including members and returns an optional entry agent.
    /// </summary>
    /// <param name="runtime">The runtime targeted for registration.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="registrar">A registration context.</param>
    /// <param name="logger">The logger to use during registration</param>
    /// <returns>The entry AgentType for the orchestration, if any.</returns>
    protected abstract ValueTask<ActorType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger);

    /// <summary>
    /// Formats and returns a unique AgentType based on the provided topic and suffix.
    /// </summary>
    /// <param name="topic">The topic identifier used in formatting the agent type.</param>
    /// <param name="suffix">A suffix to differentiate the agent type.</param>
    /// <returns>A formatted AgentType object.</returns>
    protected ActorType FormatAgentType(TopicId topic, string suffix) => new($"{topic.Type}_{suffix}");

    /// <summary>
    /// Registers the orchestration's root and boot agents, setting up completion and target routing.
    /// </summary>
    /// <param name="runtime">The runtime targeted for registration.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="completion">A TaskCompletionSource for the orchestration.</param>
    /// <param name="handoff">The actor type used for handoff.  Only defined for nested orchestrations.</param>
    /// <returns>The AgentType representing the orchestration entry point.</returns>
    private async ValueTask<ActorType> RegisterAsync(IAgentRuntime runtime, OrchestrationContext context, TaskCompletionSource<TOutput> completion, ActorType? handoff)
    {
        // Create a logger for the orchestration registration.
        ILogger logger = context.LoggerFactory.CreateLogger(this.GetType());
        logger.LogOrchestrationRegistrationStart(context.Orchestration, context.Topic);

        // Register orchestration
        RegistrationContext registrar = new(this.FormatAgentType(context.Topic, "Root"), runtime, context, completion, this.ResultTransform ?? DefaultTransforms.ToOutput<TOutput>);
        ActorType? entryAgent = await this.RegisterOrchestrationAsync(runtime, context, registrar, logger).ConfigureAwait(false);

        // Register actor for orchestration entry-point
        ActorType orchestrationEntry =
            await runtime.RegisterOrchestrationAgentAsync(
                this.FormatAgentType(context.Topic, "Boot"),
                (agentId, runtime) =>
                {
                    RequestActor actor =
                        new(agentId,
                            runtime,
                            context,
                            this.InputTransform ?? DefaultTransforms.FromInput<TInput>,
                            completion,
                            input => this.StartAsync(runtime, context.Topic, input, entryAgent),
                            context.LoggerFactory.CreateLogger<RequestActor>());
                    return new ValueTask<IRuntimeActor>(actor);
                }).ConfigureAwait(false);

        logger.LogOrchestrationRegistrationDone(context.Orchestration, context.Topic);

        return orchestrationEntry;
    }

    /// <summary>
    /// A context used during registration (<see cref="RegisterAsync"/>).
    /// </summary>
    public sealed class RegistrationContext(
        ActorType agentType,
        IAgentRuntime runtime,
        OrchestrationContext context,
        TaskCompletionSource<TOutput> completion,
        Func<IList<ChatMessage>, JsonSerializerOptions?, CancellationToken, ValueTask<TOutput>> outputTransform)
    {
        /// <summary>
        /// Register the final result type.
        /// </summary>
        public async ValueTask<ActorType> RegisterResultTypeAsync<TResult>(Func<TResult, IList<ChatMessage>> resultTransform)
        {
            // Register actor for final result
            ActorType registeredType =
                await runtime.RegisterOrchestrationAgentAsync(
                    agentType,
                    (agentId, runtime) =>
                    {
                        ResultActor<TResult> actor =
                            new(agentId,
                                runtime,
                                context,
                                resultTransform,
                                outputTransform,
                                completion,
                                context.LoggerFactory.CreateLogger<ResultActor<TResult>>());
                        return new ValueTask<IRuntimeActor>(actor);
                    }).ConfigureAwait(false);

            return registeredType;
        }
    }
}
