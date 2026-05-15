// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Test fake that returns a non-null <see cref="HostedSessionContext"/> by default, allowing tests
/// that were written before the strict isolation-key contract to keep passing without each test
/// having to stub <c>ResponseContext.Isolation</c>. The constructor also accepts <see langword="null"/>
/// values so individual tests can exercise the handler's null-key error path.
/// </summary>
internal sealed class FakeHostedSessionIsolationKeyProvider : HostedSessionIsolationKeyProvider
{
    public const string DefaultUserId = "test-user-isolation";
    public const string DefaultChatId = "test-chat-isolation";

    private readonly HostedSessionContext? _context;

    public FakeHostedSessionIsolationKeyProvider(string? userId = DefaultUserId, string? chatId = DefaultChatId)
    {
        this._context = userId is null || chatId is null
            ? null
            : new HostedSessionContext(userId, chatId);
    }

    public override ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken)
        => new(this._context);
}
