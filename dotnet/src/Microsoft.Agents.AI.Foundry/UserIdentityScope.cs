// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// AsyncLocal carrier for the per-call <c>x-ms-user-identity</c> value from
/// <see cref="FoundryHostedRequestAgent"/> to <see cref="UserIdentityPolicy"/>.
/// </summary>
internal static class UserIdentityScope
{
    private static readonly AsyncLocal<string?> s_current = new();

    /// <summary>Gets or sets the per-async-flow user identity value.</summary>
    public static string? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}
