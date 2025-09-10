// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Declarative;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
#pragma warning disable IDE0055 // Fix formatting 
/// <summary>
/// Template model for defining prompt templates.
/// 
/// This model specifies the rendering engine used for slot filling prompts,
/// the parser used to process the rendered template into API-compatible format,
/// and additional options for the template engine.
/// 
/// It allows for the creation of reusable templates that can be filled with dynamic data
/// and processed to generate prompts for AI models.
/// 
/// Example:
/// ```yaml
/// template:
///   format: jinja2
///   parser: prompty
/// ```
/// </summary>
[ExcludeFromCodeCoverage]
public sealed class Template
{
    /// <summary>
    /// Initializes a new instance of <see cref="Template"/>.
    /// </summary>
    public Template()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Template"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Template(IDictionary<string, object> props) : this()
    {
        this.Format = props.GetValueOrDefault<string>("format") ?? throw new ArgumentException("Properties must contain a property named: format", nameof(props));
        this.Parser = props.GetValueOrDefault<string>("parser") ?? throw new ArgumentException("Properties must contain a property named: parser", nameof(props));
        this.Strict = props.GetValueOrDefault<bool?>("strict");
        this.Options = props.GetValueOrDefault<Dictionary<string, object>?>("options");
    }
    
    /// <summary>
    /// Template rendering engine used for slot filling prompts (e.g., mustache, jinja2)
    /// </summary>
    
    public string Format { get; set; } = string.Empty;
    
    
    /// <summary>
    /// Parser used to process the rendered template into API-compatible format
    /// </summary>
    
    public string Parser { get; set; } = string.Empty;
    
    
    /// <summary>
    /// Whether the template can emit structural text for parsing output
    /// </summary>
    
    public bool? Strict { get; set; }
    
    
    /// <summary>
    /// Additional options for the template engine
    /// </summary>
    
    public Dictionary<string, object>? Options { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line
#pragma warning restore IDE0055 // Fix formatting 

