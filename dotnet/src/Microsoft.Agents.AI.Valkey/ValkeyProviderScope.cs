// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Allows scoping of context for the <see cref="ValkeyContextProvider"/>.
/// </summary>
/// <remarks>
/// Context can be scoped by one or more of: application, agent, thread, and user.
/// At least one scope must be provided.
/// </remarks>
public sealed class ValkeyProviderScope
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyProviderScope"/> class.
    /// </summary>
    public ValkeyProviderScope() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyProviderScope"/> class by cloning an existing scope.
    /// </summary>
    /// <param name="sourceScope">The scope to clone.</param>
    public ValkeyProviderScope(ValkeyProviderScope sourceScope)
    {
        Throw.IfNull(sourceScope);

        this.ApplicationId = sourceScope.ApplicationId;
        this.AgentId = sourceScope.AgentId;
        this.ThreadId = sourceScope.ThreadId;
        this.UserId = sourceScope.UserId;
    }

    /// <summary>
    /// Gets or sets an optional ID for the application to scope context to.
    /// </summary>
    /// <remarks>If not set, the scope of the context will span all applications.</remarks>
    public string? ApplicationId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the agent to scope context to.
    /// </summary>
    /// <remarks>If not set, the scope of the context will span all agents.</remarks>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the thread to scope context to.
    /// </summary>
    /// <remarks>If not set, the scope of the context will span all threads.</remarks>
    public string? ThreadId { get; set; }

    /// <summary>
    /// Gets or sets an optional ID for the user to scope context to.
    /// </summary>
    /// <remarks>If not set, the scope of the context will span all users.</remarks>
    public string? UserId { get; set; }
}
