// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Configuration options for Executor behavior.
/// </summary>
public class ExecutorOptions
{
    /// <summary>
    /// The default runner configuration.
    /// </summary>
    public static ExecutorOptions Default { get; } = new();

    internal ExecutorOptions() { }

    /// <summary>
    /// If <see langword="true"/>, the result of a message handler that returns a value will be sent as a message from the executor.
    /// </summary>
    public bool AutoSendMessageHandlerResultObject { get; set; } = true;

    /// <summary>
    /// If <see langword="true"/>, the result of a message handler that returns a value will be yielded as an output of the executor.
    /// </summary>
    public bool AutoYieldOutputHandlerResultObject { get; set; } = true;
}
