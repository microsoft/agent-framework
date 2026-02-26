// Copyright (c) Microsoft. All rights reserved.

namespace AGUIServer;

internal sealed class ServerWeatherForecastResponse
{
    public string Summary { get; set; } = "";

    public int TemperatureC { get; set; }

    public DateTime Date { get; set; }
}
