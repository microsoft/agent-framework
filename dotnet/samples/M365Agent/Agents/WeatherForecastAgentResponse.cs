// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace M365Agent.Agents;

/// <summary>
/// The structured output type for the <see cref="WeatherForecastAgent"/>.
/// </summary>
internal sealed class WeatherForecastAgentResponse
{
    /// <summary>
    /// A value indicating whether the response contains a weather forecast or some other type of response.
    /// </summary>
    [JsonPropertyName("contentType")]
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public WeatherForecastAgentResponseContentType ContentType { get; set; }

    /// <summary>
    /// If the agent could not provide a weather forecast this should contain a textual response.
    /// </summary>
    [Description("If the answer is other agent response, contains the textual agent response.")]
    [JsonPropertyName("otherResponse")]
    public string? OtherResponse { get; set; }

    /// <summary>
    /// The location for which the weather forecast is given.
    /// </summary>
    [Description("If the answer is a weather forecast, contains the location for which the forecast is given.")]
    [JsonPropertyName("location")]
    public string? Location { get; set; }

    /// <summary>
    /// The temperature in Celsius for the given location.
    /// </summary>
    [Description("If the answer is a weather forecast, contains the temperature in Celsius.")]
    [JsonPropertyName("temperatureInCelsius")]
    public string? TemperatureInCelsius { get; set; }

    /// <summary>
    /// The meteorological condition for the given location.
    /// </summary>
    [Description("If the answer is a weather forecast, contains the meteorological condition (e.g., Sunny, Rainy).")]
    [JsonPropertyName("meteorologicalCondition")]
    public string? MeteorologicalCondition { get; set; }
}
