// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;

namespace Microsoft.Shared.Diagnostics;

/// <summary>Validates application-owned HTTP handler pipelines.</summary>
internal static class HttpTransportValidation
{
    public static void Validate(HttpMessageHandler handler)
    {
        while (handler is DelegatingHandler delegatingHandler)
        {
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
}
