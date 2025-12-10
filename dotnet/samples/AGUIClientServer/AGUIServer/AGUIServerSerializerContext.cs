// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIServer;

[JsonSerializable(typeof(ServerWeatherForecastRequest))]
[JsonSerializable(typeof(ServerWeatherForecastResponse))]
internal sealed partial class AGUIServerSerializerContext : JsonSerializerContext;
