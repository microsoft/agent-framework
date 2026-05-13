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
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, TestUserId);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(TestUserId, result);
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
            new Claim(ClaimsIdentity.DefaultNameClaimType, FirstValue),
            new Claim(ClaimsIdentity.DefaultNameClaimType, SecondValue),
        };
        var identity = new ClaimsIdentity(claims);
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
        this.SetupHttpContextWithClaim(ClaimsIdentity.DefaultNameClaimType, string.Empty);
        var provider = new ClaimsIdentitySessionIsolationKeyProvider(this._httpContextAccessorMock.Object);

        // Act
        string? result = await provider.GetSessionIsolationKeyAsync();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    #endregion

    #region Helper Methods

    private void SetupHttpContextWithClaim(string claimType, string claimValue)
    {
        var claims = new[] { new Claim(claimType, claimValue) };
        var identity = new ClaimsIdentity(claims);
        var principal = new ClaimsPrincipal(identity);

        var httpContext = new DefaultHttpContext
        {
            User = principal
        };

        this._httpContextAccessorMock.Setup(x => x.HttpContext).Returns(httpContext);
    }

    #endregion
}
