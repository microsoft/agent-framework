// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace RecipeAssistant;

// State response wrapper returned by the tool. Its shape is what the client renders as state.
internal sealed class RecipeResponse
{
    [JsonPropertyName("recipe")]
    public Recipe Recipe { get; set; } = new();
}

// Recipe state model.
internal sealed class Recipe
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("skill_level")]
    public string SkillLevel { get; set; } = string.Empty;

    [JsonPropertyName("cooking_time")]
    public string CookingTime { get; set; } = string.Empty;

    [JsonPropertyName("special_preferences")]
    public List<string> SpecialPreferences { get; set; } = [];

    [JsonPropertyName("ingredients")]
    public List<Ingredient> Ingredients { get; set; } = [];

    [JsonPropertyName("instructions")]
    public List<string> Instructions { get; set; } = [];
}

// A single ingredient.
internal sealed class Ingredient
{
    [JsonPropertyName("icon")]
    public string Icon { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("amount")]
    public string Amount { get; set; } = string.Empty;
}

// JSON serialization context for the tool payloads.
[JsonSerializable(typeof(RecipeResponse))]
[JsonSerializable(typeof(Recipe))]
[JsonSerializable(typeof(Ingredient))]
internal sealed partial class RecipeSerializerContext : JsonSerializerContext;
