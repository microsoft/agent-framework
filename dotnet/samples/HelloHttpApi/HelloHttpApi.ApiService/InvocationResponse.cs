// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace HelloHttpApi.ApiService;

public class InvocationResponse
{
    [JsonPropertyName("response")]
    public JsonElement Response { get; set; }

    [JsonPropertyName("status")]
    public string? Status { get; set; } = "success";
}
