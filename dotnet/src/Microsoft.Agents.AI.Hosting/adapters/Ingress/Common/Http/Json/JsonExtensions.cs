using System;
using System.ClientModel.Primitives;
using System.Text.Json;

using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Options;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.Json;

/// <summary>
/// Extension methods for JSON serialization.
/// </summary>
public static class JsonExtensions
{
    /// <summary>
    /// Gets the default JSON serializer options.
    /// </summary>
    public static readonly JsonSerializerOptions DefaultJsonSerializerOptions = GetDefaultJsonSerializerOptions();

    /// <summary>
    /// Gets the JSON serializer options from the HTTP context.
    /// </summary>
    /// <param name="ctx">The HTTP context.</param>
    /// <returns>The JSON serializer options.</returns>
    public static JsonSerializerOptions GetJsonSerializerOptions(this HttpContext ctx)
    {
        // Prefer Minimal API (Http.Json) options if present
        var httpJson = ctx.RequestServices.GetService(typeof(IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>));
        if (httpJson is IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions> httpJsonOptions)
        {
            return httpJsonOptions.Value.SerializerOptions;
        }

        // Fallback to MVC options (if you’re inside MVC)
        var mvcJson = ctx.RequestServices.GetService(typeof(IOptions<Microsoft.AspNetCore.Mvc.JsonOptions>));
        if (mvcJson is IOptions<Microsoft.AspNetCore.Mvc.JsonOptions> mvcJsonOptions)
        {
            return mvcJsonOptions.Value.JsonSerializerOptions;
        }

        return GetDefaultJsonSerializerOptions();
    }

    /// <summary>
    /// Gets the default JSON serializer options with model converters.
    /// </summary>
    /// <returns>The default JSON serializer options.</returns>
    public static JsonSerializerOptions GetDefaultJsonSerializerOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access
        options.Converters.Add(new JsonModelConverter());
#pragma warning restore IL2026
        return options;
    }

    /// <summary>
    /// Converts binary data to an object using JSON deserialization.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <param name="data">The binary data to deserialize.</param>
    /// <param name="options">Optional JSON serializer options.</param>
    /// <returns>The deserialized object or null if deserialization fails.</returns>
#pragma warning disable IL2026, IL3050 // JSON serialization requires dynamic access
    public static T? ToObject<T>(this BinaryData data, JsonSerializerOptions? options = null) where T : class
    {
        options ??= DefaultJsonSerializerOptions;

        try
        {
            return data.ToObjectFromJson<T>(options);
        }
        catch (JsonException)
        {
            return null;
        }
    }
#pragma warning restore IL2026, IL3050
}
