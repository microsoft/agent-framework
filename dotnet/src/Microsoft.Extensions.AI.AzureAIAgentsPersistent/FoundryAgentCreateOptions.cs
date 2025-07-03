// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Agents.Persistent;

namespace Microsoft.Extensions.AI.AzureAIAgentsPersistent;

/// <summary>
/// Represents the options for creating a Foundry agent, including configuration settings such as the model, tools, and
/// behavior parameters.
/// </summary>
public class FoundryAgentCreateOptions
{
    /// <summary>
    /// Gets or sets the model to use for the agent.
    /// </summary>
    public string Model { get; set; }

    /// <summary>
    /// Gets or sets the name to use for the agent.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the description to use for the agent.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the agent instructions.
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets the tools that the agent can use to perform tasks.
    /// </summary>
    public IEnumerable<ToolDefinition>? Tools { get; set; }

    /// <summary>
    /// Gets or sets the resources available to the agent for tool execution.
    /// </summary>
    public ToolResources? ToolResources { get; set; }

    /// <summary>
    /// Gets or sets the default temperature for the agent's responses, which controls the randomness of the output.
    /// </summary>
    public float? Temperature { get; set; }

    /// <summary>
    /// Gets or sets the default top-p sampling for the agent's responses, which controls the diversity of the output.
    /// </summary>
    public float? TopP { get; set; }

    /// <summary>
    /// Gets or sets the default response format for the agent's output, which can include structured data formats.
    /// </summary>
    public BinaryData? ResponseFormat { get; set; }

    /// <summary>
    /// Gets or sets the metadata associated with the agent.
    /// </summary>
    public IReadOnlyDictionary<string, string>? Metadata { get; set; }
}
