// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Model for defining the structure and behavior of AI agents.
/// Yaml Example:
/// ```yaml
/// name: Basic Prompt
/// description: A basic prompt that uses the GPT-3 chat API to answer questions
/// model:
///   id: gpt-35-turbo
///   connection:
///     provider: azure
///     type: chat
///     endpoint: https://{your-custom-endpoint}.openai.azure.com/
/// ```
/// 
/// A shorthand representation of the model configuration can also be constructed as
/// follows:
/// ```yaml
/// name: Basic Prompt
/// description: A basic prompt that uses the GPT-3 chat API to answer questions
/// model: gpt-35-turbo
/// ```
/// This will be expanded as follows:
/// ```yaml
/// name: Basic Prompt
/// description: A basic prompt that uses the GPT-3 chat API to answer questions
/// model:
///   id: gpt-35-turbo
/// ```
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class Model
{
    /// <summary>
    /// Initializes a new instance of <see cref="Model"/>.
    /// </summary>
    public Model()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Model"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Model(IDictionary<string, object> props) : this()
    {
        Id = props.GetValueOrDefault<string>("id") ?? throw new ArgumentException("Properties must contain a property named: id", nameof(props));
        Connection = props.GetValueOrDefault<Connection?>("connection");
    }
    
    /// <summary>
    /// The unique identifier of the model
    /// </summary>
    
    public string Id { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The connection configuration for the model
    /// </summary>
    
    public Connection? Connection { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

