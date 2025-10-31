// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides specialized run options for <see cref="AGUIAgent"/> instances.
/// </summary>
public sealed class AGUIAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgentRunOptions"/> class.
    /// </summary>
    /// <param name="jsonSerializerOptions">JSON serializer options for tool call argument serialization.</param>
    /// <param name="tools">Optional tools to make available to the agent during this invocation.</param>
    public AGUIAgentRunOptions(JsonSerializerOptions jsonSerializerOptions, IList<AITool>? tools = null)
    {
        this.JsonSerializerOptions = jsonSerializerOptions ?? throw new ArgumentNullException(nameof(jsonSerializerOptions));
        this.Tools = tools;
    }

    /// <summary>
    /// Gets or sets the tools to make available to the agent during this invocation.
    /// </summary>
    public IList<AITool>? Tools { get; set; }

    /// <summary>
    /// Gets or sets the JSON serializer options to use for serializing and deserializing tool call arguments.
    /// </summary>
    public JsonSerializerOptions JsonSerializerOptions { get; set; }
}
