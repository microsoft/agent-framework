// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for adding tool approval middleware to <see cref="AIAgentBuilder"/> instances.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class ToolApprovalAgentBuilderExtensions
{
    /// <summary>
    /// Adds tool approval middleware to the agent pipeline, enabling "don't ask again" approval behavior.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which tool approval support will be added.</param>
    /// <param name="jsonSerializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used for serializing argument values when storing rules
    /// and for persisting state. When <see langword="null"/>, <see cref="AgentJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with tool approval middleware added, enabling method chaining.</returns>
    /// <exception cref="System.ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// The <see cref="ToolApprovalAgent"/> middleware intercepts tool approval flows between the caller and the inner agent.
    /// When a caller responds with an <see cref="AlwaysApproveToolApprovalResponseContent"/>, the middleware records a standing
    /// approval rule so that future matching tool calls are auto-approved without user interaction.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder UseToolApproval(
        this AIAgentBuilder builder,
        JsonSerializerOptions? jsonSerializerOptions = null)
        => Throw.IfNull(builder).Use(innerAgent => new ToolApprovalAgent(innerAgent, jsonSerializerOptions));
}
