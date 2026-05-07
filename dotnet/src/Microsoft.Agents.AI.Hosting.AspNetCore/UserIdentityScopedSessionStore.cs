// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// A delegating <see cref="AgentSessionStore"/> that scopes session keys by a claim value
/// extracted from the current user's identity, ensuring that sessions are isolated per user.
/// The current user is extracted from the ambient ASP.NET <see cref="HttpContext"/>.
/// </summary>
/// <remarks>
/// This relies on <see cref="IHttpContextAccessor"/>, which uses <see cref="AsyncLocal{T}"/>
/// to provide access to the current <see cref="HttpContext"/>.
/// </remarks>
public class UserIdentityScopedSessionStore : DelegatingAgentSessionStore
{
    private readonly IHttpContextAccessor? _httpContextAccessor;
    private readonly string _claimType;
    private readonly bool _strict;

    /// <summary>
    /// Initializes a new instance of the <see cref="UserIdentityScopedSessionStore"/> class.
    /// </summary>
    /// <param name="innerStore">The underlying <see cref="AgentSessionStore"/> to delegate to.</param>
    /// <param name="contextAccessor">
    /// The <see cref="IHttpContextAccessor"/> used to retrieve the current user's claims.
    /// </param>
    /// <param name="claimType">
    /// The claim type to extract from the user's identity for scoping. Defaults to <see cref="ClaimsIdentity.DefaultNameClaimType"/>.
    /// </param>
    /// <param name="strict">
    /// If <see langword="true"/>, an exception is thrown when the specified claim is not found.
    /// If <see langword="false"/>, operations proceed without scoping when the claim is absent.
    /// </param>
    public UserIdentityScopedSessionStore(AgentSessionStore innerStore,
                                          IHttpContextAccessor? contextAccessor,
                                          string claimType = ClaimsIdentity.DefaultNameClaimType,
                                          bool strict = true) : base(innerStore)
    {
        this._httpContextAccessor = contextAccessor;
        this._claimType = claimType;
        this._strict = strict;
    }

    private string? GetScopeFromIdentity()
    {
        Claim? claim = this._httpContextAccessor?
                           .HttpContext?
                           .User?.Claims.FirstOrDefault(c => c.Type == this._claimType);

        if (this._strict && claim == null)
        {
            throw new InvalidOperationException($"No claim of type '{this._claimType}' found in principal.");
        }

        return claim?.Value;
    }

    private string? ScopeId => this.GetScopeFromIdentity();

    private string GetScopedConversationId(string bareConversationId) => $"{this.ScopeId}:{bareConversationId}";

    /// <inheritdoc />
    public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
        => this.InnerStore.GetSessionAsync(agent, this.GetScopedConversationId(conversationId), cancellationToken);

    /// <inheritdoc />
    public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
        => this.InnerStore.SaveSessionAsync(agent, this.GetScopedConversationId(conversationId), session, cancellationToken);
}
