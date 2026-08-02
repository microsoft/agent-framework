// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Source-generated <see cref="JsonSerializerContext"/> for loop types that require JSON serialization, such as the
/// structured <see cref="JudgeVerdict"/> used by <see cref="AIJudgeLoopEvaluator"/>.
/// </summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web)]
[JsonSerializable(typeof(JudgeVerdict))]
[ExcludeFromCodeCoverage]
internal sealed partial class LoopJsonContext : JsonSerializerContext;
