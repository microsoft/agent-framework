// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Agents.AI.Purview.Serialization;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Purview.UnitTests;

/// <summary>
/// Unit tests for the <see cref="PurviewClient"/> class.
/// </summary>
public sealed class PurviewClientTests : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly PurviewClientHttpMessageHandlerStub _handler;
    private readonly PurviewClient _client;
    private readonly PurviewSettings _settings;

    public PurviewClientTests()
    {
        this._handler = new PurviewClientHttpMessageHandlerStub();
        this._httpClient = new HttpClient(this._handler, false);
        this._settings = new PurviewSettings("TestApp")
        {
            GraphBaseUri = new Uri("https://graph.microsoft.com/v1.0/")
        };
        var tokenCredential = new MockTokenCredential();
        this._client = new PurviewClient(tokenCredential, this._settings, this._httpClient, NullLogger.Instance);
    }

    #region ProcessContentAsync Tests

    [Fact]
    public async Task ProcessContentAsync_WithValidRequest_ReturnsSuccessResponseAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        var expectedResponse = new ProcessContentResponse
        {
            Id = "test-id-123",
            ProtectionScopeState = ProtectionScopeState.NotModified,
            PolicyActions = new List<DlpActionInfo>
            {
                new() { Action = DlpAction.NotifyUser }
            }
        };

        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProcessContentResponse)));

        // Act
        var result = await this._client.ProcessContentAsync(request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(expectedResponse.Id, result.Id);
        Assert.Equal(ProtectionScopeState.NotModified, result.ProtectionScopeState);
        Assert.Single(result.PolicyActions!);
        Assert.Equal(DlpAction.NotifyUser, result.PolicyActions![0].Action);

        // Verify request
        Assert.Equal("https://graph.microsoft.com/v1.0/users/test-user-id/dataSecurityAndGovernance/processContent", this._handler.RequestUri?.ToString());
        Assert.Equal(HttpMethod.Post, this._handler.RequestMethod);
        Assert.Contains("Bearer ", this._handler.AuthorizationHeader);
    }

    [Fact]
    public async Task ProcessContentAsync_WithAcceptedStatus_ReturnsSuccessResponseAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        var expectedResponse = new ProcessContentResponse
        {
            Id = "test-id-456",
            ProtectionScopeState = ProtectionScopeState.Modified
        };

        this._handler.StatusCodeToReturn = HttpStatusCode.Accepted;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProcessContentResponse)));

        // Act
        var result = await this._client.ProcessContentAsync(request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(expectedResponse.Id, result.Id);
        Assert.Equal(ProtectionScopeState.Modified, result.ProtectionScopeState);
    }

    [Fact]
    public async Task ProcessContentAsync_WithScopeIdentifier_IncludesIfNoneMatchHeaderAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        request.ScopeIdentifier = "\"test-scope-123\""; // ETags must be quoted
        var expectedResponse = new ProcessContentResponse { Id = "test-id" };

        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProcessContentResponse)));

        // Act
        await this._client.ProcessContentAsync(request, CancellationToken.None);

        // Assert
        Assert.Equal("\"test-scope-123\"", this._handler.IfNoneMatchHeader);
    }

    [Fact]
    public async Task ProcessContentAsync_WithRateLimitError_ThrowsPurviewRateLimitExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = (HttpStatusCode)429;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRateLimitException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessContentAsync_WithUnauthorizedError_ThrowsPurviewAuthenticationExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = HttpStatusCode.Unauthorized;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewAuthenticationException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessContentAsync_WithForbiddenError_ThrowsPurviewAuthenticationExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = HttpStatusCode.Forbidden;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewAuthenticationException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessContentAsync_WithPaymentRequiredError_ThrowsPurviewPaymentRequiredExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = HttpStatusCode.PaymentRequired;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewPaymentRequiredException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessContentAsync_WithBadRequestError_ThrowsPurviewRequestExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = HttpStatusCode.BadRequest;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task ProcessContentAsync_WithInvalidJsonResponse_ThrowsPurviewExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = "invalid json";

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));

        Assert.Contains("Failed to deserialize ProcessContent response", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<JsonException>(exception.InnerException);
    }

    [Fact]
    public async Task ProcessContentAsync_WithHttpRequestException_ThrowsPurviewRequestExceptionAsync()
    {
        // Arrange
        var request = CreateValidProcessContentRequest();
        this._handler.ShouldThrowHttpRequestException = true;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.ProcessContentAsync(request, CancellationToken.None));

        Assert.Equal("Http error occurred while processing content.", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<HttpRequestException>(exception.InnerException);
    }

    #endregion

    #region GetProtectionScopesAsync Tests

    [Fact]
    public async Task GetProtectionScopesAsync_WithValidRequest_ReturnsSuccessResponseAsync()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id")
        {
            Activities = ProtectionScopeActivities.UploadText,
            Locations = new List<PolicyLocation>
            {
                new("microsoft.graph.policyLocationApplication", "app-123")
            }
        };

        var expectedResponse = new ProtectionScopesResponse
        {
            Scopes = new List<PolicyScopeBase>
            {
                new()
                {
                    Activities = ProtectionScopeActivities.UploadText,
                    Locations = new List<PolicyLocation>
                    {
                        new ("microsoft.graph.policyLocationApplication", "app-123")
                    }
                }
            }
        };

        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProtectionScopesResponse)));
        this._handler.ETagToReturn = "\"scope-etag-123\"";

        // Act
        var result = await this._client.GetProtectionScopesAsync(request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Scopes);
        Assert.Single(result.Scopes);
        Assert.Equal("\"scope-etag-123\"", result.ScopeIdentifier); // ETags are stored with quotes

        // Verify request
        Assert.Equal("https://graph.microsoft.com/v1.0/users/test-user-id/dataSecurityAndGovernance/protectionScopes/compute", this._handler.RequestUri?.ToString());
        Assert.Equal(HttpMethod.Post, this._handler.RequestMethod);
    }

    [Fact]
    public async Task GetProtectionScopesAsync_SetsETagFromResponse_Async()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id");
        var expectedResponse = new ProtectionScopesResponse { Scopes = new List<PolicyScopeBase>() };

        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProtectionScopesResponse)));
        this._handler.ETagToReturn = "\"custom-etag-456\"";

        // Act
        var result = await this._client.GetProtectionScopesAsync(request, CancellationToken.None);

        // Assert
        Assert.Equal("\"custom-etag-456\"", result.ScopeIdentifier);
    }

    [Fact]
    public async Task GetProtectionScopesAsync_WithRateLimitError_ThrowsPurviewRateLimitExceptionAsync()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id");
        this._handler.StatusCodeToReturn = (HttpStatusCode)429;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRateLimitException>(() =>
            this._client.GetProtectionScopesAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task GetProtectionScopesAsync_WithUnauthorizedError_ThrowsPurviewAuthenticationExceptionAsync()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id");
        this._handler.StatusCodeToReturn = HttpStatusCode.Unauthorized;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewAuthenticationException>(() =>
            this._client.GetProtectionScopesAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task GetProtectionScopesAsync_WithInvalidJsonResponse_ThrowsPurviewExceptionAsync()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id");
        this._handler.StatusCodeToReturn = HttpStatusCode.OK;
        this._handler.ResponseToReturn = "invalid json";

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.GetProtectionScopesAsync(request, CancellationToken.None));

        Assert.Contains("Failed to deserialize ProtectionScopes response", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<JsonException>(exception.InnerException);
    }

    [Fact]
    public async Task GetProtectionScopesAsync_WithHttpRequestException_ThrowsPurviewRequestExceptionAsync()
    {
        // Arrange
        var request = new ProtectionScopesRequest("test-user-id", "test-tenant-id");
        this._handler.ShouldThrowHttpRequestException = true;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.GetProtectionScopesAsync(request, CancellationToken.None));

        Assert.Equal("Http error occurred while retrieving protection scopes.", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<HttpRequestException>(exception.InnerException);
    }

    #endregion

    #region SendContentActivitiesAsync Tests

    [Fact]
    public async Task SendContentActivitiesAsync_WithValidRequest_ReturnsSuccessResponseAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        var expectedResponse = new ContentActivitiesResponse
        {
            StatusCode = HttpStatusCode.Created
        };

        this._handler.StatusCodeToReturn = HttpStatusCode.Created;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ContentActivitiesResponse)));

        // Act
        var result = await this._client.SendContentActivitiesAsync(request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Null(result.Error);

        // Verify request - note the endpoint is different from ProcessContent
        Assert.Equal("https://graph.microsoft.com/v1.0/test-user-id/dataSecurityAndGovernance/activities/contentActivities", this._handler.RequestUri?.ToString());
        Assert.Equal(HttpMethod.Post, this._handler.RequestMethod);
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithError_ReturnsResponseWithErrorAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        var expectedResponse = new ContentActivitiesResponse
        {
            Error = new ErrorDetails
            {
                Code = "InvalidRequest",
                Message = "The request is invalid"
            }
        };

        this._handler.StatusCodeToReturn = HttpStatusCode.Created;
        this._handler.ResponseToReturn = JsonSerializer.Serialize(expectedResponse, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ContentActivitiesResponse)));

        // Act
        var result = await this._client.SendContentActivitiesAsync(request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.NotNull(result.Error);
        Assert.Equal("InvalidRequest", result.Error.Code);
        Assert.Equal("The request is invalid", result.Error.Message);
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithRateLimitError_ThrowsPurviewRateLimitExceptionAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        this._handler.StatusCodeToReturn = (HttpStatusCode)429;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRateLimitException>(() =>
            this._client.SendContentActivitiesAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithUnauthorizedError_ThrowsPurviewAuthenticationExceptionAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        this._handler.StatusCodeToReturn = HttpStatusCode.Unauthorized;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewAuthenticationException>(() =>
            this._client.SendContentActivitiesAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithBadRequestError_ThrowsPurviewRequestExceptionAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        this._handler.StatusCodeToReturn = HttpStatusCode.BadRequest;

        // Act & Assert
        await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.SendContentActivitiesAsync(request, CancellationToken.None));
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithInvalidJsonResponse_ThrowsPurviewExceptionAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        this._handler.StatusCodeToReturn = HttpStatusCode.Created;
        this._handler.ResponseToReturn = "invalid json";

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.SendContentActivitiesAsync(request, CancellationToken.None));

        Assert.Contains("Failed to deserialize ContentActivities response", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<JsonException>(exception.InnerException);
    }

    [Fact]
    public async Task SendContentActivitiesAsync_WithHttpRequestException_ThrowsPurviewRequestExceptionAsync()
    {
        // Arrange
        var contentToProcess = CreateValidContentToProcess();
        var request = new ContentActivitiesRequest("test-user-id", "test-tenant-id", contentToProcess);
        this._handler.ShouldThrowHttpRequestException = true;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<PurviewRequestException>(() =>
            this._client.SendContentActivitiesAsync(request, CancellationToken.None));

        Assert.Equal("Http error occurred while creating content activities.", exception.Message);
        Assert.NotNull(exception.InnerException);
        Assert.IsType<HttpRequestException>(exception.InnerException);
    }

    #endregion

    #region Helper Methods

    private static ProcessContentRequest CreateValidProcessContentRequest()
    {
        var contentToProcess = CreateValidContentToProcess();
        return new ProcessContentRequest(contentToProcess, "test-user-id", "test-tenant-id");
    }

    private static ContentToProcess CreateValidContentToProcess()
    {
        var content = new PurviewTextContent("Test content");
        var metadata = new ProcessConversationMetadata(content, "msg-123", false, "Test message");
        var activityMetadata = new ActivityMetadata(Activity.UploadText);
        var deviceMetadata = new DeviceMetadata
        {
            OperatingSystemSpecifications = new OperatingSystemSpecifications
            {
                OperatingSystemPlatform = "Windows",
                OperatingSystemVersion = "10"
            }
        };
        var integratedAppMetadata = new IntegratedAppMetadata
        {
            Name = "TestApp",
            Version = "1.0"
        };
        var policyLocation = new PolicyLocation("microsoft.graph.policyLocationApplication", "app-123");
        var protectedAppMetadata = new ProtectedAppMetadata(policyLocation)
        {
            Name = "TestApp",
            Version = "1.0"
        };

        return new ContentToProcess(
            new List<ProcessContentMetadataBase> { metadata },
            activityMetadata,
            deviceMetadata,
            integratedAppMetadata,
            protectedAppMetadata
        );
    }

    #endregion

    public void Dispose()
    {
        this._handler.Dispose();
        this._httpClient.Dispose();
    }

    /// <summary>
    /// Mock HTTP message handler for testing
    /// </summary>
    internal sealed class PurviewClientHttpMessageHandlerStub : HttpMessageHandler
    {
        public HttpStatusCode StatusCodeToReturn { get; set; } = HttpStatusCode.OK;
        public string? ResponseToReturn { get; set; }
        public string? ETagToReturn { get; set; }
        public bool ShouldThrowHttpRequestException { get; set; }
        public Uri? RequestUri { get; private set; }
        public HttpMethod? RequestMethod { get; private set; }
        public string? AuthorizationHeader { get; private set; }
        public string? IfNoneMatchHeader { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            // Capture request details
            this.RequestUri = request.RequestUri;
            this.RequestMethod = request.Method;

            if (request.Headers.Authorization != null)
            {
                this.AuthorizationHeader = request.Headers.Authorization.ToString();
            }

            if (request.Headers.TryGetValues("If-None-Match", out var ifNoneMatchValues))
            {
                this.IfNoneMatchHeader = string.Join(", ", ifNoneMatchValues);
            }

            // Throw HttpRequestException if configured
            if (this.ShouldThrowHttpRequestException)
            {
                throw new HttpRequestException("Simulated network error");
            }

            var response = new HttpResponseMessage(this.StatusCodeToReturn);

            response.Content = new StringContent(this.ResponseToReturn ?? string.Empty, Encoding.UTF8, "application/json");

            if (!string.IsNullOrEmpty(this.ETagToReturn))
            {
                response.Headers.ETag = new System.Net.Http.Headers.EntityTagHeaderValue(this.ETagToReturn);
            }

            return await Task.FromResult(response);
        }
    }

    /// <summary>
    /// Mock token credential for testing
    /// </summary>
    internal sealed class MockTokenCredential : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            return new AccessToken("mock-token", DateTimeOffset.UtcNow.AddHours(1));
        }

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            return new ValueTask<AccessToken>(new AccessToken("mock-token", DateTimeOffset.UtcNow.AddHours(1)));
        }
    }
}
