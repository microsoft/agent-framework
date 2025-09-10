// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Declarative;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Options for ranking file search results.
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class FileSearchRankingOptions
{
    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchRankingOptions"/>.
    /// </summary>
    public FileSearchRankingOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="FileSearchRankingOptions"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal FileSearchRankingOptions(IDictionary<string, object> props) : this()
    {
        Ranker = props.GetValueOrDefault<string>("ranker") ?? throw new ArgumentException("Properties must contain a property named: ranker", nameof(props));
        ScoreThreshold = props.GetValueOrDefault<float>("scoreThreshold");
    }
    
    /// <summary>
    /// File search ranker.
    /// </summary>
    
    public string Ranker { get; set; } = string.Empty;
    
    
    /// <summary>
    /// Ranker search threshold.
    /// </summary>
    
    public float ScoreThreshold { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

