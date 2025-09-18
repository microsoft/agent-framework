// Copyright (c) Microsoft. All rights reserved.
using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Optional parameters for agent creation used when create an <see cref="AIAgent"/>
/// using an instance of <see cref="AgentFactory"/>.
/// <remarks>
/// Implementors of <see cref="AgentFactory"/> can extend this class to provide
/// agent specific creation options.
/// </remarks>
/// </summary>
public class AgentCreationOptions
{
    /// <summary>
    /// Gets or sets the <see cref="IChatClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public IChatClient? ChatClient { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="IServiceProvider"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public IServiceProvider? ServiceProvider { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="ILoggerFactory"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; set; }
}
