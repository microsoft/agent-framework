// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class ToolboxConsentParserTests
{
    [Fact]
    public void TryParseConsentRequired_SingleConsentError_ReturnsTrueWithUrlAndToolName()
    {
        // Arrange: the exact aggregate tools/list failure shape the proxy returns when a
        // single tool source needs OAuth consent before it can be enumerated.
        const string Message =
            "Request failed (remote): tools/list failed for 1 tool source(s), succeeded for 0 tool source(s) " +
            "{\"errors\":[{\"name\":\"send_email\",\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://login.example.com/consent?data=abc\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("auth-paths-toolbox", Message, out var consents);

        // Assert
        Assert.True(parsed);
        var consent = Assert.Single(consents);
        Assert.Equal("auth-paths-toolbox", consent.ToolboxName);
        Assert.Equal("send_email", consent.ToolName);
        Assert.Equal("https://login.example.com/consent?data=abc", consent.ConsentUrl);
    }

    [Theory]
    [InlineData("mcp")]
    [InlineData("a2a_preview")]
    [InlineData("some_future_source")]
    public void TryParseConsentRequired_IsSourceTypeAgnostic_ReturnsTrue(string sourceType)
    {
        // Arrange: consent detection keys off the nested CONSENT_REQUIRED error code, not the
        // tool source "type". Work IQ emits "a2a_preview" (issue #7227) rather than "mcp"; the
        // parser must surface consent for any source type so hosting does not fail like the
        // Python parser that hard-coded type == "mcp".
        string message =
            "Request failed (remote): tools/list failed for 1 tool source(s), succeeded for 0 tool source(s) " +
            "{\"errors\":[{\"name\":\"work-iq-connection\",\"type\":\"" + sourceType + "\"," +
            "\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent.example/login?data=xyz\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("work-iq-toolbox", message, out var consents);

        // Assert
        Assert.True(parsed);
        var consent = Assert.Single(consents);
        Assert.Equal("work-iq-toolbox", consent.ToolboxName);
        Assert.Equal("work-iq-connection", consent.ToolName);
        Assert.Equal("https://consent.example/login?data=xyz", consent.ConsentUrl);
    }

    [Fact]
    public void TryParseConsentRequired_MultipleConsentErrors_ReturnsAll()
    {
        // Arrange
        const string Message =
            "tools/list failed " +
            "{\"errors\":[" +
            "{\"name\":\"send_email\",\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent/a\"}}," +
            "{\"name\":\"read_calendar\",\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent/b\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", Message, out var consents);

        // Assert
        Assert.True(parsed);
        Assert.Equal(2, consents.Count);
        Assert.Equal("send_email", consents[0].ToolName);
        Assert.Equal("https://consent/a", consents[0].ConsentUrl);
        Assert.Equal("read_calendar", consents[1].ToolName);
        Assert.Equal("https://consent/b", consents[1].ConsentUrl);
    }

    [Fact]
    public void TryParseConsentRequired_MixedWithNonConsentError_ReturnsFalse()
    {
        // Arrange: when any source fails for a non-consent reason, consent alone cannot make
        // enumeration succeed, so the caller must treat the failure as a hard error.
        const string Message =
            "tools/list failed " +
            "{\"errors\":[" +
            "{\"name\":\"send_email\",\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent/a\"}}," +
            "{\"name\":\"broken\",\"type\":\"mcp\",\"error\":{\"code\":\"INTERNAL_ERROR\",\"message\":\"boom\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", Message, out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Fact]
    public void TryParseConsentRequired_NoJsonPayload_ReturnsFalse()
    {
        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", "connection refused", out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Fact]
    public void TryParseConsentRequired_CodePresentButMalformedJson_ReturnsFalse()
    {
        // Arrange: the marker code is present but the embedded JSON is not parseable.
        const string Message = "tools/list failed CONSENT_REQUIRED {\"errors\":[ not valid json";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", Message, out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Fact]
    public void TryParseConsentRequired_ConsentErrorWithoutUrl_ReturnsFalse()
    {
        // Arrange: a CONSENT_REQUIRED error with no message means there is no URL to present.
        const string Message =
            "tools/list failed " +
            "{\"errors\":[{\"name\":\"send_email\",\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", Message, out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Fact]
    public void TryParseConsentRequired_MissingToolName_FallsBackToToolboxName()
    {
        // Arrange: when the failing source has no name, the toolbox name is used as the tool name.
        const string Message =
            "tools/list failed " +
            "{\"errors\":[{\"type\":\"mcp\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent/x\"}}]}";

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("my-toolbox", Message, out var consents);

        // Assert
        Assert.True(parsed);
        var consent = Assert.Single(consents);
        Assert.Equal("my-toolbox", consent.ToolName);
    }

    [Theory]
    [InlineData("{\"errors\":[\"CONSENT_REQUIRED\"]}")]
    [InlineData("{\"errors\":[null,{\"name\":\"send_email\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent/a\"}}]}")]
    [InlineData("{\"errors\":[{\"name\":\"send_email\",\"error\":\"CONSENT_REQUIRED\"}]}")]
    [InlineData("{\"errors\":[{\"name\":\"send_email\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":5}}]}")]
    public void TryParseConsentRequired_PayloadDoesNotMatchFailureShape_ReturnsFalse(string payload)
    {
        // Arrange: the payload names CONSENT_REQUIRED but does not have the proxy's failure shape.
        string message = "tools/list failed " + payload;

        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", message, out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void TryParseConsentRequired_NullOrEmptyMessage_ReturnsFalse(string? message)
    {
        // Act
        var parsed = ToolboxConsentParser.TryParseConsentRequired("toolbox", message, out var consents);

        // Assert
        Assert.False(parsed);
        Assert.Empty(consents);
    }

    [Fact]
    public void TryDescribeConsentFailure_FailureWithoutConsent_ReturnsFalse()
    {
        // Arrange: an ordinary failure carries no consent link, so its exception can be logged as is.
        var exception = new InvalidOperationException("Connection refused.", new TimeoutException("Timed out."));

        // Act
        var described = ToolboxConsentParser.TryDescribeConsentFailure(exception, out var description);

        // Assert
        Assert.False(described);
        Assert.Empty(description);
    }

    [Fact]
    public void TryDescribeConsentFailure_ValueIsNotAnIdentifier_ReplacesIt()
    {
        // Arrange: only plain identifiers from the external payload may reach a log entry.
        const string Message =
            "tools/list failed " +
            "{\"errors\":[{\"name\":\"https://consent.example/login?data=xyz\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent.example/login?data=xyz\"}}," +
            "{\"name\":\"search\",\"error\":{\"message\":\"Upstream failed.\"}}]}";
        var exception = new AggregateException(new InvalidOperationException("Other failure."), new InvalidOperationException(Message));

        // Act
        var described = ToolboxConsentParser.TryDescribeConsentFailure(exception, out var description);

        // Assert
        Assert.True(described);
        Assert.Equal("unknown (CONSENT_REQUIRED), search (unknown)", description);
    }

    [Theory]
    [InlineData("{\"errors\":[null,{\"name\":\"send_email\",\"error\":{\"code\":\"CONSENT_REQUIRED\",\"message\":\"https://consent.example/a\"}}]}")]
    [InlineData("{\"errors\":[{\"name\":\"send_email\",\"error\":\"CONSENT_REQUIRED https://consent.example/a\"}]}")]
    public void TryDescribeConsentFailure_PayloadDoesNotMatchFailureShape_OmitsConsentLink(string payload)
    {
        // Arrange
        var exception = new InvalidOperationException("tools/list failed " + payload);

        // Act
        var described = ToolboxConsentParser.TryDescribeConsentFailure(exception, out var description);

        // Assert
        Assert.True(described);
        Assert.DoesNotContain("consent.example", description, StringComparison.Ordinal);
    }

    [Fact]
    public void TryDescribeConsentFailure_UninspectedAggregateBranch_ReturnsSafeDescription()
    {
        // Arrange: the consent failure is wrapped in a branch beyond the inspection limit.
        List<Exception> failures =
        [
            new InvalidOperationException(
                "Wrapped failure.",
                new InvalidOperationException("CONSENT_REQUIRED https://auth.example.com/authorize")),
        ];
        for (int i = 0; i < 32; i++)
        {
            failures.Add(new InvalidOperationException("Other failure."));
        }

        var exception = new AggregateException(failures);

        // Act
        var described = ToolboxConsentParser.TryDescribeConsentFailure(exception, out var description);

        // Assert
        Assert.True(described);
        Assert.Equal("unreadable", description);
    }
}
