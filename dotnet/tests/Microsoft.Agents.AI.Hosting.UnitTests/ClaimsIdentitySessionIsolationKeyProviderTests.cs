// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Claims;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="ClaimsIdentitySessionIsolationKeyProvider"/>.
/// </summary>
public class ClaimsIdentitySessionIsolationKeyProviderTests
{
    private const string TestUserId = "test-user-id";
    private const string CustomClaimType = "custom-claim-type";
    private const string CustomClaimValue = "custom-claim-value";
    private const string TestAuthenticationType = "TestAuth";

    private readonly Mock<IHttpContextAccessor> _httpContextAccessorMock;

    /// <summary>
    /// Initializes a new instance of the <see cref="ClaimsIdentitySessionIsolationKeyProviderTests"/> class.
    /// </summary>
    public ClaimsIdentitySessionIsolationKeyProviderTests()
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
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object, options: null);
        Assert.NotNull(provider);
    }

    /// <summary>
    /// Verify that constructor accepts null IHttpContextAccessor.
    /// </summary>
    [Fact]
    public void Constructor_WithNullHttpContextAccessor_DoesNotThrow()
    {
        // Act & Assert - should not throw
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(httpContextAccessor: null);
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
            new ClaimsIdentitySessionIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentitySessionIsolationKeyProviderOptions { ClaimType = null! }));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentException when claimType is empty.
    /// </summary>
    [Fact]
    public void RequiresClaimType_NotEmpty()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>("options.ClaimType", () =>
            new ClaimsIdentitySessionIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentitySessionIsolationKeyProviderOptions { ClaimType = string.Empty }));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentException when claimType is whitespace.
    /// </summary>
    [Fact]
    public void RequiresClaimType_NotWhitespace()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>("options.ClaimType", () =>
            new ClaimsIdentitySessionIsolationKeyProvider(
                this._httpContextAccessorMock.Object,
                new ClaimsIdentitySessionIsolationKeyProviderOptions { ClaimType = "   " }));
    }

    #endregion

    #region GetSessionIsolationKeyAsync Tests

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync extracts the claim value from the default claim type.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncExtractsDefaultClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimTypes.NameIdentifier, TestUserId);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(TestUserId, result);
    }

    /// <summary>
    /// Verify that the default claim type is the stable, unique NameIdentifier claim rather than the
    /// non-unique display name claim. This guards against the session-isolation collision described in
    /// the security report where two principals sharing the same name claim received the same key.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncIgnoresNameClaimByDefaultAsync()
    {
        // Arrange - only a display-name claim is present; the default provider must not use it.
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync uses custom claim type when specified.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncUsesCustomClaimTypeAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(CustomClaimType, CustomClaimValue);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(
            this._httpContextAccessorMock.Object,
            new ClaimsIdentitySessionIsolationKeyProviderOptions { ClaimType = CustomClaimType });

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(CustomClaimValue, result);
    }

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync returns null when the specified claim is missing.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNullWhenClaimMissingAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim("other-claim", "value");
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify behavior when HttpContextAccessor returns null HttpContext.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNullWhenHttpContextNullAsync()
    {
        // Arrange
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns((HttpContext?)null);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify behavior when HttpContextAccessor itself is null.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNullWhenHttpContextAccessorNullAsync()
    {
        // Arrange
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(httpContextAccessor: null);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync returns the first matching claim when multiple exist.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsFirstMatchingClaimAsync()
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
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(FirstValue, result);
    }

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync handles empty claim values.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncHandlesEmptyClaimValueAsync()
    {
        // Arrange
        this.SetupHttpContextWithClaim(ClaimTypes.NameIdentifier, string.Empty);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    /// <summary>
    /// Regression test for the session-isolation collision security report: two distinct authenticated
    /// principals that share the same display-name claim but have different stable identifiers and tenants
    /// must produce distinct isolation keys under the default options.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncDistinctForPrincipalsSharingNameClaimAsync()
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

        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(new DefaultHttpContext { User = principalA });
        string? principalAKey = await provider.GetSessionIsolationKeyAsync();

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(new DefaultHttpContext { User = principalB });
        string? principalBKey = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal("oid-user-a", principalAKey);
        Assert.Equal("oid-user-b", principalBKey);
        Assert.NotEqual(principalAKey, principalBKey);
    }

    /// <summary>
    /// Verify that GetSessionIsolationKeyAsync returns null when the request's user is not authenticated,
    /// even if a claim of the configured type is present. The provider must not derive an isolation key
    /// from claims on an unauthenticated identity.
    /// </summary>
    [Fact]
    public async Task GetSessionIsolationKeyAsyncReturnsNullWhenUserNotAuthenticatedAsync()
    {
        // Arrange - identity has the claim but no authentication type, so IsAuthenticated is false.
        var claims = new[] { new Claim(ClaimTypes.NameIdentifier, TestUserId) };
        var unauthenticatedIdentity = new ClaimsIdentity(claims);
        var principal = new ClaimsPrincipal(unauthenticatedIdentity);
        var httpContext = new DefaultHttpContext { User = principal };
        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

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
