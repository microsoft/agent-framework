// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// An identifier representing the app's location for Purview policy evaluation.
/// </summary>
public class PurviewAppLocation
{
    /// <summary>
    /// Creates a new instance of <see cref="PurviewAppLocation"/>.
    /// </summary>
    /// <param name="locationType">The type of location.</param>
    /// <param name="locationValue">The value of the location.</param>
    public PurviewAppLocation(PurviewLocationType locationType, string locationValue)
    {
        this.LocationType = locationType;
        this.LocationValue = locationValue;
    }

    /// <summary>
    /// The type of location.
    /// </summary>
    public PurviewLocationType LocationType { get; set; }

    /// <summary>
    /// The location value.
    /// </summary>
    public string LocationValue { get; set; }

    /// <summary>
    /// Returns the <see cref="PolicyLocation"/> model for this <see cref="PurviewAppLocation"/>.
    /// </summary>
    /// <returns>PolicyLocation request model.</returns>
    /// <exception cref="InvalidOperationException">Thrown when an invalid location type is provided.</exception>
    internal PolicyLocation GetPolicyLocation()
    {
        switch (this.LocationType)
        {
            case PurviewLocationType.Application:
                return new PolicyLocation($"{Constants.ODataGraphNamespace}.policyLocationApplication", this.LocationValue);
            case PurviewLocationType.Uri:
                return new PolicyLocation($"{Constants.ODataGraphNamespace}.policyLocationUrl", this.LocationValue);
            case PurviewLocationType.Domain:
                return new PolicyLocation($"{Constants.ODataGraphNamespace}.policyLocationDomain", this.LocationValue);
            default:
                throw new InvalidOperationException("Invalid location type.");
        }
    }
}
