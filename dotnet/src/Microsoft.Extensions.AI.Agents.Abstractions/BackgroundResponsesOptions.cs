// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Options for background responses.
/// </summary>
public sealed class BackgroundResponsesOptions
{
    /// <summary>
    /// Creates a new instance of <see cref="BackgroundResponsesOptions"/>.
    /// </summary>
    public BackgroundResponsesOptions()
    {
    }

    /// <summary>
    /// Creates an instance of <see cref="BackgroundResponsesOptions"/> by cloning the provided options.
    /// </summary>
    /// <param name="options">The options to clone.</param>
    public BackgroundResponsesOptions(BackgroundResponsesOptions options)
    {
        Throw.IfNull(options);

        this.Allow = options.Allow;
    }

    /// <summary>
    /// Gets or sets a value indicating whether the background responses are allowed.
    /// </summary>
    public bool? Allow { get; set; }
}
