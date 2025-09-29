// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A tag interface for objects that have a unique identifier within an appropriate namespace.
/// </summary>
public interface IIdentified
{
    /// <summary>
    /// The unique identifier.
    /// </summary>
    string Id { get; }
}
