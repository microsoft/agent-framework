// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Source-generated JSON options for checkpointing declarative workflows under
/// AOT / trim-aggressive deployments where reflection-based serialization is disabled.
/// </summary>
/// <remarks>
/// <para>
/// Pass <see cref="Default"/> to <see cref="CheckpointManager.CreateJson(ICheckpointStore{JsonElement}, JsonSerializerOptions?)"/>.
/// </para>
/// <para>
/// User-defined types (workflow inputs, custom <see cref="ActionExecutorResult.Result"/> payloads,
/// non-primitive approval-request arguments) must be registered in user-supplied options. Compose by
/// cloning <see cref="Default"/> and appending your own resolver, for example:
/// <code>
/// JsonSerializerOptions options = new(DeclarativeWorkflowJsonOptions.Default);
/// options.TypeInfoResolverChain.Add(MyAppJsonContext.Default);
/// options.MakeReadOnly();
/// CheckpointManager manager = CheckpointManager.CreateJson(store, options);
/// </code>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static partial class DeclarativeWorkflowJsonOptions
{
    /// <summary>Gets the source-gen <see cref="JsonSerializerOptions"/> covering declarative-package checkpoint types.</summary>
    public static JsonSerializerOptions Default { get; } = CreateDefaultOptions();

    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Source-gen context.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Source-gen context.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        JsonSerializerOptions options = new(DeclarativeJsonContext.Default.Options);

        // Declarative source-gen first, then agent abstractions for ChatMessage/AgentResponse/etc.
        // Framework types resolve via JsonMarshaller's internal options, so we do not chain WorkflowsJsonUtilities here.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(DeclarativeJsonContext.Default);
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }

    [JsonSourceGenerationOptions(
        JsonSerializerDefaults.Web,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]
    [JsonSerializable(typeof(ActionExecutorResult))]
    [JsonSerializable(typeof(ExternalInputRequest))]
    [JsonSerializable(typeof(ExternalInputResponse))]
    [JsonSerializable(typeof(UnassignedValue))]
    [JsonSerializable(typeof(List<string>))]
    // TypeInfoPropertyName disambiguates the two ApprovalSnapshot records that share a simple name.
    [JsonSerializable(typeof(Dictionary<string, InvokeFunctionToolExecutor.ApprovalSnapshot>),
        TypeInfoPropertyName = "DictionaryStringFunctionApprovalSnapshot")]
    [JsonSerializable(typeof(InvokeFunctionToolExecutor.ApprovalSnapshot),
        TypeInfoPropertyName = "FunctionApprovalSnapshot")]
    [JsonSerializable(typeof(Dictionary<string, InvokeMcpToolExecutor.ApprovalSnapshot>),
        TypeInfoPropertyName = "DictionaryStringMcpApprovalSnapshot")]
    [JsonSerializable(typeof(InvokeMcpToolExecutor.ApprovalSnapshot),
        TypeInfoPropertyName = "McpApprovalSnapshot")]
    [ExcludeFromCodeCoverage]
    internal sealed partial class DeclarativeJsonContext : JsonSerializerContext;
}
