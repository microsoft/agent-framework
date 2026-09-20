// Copyright (c) Microsoft. All rights reserved.

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
