// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Context for a function invocation, tracking the call and its result.
/// </summary>
public class InvocationContext
{
    private Action? _resultArrived;

    /// <summary>
    /// Initializes a new instance of the <see cref="InvocationContext"/> class.
    /// </summary>
    /// <param name="call">The function call content.</param>
    public InvocationContext(FunctionCallContent call)
    {
        this.Call = call;
    }

    /// <summary>
    /// Gets the function call content.
    /// </summary>
    public FunctionCallContent Call { get; }

    /// <summary>
    /// Gets the function result content, if available.
    /// </summary>
    public FunctionResultContent? ResultContent { get; private set; }

    /// <summary>
    /// Gets a value indicating whether the result has arrived.
    /// </summary>
    public bool HasResult => this.ResultContent != null;

    /// <summary>
    /// Gets the function name from the call.
    /// </summary>
    public string FunctionName => this.Call.Name;

    /// <summary>
    /// Gets the call ID.
    /// </summary>
    public string CallId => this.Call.CallId;

    /// <summary>
    /// Gets the arguments from the call.
    /// </summary>
    public IDictionary<string, object?>? Arguments => this.Call.Arguments;

    /// <summary>
    /// Event raised when the result arrives.
    /// </summary>
#pragma warning disable CA1003 // Use generic event handler instances
    public event Action? ResultArrived
#pragma warning restore CA1003 // Use generic event handler instances
    {
        add => this._resultArrived += value;
        remove => this._resultArrived -= value;
    }

    /// <summary>
    /// Sets the result and raises the ResultArrived event.
    /// </summary>
    /// <param name="result">The function result content.</param>
    internal void SetResult(FunctionResultContent result)
    {
        this.ResultContent = result;
        this._resultArrived?.Invoke();
        this._resultArrived = null; // Clear invocation list after firing
    }

    /// <summary>
    /// Gets an argument value by name, deserializing from JSON if necessary.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <param name="name">The argument name.</param>
    /// <returns>The argument value, or default if not found.</returns>
    public T? GetArgument<T>(string name)
    {
        if (this.Arguments is null || !this.Arguments.TryGetValue(name, out var value))
        {
            return default;
        }

        if (value is null)
        {
            return default;
        }

        if (value is T typed)
        {
            return typed;
        }

        if (value is JsonElement jsonElement)
        {
            return jsonElement.Deserialize<T>();
        }

        // Try to convert via JSON serialization
        var json = JsonSerializer.Serialize(value);
        return JsonSerializer.Deserialize<T>(json);
    }

    /// <summary>
    /// Gets the result as a specific type, deserializing from JSON if necessary.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <returns>The result value, or default if not available.</returns>
    public T? GetResult<T>()
    {
        if (this.ResultContent?.Result is null)
        {
            return default;
        }

        if (this.ResultContent.Result is T typed)
        {
            return typed;
        }

        if (this.ResultContent.Result is JsonElement jsonElement)
        {
            return jsonElement.Deserialize<T>();
        }

        // Try to convert via JSON serialization
        var json = JsonSerializer.Serialize(this.ResultContent.Result);
        return JsonSerializer.Deserialize<T>(json);
    }
}
