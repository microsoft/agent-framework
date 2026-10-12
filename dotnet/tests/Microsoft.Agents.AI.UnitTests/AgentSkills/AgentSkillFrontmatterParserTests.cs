// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillFrontmatterParser"/>.
/// </summary>
public sealed class AgentSkillFrontmatterParserTests
{
    private const string SkillLocation = "skill://test-skill/SKILL.md";

    /// <summary>
    /// Existing scalar representations with metadata before or after them, with and without duplicate metadata.
    /// </summary>
    public static TheoryData<string, string, string, bool, bool, string> ExistingScalarFormats
    {
        get
        {
            var data = new TheoryData<string, string, string, bool, bool, string>();
            // Cover scalar representations supported by the lightweight parser.
            (string Value, string Expected)[] cases =
            [
                ("Read files", "Read files"),
                ("'Read files'", "Read files"),
                ("\"Read files\"", "Read files"),
                ("\"  Read files  \"", "  Read files  "),
                ("\"Use #tags: safely\"", "Use #tags: safely"),
                ("\"Use 'quotes' safely\"", "Use 'quotes' safely"),
                ("'Use \"quotes\" safely'", "Use \"quotes\" safely"),
                ("\"| not a block\"", "| not a block"),
                ("\n  Read files", "Read files"),
                ("\n\n  'Read files'", "Read files"),
                ("\n  >-\n    Read\n    files", "Read files"),
                ("|\n  Read\n  files", "Read\nfiles\n"),
                ("|-\n  Read\n  files", "Read\nfiles"),
                ("|+\n  Read\n  files", "Read\nfiles\n"),
                (">\n  Read\n  files", "Read files\n"),
                (">-\n  Read\n  files", "Read files"),
                (">+\n  Read\n  files", "Read files\n"),
                ("|-\n\n  Read\n  files", "\nRead\nfiles"),
                ("|-\n  Read\n\n  files", "Read\n\nfiles"),
                ("|-\n  Read\n    indented\n  files", "Read\n  indented\nfiles"),
                ("|-\n  description: text\n  Description: text", "description: text\nDescription: text"),
                ("|-\n  \"description\": text\n  'allowed-tools': text", "\"description\": text\n'allowed-tools': text"),
            ];
            foreach (var (value, expected) in cases)
            {
                foreach (string newline in new[] { "\n", "\r\n" })
                {
                    foreach (bool metadataFirst in new[] { false, true })
                    {
                        foreach (string quote in new[] { "", "'", "\"" })
                        {
                            data.Add(value, expected, newline, metadataFirst, false, quote);
                            data.Add(value, expected, newline, metadataFirst, true, quote);
                        }
                    }
                }
            }

            return data;
        }
    }

    /// <summary>
    /// Block-scalar chomping with trailing blank lines, LF and CRLF, and another field or the closing delimiter.
    /// </summary>
    public static TheoryData<string, string, string, bool> BlockScalarChomping
    {
        get
        {
            var data = new TheoryData<string, string, string, bool>();
            foreach (char style in new[] { '|', '>' })
            {
                foreach (string chomping in new[] { "", "-", "+" })
                {
                    for (int trailingBlankLines = 0; trailingBlankLines <= 2; trailingBlankLines++)
                    {
                        string value = $"{style}{chomping}\n  Read\n  files\n" + new string('\n', trailingBlankLines);
                        string expected = style == '|' ? "Read\nfiles" : "Read files";
                        expected += chomping switch
                        {
                            "-" => "",
                            "+" => new string('\n', trailingBlankLines + 1),
                            _ => "\n",
                        };
                        foreach (string newline in new[] { "\n", "\r\n" })
                        {
                            data.Add(value, expected, newline, false);
                            data.Add(value, expected, newline, true);
                        }
                    }
                }
            }

            return data;
        }
    }

    /// <summary>
    /// Duplicate and incorrectly cased root properties with quoted names.
    /// </summary>
    public static TheoryData<string, string> ConflictingQuotedFields
    {
        get
        {
            var data = new TheoryData<string, string>();
            (string Key, string Value)[] fields =
            [
                ("name", "test-skill"),
                ("description", "Read files"),
                ("license", "MIT"),
                ("compatibility", "Any runtime"),
                ("metadata", "\n  author: First"),
                ("allowed-tools", "read"),
            ];
            foreach (var (key, value) in fields)
            {
                string otherFields = string.Join("\n", fields.Where(f => f.Key != key).Select(f => $"{f.Key}: {f.Value}"));
                foreach (char quote in new[] { '\'', '"' })
                {
                    string quotedKey = $"{quote}{key}{quote}";
                    string quotedField = $"{quotedKey}: {value}";
                    string bareField = $"{key}: {value}";
                    char otherQuote = quote == '\'' ? '"' : '\'';
                    foreach (string newline in new[] { "\n", "\r\n" })
                    {
                        string incorrectlyCasedField = $"{quote}{key.ToUpperInvariant()}{quote}: {value}";
                        string content = $"---\n{otherFields}\n{incorrectlyCasedField}\n---\nBody.";
                        string diagnostic = $"incorrectly cased frontmatter field '{key.ToUpperInvariant()}'; expected '{key}'";
                        data.Add(content.Replace("\n", newline), diagnostic);
                        foreach (string declaration in new[]
                        {
                            $"{quotedField}\n{bareField}",
                            $"{bareField}\n{quotedField}",
                            $"{quotedField}\n{quotedField}",
                            $"{quotedField}\n{otherQuote}{key}{otherQuote}: {value}",
                            $"{quotedKey}:\n{bareField}",
                            $"{bareField}\n{quotedKey}:",
                        })
                        {
                            content = $"---\n{otherFields}\n{declaration}\n---\nBody.";
                            data.Add(content.Replace("\n", newline), $"duplicate frontmatter field '{key}'");
                        }
                    }
                }
            }

            return data;
        }
    }

    /// <summary>
    /// Existing metadata scalar outputs, including the lightweight parser's incomplete YAML normalization.
    /// </summary>
    public static TheoryData<string, string, string> ExistingMetadataScalarFormats
    {
        get
        {
            var data = new TheoryData<string, string, string>();
            (string Value, string Expected)[] cases =
            [
                ("First", "First"),
                ("'First'", "First"),
                ("\"First\"", "First"),
                ("\"  First  \"", "  First  "),
                ("\"Use #tags: safely\"", "Use #tags: safely"),
                ("\"Use 'quotes' safely\"", "Use 'quotes' safely"),
                ("'Use \"quotes\" safely'", "Use \"quotes\" safely"),
                ("''", "''"),
                ("\"\"", "\"\""),
                ("\"\\n\"", "\\n"),
                ("'It''s fine'", "It''s fine"),
                ("\n    First", "First"),
                ("\n    'First'", "First"),
                ("\n    \"First\"", "First"),
                ("First\n    Second", "First"),
                ("\"First\n    Second\"", "\"First"),
                ("'First\n    Second'", "'First"),
                ("|\n    First\n    Second", "|"),
                ("|-\n    First\n    Second", "|-"),
                ("|+\n    First\n    Second", "|+"),
                (">\n    First\n    Second", ">"),
                (">-\n    First\n    Second", ">-"),
                (">+\n    First\n    Second", ">+"),
                ("\n    |-\n      First\n      Second", "|-"),
            ];
            foreach (var (value, expected) in cases)
            {
                data.Add(value, expected, "\n");
                data.Add(value, expected, "\r\n");
            }

            return data;
        }
    }

    /// <summary>
    /// Duplicate and incorrectly cased fields before and after inline or block values.
    /// </summary>
    public static TheoryData<string, string, string> ConflictingScalarFormats
    {
        get
        {
            var data = new TheoryData<string, string, string>();
            string[] firstValues = ["First", "'First'", "\"First\"", "|-\n  First", ">-\n  First"];
            string[] secondValues = ["Second", "'Second'", "\"Second\"", "|-\n  Second", ">-\n  Second"];
            string[] secondKeys = ["description", "Description", "DESCRIPTION"];
            foreach (string firstValue in firstValues)
            {
                foreach (string secondValue in secondValues)
                {
                    foreach (string secondKey in secondKeys)
                    {
                        data.Add(firstValue, secondValue, secondKey);
                    }
                }
            }

            return data;
        }
    }

    /// <summary>
    /// Duplicate metadata values and case-insensitive key collisions, with LF and CRLF.
    /// </summary>
    public static TheoryData<string, string, string, string, string, string> DuplicateMetadataEntries
    {
        get
        {
            var data = new TheoryData<string, string, string, string, string, string>();
            (string Key, string DuplicateKey, string Value, string DuplicateValue, string Expected)[] cases =
            [
                ("author", "author", "First", "Second", "First"),
                ("Author", "Author", "'First'", "\"Second\"", "First"),
                ("author", "author", "\"First\"", "'Second'", "First"),
                ("author", "author", "Same", "Same", "Same"),
                ("author", "author", "''", "Second", "''"),
                ("author", "author", "\"\"", "Second", "\"\""),
                ("author", "author", "\"  First  \"", "Second", "  First  "),
                ("author", "author", "0", "Second", "0"),
                ("description", "description", "First", "Second", "First"),
                ("metadata", "metadata", "First", "Second", "First"),
                ("vendor-key", "vendor-key", "First", "Second", "First"),
                ("vendor_key", "vendor_key", "First", "Second", "First"),
                ("author", "Author", "First", "Second", "First"),
                ("Author", "author", "First", "Second", "First"),
                ("author", "AUTHOR", "First", "Second", "First"),
                ("description", "Description", "First", "Second", "First"),
                ("metadata", "Metadata", "First", "Second", "First"),
                ("vendor-key", "Vendor-Key", "First", "Second", "First"),
                ("author", "author", "\n    'First'", "Second", "First"),
                ("author", "Author", "First", "\n    \"Second\"", "First"),
                ("author", "author", "\"author: First\"", "Second", "author: First"),
                ("author", "author", "First\n  # author: Not a field", "Second", "First"),
                ("author", "author", "|-\n    First\n    paragraph", "Second", "|-"),
                ("author", "Author", "First", ">-\n    Second\n    paragraph", "First"),
                ("author", "author", ">\n    First\n    paragraph", "|\n    Second\n    paragraph", ">"),
            ];
            foreach (var (key, duplicateKey, value, duplicateValue, expected) in cases)
            {
                data.Add(key, duplicateKey, value, duplicateValue, expected, "\n");
                data.Add(key, duplicateKey, value, duplicateValue, expected, "\r\n");
            }

            return data;
        }
    }

    [Theory]
    [MemberData(nameof(ExistingScalarFormats))]
    public void TryParse_ExistingScalarFormats_ReturnsExpectedValues(
        string value, string expected, string newline, bool metadataFirst, bool duplicateMetadata, string quote)
    {
        // Arrange
        string fields = $"{quote}name{quote}: test-skill\n{quote}description{quote}: {value}\n" +
            $"{quote}license{quote}: 'MIT'\n{quote}compatibility{quote}: Any runtime\n{quote}allowed-tools{quote}: read\n";
        string metadata = $"{quote}metadata{quote}:\n  author: test\n" + (duplicateMetadata ? "  author: Ignored\n" : "");
        string content = ("---\n" + (metadataFirst ? metadata + fields : fields + metadata) + "---\nBody.").Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("test-skill", frontmatter.Name);
        Assert.Equal(expected, frontmatter.Description);
        Assert.Equal("MIT", frontmatter.License);
        Assert.Equal("Any runtime", frontmatter.Compatibility);
        Assert.Equal("read", frontmatter.AllowedTools);
        Assert.NotNull(frontmatter.Metadata);
        Assert.Equal("test", frontmatter.Metadata["author"]);
    }

    [Theory]
    [MemberData(nameof(BlockScalarChomping))]
    public void TryParse_BlockScalarChomping_PreservesExpectedNewlines(string value, string expected, string newline, bool followingField)
    {
        // Arrange
        string content = ("---\nname: test-skill\ndescription: " + value +
            (followingField ? "license: MIT\n" : "") + "---\nBody.").Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal(expected, frontmatter.Description);
        Assert.Equal(followingField ? "MIT" : null, frontmatter.License);
    }

    [Theory]
    [InlineData("|2", "Read files\n")]
    [InlineData(">2", "Read files\n")]
    [InlineData("|2-", "Read files")]
    [InlineData(">2-", "Read files")]
    [InlineData("|-2", "Read files")]
    [InlineData(">-2", "Read files")]
    [InlineData("|2+", "Read files\n\n")]
    [InlineData(">2+", "Read files\n\n")]
    [InlineData("|+2", "Read files\n\n")]
    [InlineData(">+2", "Read files\n\n")]
    public void TryParse_BlockScalarChompingWithIndentationIndicator_PreservesExpectedNewlines(string value, string expected)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: {value}\n  Read files\n\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal(expected, frontmatter.Description);
    }

    [Theory]
    [InlineData("|", "")]
    [InlineData("|-", "")]
    [InlineData("|+", "\n\n")]
    [InlineData(">", "")]
    [InlineData(">-", "")]
    [InlineData(">+", "\n\n")]
    public void TryParse_BlankOptionalBlockScalar_PreservesChomping(string value, string expected)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: Read files\nlicense: {value}\n\n\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal(expected, frontmatter.License);
    }

    [Theory]
    [InlineData(1023, true)]
    [InlineData(1024, false)]
    public void TryParse_ClippedDescription_ValidatesLengthIncludingNewline(int contentLength, bool expected)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: |\n  {new string('a', contentLength)}\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.Equal(expected, result);
        if (expected)
        {
            Assert.NotNull(frontmatter);
            Assert.Equal(contentLength + 1, frontmatter.Description.Length);
            Assert.EndsWith("\n", frontmatter.Description);
        }
        else
        {
            Assert.Null(frontmatter);
        }
    }

    [Theory]
    [MemberData(nameof(ExistingMetadataScalarFormats))]
    public void TryParse_ExistingMetadataScalarFormats_Preserved(string value, string expected, string newline)
    {
        // Arrange
        string content = ("---\nname: test-skill\ndescription: Read files\n" +
            $"metadata:\n  author: {value}\n  version: '1.0'\nlicense: MIT\n---\nBody.").Replace("\n", newline);
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.Equal("MIT", frontmatter.License);
        Assert.NotNull(frontmatter.Metadata);
        Assert.Equal(2, frontmatter.Metadata.Count);
        Assert.Equal(expected, frontmatter.Metadata["author"]);
        Assert.Equal("1.0", frontmatter.Metadata["version"]);
        logger.Verify(
            l => l.Log(
                It.Is<LogLevel>(level => level >= LogLevel.Warning),
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Never);
    }

    [Theory]
    [MemberData(nameof(ConflictingScalarFormats))]
    public void TryParse_ConflictingScalarFormats_ReturnsFalseAndLogsError(string firstValue, string secondValue, string secondKey)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: {firstValue}\n{secondKey}: {secondValue}\nlicense: MIT\n---\nBody.";
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
        string diagnostic = secondKey == "description"
            ? "duplicate frontmatter field 'description'"
            : $"incorrectly cased frontmatter field '{secondKey}'; expected 'description'";
        VerifyDiagnostic(logger, LogLevel.Error, diagnostic, Times.Once());
    }

    [Theory]
    [MemberData(nameof(ConflictingQuotedFields))]
    public void TryParse_ConflictingQuotedFields_ReturnsFalseAndLogsError(string content, string diagnostic)
    {
        // Arrange
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
        VerifyDiagnostic(logger, LogLevel.Error, diagnostic, Times.Once());
    }

    [Fact]
    public void TryParse_NestedMetadataAndUnknownFields_KeepsFirstMetadataValue()
    {
        // Arrange
        const string Content =
            "---\nname: test-skill\ndescription: Read files\n" +
            "# description: Not a field\n" +
            "metadata:\n  author: First\n  author: Second\n  Description: Nested text\n" +
            "  \"description\": Ignored\n  'metadata': Ignored\n" +
            "vendor-option: First\nvendor-option: Second\n" +
            "'vendor-option': Third\n\"VENDOR-OPTION\": Fourth\n---\n\"description\": Body text";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(Content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.NotNull(frontmatter.Metadata);
        Assert.Equal(2, frontmatter.Metadata.Count);
        Assert.Equal("First", frontmatter.Metadata["author"]);
        Assert.Equal("Nested text", frontmatter.Metadata["Description"]);
    }

    [Theory]
    [MemberData(nameof(DuplicateMetadataEntries))]
    public void TryParse_DuplicateMetadata_KeepsFirstValueAndLogsWarning(
        string key, string duplicateKey, string value, string duplicateValue, string expected, string newline)
    {
        // Arrange
        string content = ("---\nname: test-skill\ndescription: Read files\nmetadata:\n" +
            $"  {key}: {value}\n  other: Preserved\n  {duplicateKey}: {duplicateValue}\n" +
            $"  {duplicateKey}: Third\n  tail: Retained\nlicense: MIT\n---\nBody.").Replace("\n", newline);
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.Equal("MIT", frontmatter.License);
        Assert.NotNull(frontmatter.Metadata);
        Assert.Equal(3, frontmatter.Metadata.Count);
        Assert.Equal(expected, frontmatter.Metadata[key]);
        Assert.Equal(expected, frontmatter.Metadata[duplicateKey]);
        Assert.Equal("Preserved", frontmatter.Metadata["other"]);
        Assert.Equal("Retained", frontmatter.Metadata["tail"]);
        Assert.Equal(key, Assert.Single(frontmatter.Metadata.Keys, k => string.Equals(k, key, StringComparison.OrdinalIgnoreCase)));
        VerifyDiagnostic(logger, LogLevel.Warning, $"duplicate metadata key '{duplicateKey}'; keeping the first value", Times.Exactly(2));
    }

    [Theory]
    [InlineData("''")]
    [InlineData("\"\"")]
    public void TryParse_EmptyQuotedOptionalValues_KeepExistingRepresentation(string value)
    {
        // Arrange
        string content = "---\nname: test-skill\ndescription: Read files\n" +
            $"license: {value}\ncompatibility: {value}\nallowed-tools: {value}\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert - empty-quote normalization belongs to the separate YAML conformance work.
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal(value, frontmatter.License);
        Assert.Equal(value, frontmatter.Compatibility);
        Assert.Equal(value, frontmatter.AllowedTools);
    }

    [Theory]
    [InlineData("|")]
    [InlineData("|-")]
    [InlineData("|+")]
    [InlineData(">")]
    [InlineData(">-")]
    [InlineData(">+")]
    public void TryParse_EmptyBlockBeforeAnotherField_ReturnsFalse(string value)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: {value}\n\nlicense: MIT\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
    }

    [Theory]
    [InlineData("")]
    [InlineData("No frontmatter here.")]
    [InlineData("Prefix.\n---\nname: test-skill\ndescription: Read files\n---\nBody.")]
    [InlineData("---\nname: test-skill\ndescription: Read files\nBody.")]
    public void TryParse_MissingFrontmatter_ReturnsFalseAndLogsError(string content)
    {
        // Arrange
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
        VerifyDiagnostic(logger, LogLevel.Error, "does not contain valid YAML frontmatter", Times.Once());
    }

    [Theory]
    [InlineData("description: Read files", "name")]
    [InlineData("name: test-skill", "description")]
    [InlineData("name:\ndescription: Read files", "name")]
    [InlineData("name: test-skill\ndescription:", "description")]
    [InlineData("name: BadName\ndescription: Read files", "name")]
    [InlineData("name: -leading-hyphen\ndescription: Read files", "name")]
    [InlineData("name: trailing-hyphen-\ndescription: Read files", "name")]
    [InlineData("name: has spaces\ndescription: Read files", "name")]
    [InlineData("name: consecutive--hyphens\ndescription: Read files", "name")]
    public void TryParse_InvalidRequiredField_ReturnsFalseAndLogsError(string fields, string field)
    {
        // Arrange
        string content = $"---\n{fields}\n---\nBody.";
        var logger = CreateLogger();

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, logger.Object, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
        VerifyDiagnostic(logger, LogLevel.Error, $"Skill {field}", Times.Once());
    }

    [Theory]
    [InlineData("name", 65)]
    [InlineData("description", 1025)]
    public void TryParse_RequiredFieldExceedsMaxLength_ReturnsFalse(string field, int length)
    {
        // Arrange
        string name = field == "name" ? new string('a', length) : "test-skill";
        string description = field == "description" ? new string('a', length) : "Read files";
        string content = $"---\nname: {name}\ndescription: {description}\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
    }

    [Theory]
    [InlineData("name")]
    [InlineData("description")]
    [InlineData("license")]
    [InlineData("compatibility")]
    [InlineData("metadata")]
    [InlineData("allowed-tools")]
    public void TryParse_DuplicateRecognizedField_ReturnsFalse(string field)
    {
        // Arrange
        string fields = field switch
        {
            "name" => "name: test-skill\nname: test-skill\ndescription: Read files",
            "description" => "name: test-skill\ndescription: Read files\ndescription: Read files",
            "metadata" => "name: test-skill\ndescription: Read files\nmetadata:\n  author: first\nmetadata:\n  version: 1.0",
            _ => $"name: test-skill\ndescription: Read files\n{field}: first\n{field}: second",
        };

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse($"---\n{fields}\n---\nBody.", SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
    }

    [Theory]
    [InlineData("name", "Name")]
    [InlineData("description", "Description")]
    [InlineData("license", "License")]
    [InlineData("compatibility", "Compatibility")]
    [InlineData("metadata", "Metadata")]
    [InlineData("allowed-tools", "Allowed-Tools")]
    public void TryParse_IncorrectlyCasedRecognizedField_ReturnsFalse(string field, string incorrectlyCasedField)
    {
        // Arrange
        string fields = field switch
        {
            "name" => $"{incorrectlyCasedField}: test-skill\ndescription: Read files",
            "description" => $"name: test-skill\n{incorrectlyCasedField}: Read files",
            "metadata" => $"name: test-skill\ndescription: Read files\n{incorrectlyCasedField}:\n  author: test",
            _ => $"name: test-skill\ndescription: Read files\n{incorrectlyCasedField}: value",
        };

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse($"---\n{fields}\n---\nBody.", SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
    }

    [Theory]
    [InlineData("'", "\n")]
    [InlineData("'", "\r\n")]
    [InlineData("\"", "\n")]
    [InlineData("\"", "\r\n")]
    public void TryParse_QuotedEmptyOptionalFields_RemainUnset(string quote, string newline)
    {
        // Arrange
        string content = ($"---\n{quote}metadata{quote}:\n{quote}name{quote}: test-skill\n" +
            $"{quote}description{quote}: Read files\n{quote}license{quote}:\n" +
            $"{quote}compatibility{quote}:\n{quote}allowed-tools{quote}:\n---\nBody.").Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("test-skill", frontmatter.Name);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.Null(frontmatter.Metadata);
        Assert.Null(frontmatter.License);
        Assert.Null(frontmatter.Compatibility);
        Assert.Null(frontmatter.AllowedTools);
    }

    [Theory]
    [InlineData("metadata", "\n")]
    [InlineData("metadata", "\r\n")]
    [InlineData("license", "\n")]
    [InlineData("license", "\r\n")]
    [InlineData("compatibility", "\n")]
    [InlineData("compatibility", "\r\n")]
    [InlineData("allowed-tools", "\n")]
    [InlineData("allowed-tools", "\r\n")]
    [InlineData("vendor-option", "\n")]
    [InlineData("vendor-option", "\r\n")]
    public void TryParse_EmptyInlineValue_DoesNotConsumeNextField(string field, string newline)
    {
        // Arrange
        string content = $"---\n{field}: \t\nname: test-skill\ndescription: Read files\n---\nBody.".Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("test-skill", frontmatter.Name);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.Null(frontmatter.License);
        Assert.Null(frontmatter.Compatibility);
        Assert.Null(frontmatter.AllowedTools);
    }

    [Theory]
    [InlineData("license", "\n")]
    [InlineData("license", "\r\n")]
    [InlineData("compatibility", "\n")]
    [InlineData("compatibility", "\r\n")]
    [InlineData("allowed-tools", "\n")]
    [InlineData("allowed-tools", "\r\n")]
    public void TryParse_EmptyOptionalScalarAtEnd_RemainsNull(string field, string newline)
    {
        // Arrange
        string content = $"---\nname: test-skill\ndescription: Read files\n{field}: \t\n---\nBody.".Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Null(frontmatter.License);
        Assert.Null(frontmatter.Compatibility);
        Assert.Null(frontmatter.AllowedTools);
    }

    [Theory]
    [InlineData("name:", "\n")]
    [InlineData("name:", "\r\n")]
    [InlineData("description:", "\n")]
    [InlineData("description:", "\r\n")]
    [InlineData("metadata:\nmetadata:", "\n")]
    [InlineData("metadata:\nmetadata:", "\r\n")]
    [InlineData("license:\nlicense: MIT", "\n")]
    [InlineData("license:\nlicense: MIT", "\r\n")]
    [InlineData("license: MIT\nlicense:", "\n")]
    [InlineData("license: MIT\nlicense:", "\r\n")]
    [InlineData("compatibility:\ncompatibility: Any runtime", "\n")]
    [InlineData("compatibility:\ncompatibility: Any runtime", "\r\n")]
    [InlineData("allowed-tools:\nallowed-tools: read", "\n")]
    [InlineData("allowed-tools:\nallowed-tools: read", "\r\n")]
    [InlineData("Metadata:", "\n")]
    [InlineData("Metadata:", "\r\n")]
    [InlineData("allowed-tools: read\nALLOWED-TOOLS:", "\n")]
    [InlineData("allowed-tools: read\nALLOWED-TOOLS:", "\r\n")]
    public void TryParse_EmptyInlineValue_DoesNotBypassKeyValidation(string fields, string newline)
    {
        // Arrange
        string content = $"---\n{fields}\nname: test-skill\ndescription: Read files\n---\nBody.".Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.False(result);
        Assert.Null(frontmatter);
    }

    [Theory]
    [InlineData("\n", false)]
    [InlineData("\r\n", false)]
    [InlineData("\n", true)]
    [InlineData("\r\n", true)]
    public void TryParse_NewlinesAndBom_ReturnsFrontmatter(string newline, bool bom)
    {
        // Arrange
        string content = (bom ? "\uFEFF" : "") + "---\nname: test-skill\ndescription: Read files\n---\nBody.".Replace("\n", newline);

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("test-skill", frontmatter.Name);
        Assert.Equal("Read files", frontmatter.Description);
        Assert.Null(frontmatter.License);
        Assert.Null(frontmatter.Compatibility);
        Assert.Null(frontmatter.AllowedTools);
        Assert.Null(frontmatter.Metadata);
    }

    [Fact]
    public void TryParse_AllOptionalFields_ReturnsFrontmatter()
    {
        // Arrange
        const string Content = "---\nname: test-skill\ndescription: Read files\nlicense: Apache-2.0\ncompatibility: Requires Python 3.10+\nallowed-tools: grep glob view\nmetadata:\n  org: 'contoso'\n  tier: \"premium\"\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(Content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("Apache-2.0", frontmatter.License);
        Assert.Equal("Requires Python 3.10+", frontmatter.Compatibility);
        Assert.Equal("grep glob view", frontmatter.AllowedTools);
        Assert.NotNull(frontmatter.Metadata);
        Assert.Equal("contoso", frontmatter.Metadata["org"]);
        Assert.Equal("premium", frontmatter.Metadata["tier"]);
    }

    [Theory]
    [InlineData("name", 64)]
    [InlineData("description", 1024)]
    public void TryParse_RequiredFieldAtMaxLength_ReturnsFrontmatter(string field, int length)
    {
        // Arrange
        string name = field == "name" ? new string('a', length) : "test-skill";
        string description = field == "description" ? new string('a', length) : "Read files";
        string content = $"---\nname: {name}\ndescription: {description}\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(content, SkillLocation, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal(name, frontmatter.Name);
        Assert.Equal(description, frontmatter.Description);
    }

    [Theory]
    [InlineData(@"C:\skills\other-skill\SKILL.md")]
    [InlineData("skill://other-skill/SKILL.md")]
    public void TryParse_LocationDiffersFromName_DoesNotValidateLocation(string location)
    {
        // Arrange
        const string Content = "---\nname: test-skill\ndescription: Read files\n---\nBody.";

        // Act
        bool result = AgentSkillFrontmatterParser.TryParse(Content, location, NullLogger.Instance, out var frontmatter);

        // Assert
        Assert.True(result);
        Assert.NotNull(frontmatter);
        Assert.Equal("test-skill", frontmatter.Name);
    }

    private static Mock<ILogger> CreateLogger()
    {
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        return logger;
    }

    private static void VerifyDiagnostic(Mock<ILogger> logger, LogLevel level, string diagnostic, Times times)
    {
        logger.Verify(
            l => l.Log(
                level,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((state, _) =>
                    state.ToString()!.IndexOf(SkillLocation, StringComparison.Ordinal) >= 0 &&
                    state.ToString()!.IndexOf(diagnostic, StringComparison.Ordinal) >= 0),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            times);
    }
}
