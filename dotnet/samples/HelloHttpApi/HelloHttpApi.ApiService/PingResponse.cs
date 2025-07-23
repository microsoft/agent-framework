// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace HelloHttpApi.ApiService;

public class PingResponse(PingResponseStatus status, long timeOfLastUpdate)
{
    [JsonPropertyName("status")]
    public PingResponseStatus Status { get; } = status;

    [JsonPropertyName("time_of_last_update")]
    public long TimeOfLastUpdate { get; } = timeOfLastUpdate;
}
