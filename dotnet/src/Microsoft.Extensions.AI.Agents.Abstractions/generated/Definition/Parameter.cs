// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a parameter for a tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class Parameter
{
    /// <summary>
    /// Initializes a new instance of <see cref="Parameter"/>.
    /// </summary>
    public Parameter()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Parameter"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Parameter(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Required = props.GetValueOrDefault<bool?>("required");
        Enum = props.GetValueOrDefault<IList<object>?>("enum");
    }
    
    /// <summary>
    /// Name of the parameter
    /// </summary>
    
    public string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The data type of the tool parameter
    /// </summary>
    
    public string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// A short description of the property
    /// </summary>
    
    public string? Description { get; set; }
    
    
    /// <summary>
    /// Whether the tool parameter is required
    /// </summary>
    
    public bool? Required { get; set; }
    
    
    /// <summary>
    /// Allowed enumeration values for the parameter
    /// </summary>
    
    public IList<object>? Enum { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

