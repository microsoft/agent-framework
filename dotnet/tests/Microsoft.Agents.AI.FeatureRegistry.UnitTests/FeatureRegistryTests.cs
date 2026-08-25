// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace Microsoft.Agents.AI.FeatureRegistry.UnitTests;

/// <summary>
/// Validates the package-local .NET v1 feature index declarations against the Markdown registry.
/// </summary>
public sealed class FeatureRegistryTests
{
    private const string DotNetTableHeading = "## Index table — .NET (`agent-framework-dotnet`, version 1)";
    private static readonly Dictionary<int, string> s_externalRegistryEntries =
        new()
        {
            [67] = "durabletask",
            [68] = "azurefunctions",
        };

    private static readonly Dictionary<string, string> s_expectedOwnersById =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["core.agent"] = "Microsoft.Agents.AI",
            ["core.harness_agent"] = "Microsoft.Agents.AI.Harness",
            ["core.workflow"] = "Microsoft.Agents.AI.Workflows",
            ["core.tool_approval"] = "Microsoft.Agents.AI",
            ["core.chat_history_memory_provider"] = "Microsoft.Agents.AI",
            ["core.file_memory_provider"] = "Microsoft.Agents.AI",
            ["core.text_search_provider"] = "Microsoft.Agents.AI",
            ["core.file_access_provider"] = "Microsoft.Agents.AI",
            ["core.skills_provider"] = "Microsoft.Agents.AI",
            ["core.compaction_provider"] = "Microsoft.Agents.AI",
            ["core.todo_provider"] = "Microsoft.Agents.AI",
            ["core.agent_mode_provider"] = "Microsoft.Agents.AI",
            ["core.background_agents_provider"] = "Microsoft.Agents.AI",
            ["core.in_memory_history_provider"] = "Microsoft.Agents.AI.Abstractions",
            ["core.mcp"] = "Microsoft.Agents.AI.Mcp",
            ["core.file_skills_source"] = "Microsoft.Agents.AI",
            ["core.in_memory_skills_source"] = "Microsoft.Agents.AI",
            ["core.inline_skill"] = "Microsoft.Agents.AI",
            ["core.class_skill"] = "Microsoft.Agents.AI",
            ["core.mcp_skills_source"] = "Microsoft.Agents.AI.Mcp",
            ["orchestration.sequential"] = "Microsoft.Agents.AI.Workflows",
            ["orchestration.concurrent"] = "Microsoft.Agents.AI.Workflows",
            ["orchestration.group_chat"] = "Microsoft.Agents.AI.Workflows",
            ["orchestration.magentic"] = "Microsoft.Agents.AI.Workflows",
            ["orchestration.handoff"] = "Microsoft.Agents.AI.Workflows",
            ["foundry.chat_client"] = "Microsoft.Agents.AI.Foundry",
            ["foundry.agent"] = "Microsoft.Agents.AI.Foundry",
            ["foundry.memory"] = "Microsoft.Agents.AI.Foundry",
            ["foundry.evals"] = "Microsoft.Agents.AI.Foundry",
            ["foundry.toolbox"] = "Microsoft.Agents.AI.Foundry",
            ["foundry_hosting"] = "Microsoft.Agents.AI.Foundry.Hosting",
            ["openai"] = "Microsoft.Agents.AI.OpenAI",
            ["anthropic"] = "Microsoft.Agents.AI.Anthropic",
            ["copilotstudio"] = "Microsoft.Agents.AI.CopilotStudio",
            ["github_copilot"] = "Microsoft.Agents.AI.GitHub.Copilot",
            ["azure_cosmos"] = "Microsoft.Agents.AI.CosmosNoSql",
            ["valkey"] = "Microsoft.Agents.AI.Valkey",
            ["mem0"] = "Microsoft.Agents.AI.Mem0",
            ["purview"] = "Microsoft.Agents.AI.Purview",
            ["a2a"] = "Microsoft.Agents.AI.A2A",
            ["hosting.ag_ui"] = "Microsoft.Agents.AI.Hosting.AGUI.AspNetCore",
            ["devui"] = "Microsoft.Agents.AI.DevUI",
            ["declarative.agent"] = "Microsoft.Agents.AI.Declarative",
            ["declarative.workflow"] = "Microsoft.Agents.AI.Workflows.Declarative",
            ["tools.shell"] = "Microsoft.Agents.AI.Tools.Shell",
            ["hyperlight"] = "Microsoft.Agents.AI.Hyperlight",
            ["hosting.agent"] = "Microsoft.Agents.AI.Hosting",
            ["local_codeact"] = "Microsoft.Agents.AI.LocalCodeAct",
            ["hosting.a2a"] = "Microsoft.Agents.AI.Hosting.A2A.AspNetCore",
            ["hosting.openai"] = "Microsoft.Agents.AI.Hosting.OpenAI",
        };

    /// <summary>
    /// Ensures the .NET v1 registry and all in-repository package-local declarations have exact parity.
    /// </summary>
    [Fact]
    public void DotNetV1DeclarationsMatchRegistry()
    {
        // Arrange
        string repositoryRoot = FindRepositoryRoot();
        List<RegistryEntry> registry = ReadDotNetV1Registry(repositoryRoot);
        var parsingErrors = new List<string>();
        List<FeatureDeclaration> declarations = ReadFeatureDeclarations(repositoryRoot, parsingErrors);

        // Act
        List<string> validationErrors = ValidateRegistry(registry, declarations, parsingErrors);

        // Assert
        AssertNoErrors(validationErrors);
    }

    /// <summary>
    /// Ensures registry/member matching remains insensitive to acronym casing while preserving ordinal semantics.
    /// </summary>
    [Fact]
    public void RegistryKeyNormalizationIsAcronymSafe()
    {
        // Arrange
        (string RegistryId, string MemberName)[] examples =
        [
            ("hosting.ag_ui", "HostingAGUI"),
            ("github_copilot", "GitHubCopilot"),
            ("a2a", "A2A"),
        ];

        // Act
        bool allMatch = examples.All(
            example => StringComparer.OrdinalIgnoreCase.Equals(
                NormalizeRegistryKey(example.RegistryId),
                NormalizeRegistryKey(example.MemberName)));

        // Assert
        Assert.True(allMatch);
    }

    /// <summary>
    /// Ensures every declaration is referenced from its owning package's activation code.
    /// </summary>
    /// <remarks>
    /// This prevents declaration parity from being misreported as activation coverage.
    /// </remarks>
    [Fact]
    public void FeatureIndexesHaveActivationReferences()
    {
        // Arrange
        string repositoryRoot = FindRepositoryRoot();
        var parsingErrors = new List<string>();
        List<FeatureDeclaration> declarations = ReadFeatureDeclarations(repositoryRoot, parsingErrors);

        // Act
        string[] missingReferences = FindMissingActivationReferences(repositoryRoot, declarations);

        // Assert
        AssertNoErrors(parsingErrors.Concat(missingReferences).ToArray());
    }

    private static List<string> ValidateRegistry(
        List<RegistryEntry> registry,
        List<FeatureDeclaration> declarations,
        List<string> parsingErrors)
    {
        var errors = new List<string>(parsingErrors);

        foreach (RegistryEntry entry in registry.Where(entry => entry.Index is < 0 or > 127))
        {
            errors.Add($"Registry entry '{entry.Id}' has out-of-range index {entry.Index}.");
        }

        foreach (IGrouping<int, RegistryEntry> overlap in registry.GroupBy(entry => entry.Index).Where(group => group.Count() > 1))
        {
            errors.Add($"Registry index {overlap.Key} is assigned to: {string.Join(", ", overlap.Select(entry => entry.Id))}.");
        }

        foreach (IGrouping<string, RegistryEntry> duplicateKey in registry
            .GroupBy(entry => NormalizeRegistryKey(entry.Id), StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() > 1))
        {
            errors.Add($"Normalized registry key '{duplicateKey.Key}' is not unique: {string.Join(", ", duplicateKey.Select(entry => entry.Id))}.");
        }

        Dictionary<int, RegistryEntry> registryByIndex = registry
            .GroupBy(entry => entry.Index)
            .Where(group => group.Count() == 1)
            .ToDictionary(group => group.Key, group => group.Single());

        ValidateExternalEntries(registryByIndex, declarations, errors);
        ValidateOwnershipMap(registry, errors);

        foreach (FeatureDeclaration declaration in declarations)
        {
            if (declaration.Index is < 0 or > 127)
            {
                errors.Add($"{declaration.FilePath}: '{declaration.MemberName}' has out-of-range index {declaration.Index}.");
                continue;
            }

            if (!registryByIndex.TryGetValue(declaration.Index, out RegistryEntry? registryEntry))
            {
                errors.Add($"{declaration.FilePath}: '{declaration.MemberName}' uses unassigned index {declaration.Index}.");
                continue;
            }

            if (!StringComparer.OrdinalIgnoreCase.Equals(
                NormalizeRegistryKey(declaration.MemberName),
                NormalizeRegistryKey(registryEntry.Id)))
            {
                errors.Add(
                    $"{declaration.FilePath}: index {declaration.Index} declares '{declaration.MemberName}', " +
                    $"but the registry id is '{registryEntry.Id}'.");
            }

            if (s_expectedOwnersById.TryGetValue(registryEntry.Id, out string? expectedOwner) &&
                !StringComparer.Ordinal.Equals(declaration.Owner, expectedOwner))
            {
                errors.Add(
                    $"Registry id '{registryEntry.Id}' ({declaration.Index}) is declared by '{declaration.Owner}', " +
                    $"but ownership is assigned to '{expectedOwner}'.");
            }
        }

        foreach (IGrouping<int, FeatureDeclaration> overlap in declarations
            .GroupBy(declaration => declaration.Index)
            .Where(group => group.Count() > 1))
        {
            errors.Add(
                $"Feature index {overlap.Key} overlaps across declarations: " +
                string.Join(", ", overlap.Select(declaration => $"{declaration.Owner}.{declaration.MemberName}")) + ".");
        }

        foreach (RegistryEntry entry in registry.Where(entry => !s_externalRegistryEntries.ContainsKey(entry.Index)))
        {
            FeatureDeclaration[] matches = declarations
                .Where(declaration =>
                    declaration.Index == entry.Index &&
                    StringComparer.OrdinalIgnoreCase.Equals(
                        NormalizeRegistryKey(declaration.MemberName),
                        NormalizeRegistryKey(entry.Id)))
                .ToArray();

            if (matches.Length != 1)
            {
                errors.Add($"Registry id '{entry.Id}' ({entry.Index}) has {matches.Length} matching in-repository declarations; expected 1.");
            }
        }

        return errors;
    }

    private static void ValidateExternalEntries(
        Dictionary<int, RegistryEntry> registryByIndex,
        List<FeatureDeclaration> declarations,
        List<string> errors)
    {
        foreach ((int index, string id) in s_externalRegistryEntries)
        {
            if (!registryByIndex.TryGetValue(index, out RegistryEntry? entry) ||
                !StringComparer.Ordinal.Equals(entry.Id, id))
            {
                errors.Add($"External registry exception {index} must remain assigned to '{id}'.");
            }

            if (declarations.Any(declaration => declaration.Index == index))
            {
                errors.Add($"External registry exception '{id}' ({index}) must not have an in-repository declaration.");
            }
        }
    }

    private static void ValidateOwnershipMap(List<RegistryEntry> registry, List<string> errors)
    {
        RegistryEntry[] localEntries = registry
            .Where(entry => !s_externalRegistryEntries.ContainsKey(entry.Index))
            .ToArray();

        foreach (RegistryEntry entry in localEntries.Where(entry => !s_expectedOwnersById.ContainsKey(entry.Id)))
        {
            errors.Add($"Registry id '{entry.Id}' ({entry.Index}) does not have an in-repository owner assignment.");
        }

        HashSet<string> localIds = localEntries.Select(entry => entry.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string extraId in s_expectedOwnersById.Keys.Where(id => !localIds.Contains(id)))
        {
            errors.Add($"Ownership map contains '{extraId}', which is not a local .NET v1 registry id.");
        }
    }

    private static List<RegistryEntry> ReadDotNetV1Registry(string repositoryRoot)
    {
        string registryPath = Path.Combine(repositoryRoot, "docs", "specs", "feature-usage-bit-registry.md");
        var entries = new List<RegistryEntry>();
        bool inDotNetTable = false;

        foreach (string line in File.ReadLines(registryPath))
        {
            if (!inDotNetTable)
            {
                inDotNetTable = StringComparer.Ordinal.Equals(line, DotNetTableHeading);
                continue;
            }

            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                break;
            }

            string[] columns = line.Split('|');
            if (columns.Length < 4 ||
                !int.TryParse(columns[1].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out int index))
            {
                continue;
            }

            string id = columns[2].Trim().Trim('`');
            entries.Add(new RegistryEntry(index, id));
        }

        if (!inDotNetTable || entries.Count == 0)
        {
            throw new InvalidDataException($"Could not parse the .NET v1 table from '{registryPath}'.");
        }

        return entries;
    }

    private static List<FeatureDeclaration> ReadFeatureDeclarations(
        string repositoryRoot,
        List<string> errors)
    {
        string sourceRoot = Path.Combine(repositoryRoot, "dotnet", "src");
        var declarations = new List<FeatureDeclaration>();

        foreach (string filePath in Directory.EnumerateFiles(sourceRoot, "*.cs", SearchOption.AllDirectories)
            .Where(path => !IsBuildOutput(path)))
        {
            string source = File.ReadAllText(filePath);
            if (!source.Contains("FeatureIndex", StringComparison.Ordinal))
            {
                continue;
            }

            CompilationUnitSyntax root = CSharpSyntaxTree.ParseText(source).GetCompilationUnitRoot();
            EnumDeclarationSyntax[] enums = root.DescendantNodes()
                .OfType<EnumDeclarationSyntax>()
                .Where(declaration => StringComparer.Ordinal.Equals(declaration.Identifier.ValueText, "FeatureIndex"))
                .ToArray();

            foreach (EnumDeclarationSyntax featureIndex in enums)
            {
                if (!featureIndex.Modifiers.Any(SyntaxKind.InternalKeyword))
                {
                    errors.Add($"{filePath}: FeatureIndex must be internal.");
                }

                string owner = GetProjectOwner(sourceRoot, filePath);
                foreach (EnumMemberDeclarationSyntax member in featureIndex.Members)
                {
                    if (member.EqualsValue?.Value is not LiteralExpressionSyntax literal ||
                        literal.Token.Value is not int index)
                    {
                        errors.Add($"{filePath}: '{member.Identifier.ValueText}' must have an explicit integer value.");
                        continue;
                    }

                    declarations.Add(new FeatureDeclaration(owner, member.Identifier.ValueText, index, filePath));
                }
            }
        }

        return declarations;
    }

    private static string[] FindMissingActivationReferences(
        string repositoryRoot,
        List<FeatureDeclaration> declarations)
    {
        string sourceRoot = Path.Combine(repositoryRoot, "dotnet", "src");
        var references = new HashSet<(string Owner, string MemberName)>();

        foreach (string filePath in Directory.EnumerateFiles(sourceRoot, "*.cs", SearchOption.AllDirectories)
            .Where(path => !IsBuildOutput(path)))
        {
            CompilationUnitSyntax root = CSharpSyntaxTree.ParseText(File.ReadAllText(filePath)).GetCompilationUnitRoot();
            string owner = GetProjectOwner(sourceRoot, filePath);

            foreach (MemberAccessExpressionSyntax memberAccess in root.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
            {
                if (IsFeatureIndexExpression(memberAccess.Expression))
                {
                    references.Add((owner, memberAccess.Name.Identifier.ValueText));
                }
            }
        }

        return declarations
            .Where(declaration => !references.Contains((declaration.Owner, declaration.MemberName)))
            .Select(declaration =>
                $"{declaration.Owner}.{declaration.MemberName} ({declaration.Index}) has no Stage 2 activation reference.")
            .ToArray();
    }

    private static bool IsFeatureIndexExpression(ExpressionSyntax expression)
        => expression is IdentifierNameSyntax identifierName
            ? StringComparer.Ordinal.Equals(identifierName.Identifier.ValueText, "FeatureIndex")
            : expression is MemberAccessExpressionSyntax memberAccess &&
              StringComparer.Ordinal.Equals(memberAccess.Name.Identifier.ValueText, "FeatureIndex");

    private static string GetProjectOwner(string sourceRoot, string filePath)
    {
        string relativePath = Path.GetRelativePath(sourceRoot, filePath);
        int separatorIndex = relativePath.IndexOf(Path.DirectorySeparatorChar);
        return separatorIndex < 0 ? string.Empty : relativePath[..separatorIndex];
    }

    private static bool IsBuildOutput(string path)
        => path.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase) ||
           path.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase);

    private static string NormalizeRegistryKey(string value)
        => string.Concat(value.Where(character => character is not '.' and not '_'));

    private static string FindRepositoryRoot()
    {
        for (DirectoryInfo? directory = new(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "CODE_OF_CONDUCT.md")) &&
                Directory.Exists(Path.Combine(directory.FullName, "dotnet", "src")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException($"Could not find the repository root from '{AppContext.BaseDirectory}'.");
    }

    private static void AssertNoErrors(IReadOnlyCollection<string> errors)
    {
        if (errors.Count > 0)
        {
            Assert.Fail(Environment.NewLine + string.Join(Environment.NewLine, errors));
        }
    }

    private sealed record RegistryEntry(int Index, string Id);

    private sealed record FeatureDeclaration(string Owner, string MemberName, int Index, string FilePath);
}
