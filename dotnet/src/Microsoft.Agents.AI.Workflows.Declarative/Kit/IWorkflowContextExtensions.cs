// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Extension methods for <see cref="IWorkflowContext"/> that assist with
/// Power Fx expression evaluation.
/// </summary>
public static class IWorkflowContextExtensions
{
    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="line">The template line to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>
    /// A single string containing the formatted results of all lines separated by newline characters.
    /// A trailing newline will be present if at least one line was processed.
    /// </returns>
    /// <example>
    /// Example:
    /// var text = await context.FormatAsync("Hello @{User.Name}", "Count: @{Metrics.Count}");
    /// </example>
    public static ValueTask<string> FormatTemplateAsync(this IWorkflowContext context, string line, CancellationToken cancellationToken = default) =>
        context.FormatTemplateAsync([line], cancellationToken);

    /// <summary>
    /// Formats a template line using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within the line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="line">The template line to format.</param>
    /// <returns>The formatted line and its sensitivity metadata.</returns>
    public static ValueTask<EvaluationResult<string>> FormatTemplateWithSensitivityAsync(this IWorkflowContext context, string line) =>
        context.FormatTemplateWithSensitivityAsync(line, default);

    /// <summary>
    /// Formats a template line using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within the line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="line">The template line to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The formatted line and its sensitivity metadata.</returns>
    public static ValueTask<EvaluationResult<string>> FormatTemplateWithSensitivityAsync(this IWorkflowContext context, string line, CancellationToken cancellationToken) =>
        context.FormatTemplateWithSensitivityAsync([line], cancellationToken);

    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="lines">The template lines to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>
    /// A single string containing the formatted results of all lines separated by newline characters.
    /// A trailing newline will be present if at least one line was processed.
    /// </returns>
    /// <example>
    /// Example:
    /// var text = await context.FormatAsync("Hello @{User.Name}", "Count: @{Metrics.Count}");
    /// </example>
    public static async ValueTask<string> FormatTemplateAsync(this IWorkflowContext context, IEnumerable<string> lines, CancellationToken cancellationToken = default)
    {
        EvaluationResult<string> result = await context.FormatTemplateWithSensitivityAsync(lines, cancellationToken).ConfigureAwait(false);
        ThrowIfSensitive(result.Sensitivity);
        return result.Value;
    }

    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="lines">The template lines to format.</param>
    /// <returns>The formatted lines and their sensitivity metadata.</returns>
    public static ValueTask<EvaluationResult<string>> FormatTemplateWithSensitivityAsync(this IWorkflowContext context, IEnumerable<string> lines) =>
        context.FormatTemplateWithSensitivityAsync(lines, default);

    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="lines">The template lines to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The formatted lines and their sensitivity metadata.</returns>
    public static async ValueTask<EvaluationResult<string>> FormatTemplateWithSensitivityAsync(this IWorkflowContext context, IEnumerable<string> lines, CancellationToken cancellationToken)
    {
        WorkflowFormulaState state = await context.GetStateAsync(cancellationToken).ConfigureAwait(false);

        StringBuilder builder = new();
        SensitivityLevel sensitivity = SensitivityLevel.None;
        foreach (string line in lines)
        {
            EvaluationResult<string> result = state.Evaluator.Format(TemplateLine.Parse(line));
            sensitivity = MaxSensitivity(sensitivity, result.Sensitivity);
            builder.AppendLine(result.Value);
        }

        return new(builder.ToString(), sensitivity);
    }

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="expression">The expression to evaluate.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated expression value</returns>
    public static ValueTask<object?> EvaluateValueAsync(this IWorkflowContext context, string expression, CancellationToken cancellationToken = default) =>
            context.EvaluateValueAsync<object>(expression, cancellationToken);

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="expression">The expression to evaluate.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated expression value</returns>
    public static async ValueTask<TValue?> EvaluateValueAsync<TValue>(this IWorkflowContext context, string expression, CancellationToken cancellationToken = default)
    {
        EvaluationResult<TValue?> result = await context.EvaluateValueWithSensitivityAsync<TValue>(expression, cancellationToken).ConfigureAwait(false);
        ThrowIfSensitive(result.Sensitivity);
        return result.Value;
    }

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <typeparam name="TValue">The type of the evaluated value.</typeparam>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="expression">The expression to evaluate.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated expression value and its sensitivity metadata.</returns>
    public static async ValueTask<EvaluationResult<TValue?>> EvaluateValueWithSensitivityAsync<TValue>(this IWorkflowContext context, string expression, CancellationToken cancellationToken = default)
    {
        WorkflowFormulaState state = await context.GetStateAsync(cancellationToken).ConfigureAwait(false);

        EvaluationResult<DataValue> result = state.Evaluator.GetValue(ValueExpression.Expression(expression));

        return new((TValue?)result.Value.ToObject(), result.Sensitivity);
    }

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <typeparam name="TElement">The type of the list element.</typeparam>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="expression">The expression to evaluate.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated list expression</returns>
    public static async ValueTask<IList<TElement>?> EvaluateListAsync<TElement>(this IWorkflowContext context, string expression, CancellationToken cancellationToken = default)
    {
        WorkflowFormulaState state = await context.GetStateAsync(cancellationToken).ConfigureAwait(false);

        EvaluationResult<DataValue> result = state.Evaluator.GetValue(ValueExpression.Expression(expression));
        ThrowIfSensitive(result.Sensitivity);

        return result.Value.AsList<TElement>();
    }

    /// <summary>
    /// Reads a state value together with its sensitivity metadata.
    /// </summary>
    /// <typeparam name="TValue">The type of the state value.</typeparam>
    /// <param name="context">The workflow execution context used to read state.</param>
    /// <param name="key">The key of the state value.</param>
    /// <param name="scopeName">An optional name that specifies the scope to read. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The state value and its sensitivity metadata.</returns>
    public static async ValueTask<EvaluationResult<TValue?>> ReadStateWithSensitivityAsync<TValue>(
        this IWorkflowContext context,
        string key,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        if (context is DeclarativeWorkflowContext declarativeContext)
        {
            string effectiveScopeName = scopeName ?? WorkflowFormulaState.DefaultScopeName;
            TValue? declarativeValue = await context.ReadStateAsync<TValue>(key, effectiveScopeName, cancellationToken).ConfigureAwait(false);
            SensitivityLevel declarativeSensitivity = declarativeContext.State.GetSensitivity(key, effectiveScopeName);
            return new(declarativeValue, declarativeSensitivity);
        }

        string plainScopeName = scopeName ?? WorkflowFormulaState.DefaultScopeName;
        TValue? value = await context.ReadStateAsync<TValue>(key, plainScopeName, cancellationToken).ConfigureAwait(false);
        SensitivityLevel sensitivity = ShouldPersistSensitivity(plainScopeName)
            ? await context.ReadStateAsync<SensitivityLevel>(key, WorkflowFormulaState.GetSensitivityScopeName(plainScopeName), cancellationToken).ConfigureAwait(false)
            : SensitivityLevel.None;
        return new(value, sensitivity);
    }

    /// <summary>
    /// Queues a state update using sensitivity metadata carried with the value.
    /// </summary>
    /// <typeparam name="TValue">The type of the state value.</typeparam>
    /// <param name="context">The workflow execution context used to queue state updates.</param>
    /// <param name="key">The key of the state value.</param>
    /// <param name="value">The value and sensitivity metadata to store.</param>
    /// <param name="scopeName">An optional name that specifies the scope to update. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>A task representing the queued state update.</returns>
    public static async ValueTask QueueStateUpdateWithSensitivityAsync<TValue>(
        this IWorkflowContext context,
        string key,
        EvaluationResult<TValue> value,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        if (context is DeclarativeWorkflowContext declarativeContext)
        {
            string effectiveScopeName = scopeName ?? WorkflowFormulaState.DefaultScopeName;
            await declarativeContext.QueueStateUpdateAsync(key, value.Value, effectiveScopeName, value.Sensitivity, cancellationToken).ConfigureAwait(false);
            return;
        }

        string plainScopeName = scopeName ?? WorkflowFormulaState.DefaultScopeName;
        await context.QueueStateUpdateAsync(key, value.Value, plainScopeName, cancellationToken).ConfigureAwait(false);
        if (ShouldPersistSensitivity(plainScopeName))
        {
            await context.QueueStateUpdateAsync(key, value.Sensitivity, WorkflowFormulaState.GetSensitivityScopeName(plainScopeName), cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Convert the result of an expression to the specified target type.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="targetType">Describes the target type for the value conversion.</param>
    /// <param name="expression">The expression to evaluate.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The converted expression value</returns>
    public static async ValueTask<object?> ConvertValueAsync(this IWorkflowContext context, VariableType targetType, string expression, CancellationToken cancellationToken = default)
    {
        object? sourceValue = await context.EvaluateValueAsync(expression, cancellationToken).ConfigureAwait(false);
        return sourceValue.ConvertType(targetType);
    }

    /// <summary>
    /// Convert the variable value to the specified target type.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="targetType">Describes the target type for the value conversion.</param>
    /// <param name="key">The key of the state value.</param>
    /// <param name="scopeName">An optional name that specifies the scope to read. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The converted value</returns>
    public static async ValueTask<object?> ConvertValueAsync(this IWorkflowContext context, VariableType targetType, string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        object? sourceValue = await context.ReadStateAsync<object>(key, scopeName, cancellationToken).ConfigureAwait(false);
        return sourceValue.ConvertType(targetType);
    }

    /// <summary>
    /// Convert the variable value to the specified target type while preserving sensitivity metadata.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="targetType">Describes the target type for the value conversion.</param>
    /// <param name="key">The key of the state value.</param>
    /// <param name="scopeName">An optional name that specifies the scope to read. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The converted value and its sensitivity metadata.</returns>
    public static async ValueTask<EvaluationResult<object?>> ConvertValueWithSensitivityAsync(
        this IWorkflowContext context,
        VariableType targetType,
        string key,
        string? scopeName = null,
        CancellationToken cancellationToken = default)
    {
        EvaluationResult<PortableValue?> sourceValue = await context.ReadStateWithSensitivityAsync<PortableValue>(key, scopeName, cancellationToken).ConfigureAwait(false);
        object? convertedValue = sourceValue.Value is null ? null : sourceValue.Value.ToFormula().ToObject().ConvertType(targetType);
        return new(convertedValue, sourceValue.Sensitivity);
    }

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <typeparam name="TElement">The type of the list element.</typeparam>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="key">The key of the state value.</param>
    /// <param name="scopeName">An optional name that specifies the scope to read. If null, the default scope is used.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated list expression</returns>
    public static async ValueTask<IList<TElement>?> ReadListAsync<TElement>(this IWorkflowContext context, string key, string? scopeName = null, CancellationToken cancellationToken = default)
    {
        object? value = await context.ReadStateAsync<object>(key, scopeName, cancellationToken).ConfigureAwait(false);
        return value.AsList<TElement>();
    }

    private static async Task<WorkflowFormulaState> GetStateAsync(this IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (context is DeclarativeWorkflowContext declarativeContext)
        {
            return declarativeContext.State;
        }

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());

        await state.RestoreAsync(context, cancellationToken).ConfigureAwait(false);

        return state;
    }

    private static void ThrowIfSensitive(SensitivityLevel sensitivity)
    {
        if (sensitivity == SensitivityLevel.Sensitive)
        {
            throw new DeclarativeActionException("Cannot return sensitive workflow expression value.");
        }
    }

    private static SensitivityLevel MaxSensitivity(SensitivityLevel left, SensitivityLevel right) =>
        left == SensitivityLevel.Sensitive || right == SensitivityLevel.Sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None;

    private static bool ShouldPersistSensitivity(string scopeName) =>
        DeclarativeWorkflowContext.ManagedScopes.Contains(scopeName) ||
        scopeName == VariableScopeNames.Environment ||
        scopeName == VariableScopeNames.System;
}
