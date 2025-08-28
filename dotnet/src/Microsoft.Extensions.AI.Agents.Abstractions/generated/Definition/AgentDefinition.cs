// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an instance of AgentDefinition.
/// </summary>
public sealed class AgentDefinition
{
    /// <summary>
    /// Initializes a new instance of <see cref="AgentDefinition"/>.
    /// </summary>
    public AgentDefinition()
    {
        Model = new Model();
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentDefinition"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal AgentDefinition(IDictionary<string, object> props) : this()
    {
        Id = props.GetValueOrDefault<string?>("id");
        Version = props.GetValueOrDefault<string?>("version");
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Metadata = props.GetValueOrDefault<Metadata?>("metadata");
        Model = props.GetValueOrDefault<Model>("model") ?? throw new ArgumentException("Properties must contain a property named: model", nameof(props));
        Inputs = props.GetValueOrDefault<IList<Input>?>("inputs");
        Outputs = props.GetValueOrDefault<IList<Output>?>("outputs");
        Tools = props.GetValueOrDefault<IList<Tool>?>("tools");
        Template = props.GetValueOrDefault<Template?>("template");
        Instructions = props.GetValueOrDefault<string?>("instructions");
        AdditionalInstructions = props.GetValueOrDefault<string?>("additional_instructions");
    }

    /// <summary>
    /// Unique identifier for the AgentDefinition document
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Unique identifier for the Prompty document
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// Version of the AgentDefinition specification
    /// </summary>
    public string? Version { get; set; }

    /// <summary>
    /// Human-readable name of the agent
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Description of the agent's capabilities and purpose
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Additional metadata including authors, tags, and other arbitrary properties
    /// </summary>
    public Metadata? Metadata { get; set; }

    /// <summary>
    /// Model configuration used for execution
    /// </summary>
    public Model Model { get; set; } = new Model();

    /// <summary>
    /// Input parameters that participate in template rendering
    /// </summary>
    public IList<Input>? Inputs { get; set; }

    /// <summary>
    /// Expected output format and structure from the agent
    /// </summary>
    public IList<Output>? Outputs { get; set; }

    /// <summary>
    /// Tools available to the agent for extended functionality
    /// </summary>
    public IList<Tool>? Tools { get; set; }

    /// <summary>
    /// Template configuration for prompt rendering
    /// </summary>
    public Template? Template { get; set; }

    /// <summary>
    /// Give your agent clear directions on what to do and how to do it. Include specific tasks, their order, and any special instructions like tone or engagement style. (can use this for a pure yaml declaration or as content in the markdown format)
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// Additional instructions or context for the agent, can be used to provide extra guidance (can use this for a pure yaml declaration)
    /// </summary>
    public string? AdditionalInstructions { get; set; }
}
