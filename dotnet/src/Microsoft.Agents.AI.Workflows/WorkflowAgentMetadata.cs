// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Describes an <see cref="AIAgent"/> that runs a <see cref="Workflow"/>, for hosts that receive a
/// finished agent and have to treat a workflow differently from other agents.
/// </summary>
/// <remarks>
/// <para>
/// Retrieve it with <c>agent.GetService&lt;WorkflowAgentMetadata&gt;()</c>. Getting an instance back
/// is what identifies the agent as running a workflow; <see langword="null"/> means it does not.
/// Going through <see cref="AIAgent.GetService(System.Type, object?)"/> means the answer is still
/// found when the agent has been wrapped, by middleware for example, which a test on the type of the
/// agent would miss.
/// </para>
/// <para>
/// This is separate from <see cref="AIAgentMetadata"/> rather than a specialization of it, because
/// that type is sealed. It also carries nothing that belongs there: the provider name it holds names
/// the inference service behind an agent, and a workflow has none of its own.
/// </para>
/// </remarks>
public sealed class WorkflowAgentMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowAgentMetadata"/> class.
    /// </summary>
    /// <param name="usesOwnCheckpointStorage">
    /// Whether the agent was built with an execution environment that already names a checkpoint
    /// manager.
    /// </param>
    public WorkflowAgentMetadata(bool usesOwnCheckpointStorage)
    {
        this.UsesOwnCheckpointStorage = usesOwnCheckpointStorage;
    }

    /// <summary>
    /// Gets a value indicating whether the agent already writes its checkpoints to a
    /// <see cref="CheckpointManager"/> named when the agent was built.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When this is <see langword="false"/>, the agent keeps its checkpoints in memory and they are
    /// carried inside the serialized agent session. When it is <see langword="true"/>, the caller
    /// passed an execution environment built with
    /// <see cref="InProc.InProcessExecutionEnvironment.WithCheckpointing(CheckpointManager?)"/>, and
    /// <see cref="WorkflowHostingExtensions.WithCheckpointing(AIAgent, CheckpointManager)"/> leaves
    /// such an agent alone rather than overriding that choice.
    /// </para>
    /// </remarks>
    public bool UsesOwnCheckpointStorage { get; }
}
