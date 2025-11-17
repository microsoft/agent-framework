// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

internal sealed class FakeAuthenticationTokenProvider : AuthenticationTokenProvider
{
    public override GetTokenOptions? CreateTokenOptions(IReadOnlyDictionary<string, object> properties)
    {
        return new GetTokenOptions(new Dictionary<string, object>());
    }

    public override AuthenticationToken GetToken(GetTokenOptions options, CancellationToken cancellationToken)
    {
        return new AuthenticationToken("token-value", "token-type", DateTimeOffset.UtcNow.AddHours(1));
    }

    public override ValueTask<AuthenticationToken> GetTokenAsync(GetTokenOptions options, CancellationToken cancellationToken)
    {
        return new ValueTask<AuthenticationToken>(this.GetToken(options, cancellationToken));
    }
}
