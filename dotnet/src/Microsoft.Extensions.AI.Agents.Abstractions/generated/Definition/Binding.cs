// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a binding between an input property and a tool parameter.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class Binding
{
    /// <summary>
    /// Initializes a new instance of <see cref="Binding"/>.
    /// </summary>
    public Binding()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Binding"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Binding(IDictionary<string, object> props) : this()
    {
        Name = props.GetValueOrDefault<string>("name") ?? throw new ArgumentException("Properties must contain a property named: name", nameof(props));
        Input = props.GetValueOrDefault<string>("input") ?? throw new ArgumentException("Properties must contain a property named: input", nameof(props));
    }
    
    /// <summary>
    /// Name of the binding
    /// </summary>
    
    public string Name { get; set; } = string.Empty;
    
    
    /// <summary>
    /// The input property that will be bound to the tool parameter argument
    /// </summary>
    
    public string Input { get; set; } = string.Empty;
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

