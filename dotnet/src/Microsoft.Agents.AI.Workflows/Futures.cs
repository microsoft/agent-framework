// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Process-wide opt-in switches for in-development behavior changes that will become
/// the default in a future major release. Each flag defaults to <see langword="false"/>
/// and should be toggled once at application startup.
/// </summary>
public static class Futures
{
    /// <summary>
    /// When <see langword="true"/>, <see cref="AgentResponse"/> and
    /// <see cref="AgentResponseUpdate"/> payloads yielded by an executor participate
    /// in the normal output-filter pipeline (i.e. they must be designated via
    /// <see cref="WorkflowBuilder.WithOutputFrom(ExecutorBinding[])"/> or
    /// <see cref="WorkflowBuilderExtensions.WithIntermediateOutputFrom(WorkflowBuilder, System.Collections.Generic.IEnumerable{ExecutorBinding})"/>
    /// to surface), and the resulting <see cref="WorkflowOutputEvent"/>s carry
    /// <see cref="WorkflowOutputEvent.Tags"/> reflecting that designation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When <see langword="false"/> (the current default), the runner emits
    /// <see cref="AgentResponseEvent"/> and <see cref="AgentResponseUpdateEvent"/> unconditionally,
    /// bypassing the output filter (historical behavior). Lifecycle: opt-in today, marked
    /// <c>[Obsolete]</c> in v2.0.0 when the new behavior becomes default, and removed in v3.0.0.
    /// </para>
    /// <para>
    /// <b>Interaction with <see cref="WorkflowHostingExtensions.AsAIAgent"/>.</b> When this flag
    /// is <see langword="true"/>, <see cref="AgentResponseEvent"/> joins
    /// <see cref="AgentResponseUpdateEvent"/> in being forwarded out of the agent surface
    /// unconditionally — neither honors the host's <c>includeWorkflowOutputsInResponse</c>
    /// switch. That switch only governs the generic <see cref="WorkflowOutputEvent"/> path for
    /// non-AIAgent payloads. When this flag is <see langword="false"/>, the legacy asymmetry
    /// is preserved: <see cref="AgentResponseUpdateEvent"/> is always forwarded but
    /// <see cref="AgentResponseEvent"/> stays gated by <c>includeWorkflowOutputsInResponse</c>.
    /// </para>
    /// </remarks>
    public static bool EnableAgentResponseOutputTaggingAndFiltering { get; set; }
}
