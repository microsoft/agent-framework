# Origin Pinning

HTTP message handler utilities that keep credentials on a pinned origin.

Provides `OriginPinningHandler`, an internal `DelegatingHandler` that removes configured headers from
any outbound request whose origin (scheme, host, and port) differs from a pinned endpoint. By default
it removes `Authorization`, `Proxy-Authorization`, and `Cookie`. Both the pinned endpoint and the
header names are configurable, so the handler works with any `HttpClient` stack.

Place the handler inside every handler that adds credentials, so headers added by those outer handlers
are removed before the request leaves the pinned origin:

```csharp
var handler = new CredentialHandler
{
    InnerHandler = new OriginPinningHandler(endpoint)
    {
        InnerHandler = new HttpClientHandler(),
    },
};
```

`OriginPinningHandler.IsSameOrigin` exposes the same origin comparison for handlers that must decide
whether to attach credentials at all.

To use this in your project, add the following to your `.csproj` file:

```xml
<PropertyGroup>
  <InjectSharedOriginPinning>true</InjectSharedOriginPinning>
</PropertyGroup>
```

This also depends on the shared Throw class, so InjectSharedThrow must also be enabled:

```xml
<PropertyGroup>
  <InjectSharedThrow>true</InjectSharedThrow>
</PropertyGroup>
```