// Copyright (c) Microsoft. All rights reserved.
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

#pragma warning disable RCS1037 // Remove trailing white-space
/// <summary>
/// /// Generic options available for certain models, configurations, or tools.
/// This can include additional settings or parameters that are not strictly defined
/// and are used by various providers to specify custom behavior or metadata.
/// 
/// Example:
/// ```yaml
/// options:
///   customSetting: true
///   timeout: 5000
///   retryAttempts: 3
///  ```.
/// </summary>
public sealed class Options
{
    /// <summary>
    /// Initializes a new instance of <see cref="Options"/>.
    /// </summary>
    public Options()
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="Options"/>.
    /// </summary>
    /// <param name="props">Properties for this instance.</param>
    internal Options(IDictionary<string, object> props) : this()
    {
    }
}
#pragma warning restore RCS1037 // Remove trailing white-space
