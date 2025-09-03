// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// The Bing search tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class BingSearchTool : Tool
{
    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchTool"/>.
    /// </summary>
    public BingSearchTool()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchTool"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal BingSearchTool(IDictionary<string, object> props) : this()
    {
        Type = props.GetValueOrDefault<string>("type") ?? throw new ArgumentException("Properties must contain a property named: type", nameof(props));
        Options = props.GetValueOrDefault<BingSearchOptions>("options") ?? throw new ArgumentException("Properties must contain a property named: options", nameof(props));
    }
    
    /// <summary>
    /// The type identifier for Bing search tools
    /// </summary>
    
    public override string Type { get; set; } = "bing_search";
    
    
    /// <summary>
    /// The options for the Bing search tool
    /// </summary>
    
    public BingSearchOptions Options { get; set; } = new BingSearchOptions();
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

