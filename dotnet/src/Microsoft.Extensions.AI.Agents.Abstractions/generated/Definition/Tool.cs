// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a tool that can be used in prompts.
/// </summary>
[ExcludeFromCodeCoverage]
public abstract class Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="Tool"/>.
    /// </summary>
    protected Tool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Tool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Tool(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Description = props.GetValueOrDefault<string?>("description");
        Bindings = props.GetValueOrDefault<IList<Binding>?>("bindings");
    }
    
    /// <summary>
    /// Name of the item
    /// </summary>
    
    public virtual string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The type identifier for the tool
    /// </summary>
    
    public virtual string Type { get; set; } = string.Empty;
    
    
    /// <summary>
    /// A short description of the tool for metadata purposes
    /// </summary>
    
    public virtual string? Description { get; set; }
    
    
    /// <summary>
    /// Tool argument bindings to input properties
    /// </summary>
    
    public virtual IList<Binding>? Bindings { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

