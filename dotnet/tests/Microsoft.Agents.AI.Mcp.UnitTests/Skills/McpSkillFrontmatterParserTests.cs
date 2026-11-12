// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed class McpSkillFrontmatterParserTests
{
    [Fact]
    public void Parse_PreservesCompleteFrontmatter()
    {
        // Arrange
        const string Content = """
            ---
            name: example
            description: An example skill
            license: MIT
            compatibility: Any runtime
            allowed-tools: read write
            metadata:
              Owner: Example
              owner: Other
            future:
              values: [true, false, 42, 1.25, "123", null, {}, []]
            explicit-null: null
            Name: Distinct field
            ---
            # Instructions
            This is not valid YAML: [
            """;

        // Act
        JsonElement result = McpSkillFrontmatterParser.Parse(Content, AgentMcpSkill.DefaultMaxResourceSizeBytes);

        // Assert
        Assert.Equal("example", result.GetProperty("name").GetString());
        Assert.Equal("An example skill", result.GetProperty("description").GetString());
        Assert.Equal("MIT", result.GetProperty("license").GetString());
        Assert.Equal("Any runtime", result.GetProperty("compatibility").GetString());
        Assert.Equal("read write", result.GetProperty("allowed-tools").GetString());
        Assert.Equal("Example", result.GetProperty("metadata").GetProperty("Owner").GetString());
        Assert.Equal("Other", result.GetProperty("metadata").GetProperty("owner").GetString());
        Assert.Equal("[true,false,42,1.25,\"123\",null,{},[]]", result.GetProperty("future").GetProperty("values").GetRawText());
        Assert.Equal(JsonValueKind.Null, result.GetProperty("explicit-null").ValueKind);
        Assert.False(result.TryGetProperty("missing", out _));
        Assert.Equal("Distinct field", result.GetProperty("Name").GetString());
    }

    [Theory]
    [InlineData("true", "true")]
    [InlineData("false", "false")]
    [InlineData("null", "null")]
    [InlineData("", "null")]
    [InlineData("0", "0")]
    [InlineData("-0", "-0")]
    [InlineData("-12", "-12")]
    [InlineData("0.125", "0.125")]
    [InlineData("1e+300", "1e+300")]
    [InlineData("1e9999", "1e9999")]
    [InlineData("9007199254740993", "9007199254740993")]
    [InlineData("0.123456789012345678901234567890123456789", "0.123456789012345678901234567890123456789")]
    [InlineData("'true'", "\"true\"")]
    [InlineData("\"42\"", "\"42\"")]
    [InlineData("''", "\"\"")]
    [InlineData("01", "\"01\"")]
    [InlineData("0x10", "\"0x10\"")]
    [InlineData("0o10", "\"0o10\"")]
    [InlineData("+12", "\"+12\"")]
    [InlineData(".5", "\".5\"")]
    [InlineData("1.", "\"1.\"")]
    [InlineData("True", "\"True\"")]
    [InlineData("False", "\"False\"")]
    [InlineData("NULL", "\"NULL\"")]
    [InlineData("~", "\"~\"")]
    [InlineData("yes", "\"yes\"")]
    [InlineData("2026-11-03", "\"2026-11-03\"")]
    [InlineData(".inf", "\".inf\"")]
    [InlineData(".nan", "\".nan\"")]
    [InlineData("123abc", "\"123abc\"")]
    public void Parse_Scalars_UsesJsonCompatibleTypes(string yaml, string expectedJson)
    {
        // Arrange
        string content = $"---\nvalue: {yaml}\n---";
        using JsonDocument expected = JsonDocument.Parse(expectedJson);

        // Act
        JsonElement result = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes);

        // Assert
        JsonElement value = result.GetProperty("value");
        Assert.Equal(expected.RootElement.ValueKind, value.ValueKind);
        if (value.ValueKind == JsonValueKind.String)
        {
            Assert.Equal(expected.RootElement.GetString(), value.GetString());
        }
        else
        {
            Assert.Equal(expectedJson, value.GetRawText());
        }
    }

    [Theory]
    [InlineData("plain text # comment", "plain text")]
    [InlineData("'single ''quoted'' text'", "single 'quoted' text")]
    [InlineData("\"line\\nbreak\\t\\u0061\"", "line\nbreak\ta")]
    [InlineData("\"\\U0001F600\"", "\uD83D\uDE00")]
    [InlineData("\"  padded  \"", "  padded  ")]
    [InlineData("'value # not a comment'", "value # not a comment")]
    [InlineData("|\n  first\n  second", "first\nsecond\n")]
    [InlineData("|-\n  first\n  second", "first\nsecond")]
    [InlineData("|-\n  true", "true")]
    [InlineData("|-\n  null", "null")]
    [InlineData("|-\n  42", "42")]
    [InlineData("|+\n  first\n\n", "first\n\n\n")]
    [InlineData(">\n  first\n  second", "first second\n")]
    [InlineData(">-\n  first\n  second", "first second")]
    [InlineData("\"first\n  second\"", "first second")]
    public void Parse_Strings_UsesYamlDecoding(string yaml, string expected)
    {
        // Arrange
        string content = $"---\nvalue: {yaml}\n---";

        // Act
        JsonElement result = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes);

        // Assert
        Assert.Equal(JsonValueKind.String, result.GetProperty("value").ValueKind);
        Assert.Equal(expected, result.GetProperty("value").GetString());
    }

    [Theory]
    [InlineData("", "\n", "")]
    [InlineData("\uFEFF", "\n", "\n")]
    [InlineData("", "\r\n", " \t")]
    [InlineData("\uFEFF", "\r\n", "\r\nbody")]
    public void Parse_Delimiters_AcceptsBomLineEndingsAndTrailingWhitespace(string bom, string newline, string suffix)
    {
        // Arrange
        string content = $"{bom}--- \t{newline}value: |{newline}  first{newline}  second{newline}---{suffix}";

        // Act
        JsonElement result = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes);

        // Assert
        Assert.Equal("first\nsecond\n", result.GetProperty("value").GetString());
    }

    [Theory]
    [InlineData("---\n{}\n---")]
    [InlineData("---\n{first: {value: 1}, second: [two, three]}\n---")]
    [InlineData("---\n# comment\nvalue: 1 # inline comment\n...\n---")]
    [InlineData("---\n\"true\": value\n\"42\": other\n\"\": empty\n\"<<\": literal\n---")]
    public void Parse_SupportedMappings_ReturnsObject(string content)
    {
        // Arrange & Act
        JsonElement result = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes);

        // Assert
        Assert.Equal(JsonValueKind.Object, result.ValueKind);
    }

    [Theory]
    [InlineData("")]
    [InlineData("name: example")]
    [InlineData("\n---\nname: example\n---")]
    [InlineData("\uFEFF\uFEFF---\nname: example\n---")]
    [InlineData(" ---\nname: example\n---")]
    [InlineData("--- invalid\nname: example\n---")]
    [InlineData("---\nname: example")]
    [InlineData("---\nname: example\n ---")]
    [InlineData("---\nname: example\n--- invalid")]
    [InlineData("---\n---")]
    [InlineData("---\n# comment only\n---")]
    [InlineData("---\nnull\n---")]
    [InlineData("---\nvalue\n---")]
    [InlineData("---\n[]\n---")]
    [InlineData("---\nvalue: [invalid\n---")]
    [InlineData("---\nvalue: \"\\q\"\n---")]
    [InlineData("---\nvalue: 1\n...\n--- # second document\nother: 2\n---")]
    [InlineData("---\nname: first\nname: second\n---")]
    [InlineData("---\nname: first\n\"\\u006eame\": second\n---")]
    [InlineData("---\nfuture: {key: first, key: second}\n---")]
    [InlineData("---\nfuture: [{key: first, key: second}]\n---")]
    [InlineData("---\n42: value\n---")]
    [InlineData("---\ntrue: value\n---")]
    [InlineData("---\nnull: value\n---")]
    [InlineData("---\n? [complex, key]\n: value\n---")]
    [InlineData("---\nvalue: !custom text\n---")]
    [InlineData("---\nvalue: !!str 123\n---")]
    [InlineData("---\n!custom {key: value}\n---")]
    [InlineData("---\nvalue: &anchor text\n---")]
    [InlineData("---\nvalue: &anchor [one]\n---")]
    [InlineData("---\nvalue: &anchor {key: value}\n---")]
    [InlineData("---\nvalue: *missing\n---")]
    [InlineData("---\n&anchor key: value\n---")]
    [InlineData("---\n!custom key: value\n---")]
    [InlineData("---\n<<: {key: value}\n---")]
    public void Parse_InvalidOrUnsupportedFrontmatter_Throws(string content)
    {
        // Arrange & Act & Assert
        Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes));
    }

    [Theory]
    [InlineData("\"\\uD800\"")]
    [InlineData("\"\\uDC00\"")]
    [InlineData("\"\\uD800\\uD800\"")]
    [InlineData("\"\\uDC00\\uD800\"")]
    [InlineData("\"\\U00110000\"")]
    [InlineData("\"\\UFFFFFFFF\"")]
    public void Parse_InvalidUnicodeEscape_ThrowsInsteadOfReplacingValueOrKey(string scalar)
    {
        // Arrange
        string valueContent = $"---\nvalue: {scalar}\n---";
        string keyContent = $"---\n{scalar}: value\n---";

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(valueContent, AgentMcpSkill.DefaultMaxResourceSizeBytes));
        Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(keyContent, AgentMcpSkill.DefaultMaxResourceSizeBytes));
    }

    [Theory]
    [InlineData("plain")]
    [InlineData("\u00E9")]
    [InlineData("\uD83D\uDE00")]
    public void Parse_ResourceSize_EnforcesExactUtf8ByteLimit(string value)
    {
        // Arrange
        string content = $"---\nvalue: {value}\n---\nMarkdown body";
        int byteCount = Encoding.UTF8.GetByteCount(content);

        // Act
        JsonElement result = McpSkillFrontmatterParser.Parse(content, byteCount);

        // Assert
        Assert.Equal(value, result.GetProperty("value").GetString());
        Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(content, byteCount - 1));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Parse_InvalidSizeLimit_Throws(long maxResourceSizeBytes)
    {
        // Arrange
        const string Content = "---\n{}\n---";

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => McpSkillFrontmatterParser.Parse(Content, maxResourceSizeBytes));
    }

    [Fact]
    public void Parse_NullContent_Throws()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => McpSkillFrontmatterParser.Parse(null!, AgentMcpSkill.DefaultMaxResourceSizeBytes));
    }

    [Theory]
    [InlineData('1', JsonValueKind.Number)]
    [InlineData('a', JsonValueKind.String)]
    public void Parse_LongScalar_PreservesValue(char character, JsonValueKind expectedKind)
    {
        // Arrange
        string scalar = new(character, 100_000);
        string content = $"---\nvalue: {scalar}\n---";

        // Act
        JsonElement value = McpSkillFrontmatterParser.Parse(content, Encoding.UTF8.GetByteCount(content)).GetProperty("value");

        // Assert
        Assert.Equal(expectedKind, value.ValueKind);
        Assert.Equal(scalar, expectedKind == JsonValueKind.String ? value.GetString() : value.GetRawText());
    }

    [Theory]
    [InlineData(63, true)]
    [InlineData(64, false)]
    [InlineData(1000, false)]
    public void Parse_SequenceDepth_EnforcesLimitIncludingRootMapping(int sequenceDepth, bool valid)
    {
        // Arrange
        string content = $"---\nvalue: {new string('[', sequenceDepth)}0{new string(']', sequenceDepth)}\n---";

        // Act & Assert
        if (valid)
        {
            JsonElement value = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes).GetProperty("value");
            for (int i = 0; i < sequenceDepth; i++)
            {
                value = value[0];
            }

            Assert.Equal(0, value.GetInt32());
        }
        else
        {
            InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes));
            Assert.Contains("maximum nesting depth of 64", exception.Message);
        }
    }

    [Theory]
    [InlineData(63, true)]
    [InlineData(64, false)]
    public void Parse_MappingDepth_EnforcesLimitIncludingRootMapping(int mappingDepth, bool valid)
    {
        // Arrange
        string content = $"---\nvalue: {string.Concat(Enumerable.Repeat("{key: ", mappingDepth))}0{new string('}', mappingDepth)}\n---";

        // Act & Assert
        if (valid)
        {
            JsonElement value = McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes).GetProperty("value");
            for (int i = 0; i < mappingDepth; i++)
            {
                value = value.GetProperty("key");
            }

            Assert.Equal(0, value.GetInt32());
        }
        else
        {
            InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => McpSkillFrontmatterParser.Parse(content, AgentMcpSkill.DefaultMaxResourceSizeBytes));
            Assert.Contains("maximum nesting depth of 64", exception.Message);
        }
    }
}
