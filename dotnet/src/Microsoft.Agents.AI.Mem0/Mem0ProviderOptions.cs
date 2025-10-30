// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Mem0;

/// <summary>
/// Options for configuring the <see cref="Mem0Provider"/>.
/// </summary>
/// <remarks>
/// Mem0 memories can be scoped by one or more of: application, agent, thread, and user.
/// At least one scope must be provided; otherwise Mem0 will reject requests.
/// </remarks>
public sealed class Mem0ProviderOptions
{
    /// <summary>
    /// Gets or sets an optional ID for the application to scope memories to.
    /// </summary>
    /// <remarks>If not set, the scope of the memories will span all applications.</remarks>
    public string? ApplicationId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the agent to scope memories to.
    /// </summary>
    /// <remarks>If not set, the scope of the memories will span all agents.</remarks>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the thread to scope memories to.
    /// </summary>
    public string? ThreadId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the user to scope memories to.
    /// </summary>
    /// <remarks>If not set, the scope of the memories will span all users.</remarks>
    public string? UserId { get; set; }

    /// <summary>
    /// When providing memories to the model, this string is prefixed to the retrieved memories to supply context.
    /// </summary>
    /// <value>Defaults to "## Memories\nConsider the following memories when answering user questions:".</value>
    public string? ContextPrompt { get; set; }
}
