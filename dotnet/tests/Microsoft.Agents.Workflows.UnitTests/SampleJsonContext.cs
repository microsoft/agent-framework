// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows.Sample;

namespace Microsoft.Agents.Workflows.UnitTests;

// Checkpointing Types
[JsonSerializable(typeof(NumberSignal))]
[ExcludeFromCodeCoverage]
internal sealed partial class SampleJsonContext : JsonSerializerContext;
