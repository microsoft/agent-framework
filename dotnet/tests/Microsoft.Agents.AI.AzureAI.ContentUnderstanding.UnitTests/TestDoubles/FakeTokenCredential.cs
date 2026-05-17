// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Non-network test double for <see cref="TokenCredential"/>. The constructor-validation tests
/// only need a non-null reference, never an actual token request.
/// </summary>
internal sealed class FakeTokenCredential : TokenCredential
{
    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => throw new NotSupportedException("FakeTokenCredential is for argument-validation tests only.");

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => throw new NotSupportedException("FakeTokenCredential is for argument-validation tests only.");
}
