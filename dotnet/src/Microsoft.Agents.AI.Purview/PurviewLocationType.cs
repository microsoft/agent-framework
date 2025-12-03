// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// The type of location for Purview policy evaluation.
/// </summary>
public enum PurviewLocationType
{
    /// <summary>
    /// An application location.
    /// </summary>
    Application,

    /// <summary>
    /// A URI location.
    /// </summary>
    Uri,

    /// <summary>
    /// A domain name location.
    /// </summary>
    Domain
}
