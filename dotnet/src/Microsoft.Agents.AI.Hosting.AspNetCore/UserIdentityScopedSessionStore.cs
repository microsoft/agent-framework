// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.Shared.Diagnostics;

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
    /// <param name="options">The options for configuring the session store. If null, defaults are used.</param>
    public UserIdentityScopedSessionStore(
        AgentSessionStore innerStore,
        IHttpContextAccessor? contextAccessor,
        UserIdentityScopedSessionStoreOptions? options = null) : base(innerStore)
    {
        options ??= new UserIdentityScopedSessionStoreOptions();

        this._httpContextAccessor = contextAccessor;
        this._claimType = Throw.IfNullOrWhitespace(options.ClaimType);
        this._strict = options.Strict;
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

    private static string EscapeScopeId(string scopeId) => scopeId.Replace("\\", "\\\\").Replace(":", "\\:");

    private string GetScopedConversationId(string bareConversationId)
    {
        string? scopeId = this.ScopeId;
        if (scopeId == null)
        {
            return bareConversationId;
        }

        return $"{EscapeScopeId(scopeId)}::{bareConversationId}";
    }

    /// <inheritdoc />
    public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
        => this.InnerStore.GetSessionAsync(agent, this.GetScopedConversationId(conversationId), cancellationToken);

    /// <inheritdoc />
    public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
        => this.InnerStore.SaveSessionAsync(agent, this.GetScopedConversationId(conversationId), session, cancellationToken);
}
