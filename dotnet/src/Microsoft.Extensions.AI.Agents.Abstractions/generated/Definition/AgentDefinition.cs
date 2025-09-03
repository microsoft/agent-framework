// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
/// <summary>
/// /// Prompty is a specification for defining AI agents with structured metadata, inputs, outputs, tools, and templates.
/// It provides a way to create reusable and composable AI agents that can be executed with specific configurations.
/// The specification includes metadata about the agent, model configuration, input parameters, expected outputs,
/// available tools, and template configurations for prompt rendering.
/// 
/// These can be written in a markdown format or in a pure YAML format.
/// 
/// ## Markdown Example
/// 
/// ```markdown
/// ---
/// name: Basic Prompt
/// description: A basic prompt that uses the GPT-3 chat API to answer questions
/// metadata:
///   authors:
///     - sethjuarez
///     - jietong
/// 
/// model:
///  id: gpt-35-turbo
///  connection:
///    provider: azure
///    type: chat
///    endpoint: https://{your-custom-endpoint}.openai.azure.com/
/// 
/// inputs:
///   firstName:
///     type: string
///     description: The first name of the customer.
///     sample: Jane
///     default: Jane
///     required: true
///   lastName: Doe
///   question: What is the meaning of life?
/// 
/// template:
///   format: jinja2
///   parser: prompty
/// ---
/// system:
/// You are an AI assistant who helps people find information.
/// As the assistant, you answer questions briefly, succinctly,
/// and in a personable manner using markdown and even add some personal flair with appropriate emojis.
/// 
/// # Customer
/// You are helping {{firstName}} {{lastName}} to find answers to their questions.
/// Use their name to address them in your responses.
/// 
/// user:
/// {{question}}
/// ```
/// 
/// ## Yaml Example
/// 
/// ```yaml
/// name: Basic Prompt
/// description: A basic prompt that uses the GPT-3 chat API to answer questions
/// metadata:
///   authors:
///     - sethjuarez
///     - jietong
/// 
/// model:
///  id: gpt-35-turbo
///  connection:
///    provider: azure
///    type: chat
///    endpoint: https://{your-custom-endpoint}.openai.azure.com/
/// 
/// inputs:
///   firstName:
///     type: string
///     description: The first name of the customer.
///     sample: Jane
///     default: Jane
///     required: true
///   lastName: Doe
///   question: What is the meaning of life?
/// 
/// template:
///   format: jinja2
///   parser: prompty
/// 
/// instructions: |
///   system:
///   You are an AI assistant who helps people find information.
///   As the assistant, you answer questions briefly, succinctly,
///   and in a personable manner using markdown and even add some personal flair with appropriate emojis.
/// 
///   # Customer
///   You are helping {{firstName}} {{lastName}} to find answers to their questions.
///   Use their name to address them in your responses.
/// 
///   user:
///   {{question}}
/// ```.
/// </summary>
public sealed class AgentDefinition
{
    /// <summary>
    /// Initializes a new instance of <see cref="AgentDefinition"/>.
    /// </summary>
    public AgentDefinition()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentDefinition"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal AgentDefinition(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Id = props.GetValueOrDefault<string?>("id");
        Version = props.GetValueOrDefault<string?>("version");
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Metadata = props.GetValueOrDefault<AgentMetadata?>("metadata");
        Model = props.GetValueOrDefault<Model>("model") ?? throw new ArgumentException("Properties must contain a property named: model", nameof(props));
        Inputs = props.GetValueOrDefault<IList<AgentInput>?>("inputs");
        Outputs = props.GetValueOrDefault<IList<AgentOutput>?>("outputs");
        Tools = props.GetValueOrDefault<IList<Tool>?>("tools");
        Template = props.GetValueOrDefault<Template?>("template");
        Instructions = props.GetValueOrDefault<string?>("instructions");
        AdditionalInstructions = props.GetValueOrDefault<string?>("additional_instructions");
    }

    /// <summary>
    /// Type represented by the Prompty document
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// Unique identifier for the Prompty document
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Version of the Prompty specification
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
    public AgentMetadata? Metadata { get; set; }

    /// <summary>
    /// Model configuration used for execution
    /// </summary>
    public Model Model { get; set; } = new Model();

    /// <summary>
    /// Input parameters that participate in template rendering
    /// </summary>
    public IList<AgentInput>? Inputs { get; set; }

    /// <summary>
    /// Expected output format and structure from the agent
    /// </summary>
    public IList<AgentOutput>? Outputs { get; set; }

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
#pragma warning restore RCS1037 // Remove trailing white-space
