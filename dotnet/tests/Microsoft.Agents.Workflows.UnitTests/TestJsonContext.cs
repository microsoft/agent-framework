// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows.UnitTests;

// Checkpointing Types
[JsonSerializable(typeof(TestJsonSerializable))]
[ExcludeFromCodeCoverage]
internal sealed partial class TestJsonContext : JsonSerializerContext;
