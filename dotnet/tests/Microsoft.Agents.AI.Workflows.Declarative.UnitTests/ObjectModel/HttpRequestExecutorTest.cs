// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="HttpRequestExecutor"/>.
/// </summary>
public sealed class HttpRequestExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    private const string TestUrl = "https://api.example.com/data";

    private readonly Mock<ResponseAgentProvider> _agentProvider = new(MockBehavior.Loose);

    [Fact]
    public void InvalidModel()
    {
        // Arrange
        Mock<IHttpRequestHandler> mockHandler = new();

        // Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new HttpRequestExecutor(
            new HttpRequestAction(),
            mockHandler.Object,
            this._agentProvider.Object,
            this.State));
    }

    [Fact]
    public void HttpRequestIsDiscreteAction()
    {
        // Arrange
        Mock<IHttpRequestHandler> mockHandler = new();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestIsDiscreteAction),
            url: TestUrl,
            method: HttpMethodType.Get);
        HttpRequestExecutor action = new(model, mockHandler.Object, this._agentProvider.Object, this.State);

        // Act & Assert — IsDiscreteAction should be true for HttpRequest (single-step action).
        VerifyIsDiscrete(action, isDiscrete: true);
    }

    [Fact]
    public async Task HttpGetReturnsJsonObjectAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ResponseVar = "Result";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetReturnsJsonObjectAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            responseVariable: ResponseVar);

        MockHttpRequestHandler handler = new(HttpRequestResult("{\"key\":\"value\",\"number\":42}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        Assert.IsType<RecordValue>(this.State.Get(ResponseVar), exactMatch: false);
        handler.VerifySent(info => info.Method == "GET" && info.Url == TestUrl);
    }

    [Fact]
    public async Task HttpGetReturnsPlainStringAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ResponseVar = "Result";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetReturnsPlainStringAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            responseVariable: ResponseVar);

        MockHttpRequestHandler handler = new(HttpRequestResult("not-json content"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState(ResponseVar, FormulaValue.New("not-json content"));
    }

    [Fact]
    public async Task HttpGetWithEmptyBodyYieldsBlankAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ResponseVar = "Result";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetWithEmptyBodyYieldsBlankAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            responseVariable: ResponseVar);

        MockHttpRequestHandler handler = new(HttpRequestResult(null));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyUndefined(ResponseVar);
    }

    [Fact]
    public async Task HttpGetForwardsHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetForwardsHeadersAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            headers: new Dictionary<string, string>
            {
                ["Authorization"] = "Bearer token",
                ["Accept"] = "application/json",
            });

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.Headers?["Authorization"] == "Bearer token" &&
            info.Headers?["Accept"] == "application/json");
    }

    [Fact]
    public async Task HttpPostWithJsonBodyAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpPostWithJsonBodyAsync),
            url: TestUrl,
            method: HttpMethodType.Post,
            jsonBody: new StringDataValue("hello"));

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.Method == "POST" &&
            info.BodyContentType == "application/json" &&
            info.Body == "\"hello\"");
    }

    [Fact]
    public async Task HttpPostWithRawBodyAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpPostWithRawBodyAsync),
            url: TestUrl,
            method: HttpMethodType.Post,
            rawBody: "raw body content",
            rawContentType: "text/plain");

        MockHttpRequestHandler handler = new(HttpRequestResult(""));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.BodyContentType == "text/plain" &&
            info.Body == "raw body content");
    }

    [Fact]
    public async Task HttpRequestRaisesOnErrorByDefaultAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestRaisesOnErrorByDefaultAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(HttpRequestResult("server error", statusCode: 500, isSuccess: false));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act & Assert
        await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));
    }

    [Fact]
    public async Task HttpRequestFailureExceptionTruncatesLongBodyAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestFailureExceptionTruncatesLongBodyAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        string longBody = new('x', 10_000);
        MockHttpRequestHandler handler = new(HttpRequestResult(longBody, statusCode: 500, isSuccess: false));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        DeclarativeActionException exception =
            await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert - message contains status and truncation marker, bounded in length, never the full body.
        Assert.Contains("500", exception.Message);
        Assert.Contains("[truncated]", exception.Message);
        Assert.DoesNotContain(longBody, exception.Message);
        Assert.True(exception.Message.Length < 512, $"Exception message too long: {exception.Message.Length} chars.");
    }

    [Fact]
    public async Task HttpRequestFailureExceptionOmitsEmptyBodyAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestFailureExceptionOmitsEmptyBodyAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(HttpRequestResult(body: null, statusCode: 404, isSuccess: false));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        DeclarativeActionException exception =
            await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert - status present, no stray "Body: ''" noise.
        Assert.Contains("404", exception.Message);
        Assert.DoesNotContain("Body:", exception.Message);
    }

    [Fact]
    public async Task HttpRequestFailureExceptionSanitizesControlCharsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestFailureExceptionSanitizesControlCharsAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(HttpRequestResult("line1\r\nline2\tend", statusCode: 400, isSuccess: false));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        DeclarativeActionException exception =
            await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert - CR/LF/TAB collapsed to spaces so the message stays on one line.
        Assert.DoesNotContain("\r", exception.Message);
        Assert.DoesNotContain("\n", exception.Message);
        Assert.DoesNotContain("\t", exception.Message);
        Assert.Contains("line1", exception.Message);
        Assert.Contains("line2", exception.Message);
    }

    [Fact]
    public async Task HttpRequestPassesTimeoutToHandlerAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestPassesTimeoutToHandlerAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            timeoutMilliseconds: 1500);

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.Timeout is not null &&
            info.Timeout.Value == TimeSpan.FromMilliseconds(1500));
    }

    [Fact]
    public async Task HttpRequestTimeoutRaisesDeclarativeExceptionAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestTimeoutRaisesDeclarativeExceptionAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(
            HttpRequestResult("{}"),
            throwOnSend: new OperationCanceledException());
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act & Assert
        await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));
    }

    [Fact]
    public async Task HttpRequestTransportFailureRaisesDeclarativeExceptionAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestTransportFailureRaisesDeclarativeExceptionAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(
            HttpRequestResult("{}"),
            throwOnSend: new InvalidOperationException("transport failure"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act & Assert
        await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));
    }

    [Fact]
    public async Task HttpRequestStoresResponseHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string HeaderVar = "Headers";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestStoresResponseHeadersAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            responseHeadersVariable: HeaderVar);

        Dictionary<string, IReadOnlyList<string>> responseHeaders = new(StringComparer.OrdinalIgnoreCase)
        {
            ["X-Request-Id"] = ["abc-123"],
            ["Set-Cookie"] = ["a=1", "b=2"],
        };
        MockHttpRequestHandler handler = new(HttpRequestResult("{}", headers: responseHeaders));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        FormulaValue storedHeaders = this.State.Get(HeaderVar);
        Assert.IsType<RecordValue>(storedHeaders, exactMatch: false);
    }

    [Fact]
    public async Task HttpRequestForwardsQueryParametersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestForwardsQueryParametersAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            queryParameters: new Dictionary<string, DataValue>
            {
                ["filter"] = StringDataValue.Create("active"),
                ["limit"] = NumberDataValue.Create(10),
                ["includeDeleted"] = BooleanDataValue.Create(false),
            });

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.QueryParameters?.Count == 3 &&
            info.QueryParameters["filter"] == "active" &&
            info.QueryParameters["limit"] == "10" &&
            info.QueryParameters["includeDeleted"] == "false");
    }

    [Fact]
    public async Task HttpRequestAddsResponseToConversationAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ConversationId = "conv-12345";
        const string ResponseBody = "response-text";

        this._agentProvider
            .Setup(p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
            .Returns<string, ChatMessage, CancellationToken>((_, message, _) => Task.FromResult(message));

        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestAddsResponseToConversationAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            conversationId: ConversationId);

        MockHttpRequestHandler handler = new(HttpRequestResult(ResponseBody));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this._agentProvider.Verify(
            p => p.CreateMessageAsync(
                ConversationId,
                It.Is<ChatMessage>(m => m.Role == ChatRole.Assistant && m.Text == ResponseBody),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task HttpRequestWithoutConversationIdSkipsConversationAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestWithoutConversationIdSkipsConversationAsync),
            url: TestUrl,
            method: HttpMethodType.Get);

        MockHttpRequestHandler handler = new(HttpRequestResult("response"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this._agentProvider.Verify(
            p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task HttpRequestForwardsConnectionNameAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ConnectionName = "my-connection";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestForwardsConnectionNameAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            connectionName: ConnectionName);

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info => info.ConnectionName == ConnectionName);
    }

    [Fact]
    public async Task HttpRequestEmptyConversationIdSkipsConversationAsync()
    {
        // Arrange - empty-string conversationId should be treated as unset.
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestEmptyConversationIdSkipsConversationAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            conversationId: "");

        MockHttpRequestHandler handler = new(HttpRequestResult("response"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this._agentProvider.Verify(
            p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task HttpRequestEmptyResponseBodySkipsConversationAsync()
    {
        // Arrange - conversationId set, but empty body should not produce a conversation message.
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestEmptyResponseBodySkipsConversationAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            conversationId: "conv-1");

        MockHttpRequestHandler handler = new(HttpRequestResult(""));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this._agentProvider.Verify(
            p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task HttpGetReturnsJsonArrayAsync()
    {
        // Arrange - exercises JsonValueKind.Array branch of ParseResponseBody.
        this.State.InitializeSystem();
        const string ResponseVar = "Result";
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetReturnsJsonArrayAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            responseVariable: ResponseVar);

        MockHttpRequestHandler handler = new(HttpRequestResult("[1, 2, 3]"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        FormulaValue stored = this.State.Get(ResponseVar);
        Assert.IsType<TableValue>(stored, exactMatch: false);
    }

    [Fact]
    public async Task HttpGetWithEmptyHeaderValueDropsHeaderAsync()
    {
        // Arrange - empty header values should be filtered out (matches GetHeaders guard).
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpGetWithEmptyHeaderValueDropsHeaderAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            headers: new Dictionary<string, string>
            {
                ["X-Trace"] = "trace-1",
                ["X-Empty"] = "",
            });

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info =>
            info.Headers?.ContainsKey("X-Trace") == true &&
            info.Headers?.ContainsKey("X-Empty") == false);
    }

    [Fact]
    public async Task HttpRequestZeroTimeoutNotForwardedAsync()
    {
        // Arrange - non-positive timeouts should not be forwarded (handler default applies).
        this.State.InitializeSystem();
        HttpRequestAction model = this.CreateModel(
            displayName: nameof(HttpRequestZeroTimeoutNotForwardedAsync),
            url: TestUrl,
            method: HttpMethodType.Get,
            timeoutMilliseconds: 0);

        MockHttpRequestHandler handler = new(HttpRequestResult("{}"));
        HttpRequestExecutor action = new(model, handler.Object, this._agentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        handler.VerifySent(info => info.Timeout is null);
    }

    private static HttpRequestResult HttpRequestResult(
        string? body,
        int statusCode = 200,
        bool isSuccess = true,
        IReadOnlyDictionary<string, IReadOnlyList<string>>? headers = null) =>
        new()
        {
            StatusCode = statusCode,
            IsSuccessStatusCode = isSuccess,
            Body = body,
            Headers = headers,
        };

    private HttpRequestAction CreateModel(
        string displayName,
        string url,
        HttpMethodType method,
        string? responseVariable = null,
        string? responseHeadersVariable = null,
        IReadOnlyDictionary<string, string>? headers = null,
        IReadOnlyDictionary<string, DataValue>? queryParameters = null,
        string? conversationId = null,
        string? connectionName = null,
        DataValue? jsonBody = null,
        string? rawBody = null,
        string? rawContentType = null,
        long? timeoutMilliseconds = null,
        string? continueOnErrorStatusVariable = null,
        string? continueOnErrorBodyVariable = null)
    {
        HttpRequestAction.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            Url = new StringExpression.Builder(StringExpression.Literal(url)),
            Method = new EnumExpression<HttpMethodTypeWrapper>.Builder(
                EnumExpression<HttpMethodTypeWrapper>.Literal(HttpMethodTypeWrapper.Get(method))),
        };

        if (responseVariable is not null)
        {
            builder.Response = PropertyPath.Create(FormatVariablePath(responseVariable));
        }

        if (responseHeadersVariable is not null)
        {
            builder.ResponseHeaders = PropertyPath.Create(FormatVariablePath(responseHeadersVariable));
        }

        if (headers is not null)
        {
            foreach (KeyValuePair<string, string> header in headers)
            {
                builder.Headers.Add(header.Key, new StringExpression.Builder(StringExpression.Literal(header.Value)));
            }
        }

        if (queryParameters is not null)
        {
            foreach (KeyValuePair<string, DataValue> parameter in queryParameters)
            {
                builder.QueryParameters.Add(parameter.Key, new ValueExpression.Builder(ValueExpression.Literal(parameter.Value)));
            }
        }

        if (conversationId is not null)
        {
            builder.ConversationId = new StringExpression.Builder(StringExpression.Literal(conversationId));
        }

        if (connectionName is not null)
        {
            builder.Connection = new RemoteConnection.Builder
            {
                Name = new StringExpression.Builder(StringExpression.Literal(connectionName)),
            };
        }

        if (jsonBody is not null)
        {
            builder.Body = new JsonRequestContent.Builder()
            {
                Content = new ValueExpression.Builder(ValueExpression.Literal(jsonBody)),
            };
        }
        else if (rawBody is not null)
        {
            RawRequestContent.Builder rawBuilder = new()
            {
                Content = new StringExpression.Builder(StringExpression.Literal(rawBody)),
            };
            if (rawContentType is not null)
            {
                rawBuilder.ContentType = new StringExpression.Builder(StringExpression.Literal(rawContentType));
            }
            builder.Body = rawBuilder;
        }

        if (timeoutMilliseconds is not null)
        {
            builder.RequestTimeoutInMilliseconds = new IntExpression.Builder(IntExpression.Literal(timeoutMilliseconds.Value));
        }

        if (continueOnErrorStatusVariable is not null || continueOnErrorBodyVariable is not null)
        {
            ContinueOnErrorBehavior.Builder continueBuilder = new();
            if (continueOnErrorStatusVariable is not null)
            {
                continueBuilder.StatusCode = PropertyPath.Create(FormatVariablePath(continueOnErrorStatusVariable));
            }
            if (continueOnErrorBodyVariable is not null)
            {
                continueBuilder.ErrorResponseBody = PropertyPath.Create(FormatVariablePath(continueOnErrorBodyVariable));
            }
            builder.ErrorHandling = continueBuilder;
        }

        return AssignParent<HttpRequestAction>(builder);
    }

    private sealed class MockHttpRequestHandler : Mock<IHttpRequestHandler>
    {
        private HttpRequestInfo? _lastRequest;

        public MockHttpRequestHandler(HttpRequestResult result, Exception? throwOnSend = null)
        {
            this.Setup(handler => handler.SendAsync(It.IsAny<HttpRequestInfo>(), It.IsAny<CancellationToken>()))
                .Returns<HttpRequestInfo, CancellationToken>((info, _) =>
                {
                    this._lastRequest = info;
                    if (throwOnSend is not null)
                    {
                        throw throwOnSend;
                    }
                    return Task.FromResult(result);
                });
        }

        public void VerifySent(Func<HttpRequestInfo, bool> predicate)
        {
            Assert.NotNull(this._lastRequest);
            Assert.True(predicate(this._lastRequest!), "Sent HTTP request did not match expected predicate.");
        }
    }
}
