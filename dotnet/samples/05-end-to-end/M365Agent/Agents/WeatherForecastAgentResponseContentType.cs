// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace M365Agent.Agents;

/// <summary>
/// The type of content contained in a <see cref="WeatherForecastAgentResponse"/>.
/// </summary>
internal enum WeatherForecastAgentResponseContentType
{
    [JsonPropertyName("otherAgentResponse")]
    OtherAgentResponse,

    [JsonPropertyName("weatherForecastAgentResponse")]
    WeatherForecastAgentResponse
}
