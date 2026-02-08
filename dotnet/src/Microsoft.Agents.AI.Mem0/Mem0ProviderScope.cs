// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Mem0;

/// <summary>
/// Allows scoping of memories for the <see cref="Mem0Provider"/>.
/// </summary>
/// <remarks>
/// Mem0 memories can be scoped by one or more of: application, agent, thread, and user.
/// At least one scope must be provided; otherwise Mem0 will reject requests.
/// </remarks>
public sealed class Mem0ProviderScope
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0ProviderScope"/> class.
    /// </summary>
    public Mem0ProviderScope() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="Mem0ProviderScope"/> class by cloning an existing scope.
    /// </summary>
    /// <param name="sourceScope">The scope to clone.</param>
    public Mem0ProviderScope(Mem0ProviderScope sourceScope)
    {
        Throw.IfNull(sourceScope);

        this.ApplicationId = sourceScope.ApplicationId;
        this.AgentId = sourceScope.AgentId;
        this.ThreadId = sourceScope.ThreadId;
        this.UserId = sourceScope.UserId;
    }

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
}
