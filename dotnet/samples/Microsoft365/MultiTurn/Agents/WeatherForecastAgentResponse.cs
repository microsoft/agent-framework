// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace MultiTurn.Agents;

public enum WeatherForecastAgentResponseContentType
{
    [JsonPropertyName("text")]
    Text,

    [JsonPropertyName("adaptive-card")]
    AdaptiveCard
}

public class WeatherForecastAgentResponse
{
    [JsonPropertyName("contentType")]
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public WeatherForecastAgentResponseContentType ContentType { get; set; }

    [JsonPropertyName("content")]
    [Description("The content of the response, may be plain text, or JSON based adaptive card but must be a string.")]
    public string? Content { get; set; }
}
