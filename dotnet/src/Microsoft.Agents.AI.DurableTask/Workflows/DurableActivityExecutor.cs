// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Executes workflow activities by invoking executor bindings and handling serialization.
/// </summary>
[UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Workflow and executor types are registered at startup.")]
[UnconditionalSuppressMessage("Trimming", "IL2057", Justification = "Workflow and executor types are registered at startup.")]
[UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Workflow and executor types are registered at startup.")]
internal static class DurableActivityExecutor
{
    /// <summary>
    /// Executes an activity using the provided executor binding.
    /// </summary>
    /// <param name="binding">The executor binding to invoke.</param>
    /// <param name="input">The serialized input string.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The serialized activity output.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="binding"/> is null.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the executor factory is not configured.</exception>
    internal static async Task<string> ExecuteAsync(
        ExecutorBinding binding,
        string input,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(binding);

        if (binding.FactoryAsync is null)
        {
            throw new InvalidOperationException($"Executor binding for '{binding.Id}' does not have a factory configured.");
        }

        DurableActivityInput? inputWithState = TryDeserializeActivityInput(input);
        string executorInput = inputWithState?.Input ?? input;
        Dictionary<string, string> sharedState = inputWithState?.State ?? [];

        Executor executor = await binding.FactoryAsync(binding.Id).ConfigureAwait(false);
        Type inputType = ResolveInputType(inputWithState?.InputTypeName, executor.InputTypes);
        object typedInput = DeserializeInput(executorInput, inputType);

        DurableWorkflowContext workflowContext = new(sharedState, executor);
        object? result = await executor.ExecuteAsync(
            typedInput,
            new TypeId(inputType),
            workflowContext,
            cancellationToken).ConfigureAwait(false);

        return SerializeActivityOutput(result, workflowContext);
    }

    private static string SerializeActivityOutput(object? result, DurableWorkflowContext context)
    {
        DurableExecutorOutput output = new()
        {
            Result = SerializeResult(result),
            StateUpdates = context.StateUpdates,
            ClearedScopes = [.. context.ClearedScopes],
            Events = context.OutboundEvents.ConvertAll(SerializeEvent),
            SentMessages = context.SentMessages,
            HaltRequested = context.HaltRequested
        };

        return JsonSerializer.Serialize(output, DurableWorkflowJsonContext.Default.DurableExecutorOutput);
    }

    /// <summary>
    /// Serializes a workflow event with type information for proper deserialization.
    /// </summary>
    private static string SerializeEvent(WorkflowEvent evt)
    {
        Type eventType = evt.GetType();
        TypedPayload wrapper = new()
        {
            TypeName = eventType.AssemblyQualifiedName,
            Data = JsonSerializer.Serialize(evt, eventType, DurableSerialization.Options)
        };

        return JsonSerializer.Serialize(wrapper, DurableWorkflowJsonContext.Default.TypedPayload);
    }

    private static string SerializeResult(object? result)
    {
        if (result is null)
        {
            return string.Empty;
        }

        if (result is string str)
        {
            return str;
        }

        return JsonSerializer.Serialize(result, result.GetType(), DurableSerialization.Options);
    }

    private static DurableActivityInput? TryDeserializeActivityInput(string input)
    {
        try
        {
            return JsonSerializer.Deserialize(input, DurableWorkflowJsonContext.Default.DurableActivityInput);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static object DeserializeInput(string input, Type targetType)
    {
        if (targetType == typeof(string))
        {
            return input;
        }

        return JsonSerializer.Deserialize(input, targetType, DurableSerialization.Options)
            ?? throw new InvalidOperationException($"Failed to deserialize input to type '{targetType.Name}'.");
    }

    private static Type ResolveInputType(string? inputTypeName, ISet<Type> supportedTypes)
    {
        if (string.IsNullOrEmpty(inputTypeName))
        {
            return supportedTypes.FirstOrDefault() ?? typeof(string);
        }

        Type? matchedType = supportedTypes.FirstOrDefault(t =>
            t.AssemblyQualifiedName == inputTypeName ||
            t.FullName == inputTypeName ||
            t.Name == inputTypeName);

        if (matchedType is not null)
        {
            return matchedType;
        }

        Type? loadedType = Type.GetType(inputTypeName);

        // Fall back if type is string but executor doesn't support string
        if (loadedType == typeof(string) && !supportedTypes.Contains(typeof(string)))
        {
            return supportedTypes.FirstOrDefault() ?? typeof(string);
        }

        return loadedType ?? supportedTypes.FirstOrDefault() ?? typeof(string);
    }
}
