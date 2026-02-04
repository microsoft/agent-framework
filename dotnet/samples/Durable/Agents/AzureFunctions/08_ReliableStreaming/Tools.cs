// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;

namespace ReliableStreaming;

/// <summary>
/// Mock travel tools that return hardcoded data for demonstration purposes.
/// In a real application, these would call actual weather and events APIs.
/// </summary>
internal static class TravelTools
{
    /// <summary>
    /// Gets a weather forecast for a destination on a specific date.
    /// Returns mock weather data for demonstration purposes.
    /// </summary>
    /// <param name="destination">The destination city or location.</param>
    /// <param name="date">The date for the forecast (e.g., "2025-01-15" or "next Monday").</param>
    /// <returns>A weather forecast summary.</returns>
    [Description("Gets the weather forecast for a destination on a specific date. Use this to provide weather-aware recommendations in the itinerary.")]
    public static string GetWeatherForecast(string destination, string date)
    {
        // Mock weather data based on destination for realistic responses
        Dictionary<string, (string condition, int highF, int lowF)> weatherByRegion = new(StringComparer.OrdinalIgnoreCase)
        {
            ["Tokyo"] = ("Partly cloudy with a chance of light rain", 58, 45),
            ["Paris"] = ("Overcast with occasional drizzle", 52, 41),
            ["New York"] = ("Clear and cold", 42, 28),
            ["London"] = ("Foggy morning, clearing in afternoon", 48, 38),
            ["Sydney"] = ("Sunny and warm", 82, 68),
            ["Rome"] = ("Sunny with light breeze", 62, 48),
            ["Barcelona"] = ("Partly sunny", 59, 47),
            ["Amsterdam"] = ("Cloudy with light rain", 46, 38),
            ["Dubai"] = ("Sunny and hot", 85, 72),
            ["Singapore"] = ("Tropical thunderstorms in afternoon", 88, 77),
            ["Bangkok"] = ("Hot and humid, afternoon showers", 91, 78),
            ["Los Angeles"] = ("Sunny and pleasant", 72, 55),
            ["San Francisco"] = ("Morning fog, afternoon sun", 62, 52),
            ["Seattle"] = ("Rainy with breaks", 48, 40),
            ["Miami"] = ("Warm and sunny", 78, 65),
            ["Honolulu"] = ("Tropical paradise weather", 82, 72),
        };

        // Find a matching destination or use a default
        (string condition, int highF, int lowF) forecast = ("Partly cloudy", 65, 50);
        foreach (KeyValuePair<string, (string, int, int)> entry in weatherByRegion)
        {
            if (destination.Contains(entry.Key, StringComparison.OrdinalIgnoreCase))
            {
                forecast = entry.Value;
                break;
            }
        }

        return $"""
            Weather forecast for {destination} on {date}:
            Conditions: {forecast.condition}
            High: {forecast.highF}°F ({(forecast.highF - 32) * 5 / 9}°C)
            Low: {forecast.lowF}°F ({(forecast.lowF - 32) * 5 / 9}°C)
            
            Recommendation: {GetWeatherRecommendation(forecast.condition)}
            """;
    }

    /// <summary>
    /// Gets local events happening at a destination around a specific date.
    /// Returns mock event data for demonstration purposes.
    /// </summary>
    /// <param name="destination">The destination city or location.</param>
    /// <param name="date">The date to search for events (e.g., "2025-01-15" or "next week").</param>
    /// <returns>A list of local events and activities.</returns>
    [Description("Gets local events and activities happening at a destination around a specific date. Use this to suggest timely activities and experiences.")]
    public static string GetLocalEvents(string destination, string date)
    {
        // Mock events data based on destination
        Dictionary<string, string[]> eventsByCity = new(StringComparer.OrdinalIgnoreCase)
        {
            ["Tokyo"] = [
                "🎭 Kabuki Theater Performance at Kabukiza Theatre - Traditional Japanese drama",
                "🌸 Winter Illuminations at Yoyogi Park - Spectacular light displays",
                "🍜 Ramen Festival at Tokyo Station - Sample ramen from across Japan",
                "🎮 Gaming Expo at Tokyo Big Sight - Latest video games and technology",
            ],
            ["Paris"] = [
                "🎨 Impressionist Exhibition at Musée d'Orsay - Extended evening hours",
                "🍷 Wine Tasting Tour in Le Marais - Local sommelier guided",
                "🎵 Jazz Night at Le Caveau de la Huchette - Historic jazz club",
                "🥐 French Pastry Workshop - Learn from master pâtissiers",
            ],
            ["New York"] = [
                "🎭 Broadway Show: Hamilton - Limited engagement performances",
                "🏀 Knicks vs Lakers at Madison Square Garden",
                "🎨 Modern Art Exhibit at MoMA - New installations",
                "🍕 Pizza Walking Tour of Brooklyn - Artisan pizzerias",
            ],
            ["London"] = [
                "👑 Royal Collection Exhibition at Buckingham Palace",
                "🎭 West End Musical: The Phantom of the Opera",
                "🍺 Craft Beer Festival at Brick Lane",
                "🎪 Winter Wonderland at Hyde Park - Rides and markets",
            ],
            ["Sydney"] = [
                "🏄 Pro Surfing Competition at Bondi Beach",
                "🎵 Opera at Sydney Opera House - La Bohème",
                "🦘 Wildlife Night Safari at Taronga Zoo",
                "🍽️ Harbor Dinner Cruise with fireworks",
            ],
            ["Rome"] = [
                "🏛️ After-Hours Vatican Tour - Skip the crowds",
                "🍝 Pasta Making Class in Trastevere",
                "🎵 Classical Concert at Borghese Gallery",
                "🍷 Wine Tasting in Roman Cellars",
            ],
        };

        // Find events for the destination or use generic events
        string[] events = [
            "🎭 Local theater performance",
            "🍽️ Food and wine festival",
            "🎨 Art gallery opening",
            "🎵 Live music at local venues",
        ];

        foreach (KeyValuePair<string, string[]> entry in eventsByCity)
        {
            if (destination.Contains(entry.Key, StringComparison.OrdinalIgnoreCase))
            {
                events = entry.Value;
                break;
            }
        }

        string eventList = string.Join("\n• ", events);
        return $"""
            Local events in {destination} around {date}:
            
            • {eventList}
            
            💡 Tip: Book popular events in advance as they may sell out quickly!
            """;
    }

    private static string GetWeatherRecommendation(string condition)
    {
        // Use case-insensitive comparison instead of ToLowerInvariant() to satisfy CA1308
        return condition switch
        {
            string c when c.Contains("rain", StringComparison.OrdinalIgnoreCase) || c.Contains("drizzle", StringComparison.OrdinalIgnoreCase) =>
                "Bring an umbrella and waterproof jacket. Consider indoor activities for backup.",
            string c when c.Contains("fog", StringComparison.OrdinalIgnoreCase) =>
                "Morning visibility may be limited. Plan outdoor sightseeing for afternoon.",
            string c when c.Contains("cold", StringComparison.OrdinalIgnoreCase) =>
                "Layer up with warm clothing. Hot drinks and cozy cafés recommended.",
            string c when c.Contains("hot", StringComparison.OrdinalIgnoreCase) || c.Contains("warm", StringComparison.OrdinalIgnoreCase) =>
                "Stay hydrated and use sunscreen. Plan strenuous activities for cooler morning hours.",
            string c when c.Contains("thunder", StringComparison.OrdinalIgnoreCase) || c.Contains("storm", StringComparison.OrdinalIgnoreCase) =>
                "Keep an eye on weather updates. Have indoor alternatives ready.",
            _ => "Pleasant conditions expected. Great day for outdoor exploration!"
        };
    }
}
