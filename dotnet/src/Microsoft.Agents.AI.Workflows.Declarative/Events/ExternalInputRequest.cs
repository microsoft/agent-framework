// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more user-input requests.
/// </summary>
public sealed class ExternalInputRequest
{
    [JsonConstructor]
    internal ExternalInputRequest()
    {
    }
}
