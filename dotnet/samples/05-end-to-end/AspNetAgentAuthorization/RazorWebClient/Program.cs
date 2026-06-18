// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates an OIDC-authenticated Razor Pages web client
// that calls a JWT-secured AI agent REST API.

using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorPages();

// Persist data protection keys so antiforgery tokens survive container rebuilds
builder.Services.AddDataProtection()
    .PersistKeysToFileSystem(new DirectoryInfo("/app/keys"));

// ---------------------------------------------------------------------------
// Authentication: Cookie + OpenID Connect (Keycloak)
// ---------------------------------------------------------------------------
string authority = builder.Configuration["Auth:Authority"]
    ?? throw new InvalidOperationException("Auth:Authority is not configured.");

// PublicKeycloakUrl is the browser-facing Keycloak base URL. When the
// web-client runs inside Docker, Authority points to the internal hostname
// (e.g. http://keycloak:8080) for backchannel discovery, while
// PublicKeycloakUrl is what the browser can reach (e.g. http://localhost:5002).
// When running outside Docker, Authority already IS the public URL and
// PublicKeycloakUrl is not needed.
string? publicKeycloakUrl = builder.Configuration["Auth:PublicKeycloakUrl"];

// In Codespaces, override the public URLs with the tunnel endpoints.
string? codespaceName = Environment.GetEnvironmentVariable("CODESPACE_NAME");
string? codespaceDomain = Environment.GetEnvironmentVariable("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN");
bool isCodespaces = !string.IsNullOrEmpty(codespaceName) && !string.IsNullOrEmpty(codespaceDomain);
if (isCodespaces)
{
    publicKeycloakUrl = $"https://{codespaceName}-5002.{codespaceDomain}";
}

// Derive the internal base URL from Authority for URL rewriting.
string internalKeycloakBase = new Uri(authority).GetLeftPart(UriPartial.Authority);

builder.Services
    .AddAuthentication(options =>
    {
        options.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
        options.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
    })
    .AddCookie()
    .AddOpenIdConnect(options =>
    {
        options.Authority = authority;
        options.ClientId = builder.Configuration["Auth:ClientId"]
            ?? throw new InvalidOperationException("Auth:ClientId is not configured.");

        options.ResponseType = OpenIdConnectResponseType.Code;
        options.SaveTokens = true;
        options.GetClaimsFromUserInfoEndpoint = true;

        // Request scopes so the access token includes them
        options.Scope.Clear();
        options.Scope.Add("openid");
        options.Scope.Add("profile");
        options.Scope.Add("email");
        options.Scope.Add("agent.chat");
        options.Scope.Add("expenses.view");
        options.Scope.Add("expenses.approve");

        // For local development with HTTP-only Keycloak
        options.RequireHttpsMetadata = !builder.Environment.IsDevelopment();

        // When the web-client is inside Docker, the backchannel Authority uses
        // an internal hostname that differs from the browser-facing URL.
        // Rewrite the authorization/logout endpoints so the browser is
        // redirected to the public Keycloak URL, and disable issuer validation
        // because the token issuer (public URL) won't match the discovery
        // document issuer (internal URL).
        if (publicKeycloakUrl is not null)
        {
#pragma warning disable CA5404 // Token issuer validation disabled: backchannel uses internal Docker hostname while tokens are issued via the public URL.
            options.TokenValidationParameters.ValidateIssuer = false;
#pragma warning restore CA5404

            // The UserInfo endpoint is on the internal URL but the token
            // issuer is the public URL — Keycloak rejects the mismatch.
            // The ID token already contains all needed claims.
            options.GetClaimsFromUserInfoEndpoint = false;

            // In Codespaces the tunnel delivers with Host: localhost, so the
            // auto-generated redirect_uri is wrong. Override it explicitly.
            string? publicWebClientBase = isCodespaces
                ? $"https://{codespaceName}-8080.{codespaceDomain}"
                : null;

            options.Events = new OpenIdConnectEvents
            {
                OnRedirectToIdentityProvider = context =>
                {
                    context.ProtocolMessage.IssuerAddress = context.ProtocolMessage.IssuerAddress
                        .Replace(internalKeycloakBase, publicKeycloakUrl);
                    if (publicWebClientBase is not null)
                    {
                        context.ProtocolMessage.RedirectUri = $"{publicWebClientBase}/signin-oidc";
                    }

                    return Task.CompletedTask;
                },
                OnRedirectToIdentityProviderForSignOut = context =>
                {
                    context.ProtocolMessage.IssuerAddress = context.ProtocolMessage.IssuerAddress
                        .Replace(internalKeycloakBase, publicKeycloakUrl);
                    if (publicWebClientBase is not null)
                    {
                        context.ProtocolMessage.PostLogoutRedirectUri = $"{publicWebClientBase}/signout-callback-oidc";
                    }

                    return Task.CompletedTask;
                },
            };
        }
    });

// ---------------------------------------------------------------------------
// HttpClient for calling the AgentService — attaches Bearer token
// ---------------------------------------------------------------------------
builder.Services.AddHttpClient("AgentService", client =>
{
    string baseUrl = builder.Configuration["AgentService:BaseUrl"] ?? "http://localhost:5001";
    client.BaseAddress = new Uri(baseUrl);
});

WebApplication app = builder.Build();

app.UseStaticFiles();
app.UseRouting();
app.UseAuthentication();
app.UseAuthorization();
app.MapRazorPages();

await app.RunAsync();
