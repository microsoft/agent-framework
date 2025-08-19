// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Configuration options for Executor behavior.
/// </summary>
public sealed class ExecutorOptions
{
    /// <summary>
    /// The default runner configuration.
    /// </summary>
    public static ExecutorOptions Default { get; } = new();

    private ExecutorOptions() { }

    /// <summary>
    /// If <see langword="true"/>, the result of a message handler that returns a value will be sent as a message to the workflow.
    /// </summary>
    public bool AutoSendMessageHandlerResultObject { get; set; } = true;
}
