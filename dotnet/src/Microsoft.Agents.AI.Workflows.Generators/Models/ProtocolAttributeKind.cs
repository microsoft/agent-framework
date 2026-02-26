// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Identifies the kind of protocol attribute.
/// </summary>
internal enum ProtocolAttributeKind
{
    /// <summary>
    /// The [SendsMessage] attribute.
    /// </summary>
    Send,

    /// <summary>
    /// The [YieldsOutput] attribute.
    /// </summary>
    Yield
}
