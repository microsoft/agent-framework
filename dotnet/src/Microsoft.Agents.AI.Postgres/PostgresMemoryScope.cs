// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Identifies the application, agent, user, and conversation thread associated with PostgreSQL-backed memory.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="UserId"/> is the durable, cross-session identity. <see cref="ThreadId"/> identifies one
/// conversation. Application and agent identifiers are optional isolation dimensions.
/// </para>
/// <para>
/// Applications are responsible for authorizing caller-supplied identifiers before creating a scope.
/// </para>
/// </remarks>
public sealed class PostgresMemoryScope
{
    /// <summary>
    /// Initializes a new instance of the <see cref="PostgresMemoryScope"/> class.
    /// </summary>
    public PostgresMemoryScope()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="PostgresMemoryScope"/> class by copying another scope.
    /// </summary>
    /// <param name="source">The scope to copy.</param>
    public PostgresMemoryScope(PostgresMemoryScope source)
    {
        _ = Throw.IfNull(source);

        this.ApplicationId = source.ApplicationId;
        this.AgentId = source.AgentId;
        this.UserId = source.UserId;
        this.ThreadId = source.ThreadId;
    }

    /// <summary>
    /// Gets or sets the optional application identifier.
    /// </summary>
    public string? ApplicationId { get; set; }

    /// <summary>
    /// Gets or sets the optional agent identifier.
    /// </summary>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets the stable user identifier used for cross-session memory.
    /// </summary>
    public string? UserId { get; set; }

    /// <summary>
    /// Gets or sets the conversation thread identifier.
    /// </summary>
    public string? ThreadId { get; set; }

    /// <summary>
    /// Gets a value indicating whether a durable user identifier is present.
    /// </summary>
    internal bool HasUserId => !string.IsNullOrWhiteSpace(this.UserId);

    /// <summary>
    /// Gets a value indicating whether a thread identifier is present.
    /// </summary>
    internal bool HasThreadId => !string.IsNullOrWhiteSpace(this.ThreadId);

    /// <summary>
    /// Creates a copy without a thread identifier for user-wide operations.
    /// </summary>
    internal PostgresMemoryScope ToUserScope() =>
        new(this)
        {
            ThreadId = null,
        };
}
