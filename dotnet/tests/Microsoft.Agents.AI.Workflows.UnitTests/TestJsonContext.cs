// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

// Checkpointing Types
[JsonSerializable(typeof(TestJsonSerializable))]
[JsonSerializable(typeof(TestExternalRequestEnvelope))]
[JsonSerializable(typeof(RequestPortSourceRequest))]
[JsonSerializable(typeof(RequestPortTargetRequest))]
[JsonSerializable(typeof(RequestPortBaseRequest))]
[JsonSerializable(typeof(RequestPortDerivedRequest))]
[ExcludeFromCodeCoverage]
internal sealed partial class TestJsonContext : JsonSerializerContext;
