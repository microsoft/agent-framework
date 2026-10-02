// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Tests for <see cref="PostgresMemoryStore"/> configuration.
/// </summary>
public sealed class PostgresMemoryStoreTests
{
    [Fact]
    public void Options_DefaultToHnsw()
    {
        // Arrange and act
        var options = new PostgresMemoryClientOptions();

        // Assert
        Assert.Equal(PostgresMemoryVectorIndexKind.Hnsw, options.VectorIndexKind);
    }

    [Theory]
    [InlineData(PostgresMemoryVectorIndexKind.Hnsw, "USING hnsw", "DROP INDEX IF EXISTS \"memory\".\"memory_diskann\"")]
    [InlineData(PostgresMemoryVectorIndexKind.DiskAnn, "USING diskann", "DROP INDEX IF EXISTS \"memory\".\"memory_hnsw\"")]
    public async Task Store_GeneratesSelectedVectorIndexSqlAsync(
        PostgresMemoryVectorIndexKind indexKind,
        string expectedCreateClause,
        string expectedDropClause)
    {
        // Arrange
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        var store = new PostgresMemoryStore(
            dataSource,
            new PostgresMemoryClientOptions
            {
                Schema = "memory",
                VectorIndexKind = indexKind,
            });

        // Act
        var sql = store.GetVectorIndexSql("\"memory\".\"items\"", "memory_hnsw", "memory_diskann");

        // Assert
        Assert.Contains(expectedCreateClause, sql, StringComparison.Ordinal);
        Assert.Contains(expectedDropClause, sql, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Store_RejectsUnknownVectorIndexKindAsync()
    {
        // Arrange
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        var options = new PostgresMemoryClientOptions
        {
            VectorIndexKind = (PostgresMemoryVectorIndexKind)int.MaxValue,
        };

        // Act and assert
        _ = Assert.Throws<ArgumentOutOfRangeException>(() => new PostgresMemoryStore(dataSource, options));
    }
}