// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.A2A;

[JsonSerializable(typeof(IDictionary<string, JsonElement>))]
internal sealed partial class A2AJsonContext : JsonSerializerContext;
