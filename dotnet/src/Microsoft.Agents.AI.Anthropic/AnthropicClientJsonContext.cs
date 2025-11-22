// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1812

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Anthropic;

[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(string))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
internal sealed partial class AnthropicClientJsonContext : JsonSerializerContext;
