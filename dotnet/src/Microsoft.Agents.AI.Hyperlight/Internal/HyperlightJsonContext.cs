// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Source-generated JSON context for the well-known envelope shapes the Hyperlight
/// integration serializes (the execute_code result payload and the tool error payload).
/// User-supplied tool results are serialized via AIJsonUtilities.DefaultOptions instead
/// because their types cannot be statically known at compile time.
/// </summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.General)]
[JsonSerializable(typeof(HyperlightExecutionResult))]
[JsonSerializable(typeof(HyperlightToolError))]
internal sealed partial class HyperlightJsonContext : JsonSerializerContext;

internal sealed record HyperlightExecutionResult(
    [property: JsonPropertyName("stdout")] string Stdout,
    [property: JsonPropertyName("stderr")] string Stderr,
    [property: JsonPropertyName("exit_code")] int ExitCode,
    [property: JsonPropertyName("success")] bool Success);

internal sealed record HyperlightToolError(
    [property: JsonPropertyName("error")] string Error);
