// Copyright (c) Microsoft. All rights reserved.

namespace AGUIDojoClient.Components.Demos.ToolBasedGenerativeUI;

/// <summary>
/// Represents a haiku with Japanese and English translations, along with display properties.
/// </summary>
public class Haiku
{
    /// <summary>
    /// Gets or sets the three lines of the haiku in Japanese.
    /// </summary>
    public IReadOnlyList<string> Japanese { get; set; } = [];

    /// <summary>
    /// Gets or sets the three lines of the haiku translated to English.
    /// </summary>
    public IReadOnlyList<string> English { get; set; } = [];

    /// <summary>
    /// Gets or sets the name of the image associated with the haiku.
    /// </summary>
    public string? ImageName { get; set; }

    /// <summary>
    /// Gets or sets the CSS gradient for the haiku card background.
    /// </summary>
    public string Gradient { get; set; } = string.Empty;

    /// <summary>
    /// List of valid image names that can be used with haikus.
    /// </summary>
    public static readonly string[] ValidImageNames =
    [
        "Osaka_Castle_Turret_Stone_Wall_Pine_Trees_Daytime.jpg",
        "Tokyo_Skyline_Night_Tokyo_Tower_Mount_Fuji_View.jpg",
        "Itsukushima_Shrine_Miyajima_Floating_Torii_Gate_Sunset_Long_Exposure.jpg",
        "Takachiho_Gorge_Waterfall_River_Lush_Greenery_Japan.jpg",
        "Bonsai_Tree_Potted_Japanese_Art_Green_Foliage.jpeg",
        "Shirakawa-go_Gassho-zukuri_Thatched_Roof_Village_Aerial_View.jpg",
        "Ginkaku-ji_Silver_Pavilion_Kyoto_Japanese_Garden_Pond_Reflection.jpg",
        "Senso-ji_Temple_Asakusa_Cherry_Blossoms_Kimono_Umbrella.jpg",
        "Cherry_Blossoms_Sakura_Night_View_City_Lights_Japan.jpg",
        "Mount_Fuji_Lake_Reflection_Cherry_Blossoms_Sakura_Spring.jpg"
    ];

    /// <summary>
    /// Creates a default placeholder haiku.
    /// </summary>
    public static Haiku CreatePlaceholder() => new()
    {
        Japanese = ["仮の句よ", "まっさらながら", "花を呼ぶ"],
        English = ["A placeholder verse—", "even in a blank canvas,", "it beckons flowers."],
        ImageName = null,
        Gradient = string.Empty
    };
}
