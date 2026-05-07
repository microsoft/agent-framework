// Copyright (c) Microsoft. All rights reserved.

using System.Security.Claims;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Options for configuring <see cref="UserIdentityScopedSessionStore"/>.
/// </summary>
public class UserIdentityScopedSessionStoreOptions
{
    /// <summary>
    /// Gets or sets the claim type to extract from the user's identity for scoping.
    /// </summary>
    /// <remarks>
    /// Defaults to <see cref="ClaimsIdentity.DefaultNameClaimType"/>.
    /// </remarks>
    public string ClaimType { get; set; } = ClaimsIdentity.DefaultNameClaimType;

    /// <summary>
    /// Gets or sets a value indicating whether an exception should be thrown when the specified claim is not found.
    /// </summary>
    /// <remarks>
    /// If <see langword="true"/>, an exception is thrown when the specified claim is not found.
    /// If <see langword="false"/>, the conversation ID is passed through unmodified when the claim is absent.
    /// Defaults to <see langword="true"/>.
    /// </remarks>
    public bool Strict { get; set; } = true;
}
