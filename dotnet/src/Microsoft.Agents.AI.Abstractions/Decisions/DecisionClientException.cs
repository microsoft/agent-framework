// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Classifies why an <see cref="IDecisionClient"/> call failed, so a caller can tell a retryable condition from a
/// permanent one.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum DecisionFailureKind
{
    /// <summary>The failure could not be classified, or happened locally before a response (for example a network error).</summary>
    Unknown = 0,

    /// <summary>The credentials were missing or rejected. Not transient.</summary>
    Authentication = 1,

    /// <summary>The request failed the provider's validation. Not transient: the same request will fail again.</summary>
    InvalidRequest = 2,

    /// <summary>The provider rate-limited the caller. Transient; back off before retrying.</summary>
    RateLimited = 3,

    /// <summary>The provider is temporarily overloaded. Transient.</summary>
    Overloaded = 4,

    /// <summary>The provider failed on its side or was unreachable. Transient.</summary>
    ProviderUnavailable = 5,

    /// <summary>
    /// The provider answered successfully but the body was unusable: a missing answer, an answer of the wrong kind, a
    /// probability outside 0 to 1, or unparseable content. Not transient, and never converted into an answer.
    /// </summary>
    InvalidResponse = 6,
}

/// <summary>
/// The exception thrown by an <see cref="IDecisionClient"/> when a call did not yield usable answers.
/// </summary>
/// <remarks>
/// An operational failure is not a semantic answer. Implementations throw this exception instead of returning a
/// fabricated probability, and never include credentials in <see cref="Exception.Message"/>. <see cref="IsTransient"/>
/// tells the caller whether a retry with the same request could reasonably succeed; any retry should remain observable
/// (for example in latency and cost accounting) rather than hidden inside the client.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class DecisionClientException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class.</summary>
    public DecisionClientException()
        : this(DecisionFailureKind.Unknown, "The decision client call failed.")
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class.</summary>
    /// <param name="message">The message that describes the error.</param>
    public DecisionClientException(string message)
        : this(DecisionFailureKind.Unknown, message)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class.</summary>
    /// <param name="message">The message that describes the error.</param>
    /// <param name="innerException">The exception that is the cause of the current exception.</param>
    public DecisionClientException(string message, Exception? innerException)
        : this(DecisionFailureKind.Unknown, message, statusCode: null, innerException)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class.</summary>
    /// <param name="kind">The failure classification.</param>
    /// <param name="message">The message that describes the error. It must not contain credentials.</param>
    /// <param name="statusCode">The HTTP status the provider returned, when one was.</param>
    /// <param name="innerException">The exception that is the cause of the current exception, if any.</param>
    public DecisionClientException(DecisionFailureKind kind, string message, int? statusCode = null, Exception? innerException = null)
        : base(message, innerException)
    {
        this.Kind = kind;
        this.StatusCode = statusCode;
    }

    /// <summary>Gets the failure classification.</summary>
    public DecisionFailureKind Kind { get; }

    /// <summary>Gets the HTTP status the provider returned, or <see langword="null"/> when the failure happened before a response.</summary>
    public int? StatusCode { get; }

    /// <summary>
    /// Gets a value indicating whether a retry with the same request could reasonably succeed: <see langword="true"/> for
    /// rate limiting, overload, and provider-side failures; <see langword="false"/> for authentication, request
    /// validation, and unusable responses.
    /// </summary>
    public bool IsTransient =>
        this.Kind is DecisionFailureKind.RateLimited or DecisionFailureKind.Overloaded or DecisionFailureKind.ProviderUnavailable;
}
