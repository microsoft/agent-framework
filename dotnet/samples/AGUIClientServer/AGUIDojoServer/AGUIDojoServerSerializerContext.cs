// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoServer;

[JsonSerializable(typeof(WeatherInfo))]
internal sealed partial class AGUIDojoServerSerializerContext : JsonSerializerContext
{
}
