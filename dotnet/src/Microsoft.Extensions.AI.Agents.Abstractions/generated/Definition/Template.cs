// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
#pragma warning disable RCS1036 // Remove unnecessary blank line
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
        Format = props.GetValueOrDefault<string>("format") ?? throw new ArgumentException("Properties must contain a property named: format", nameof(props));
        Parser = props.GetValueOrDefault<string>("parser") ?? throw new ArgumentException("Properties must contain a property named: parser", nameof(props));
        Strict = props.GetValueOrDefault<bool?>("strict");
        Options = props.GetValueOrDefault<Options?>("options");
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
    
    public Options? Options { get; set; }
    
}
#pragma warning restore RCS1037 // Remove trailing white-space
#pragma warning restore RCS1036 // Remove unnecessary blank line

