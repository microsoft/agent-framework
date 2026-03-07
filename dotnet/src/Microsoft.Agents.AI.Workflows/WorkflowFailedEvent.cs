// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow fails with an error message.
/// </summary>
/// <remarks>
/// Unlike <see cref="WorkflowErrorEvent"/>, which requires an <see cref="System.Exception"/> object,
/// this event supports failure scenarios where only an error message string is available
/// (e.g., errors from external orchestrators or deserialized error responses).
/// </remarks>
/// <param name="errorMessage">The error message describing the failure.</param>
public sealed class WorkflowFailedEvent(string errorMessage) : WorkflowEvent(errorMessage)
{
    /// <summary>
    /// Gets the error message describing the failure.
    /// </summary>
    public string ErrorMessage => errorMessage;
}
