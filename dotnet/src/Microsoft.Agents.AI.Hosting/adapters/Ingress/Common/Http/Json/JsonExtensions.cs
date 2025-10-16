using System;
using System.ClientModel.Primitives;
using System.Text.Json;

using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Options;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.Json;

public static class JsonExtensions
{
    public static readonly JsonSerializerOptions DefaultJsonSerializerOptions = GetDefaultJsonSerializerOptions();

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

    public static JsonSerializerOptions GetDefaultJsonSerializerOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new JsonModelConverter());
        return options;
    }

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
}
