// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a single input property for a prompt.
/// * This model defines the structure of input properties that can be used in prompts,
/// including their type, description, whether they are required, and other attributes.
/// * It allows for the definition of dynamic inputs that can be filled with data
/// and processed to generate prompts for AI models.
/// * Example:
/// ```yaml
/// inputs:
///   property1: string
///   property2: number
///   property3: boolean
/// ```
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class AgentInput
{
    /// <summary>
    /// Initializes a new instance of <see cref="AgentInput"/>.
    /// </summary>
    public AgentInput()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentInput"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal AgentInput(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Required = props.GetValueOrDefault<bool?>("required");
        Strict = props.GetValueOrDefault<bool?>("strict");
        Default = props.GetValueOrDefault<object?>("default");
        Sample = props.GetValueOrDefault<object?>("sample");
    }
    
    /// <summary>
    /// Name of the input property
    /// </summary>
    
    public string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The data type of the input property
    /// </summary>
    
    public string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// A short description of the input property
    /// </summary>
    
    public string? Description { get; set; }
    
    
    /// <summary>
    /// Whether the input property is required
    /// </summary>
    
    public bool? Required { get; set; }
    
    
    /// <summary>
    /// Whether the input property can emit structural text when parsing output
    /// </summary>
    
    public bool? Strict { get; set; }
    
    
    /// <summary>
    /// The default value of the input
    /// </summary>
    
    public object? Default { get; set; }
    
    
    /// <summary>
    /// A sample value of the input for examples and tooling
    /// </summary>
    
    public object? Sample { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

