// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This class has been temporarily copied here from MEAI, to allow prototyping
// functionality that will be moved to MEAI in the future.
// This file is not intended to be modified.

// AF repo suppressions for code copied from MEAI.
#pragma warning disable IDE0009 // Member access should be qualified.
#pragma warning disable CA1859 // Use concrete types when possible for improved performance
#pragma warning disable CA1063 // Implement IDisposable Correctly

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

public sealed class TestChatClient : IChatClient
{
    public TestChatClient()
    {
        GetServiceCallback = DefaultGetServiceCallback;
    }

    public IServiceProvider? Services { get; set; }

    public Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>>? GetResponseAsyncCallback { get; set; }

    public Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, IAsyncEnumerable<ChatResponseUpdate>>? GetStreamingResponseAsyncCallback { get; set; }

    public Func<Type, object?, object?> GetServiceCallback { get; set; }

    private object? DefaultGetServiceCallback(Type serviceType, object? serviceKey) =>
        serviceType is not null && serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        => GetResponseAsyncCallback!.Invoke(messages, options, cancellationToken);

    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        => GetStreamingResponseAsyncCallback!.Invoke(messages, options, cancellationToken);

    public object? GetService(Type serviceType, object? serviceKey = null)
        => GetServiceCallback(serviceType, serviceKey);

    void IDisposable.Dispose()
    {
        // No resources need disposing.
    }
}
