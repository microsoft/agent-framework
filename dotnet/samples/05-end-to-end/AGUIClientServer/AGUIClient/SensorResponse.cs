// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the AG-UI client to connect to a remote AG-UI server
// and display streaming updates including conversation/response metadata, text content, and errors.

namespace AGUIClient;

internal sealed class SensorResponse
{
    public double Temperature { get; set; }
    public double Humidity { get; set; }
    public int AirQualityIndex { get; set; }
}
