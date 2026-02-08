// Copyright (c) Microsoft. All rights reserved.

namespace AGUIServer;

internal sealed class ServerWeatherForecastRequest
{
    public DateTime Date { get; set; }
    public string Location { get; set; } = "Seattle";
}
