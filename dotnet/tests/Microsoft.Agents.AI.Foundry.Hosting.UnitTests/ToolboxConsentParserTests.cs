// Copyright (c) Microsoft. All rights reserved.

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
}
