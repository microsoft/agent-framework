// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.CompilerServices;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for an <see cref="AIAgent"/> that runs a workflow, served by Foundry Responses hosting.
/// </summary>
/// <remarks>
/// They extend <see cref="AIAgent"/> because that is the type <c>Workflow.AsAIAgent</c> returns; the workflow agent
/// type itself is not public. Any other agent is returned unchanged.
/// </remarks>
public static class WorkflowAgentExtensions
{
    private static readonly object s_checkpointManagerGate = new();
    private static readonly object s_mark = new();
    private static CheckpointManager? s_checkpointManager;

    /// <summary>
    /// Caches the copy made of each agent. Rebuilding it per request would restart the agent's protocol
    /// validation and throw away the session identifiers it tracks, so the copy has to live as long as the
    /// agent it was made from.
    /// </summary>
    private static readonly ConditionalWeakTable<AIAgent, AIAgent> s_copies = new();

    /// <summary>
    /// Marks every copy made by <see cref="WithFoundryCheckpointing"/>, by the copy's
    /// <see cref="WorkflowAgentMetadata"/>. An agent hands back the same metadata object every time, and
    /// <see cref="AIAgent.GetService(Type, object?)"/> finds it through any wrapper added afterwards.
    /// </summary>
    private static readonly ConditionalWeakTable<WorkflowAgentMetadata, object> s_marks = new();

    /// <summary>
    /// Returns a copy of a workflow agent that stores its checkpoints in Foundry, the same way Foundry
    /// Responses hosting stores them for the agent it serves.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Without this, a workflow agent keeps every checkpoint of a conversation inside its saved session, which
    /// grows with each superstep until the session can no longer be saved. With it, each checkpoint is a record
    /// of its own in the Foundry state store, and the session keeps only a reference to the last one. Outside
    /// Foundry, the AgentServer SDK's local state-store fallback is used.
    /// </para>
    /// <para>
    /// Hosting applies this to the agent it serves before adding its own telemetry wrapper. Call it yourself
    /// before adding other middleware when building an agent outside hosting: only the workflow agent itself can
    /// be copied, so a wrapped agent is returned unchanged. The agent is also returned unchanged when it does not
    /// run a workflow, when it was built with a checkpoint manager of its own, or when its checkpoints are already
    /// stored in Foundry.
    /// </para>
    /// <code>
    /// AIAgent agent = workflow.AsAIAgent(name: "triage")
    ///     .WithFoundryCheckpointing(services)
    ///     .AsBuilder()
    ///     .UseOpenTelemetry()
    ///     .Build();
    /// </code>
    /// </remarks>
    /// <param name="agent">The workflow agent.</param>
    /// <param name="services">The service provider that supplies the checkpoint store's logger.</param>
    /// <returns>The copy that stores its checkpoints in Foundry, or <paramref name="agent"/> when it is not changed.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> or <paramref name="services"/> is <see langword="null"/>.</exception>
    public static AIAgent WithFoundryCheckpointing(this AIAgent agent, IServiceProvider services)
    {
        _ = Throw.IfNull(agent);
        _ = Throw.IfNull(services);

        if (agent.GetService<WorkflowAgentMetadata>() is null || UsesFoundryCheckpointing(agent))
        {
            return agent;
        }

        return s_copies.GetValue(agent, source =>
        {
            AIAgent copy = source.WithCheckpointing(GetCheckpointManager(services.GetService<ILoggerFactory>()));
            if (!ReferenceEquals(copy, source) && copy.GetService<WorkflowAgentMetadata>() is { } metadata)
            {
                s_marks.AddOrUpdate(metadata, s_mark);
            }

            return copy;
        });
    }

    /// <summary>
    /// Determines whether an agent, or the workflow agent inside its wrappers, stores its checkpoints in Foundry
    /// because it is a copy made by <see cref="WithFoundryCheckpointing"/>.
    /// </summary>
    /// <param name="agent">The agent to check.</param>
    internal static bool UsesFoundryCheckpointing(AIAgent agent) =>
        agent.GetService<WorkflowAgentMetadata>() is { } metadata && s_marks.TryGetValue(metadata, out _);

    /// <summary>
    /// Gets the one checkpoint manager shared by every workflow in this process. It is created on first use so
    /// that no credential is built and no platform call is made when the process is not running on the platform,
    /// which also means the first caller supplies its logger.
    /// </summary>
    private static CheckpointManager GetCheckpointManager(ILoggerFactory? loggerFactory)
    {
        lock (s_checkpointManagerGate)
        {
            return s_checkpointManager ??= CheckpointManager.CreateJson(
                new FoundryJsonCheckpointStore(
                    credential: ServiceCollectionExtensions.CreateStateStoreCredential(),
                    loggerFactory: loggerFactory));
        }
    }
}
