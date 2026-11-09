// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;

namespace Microsoft.Shared.Diagnostics;

/// <summary>Validates application-owned HTTP handler pipelines.</summary>
internal static class HttpTransportValidation
{
    public static void Validate(HttpMessageHandler handler)
    {
        HashSet<HttpMessageHandler> visited = new(HttpMessageHandlerReferenceComparer.Instance);
        while (handler is DelegatingHandler delegatingHandler)
        {
            if (!visited.Add(handler))
            {
                throw new InvalidOperationException("The HTTP handler pipeline must not contain a cycle.");
            }

            handler = delegatingHandler.InnerHandler
                ?? throw new InvalidOperationException("The HTTP handler pipeline must have a primary handler.");
        }

        bool allowAutoRedirect;
        bool useCookies;
        if (handler is HttpClientHandler httpClientHandler)
        {
            allowAutoRedirect = httpClientHandler.AllowAutoRedirect;
            useCookies = httpClientHandler.UseCookies;
        }
#if NET
        else if (handler is SocketsHttpHandler socketsHttpHandler)
        {
            allowAutoRedirect = socketsHttpHandler.AllowAutoRedirect;
            useCookies = socketsHttpHandler.UseCookies;
        }
#endif
        else
        {
            throw new InvalidOperationException("The HTTP handler pipeline must use a supported primary HTTP handler.");
        }

        if (allowAutoRedirect || useCookies)
        {
            throw new InvalidOperationException("The primary HTTP handler must disable automatic redirects and cookies.");
        }
    }

    private sealed class HttpMessageHandlerReferenceComparer : IEqualityComparer<HttpMessageHandler>
    {
        public static HttpMessageHandlerReferenceComparer Instance { get; } = new();

        public bool Equals(HttpMessageHandler? x, HttpMessageHandler? y) => ReferenceEquals(x, y);

        public int GetHashCode(HttpMessageHandler obj) => RuntimeHelpers.GetHashCode(obj);
    }
}
