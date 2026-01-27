// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Azure Functions-specific workflow runner that extends the base <see cref="DurableWorkflowRunner"/>
/// with Azure Functions activity execution support.
/// </summary>
internal sealed class FunctionsWorkflowRunner : DurableWorkflowRunner
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionsWorkflowRunner"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public FunctionsWorkflowRunner(ILogger<FunctionsWorkflowRunner> logger, DurableOptions durableOptions)
        : base(logger, durableOptions)
    {
    }

    /// <summary>
    /// Executes an activity function for a workflow executor.
    /// </summary>
    /// <param name="activityFunctionName">The name of the activity function to execute.</param>
    /// <param name="input">The serialized executor input (may include state via ActivityInputWithState wrapper).</param>
    /// <param name="durableTaskClient">The durable task client (unused in pipeline mode, kept for API compatibility).</param>
    /// <param name="functionContext">The function context containing binding data with the orchestration instance ID.</param>
    /// <returns>The serialized executor output (wrapped in ActivityOutputWithState).</returns>
    [UnconditionalSuppressMessage("AOT", "IL2026:RequiresUnreferencedCode", Justification = "Executor types are registered at startup.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Executor types are registered at startup.")]
    internal async Task<string> ExecuteActivityAsync(
        string activityFunctionName,
        string input,
        DurableTaskClient durableTaskClient,
        FunctionContext functionContext)
    {
        ArgumentNullException.ThrowIfNull(activityFunctionName);
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(functionContext);

        string executorName = ParseExecutorName(activityFunctionName);

        if (!this.Options.Executors.TryGetExecutor(executorName, out ExecutorRegistration? registration) || registration is null)
        {
            throw new InvalidOperationException($"Executor '{executorName}' not found in the executor registry.");
        }

        this.Logger.LogExecutingActivity(registration.ExecutorId, executorName);

        // Deserialize the input wrapper that includes state (pipeline approach)
        ActivityInputWithState? inputWithState = TryDeserializeActivityInput(input);
        string executorInput = inputWithState?.Input ?? input;
        Dictionary<string, string> sharedState = inputWithState?.State ?? [];

        Executor executor = await registration.CreateExecutorInstanceAsync("activity-run", CancellationToken.None)
            .ConfigureAwait(false);

        Type inputType = executor.InputTypes.FirstOrDefault() ?? typeof(string);
        object typedInput = DeserializeInput(executorInput, inputType);

        // Create pipeline context that manages state locally with executor ID
        FunctionsPipelineActivityContext context = new(sharedState, executor.Id);

        object? result = await executor.ExecuteAsync(
            typedInput,
            new TypeId(inputType),
            context,
            CancellationToken.None).ConfigureAwait(false);

        // Return wrapped output with state updates, events, and result
        ActivityOutputWithState output = new()
        {
            Result = SerializeResult(result),
            StateUpdates = context.StateUpdates,
            ClearedScopes = [.. context.ClearedScopes],
            Events = context.Events.ConvertAll(SerializeEvent)
        };

        return JsonSerializer.Serialize(output);
    }

    [UnconditionalSuppressMessage("AOT", "IL2026:RequiresUnreferencedCode", Justification = "Deserializing known wrapper type.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Deserializing known wrapper type.")]
    private static ActivityInputWithState? TryDeserializeActivityInput(string input)
    {
        try
        {
            return JsonSerializer.Deserialize<ActivityInputWithState>(input);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    [UnconditionalSuppressMessage("AOT", "IL2026:RequiresUnreferencedCode", Justification = "Serializing workflow event types.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Serializing workflow event types.")]
    private static string SerializeEvent(WorkflowEvent evt)
    {
        // Serialize with type information so we can deserialize to the correct type later
        Microsoft.Agents.AI.DurableTask.SerializedWorkflowEvent wrapper = new()
        {
            TypeName = evt.GetType().AssemblyQualifiedName,
            Data = JsonSerializer.Serialize(evt, evt.GetType())
        };
        return JsonSerializer.Serialize(wrapper);
    }

    /// <summary>
    /// A pipeline-based workflow context for Azure Functions activity execution.
    /// State is passed in from the orchestration and updates are collected for return.
    /// </summary>
    private sealed class FunctionsPipelineActivityContext : IWorkflowContext
    {
        private readonly Dictionary<string, string> _initialState;
        private readonly string _executorId;

        public FunctionsPipelineActivityContext(Dictionary<string, string>? initialState, string executorId)
        {
            this._initialState = initialState ?? [];
            this._executorId = executorId;
        }

        public List<WorkflowEvent> Events { get; } = [];
        public Dictionary<string, string?> StateUpdates { get; } = [];
        public HashSet<string> ClearedScopes { get; } = [];

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
        {
            if (workflowEvent is not null)
            {
                this.Events.Add(workflowEvent);
            }

            return default;
        }

        public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default) => default;

        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
        {
            // Emit DurableYieldedOutputEvent (WorkflowOutputEvent has internal constructor)
            if (output is not null)
            {
                this.Events.Add(new DurableYieldedOutputEvent(this._executorId, output));
            }

            return default;
        }

        public ValueTask RequestHaltAsync()
        {
            // Emit DurableHaltRequestedEvent (RequestHaltEvent is internal)
            this.Events.Add(new DurableHaltRequestedEvent(this._executorId));
            return default;
        }

        [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow state types.")]
        [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow state types.")]
        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            string scopeKey = GetScopeKey(scopeName, key);
            string normalizedScope = scopeName ?? "__default__";

            if (this.ClearedScopes.Contains(normalizedScope))
            {
                if (this.StateUpdates.TryGetValue(scopeKey, out string? updatedAfterClear) && updatedAfterClear is not null)
                {
                    return ValueTask.FromResult(JsonSerializer.Deserialize<T>(updatedAfterClear));
                }

                return ValueTask.FromResult<T?>(default);
            }

            if (this.StateUpdates.TryGetValue(scopeKey, out string? updated))
            {
                return updated is null
                    ? ValueTask.FromResult<T?>(default)
                    : ValueTask.FromResult(JsonSerializer.Deserialize<T>(updated));
            }

            if (this._initialState.TryGetValue(scopeKey, out string? initial))
            {
                return ValueTask.FromResult(JsonSerializer.Deserialize<T>(initial));
            }

            return ValueTask.FromResult<T?>(default);
        }

        [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow state types.")]
        [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow state types.")]
        public async ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            T? value = await this.ReadStateAsync<T>(key, scopeName, cancellationToken).ConfigureAwait(false);
            if (value is not null)
            {
                return value;
            }

            T initialValue = initialStateFactory();
            await this.QueueStateUpdateAsync(key, initialValue, scopeName, cancellationToken).ConfigureAwait(false);
            return initialValue;
        }

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        {
            string scopePrefix = GetScopePrefix(scopeName);
            string normalizedScope = scopeName ?? "__default__";
            HashSet<string> keys = [];

            if (this.ClearedScopes.Contains(normalizedScope))
            {
                foreach (KeyValuePair<string, string?> update in this.StateUpdates)
                {
                    if (update.Key.StartsWith(scopePrefix, StringComparison.Ordinal) && update.Value is not null)
                    {
                        keys.Add(update.Key[scopePrefix.Length..]);
                    }
                }

                return ValueTask.FromResult(keys);
            }

            foreach (string stateKey in this._initialState.Keys)
            {
                if (stateKey.StartsWith(scopePrefix, StringComparison.Ordinal))
                {
                    keys.Add(stateKey[scopePrefix.Length..]);
                }
            }

            foreach (KeyValuePair<string, string?> update in this.StateUpdates)
            {
                if (update.Key.StartsWith(scopePrefix, StringComparison.Ordinal))
                {
                    string foundKey = update.Key[scopePrefix.Length..];
                    if (update.Value is not null)
                    {
                        keys.Add(foundKey);
                    }
                    else
                    {
                        keys.Remove(foundKey);
                    }
                }
            }

            return ValueTask.FromResult(keys);
        }

        [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow state types.")]
        [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow state types.")]
        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            string scopeKey = GetScopeKey(scopeName, key);
            this.StateUpdates[scopeKey] = value is null ? null : JsonSerializer.Serialize(value);
            return default;
        }

        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
        {
            string normalizedScope = scopeName ?? "__default__";
            this.ClearedScopes.Add(normalizedScope);

            string scopePrefix = GetScopePrefix(scopeName);
            List<string> keysToRemove = this.StateUpdates.Keys
                .Where(k => k.StartsWith(scopePrefix, StringComparison.Ordinal))
                .ToList();

            foreach (string key in keysToRemove)
            {
                this.StateUpdates.Remove(key);
            }

            return default;
        }

        public IReadOnlyDictionary<string, string>? TraceContext => null;
        public bool ConcurrentRunsEnabled => false;

        private static string GetScopeKey(string? scopeName, string key)
            => $"{GetScopePrefix(scopeName)}{key}";

        private static string GetScopePrefix(string? scopeName)
            => scopeName is null ? "__default__:" : $"{scopeName}:";
    }
}

/// <summary>
/// Wrapper for activity input that includes shared state from the orchestration.
/// </summary>
internal sealed class ActivityInputWithState
{
    /// <summary>
    /// Gets or sets the serialized executor input.
    /// </summary>
    public string? Input { get; set; }

    /// <summary>
    /// Gets or sets the shared state dictionary (scope-prefixed key -> serialized value).
    /// </summary>
    public Dictionary<string, string> State { get; set; } = [];
}

/// <summary>
/// Wrapper for activity output that includes state updates and events.
/// </summary>
internal sealed class ActivityOutputWithState
{
    /// <summary>
    /// Gets or sets the serialized result of the activity.
    /// </summary>
    public string? Result { get; set; }

    /// <summary>
    /// Gets or sets state updates made during activity execution.
    /// </summary>
    public Dictionary<string, string?> StateUpdates { get; set; } = [];

    /// <summary>
    /// Gets or sets scopes that were cleared during activity execution.
    /// </summary>
    public List<string> ClearedScopes { get; set; } = [];

    /// <summary>
    /// Gets or sets the serialized workflow events emitted during activity execution.
    /// </summary>
    public List<string> Events { get; set; } = [];
}
