// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// AsyncLocal carrier for the session's <c>x-ms-user-identity</c> value from
/// <see cref="FoundryHostedRequestAgent"/> to <see cref="UserIdentityPolicy"/>.
/// </summary>
internal static class UserIdentityScope
{
    private static readonly AsyncLocal<string?> s_current = new();

    /// <summary>Gets or sets the user identity value for the current asynchronous flow.</summary>
    public static string? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}
