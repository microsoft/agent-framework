// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Represents a single entry in the outbound network allow-list applied to the
/// Hyperlight sandbox.
/// </summary>
public sealed class AllowedDomain
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AllowedDomain"/> class.
    /// </summary>
    /// <param name="target">URL or domain to allow, for example <c>"https://api.github.com"</c>.</param>
    /// <param name="methods">
    /// Optional list of HTTP methods to allow (for example <c>["GET", "POST"]</c>).
    /// When <see langword="null"/>, all methods supported by the backend are allowed.
    /// </param>
    public AllowedDomain(string target, IReadOnlyList<string>? methods = null)
    {
        this.Target = target;
        this.Methods = methods;
    }

    /// <summary>Gets the URL or domain to allow.</summary>
    public string Target { get; }

    /// <summary>Gets the optional list of HTTP methods to allow.</summary>
    public IReadOnlyList<string>? Methods { get; }
}
