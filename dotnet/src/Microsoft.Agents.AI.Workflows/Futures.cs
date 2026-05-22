// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Process-wide opt-in switches for in-development behavior changes that will become
/// the default in a future major release. Each flag defaults to <see langword="false"/>
/// and should be toggled once at application startup.
/// </summary>
public static class Futures
{
    private static bool s_enableAgentResponseOutputTaggingAndFiltering;

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
    /// When <see langword="false"/> (the current default), the runner emits
    /// <see cref="AgentResponseEvent"/> and <see cref="AgentResponseUpdateEvent"/> unconditionally,
    /// bypassing the output filter (historical behavior). Lifecycle: opt-in today, marked
    /// <c>[Obsolete]</c> in v2.0.0 when the new behavior becomes default, and removed in v3.0.0.
    /// </remarks>
    public static bool EnableAgentResponseOutputTaggingAndFiltering
    {
        get => s_enableAgentResponseOutputTaggingAndFiltering;
        set => s_enableAgentResponseOutputTaggingAndFiltering = value;
    }
}
