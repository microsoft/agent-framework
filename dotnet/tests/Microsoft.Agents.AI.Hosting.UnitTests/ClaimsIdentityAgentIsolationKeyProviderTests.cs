// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Claims;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="ClaimsIdentityAgentIsolationKeyProvider"/>.
/// </summary>
public class ClaimsIdentityAgentIsolationKeyProviderTests
{
    private const string TestUserId = "test-user-id";
    private const string CustomClaimType = "custom-claim-type";
    private const string CustomClaimValue = "custom-claim-value";
    private const string TestAuthenticationType = "TestAuth";

    private readonly Mock<IHttpContextAccessor> _httpContextAccessorMock;

    /// <summary>
    /// Initializes a new instance of the <see cref="ClaimsIdentityAgentIsolationKeyProviderTests"/> class.
    /// </summary>
    public ClaimsIdentityAgentIsolationKeyProviderTests()
    {
        this._httpContextAccessorMock = new Mock<IHttpContextAccessor>();
    }

    #region Constructor Tests

    /// <summary>
    /// Verify that constructor uses default options when options is null.
    /// </summary>
    [Fact]
    public void UsesDefaultOptionsWhenNull()
    {
        // Act & Assert - should not throw
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object, options: null);
        Assert.NotNull(provider);
    }

    /// <summary>
    /// Verify that constructor accepts null IHttpContextAccessor.
    /// </summary>
    [Fact]
    public void Constructor_WithNullHttpContextAccessor_DoesNotThrow()
    {
        // Act & Assert - should not throw
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(httpContextAccessor: null);
        Assert.NotNull(provider);
    }

    /// <summary>
    /// Verify that constructor throws ArgumentException when claimType is null.
    /// </summary>
    [Fact]
    public void RequiresClaimType_NotNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("options.ClaimType", () =>
            new ClaimsIdentityAgentIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentityAgentIsolationKeyProviderOptions { ClaimType = null! }));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentException when claimType is empty.
    /// </summary>
    [Fact]
    public void RequiresClaimType_NotEmpty()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>("options.ClaimType", () =>
            new ClaimsIdentityAgentIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentityAgentIsolationKeyProviderOptions { ClaimType = string.Empty }));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentException when claimType is whitespace.
    /// </summary>
    [Fact]
    public void RequiresClaimType_NotWhitespace()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>("options.ClaimType", () =>
            new ClaimsIdentityAgentIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentityAgentIsolationKeyProviderOptions { ClaimType = "   " }));
    }

    #endregion

    #region GetIsolationKeyAsync Tests

    /// <summary>
    /// Verify that GetIsolationKeyAsync extracts the claim value from the default claim type.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncExtractsDefaultClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimTypes.NameIdentifier, TestUserId);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal(TestUserId, result);
    }

    /// <summary>
    /// Verify that the default claim type is the stable, unique NameIdentifier claim rather than the
    /// non-unique display name claim. This guards against the resource-isolation collision described in
    /// the security report where two principals sharing the same name claim received the same key.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncIgnoresNameClaimByDefaultAsync()
    {
        // Arrange - only a display-name claim is present; the default provider must not use it.
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetIsolationKeyAsync uses custom claim type when specified.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncUsesCustomClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(CustomClaimType, CustomClaimValue);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(
            this._httpContextAccessorMock.Object,
            new ClaimsIdentityAgentIsolationKeyProviderOptions { ClaimType = CustomClaimType });

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal(CustomClaimValue, result);
    }

    /// <summary>
    /// Verify that GetIsolationKeyAsync returns null when the specified claim is missing.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNullWhenClaimMissingAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify behavior when HttpContextAccessor returns null HttpContext.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNullWhenHttpContextNullAsync()
    {
        // Arrange
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns((HttpContext?)null);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify behavior when HttpContextAccessor itself is null.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNullWhenHttpContextAccessorNullAsync()
    {
        // Arrange
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(httpContextAccessor: null);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetIsolationKeyAsync returns the first matching claim when multiple exist.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsFirstMatchingClaimAsync()
    {
        // Arrange
        const string FirstValue = "first-value";
        const string SecondValue = "second-value";
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, FirstValue),
            new Claim(ClaimTypes.NameIdentifier, SecondValue),
        };
        var identity = new ClaimsIdentity(claims, TestAuthenticationType);
        var principal = new ClaimsPrincipal(identity);

        var httpContext = new DefaultHttpContext
        {
            User = principal
        };

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal(FirstValue, result);
    }

    /// <summary>
    /// Verify that GetIsolationKeyAsync handles empty claim values.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncHandlesEmptyClaimValueAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimTypes.NameIdentifier, string.Empty);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    /// <summary>
    /// Regression test for the resource-isolation collision security report: two distinct authenticated
    /// principals that share the same display-name claim but have different stable identifiers and tenants
    /// must produce distinct isolation keys under the default options.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncDistinctForPrincipalsSharingNameClaimAsync()
    {
        // Arrange - both principals share the same name claim but differ by NameIdentifier and tenant.
        const string CommonName = "John Doe";

        var principalA = CreatePrincipal(
            new Claim(ClaimsIdentity.DefaultNameClaimType, CommonName),
            new Claim(ClaimTypes.NameIdentifier, "oid-user-a"),
            new Claim("http://schemas.microsoft.com/identity/claims/tenantid", "tenant-a"));

        var principalB = CreatePrincipal(
            new Claim(ClaimsIdentity.DefaultNameClaimType, CommonName),
            new Claim(ClaimTypes.NameIdentifier, "oid-user-b"),
            new Claim("http://schemas.microsoft.com/identity/claims/tenantid", "tenant-b"));

        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(new DefaultHttpContext { User = principalA });
        string? principalAKey = await provider.GetIsolationKeyAsync();

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(new DefaultHttpContext { User = principalB });
        string? principalBKey = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.Equal("oid-user-a", principalAKey);
        Assert.Equal("oid-user-b", principalBKey);
        Assert.NotEqual(principalAKey, principalBKey);
    }

    /// <summary>
    /// Verify that GetIsolationKeyAsync returns null when the request's user is not authenticated,
    /// even if a claim of the configured type is present. The provider must not derive an isolation key
    /// from claims on an unauthenticated identity.
    /// </summary>
    [Fact]
    public async Task GetIsolationKeyAsyncReturnsNullWhenUserNotAuthenticatedAsync()
    {
        // Arrange - identity has the claim but no authentication type, so IsAuthenticated is false.
        var claims = new[] { new Claim(ClaimTypes.NameIdentifier, TestUserId) };
        var unauthenticatedIdentity = new ClaimsIdentity(claims);
        var principal = new ClaimsPrincipal(unauthenticatedIdentity);
        var httpContext = new DefaultHttpContext { User = principal };
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
        var provider = new ClaimsIdentityAgentIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetIsolationKeyAsync();

        // Assert
        Assert.False(unauthenticatedIdentity.IsAuthenticated);
        Assert.Null(result);
    }

    #endregion

    #region Helper Methods

    private void SetupHttpContextWithClaim(string claimType, string claimValue)
    {
        var claims = new[] { new Claim(claimType, claimValue) };
        var identity = new ClaimsIdentity(claims, TestAuthenticationType);
        var principal = new ClaimsPrincipal(identity);

        var httpContext = new DefaultHttpContext
        {
            User = principal
        };

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
    }

    private static ClaimsPrincipal CreatePrincipal(params Claim[] claims)
        => new(new ClaimsIdentity(claims, TestAuthenticationType));

    #endregion
}
