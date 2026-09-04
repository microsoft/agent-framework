// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Globalization;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal enum ForeachExecutionMode
{
    Sequential,
    Parallel,
}

/// <summary>
/// Strongly typed adapter for Foreach execution fields preserved by the external ObjectModel package.
/// </summary>
/// <remarks>
/// Once <see cref="Foreach"/> exposes generated properties for these fields, only this adapter needs to change.
/// </remarks>
internal sealed record ForeachExecutionOptions(
    ForeachExecutionMode Mode,
    int MaxParallelism,
    TimeSpan? IterationTimeout)
{
    internal const string ModePropertyName = "mode";
    internal const string MaxParallelismPropertyName = "maxParallelism";
    internal const string TimeoutPropertyName = "timeoutInMilliseconds";

    private const int DefaultMaxParallelism = 4;

    public bool IsParallel => this.Mode == ForeachExecutionMode.Parallel;

    public static ForeachExecutionOptions Parse(Foreach model)
    {
        DataValue? modeValue = GetExtensionValue(model, ModePropertyName);
        DataValue? maxParallelismValue = GetExtensionValue(model, MaxParallelismPropertyName);
        DataValue? timeoutValue = GetExtensionValue(model, TimeoutPropertyName);

        ForeachExecutionMode mode = ParseMode(model, modeValue);
        int maxParallelism = ParseInteger(model, MaxParallelismPropertyName, maxParallelismValue) ?? DefaultMaxParallelism;
        int? timeoutMilliseconds = ParseInteger(model, TimeoutPropertyName, timeoutValue);

        if (mode == ForeachExecutionMode.Sequential && (maxParallelismValue is not null || timeoutValue is not null))
        {
            throw InvalidConfiguration(model, $"'{MaxParallelismPropertyName}' and '{TimeoutPropertyName}' require '{ModePropertyName}: Parallel'.");
        }

        if (maxParallelism <= 0)
        {
            throw InvalidConfiguration(model, $"'{MaxParallelismPropertyName}' must be greater than zero.");
        }

        if (timeoutMilliseconds <= 0)
        {
            throw InvalidConfiguration(model, $"'{TimeoutPropertyName}' must be greater than zero when specified.");
        }

        return new(mode, maxParallelism, timeoutMilliseconds.HasValue ? TimeSpan.FromMilliseconds(timeoutMilliseconds.Value) : null);
    }

    private static ForeachExecutionMode ParseMode(Foreach model, DataValue? value)
    {
        if (value is null)
        {
            return ForeachExecutionMode.Sequential;
        }

        if (value is not StringDataValue stringValue)
        {
            throw InvalidConfiguration(model, $"'{ModePropertyName}' must be 'Sequential' or 'Parallel'.");
        }

        if (string.Equals(stringValue.Value, nameof(ForeachExecutionMode.Sequential), StringComparison.OrdinalIgnoreCase))
        {
            return ForeachExecutionMode.Sequential;
        }

        if (string.Equals(stringValue.Value, nameof(ForeachExecutionMode.Parallel), StringComparison.OrdinalIgnoreCase))
        {
            return ForeachExecutionMode.Parallel;
        }

        throw InvalidConfiguration(model, $"'{ModePropertyName}' must be 'Sequential' or 'Parallel'.");
    }

    private static int? ParseInteger(Foreach model, string propertyName, DataValue? value)
    {
        if (value is null)
        {
            return null;
        }

        object? rawValue = value.ToFormula().ToObject();
        if (rawValue is not (byte or sbyte or short or ushort or int or uint or long or ulong or float or double or decimal))
        {
            throw InvalidConfiguration(model, $"'{propertyName}' must be an integer.");
        }

        decimal decimalValue;
        try
        {
            decimalValue = Convert.ToDecimal(rawValue, CultureInfo.InvariantCulture);
        }
        catch (Exception exception) when (exception is FormatException or InvalidCastException or OverflowException)
        {
            throw InvalidConfiguration(model, $"'{propertyName}' must be an integer.", exception);
        }

        if (decimalValue != decimal.Truncate(decimalValue) || decimalValue < int.MinValue || decimalValue > int.MaxValue)
        {
            throw InvalidConfiguration(model, $"'{propertyName}' must be an integer.");
        }

        return decimal.ToInt32(decimalValue);
    }

    private static DataValue? GetExtensionValue(Foreach model, string propertyName) =>
        model.ExtensionData?.Properties.TryGetValue(propertyName, out DataValue? value) is true ? value : null;

    private static DeclarativeModelException InvalidConfiguration(Foreach model, string message, Exception? innerException = null) =>
        new($"Invalid Foreach configuration for '{model.Id.Value}': {message}", innerException);
}
