// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Represents content indicating that an agent run encountered an error.
/// </summary>
public sealed class RunErrorContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="RunErrorContent"/> class.
    /// </summary>
    /// <param name="message">The error message.</param>
    /// <param name="code">Optional error code.</param>
    public RunErrorContent(string message, string? code)
    {
        this.Message = message;
        this.Code = code;
    }

    /// <summary>
    /// Gets the error message.
    /// </summary>
    public string Message { get; }

    /// <summary>
    /// Gets the optional error code.
    /// </summary>
    public string? Code { get; }
}
