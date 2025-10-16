// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// .
/// </summary>
public class StatefulExecutorOptions : ExecutorOptions
{
    /// <summary>
    /// Gets or sets the unique key that identifies the executor's state. If not provided, will default to
    /// `{ExecutorType}.State`.
    /// </summary>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets the scope name to use for the executor's state. If not provided, the state will be
    /// private to this executor instance.
    /// </summary>
    public string? ScopeName { get; set; }
}
