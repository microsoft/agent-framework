// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the AG-UI client to connect to a remote AG-UI server
// and display streaming updates including conversation/response metadata, text content, and errors.

namespace AGUIClient;

internal sealed class SensorRequest
{
    public bool IncludeTemperature { get; set; } = true;
    public bool IncludeHumidity { get; set; } = true;
    public bool IncludeAirQualityIndex { get; set; } = true;
}
