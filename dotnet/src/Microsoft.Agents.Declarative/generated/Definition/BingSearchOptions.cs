// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Declarative;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Options for the Bing search tool.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class BingSearchOptions
{
    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchOptions"/>.
    /// </summary>
    public BingSearchOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="BingSearchOptions"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal BingSearchOptions(IDictionary<string, object> props) : this()
    {
        Configurations = props.GetValueOrDefault<IList<BingSearchConfiguration>>("configurations") ?? throw new ArgumentException("Properties must contain a property named: configurations", nameof(props));
    }
    
    /// <summary>
    /// The configuration options for the Bing search tool
    /// </summary>
    
    public IList<BingSearchConfiguration> Configurations { get; set; } = [];
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

