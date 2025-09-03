// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents the output properties of an AI agent.
/// Each output property can be a simple type, an array, or an object.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class AgentOutput
{
    /// <summary>
    /// Initializes a new instance of <see cref="AgentOutput"/>.
    /// </summary>
    public AgentOutput()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="AgentOutput"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal AgentOutput(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Required = props.GetValueOrDefault<bool?>("required");
    }
    
    /// <summary>
    /// Name of the output property
    /// </summary>
    
    public string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The data type of the output property
    /// </summary>
    
    public string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// A short description of the output property
    /// </summary>
    
    public string? Description { get; set; }
    
    
    /// <summary>
    /// Whether the output property is required
    /// </summary>
    
    public bool? Required { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

