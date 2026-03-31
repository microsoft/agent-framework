// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the AG-UI client to connect to a remote AG-UI server
// and display streaming updates including conversation/response metadata, text content, and errors.

using System.Text.Json.Serialization;

namespace AGUIClient;

[JsonSerializable(typeof(SensorRequest))]
[JsonSerializable(typeof(SensorResponse))]
internal sealed partial class AGUIClientSerializerContext : JsonSerializerContext;
