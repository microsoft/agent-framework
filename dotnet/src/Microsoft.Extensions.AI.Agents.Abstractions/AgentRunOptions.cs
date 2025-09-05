// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when running an agent.
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
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class by cloning the provided options.
    /// </summary>
    /// <param name="options">The options to clone.</param>
    public AgentRunOptions(AgentRunOptions options)
    {
        _ = Throw.IfNull(options);

        this.Instructions = options.Instructions;
        this.Tools = options.Tools;
    }

    /// <summary>Gets or sets the list of tools to use with an agent request.</summary>
    /// <related type="Article" href="https://learn.microsoft.com/dotnet/ai/microsoft-extensions-ai#tool-calling">Tool calling.</related>
    [JsonIgnore]
    public virtual IList<AITool>? Tools { get; set; }

    /// <summary>Gets or sets additional per-request instructions to be provided to the <see cref="IChatClient"/>.</summary>
    public virtual string? Instructions { get; set; }
}
