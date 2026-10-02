// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Identifies the kind of information represented by a PostgreSQL-backed memory record.
/// </summary>
public enum PostgresMemoryType
{
    /// <summary>
    /// A raw user, agent, tool, or system conversation turn.
    /// </summary>
    Turn,

    /// <summary>
    /// Declarative knowledge, such as a preference, requirement, or confirmed decision.
    /// </summary>
    Fact,

    /// <summary>
    /// A behavioral rule or instruction that should guide future agent behavior.
    /// </summary>
    Procedural,

    /// <summary>
    /// A past situation, action, and outcome that may be useful in a future similar situation.
    /// </summary>
    Episodic,

    /// <summary>
    /// A compact, incrementally maintained summary of one conversation thread.
    /// </summary>
    Summary,

    /// <summary>
    /// A cross-thread summary of durable information known about one user.
    /// </summary>
    UserSummary,
}
