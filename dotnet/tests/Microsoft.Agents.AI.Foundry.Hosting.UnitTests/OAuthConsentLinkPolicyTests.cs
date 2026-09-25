// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class OAuthConsentLinkPolicyTests
{
    [Fact]
    public void IsAllowed_NullAllowlist_AcceptsAnySafeHttpsOrigin()
    {
        // Arrange
        var policy = new OAuthConsentLinkPolicy(null);

        // Act
        var allowed = policy.IsAllowed("https://external.example/authorize?state=1");

        // Assert
        Assert.True(allowed);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("http://external.example/authorize")]
    [InlineData("javascript:alert(1)")]
    [InlineData("https://user@external.example/authorize")]
    [InlineData("https://exter nal.example/authorize")]
    [InlineData("https://external.example/authorize\n")]
    [InlineData("https:\\\\external.example/authorize")]
    [InlineData("/relative/authorize")]
    public void IsAllowed_NullAllowlist_RejectsUnsafeLinks(string? consentUrl)
    {
        // Arrange: an omitted allowlist skips only the origin check, never URL safety.
        var policy = new OAuthConsentLinkPolicy(null);

        // Act
        var allowed = policy.IsAllowed(consentUrl);

        // Assert
        Assert.False(allowed);
    }

    [Fact]
    public void IsAllowed_EmptyAllowlist_RejectsEveryLink()
    {
        // Arrange
        var policy = new OAuthConsentLinkPolicy([]);

        // Act
        var allowed = policy.IsAllowed("https://external.example/authorize");

        // Assert
        Assert.False(allowed);
    }

    [Theory]
    [InlineData("https://auth.example.com/authorize?state=1", true)]
    [InlineData("https://AUTH.example.com/authorize", true)]
    [InlineData("https://auth.example.com:443/authorize", true)]
    [InlineData("https://login.partner.example:8443/consent", true)]
    [InlineData("https://login.partner.example/consent", false)]
    [InlineData("https://other.example.com/authorize", false)]
    [InlineData("https://auth.example.com.other.example/authorize", false)]
    public void IsAllowed_ConfiguredAllowlist_MatchesExactOrigins(string consentUrl, bool expected)
    {
        // Arrange
        var policy = new OAuthConsentLinkPolicy(
        [
            "https://auth.example.com",
            "https://login.partner.example:8443/",
        ]);

        // Act
        var allowed = policy.IsAllowed(consentUrl);

        // Assert
        Assert.Equal(expected, allowed);
    }

    [Theory]
    [InlineData("http://auth.example.com")]
    [InlineData("https://auth.example.com/path")]
    [InlineData("https://auth.example.com?tenant=1")]
    [InlineData("https://auth.example.com#fragment")]
    [InlineData("auth.example.com")]
    public void Constructor_InvalidConfiguredOrigin_Throws(string origin)
    {
        // Act
        void CreatePolicy() => _ = new OAuthConsentLinkPolicy([origin]);

        // Assert
        Assert.Throws<ArgumentException>(CreatePolicy);
    }
}
