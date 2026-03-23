// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace RecipeAssistant;

// State wrapper
internal sealed class AgentState
{
    [JsonPropertyName("recipe")]
    public RecipeState Recipe { get; set; } = new();
}

// Recipe state model
internal sealed class RecipeState
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("cuisine")]
    public string Cuisine { get; set; } = string.Empty;

    [JsonPropertyName("ingredients")]
    public List<string> Ingredients { get; set; } = [];

    [JsonPropertyName("steps")]
    public List<string> Steps { get; set; } = [];

    [JsonPropertyName("prep_time_minutes")]
    public int PrepTimeMinutes { get; set; }

    [JsonPropertyName("cook_time_minutes")]
    public int CookTimeMinutes { get; set; }

    [JsonPropertyName("skill_level")]
    public string SkillLevel { get; set; } = string.Empty;
}

// JSON serialization context
[JsonSerializable(typeof(AgentState))]
[JsonSerializable(typeof(RecipeState))]
[JsonSerializable(typeof(System.Text.Json.JsonElement))]
internal sealed partial class RecipeSerializerContext : JsonSerializerContext;
