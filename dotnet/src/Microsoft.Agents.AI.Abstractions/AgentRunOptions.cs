// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides optional parameters and configuration settings for controlling agent run behavior.
/// </summary>
public class AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class.
    /// </summary>
    public AgentRunOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class by copying values from the specified options.
    /// </summary>
    /// <param name="options">The options instance from which to copy values.</param>
    /// <exception cref="ArgumentNullException"><paramref name="options"/> is <see langword="null"/>.</exception>
    public AgentRunOptions(AgentRunOptions options)
    {
        _ = Throw.IfNull(options);
    }
}
