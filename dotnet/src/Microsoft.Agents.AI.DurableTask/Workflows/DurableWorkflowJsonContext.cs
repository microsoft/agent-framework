// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Source-generated JSON serialization context for durable workflow types.
/// </summary>
/// <remarks>
/// <para>
/// This context provides AOT-compatible and trimmer-safe JSON serialization for the
/// internal data transfer types used by the durable workflow infrastructure:
/// </para>
/// <list type="bullet">
/// <item><description><see cref="DurableActivityInput"/>: Activity input wrapper with state</description></item>
/// <item><description><see cref="DurableActivityOutput"/>: Activity output wrapper with results and events</description></item>
/// <item><description><see cref="SentMessageInfo"/>: Messages sent via SendMessageAsync</description></item>
/// </list>
/// <para>
/// Note: User-defined executor input/output types still use reflection-based serialization
/// since their types are not known at compile time.
/// </para>
/// </remarks>
[JsonSourceGenerationOptions(
    WriteIndented = false,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(DurableActivityInput))]
[JsonSerializable(typeof(DurableActivityOutput))]
[JsonSerializable(typeof(SentMessageInfo))]
[JsonSerializable(typeof(List<SentMessageInfo>))]
[JsonSerializable(typeof(Dictionary<string, string?>))]
internal partial class DurableWorkflowJsonContext : JsonSerializerContext;
