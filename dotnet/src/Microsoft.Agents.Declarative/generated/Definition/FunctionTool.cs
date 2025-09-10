// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Declarative;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Represents a local function tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class FunctionTool : Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="FunctionTool"/>.
    /// </summary>
    public FunctionTool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="FunctionTool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal FunctionTool(IDictionary<string, object> props) : this()
    {
        this.Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        this.Parameters = props.GetValueOrDefault<IList<Parameter>>("parameters") ?? throw new ArgumentException("Properties must contain a property named: parameters", nameof(props));
    }
    
    /// <summary>
    /// The type identifier for function tools
    /// </summary>
    
    public override string Type { get; set; } = "function";
    
    
    /// <summary>
    /// Parameters accepted by the function tool
    /// </summary>
    
    public IList<Parameter> Parameters { get; set; } = [];
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

