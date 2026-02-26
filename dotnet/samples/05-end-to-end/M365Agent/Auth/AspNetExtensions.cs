// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Globalization;
using System.IdentityModel.Tokens.Jwt;
using System.Text;
using Microsoft.Agents.Authentication;
using Microsoft.Agents.Core;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;
using Microsoft.IdentityModel.Validators;

namespace M365Agent;

internal static class AspNetExtensions
{
    private static readonly CompositeFormat s_cachedValidTokenIssuerUrlTemplateV1Format = CompositeFormat.Parse(AuthenticationConstants.ValidTokenIssuerUrlTemplateV1);
    private static readonly CompositeFormat s_cachedValidTokenIssuerUrlTemplateV2Format = CompositeFormat.Parse(AuthenticationConstants.ValidTokenIssuerUrlTemplateV2);

    private static readonly ConcurrentDictionary<string, ConfigurationManager<OpenIdConnectConfiguration>> s_openIdMetadataCache = new();

    /// <summary>
    /// Adds AspNet token validation typical for ABS/SMBA and agent-to-agent using settings in configuration.
    /// </summary>
    /// <param name="services">The service collection to resolve dependencies.</param>
    /// <param name="configuration">Used to read configuration settings.</param>
    /// <param name="tokenValidationSectionName">Name of the config section to read.</param>
    /// <remarks>
    /// <para>This extension reads <see cref="TokenValidationOptions"/> settings from configuration.  If configuration is missing JWT token
    /// is not enabled.</para>
    /// <p>The minimum, but typical, configuration is:</p>
    /// <code>
    /// "TokenValidation": {
    ///    "Enabled": boolean,
    ///    "Audiences": [
    ///      "{{ClientId}}" // this is the Client ID used for the Azure Bot
    ///    ],
    ///    "TenantId": "{{TenantId}}"
    /// }
    /// </code>
    /// <para>The full options are:</para>
    /// <code>
    /// "TokenValidation": {
    ///   "Enabled": boolean,
    ///   "Audiences": [
    ///     "{required:agent-appid}"
    ///   ],
    ///   "TenantId": "{recommended:tenant-id}",
    ///   "ValidIssuers": [
    ///     "{default:Public-AzureBotService}"
    ///   ],
    ///   "IsGov": {optional:false},
    ///   "AzureBotServiceOpenIdMetadataUrl": optional,
    ///   "OpenIdMetadataUrl": optional,
    ///   "AzureBotServiceTokenHandling": "{optional:true}"
    ///   "OpenIdMetadataRefresh": "optional-12:00:00"
    /// }
    /// </code>
    /// </remarks>
    public static void AddAgentAspNetAuthentication(this IServiceCollection services, IConfiguration configuration, string tokenValidationSectionName = "TokenValidation")
    {
        IConfigurationSection tokenValidationSection = configuration.GetSection(tokenValidationSectionName);

        if (!tokenValidationSection.Exists() || !tokenValidationSection.GetValue("Enabled", true))
        {
            // Noop if TokenValidation section missing or disabled.
            System.Diagnostics.Trace.WriteLine("AddAgentAspNetAuthentication: Auth disabled");
            return;
        }

        services.AddAgentAspNetAuthentication(tokenValidationSection.Get<TokenValidationOptions>()!);
    }

    /// <summary>
    /// Adds AspNet token validation typical for ABS/SMBA and agent-to-agent.
    /// </summary>
    public static void AddAgentAspNetAuthentication(this IServiceCollection services, TokenValidationOptions validationOptions)
    {
        AssertionHelpers.ThrowIfNull(validationOptions, nameof(validationOptions));

        // Must have at least one Audience.
        if (validationOptions.Audiences == null || validationOptions.Audiences.Count == 0)
        {
            throw new ArgumentException($"{nameof(TokenValidationOptions)}:Audiences requires at least one ClientId");
        }

        // Audience values must be GUID's
        foreach (var audience in validationOptions.Audiences)
        {
            if (!Guid.TryParse(audience, out _))
            {
                throw new ArgumentException($"{nameof(TokenValidationOptions)}:Audiences values must be a GUID");
            }
        }

        // If ValidIssuers is empty, default for ABS Public Cloud
        if (validationOptions.ValidIssuers == null || validationOptions.ValidIssuers.Count == 0)
        {
            validationOptions.ValidIssuers =
            [
                "https://api.botframework.com",
                "https://sts.windows.net/d6d49420-f39b-4df7-a1dc-d59a935871db/",
                "https://login.microsoftonline.com/d6d49420-f39b-4df7-a1dc-d59a935871db/v2.0",
                "https://sts.windows.net/f8cdef31-a31e-4b4a-93e4-5f571e91255a/",
                "https://login.microsoftonline.com/f8cdef31-a31e-4b4a-93e4-5f571e91255a/v2.0",
                "https://sts.windows.net/69e9b82d-4842-4902-8d1e-abc5b98a55e8/",
                "https://login.microsoftonline.com/69e9b82d-4842-4902-8d1e-abc5b98a55e8/v2.0",
            ];

            if (!string.IsNullOrEmpty(validationOptions.TenantId) && Guid.TryParse(validationOptions.TenantId, out _))
            {
                validationOptions.ValidIssuers.Add(string.Format(CultureInfo.InvariantCulture, s_cachedValidTokenIssuerUrlTemplateV1Format, validationOptions.TenantId));
                validationOptions.ValidIssuers.Add(string.Format(CultureInfo.InvariantCulture, s_cachedValidTokenIssuerUrlTemplateV2Format, validationOptions.TenantId));
            }
        }

        // If the `AzureBotServiceOpenIdMetadataUrl` setting is not specified, use the default based on `IsGov`.  This is what is used to authenticate ABS tokens.
        if (string.IsNullOrEmpty(validationOptions.AzureBotServiceOpenIdMetadataUrl))
        {
            validationOptions.AzureBotServiceOpenIdMetadataUrl = validationOptions.IsGov ? AuthenticationConstants.GovAzureBotServiceOpenIdMetadataUrl : AuthenticationConstants.PublicAzureBotServiceOpenIdMetadataUrl;
        }

        // If the `OpenIdMetadataUrl` setting is not specified, use the default based on `IsGov`.  This is what is used to authenticate Entra ID tokens.
        if (string.IsNullOrEmpty(validationOptions.OpenIdMetadataUrl))
        {
            validationOptions.OpenIdMetadataUrl = validationOptions.IsGov ? AuthenticationConstants.GovOpenIdMetadataUrl : AuthenticationConstants.PublicOpenIdMetadataUrl;
        }

        var openIdMetadataRefresh = validationOptions.OpenIdMetadataRefresh ?? BaseConfigurationManager.DefaultAutomaticRefreshInterval;

        _ = services.AddAuthentication(options =>
        {
            options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
            options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
        })
        .AddJwtBearer(options =>
        {
            options.SaveToken = true;
            options.TokenValidationParameters = new TokenValidationParameters
            {
                ValidateIssuer = true,
                ValidateAudience = true,
                ValidateLifetime = true,
                ClockSkew = TimeSpan.FromMinutes(5),
                ValidIssuers = validationOptions.ValidIssuers,
                ValidAudiences = validationOptions.Audiences,
                ValidateIssuerSigningKey = true,
                RequireSignedTokens = true,
            };

            // Using Microsoft.IdentityModel.Validators
            options.TokenValidationParameters.EnableAadSigningKeyIssuerValidation();

            options.Events = new JwtBearerEvents
            {
                // Create a ConfigurationManager based on the requestor.  This is to handle ABS non-Entra tokens.
                OnMessageReceived = async context =>
                {
                    string authorizationHeader = context.Request.Headers.Authorization.ToString();

                    if (string.IsNullOrWhiteSpace(authorizationHeader))
                    {
                        // Default to AadTokenValidation handling
                        context.Options.TokenValidationParameters.ConfigurationManager ??= options.ConfigurationManager as BaseConfigurationManager;
                        await Task.CompletedTask.ConfigureAwait(false);
                        return;
                    }

                    string[] parts = authorizationHeader.Split(' ')!;
                    if (parts.Length != 2 || parts[0] != "Bearer")
                    {
                        // Default to AadTokenValidation handling
                        context.Options.TokenValidationParameters.ConfigurationManager ??= options.ConfigurationManager as BaseConfigurationManager;
                        await Task.CompletedTask.ConfigureAwait(false);
                        return;
                    }

                    JwtSecurityToken token = new(parts[1]);
                    string issuer = token.Claims.FirstOrDefault(claim => claim.Type == AuthenticationConstants.IssuerClaim)?.Value!;

                    string openIdMetadataUrl = (validationOptions.AzureBotServiceTokenHandling && AuthenticationConstants.BotFrameworkTokenIssuer.Equals(issuer, StringComparison.Ordinal))
                        ? validationOptions.AzureBotServiceOpenIdMetadataUrl
                        : validationOptions.OpenIdMetadataUrl;

                    context.Options.TokenValidationParameters.ConfigurationManager = s_openIdMetadataCache.GetOrAdd(openIdMetadataUrl, key =>
                    {
                        return new ConfigurationManager<OpenIdConnectConfiguration>(openIdMetadataUrl, new OpenIdConnectConfigurationRetriever(), new HttpClient())
                        {
                            AutomaticRefreshInterval = openIdMetadataRefresh
                        };
                    });

                    await Task.CompletedTask.ConfigureAwait(false);
                },

                OnTokenValidated = context => Task.CompletedTask,
                OnForbidden = context => Task.CompletedTask,
                OnAuthenticationFailed = context => Task.CompletedTask
            };
        });
    }
}
