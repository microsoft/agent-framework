// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

/// <summary>
/// This class represents the result of a call to a message handler.
/// </summary>
internal sealed class CallResult
{
    /// <summary>
    /// Indicates whether the call was to a void-return executor (i.e., no result expected).
    /// </summary>
    public bool IsVoid { get; init; }

    /// <summary>
    /// If the call was successful, this property contains the result of the call. For calls to
    /// void handlers, this will be <c>null</c>.
    /// </summary>
    public object? Result { get; init; }

    /// <summary>
    /// If the call failed, this property contains the exception that was raised during the call.
    /// </summary>
    public Exception? Exception { get; init; }

    /// <summary>
    /// Indicates whether the call was successful. A call is considered successful if it returned
    /// without throwing an exception.
    /// </summary>
    public bool IsSuccess => this.Exception is null;

    private CallResult(bool isVoid = false)
    {
        // Private constructor to enforce use of static methods.
        this.IsVoid = isVoid;
    }

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating a successful call that returned a result (non-void).
    /// </summary>
    /// <param name="result">The result to return.</param>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    public static CallResult ReturnResult(object? result = null) => new() { Result = result };

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating a successful call that returned no result (void).
    /// </summary>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    public static CallResult ReturnVoid() => new(isVoid: true);

    /// <summary>
    /// Create a <see cref="CallResult"/> indicating that an exception was raised during the call.
    /// </summary>
    /// <param name="wasVoid">A boolean specifying whether the call was void (was not expected to return
    /// a value).</param>
    /// <param name="exception">The exception that was raised during the call.</param>
    /// <returns>A <see cref="CallResult"/> indicating the result of the call.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="exception"/> is null.</exception>
    public static CallResult RaisedException(bool wasVoid, Exception exception)
    {
        Throw.IfNull(exception);

        return new(wasVoid) { Exception = exception };
    }
}
