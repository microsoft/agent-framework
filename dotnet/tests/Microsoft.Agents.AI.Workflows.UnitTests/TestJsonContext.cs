// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

// Checkpointing Types
[JsonSerializable(typeof(TestJsonSerializable))]
[JsonSerializable(typeof(TestExternalRequestEnvelope))]
[ExcludeFromCodeCoverage]
internal sealed partial class TestJsonContext : JsonSerializerContext;
