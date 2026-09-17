// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring <see cref="ChatClientPromptAgentFactory"/>.
/// </summary>
public sealed class ChatClientPromptAgentFactoryOptions
{
    /// <summary>
    /// Gets or sets configuration keys that may be exposed to Power Fx when the agent definition references them through <c>Env</c>.
    /// </summary>
    public IEnumerable<string>? AllowedConfigurationVariables { get; init; }

    /// <summary>
    /// Gets or sets an optional Power Fx engine used to evaluate declarative expressions.
    /// </summary>
    public RecalcEngine? Engine { get; init; }

    /// <summary>
    /// Gets or sets optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.
    /// </summary>
    public IConfiguration? Configuration { get; init; }

    /// <summary>
    /// Gets or sets an optional logger factory used by created agents.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; init; }

    /// <summary>
    /// Gets or sets an optional maximum length for Power Fx expressions evaluated by the factory-created engine.
    /// </summary>
    public int? MaximumExpressionLength { get; init; }

    /// <summary>
    /// Gets or sets an optional maximum nested call depth for Power Fx expressions evaluated by the factory-created engine.
    /// </summary>
    public int? MaximumCallDepth { get; init; }
}
