// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoClient.Components.Shared;

/// <summary>
/// Weather information model for backend tool rendering.
/// </summary>
public sealed class WeatherInfo
{
    [JsonPropertyName("temperature")]
    public int Temperature { get; init; }

    [JsonPropertyName("conditions")]
    public string Conditions { get; init; } = string.Empty;

    [JsonPropertyName("humidity")]
    public int Humidity { get; init; }

    [JsonPropertyName("wind_speed")]
    public int WindSpeed { get; init; }

    [JsonPropertyName("feelsLike")]
    public int FeelsLike { get; init; }

    /// <summary>
    /// Gets the temperature in Fahrenheit.
    /// </summary>
    public double TemperatureFahrenheit => (Temperature * 9.0 / 5.0) + 32;

    /// <summary>
    /// Gets an emoji icon based on weather conditions.
    /// </summary>
    public string ConditionIcon => GetConditionIcon(Conditions);

    private static string GetConditionIcon(string conditions)
    {
        if (string.Equals(conditions, "sunny", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "clear", StringComparison.OrdinalIgnoreCase))
            return "☀️";
        if (string.Equals(conditions, "cloudy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "overcast", StringComparison.OrdinalIgnoreCase))
            return "☁️";
        if (string.Equals(conditions, "rainy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "rain", StringComparison.OrdinalIgnoreCase))
            return "🌧️";
        if (string.Equals(conditions, "stormy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "thunderstorm", StringComparison.OrdinalIgnoreCase))
            return "⛈️";
        if (string.Equals(conditions, "snowy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "snow", StringComparison.OrdinalIgnoreCase))
            return "❄️";
        if (string.Equals(conditions, "foggy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(conditions, "fog", StringComparison.OrdinalIgnoreCase))
            return "🌫️";
        if (string.Equals(conditions, "windy", StringComparison.OrdinalIgnoreCase))
            return "💨";
        if (string.Equals(conditions, "partly cloudy", StringComparison.OrdinalIgnoreCase))
            return "⛅";
        return "🌡️";
    }
}
