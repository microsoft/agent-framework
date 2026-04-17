// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Represents a single entry in the outbound network allow-list applied to the
/// Hyperlight sandbox.
/// </summary>
/// <param name="Target">
/// URL or domain to allow, for example <c>"https://api.github.com"</c>.
/// </param>
/// <param name="Methods">
/// Optional list of HTTP methods to allow (for example <c>["GET", "POST"]</c>).
/// When <see langword="null"/>, all methods supported by the backend are allowed.
/// </param>
public sealed record AllowedDomain(string Target, IReadOnlyList<string>? Methods = null);
