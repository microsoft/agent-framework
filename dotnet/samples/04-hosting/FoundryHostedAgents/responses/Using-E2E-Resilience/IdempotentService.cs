// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Hosts the SQLite-backed operation service used by the resilience demonstration.
/// </summary>
/// <remarks>
/// <para>
/// For demonstration purposes only. This service and its client should not be used as-is in production.
/// The service runs in a separate process so its operation records survive the hosted workflow process being replaced.
/// </para>
/// <para>
/// Recovery may execute an unconfirmed workflow step again. The same scope and operation ID return the stored result
/// instead of adding another row. Reusing the result prevents a repeated service effect, not repeated stream text.
/// The database insert is the simulated effect; this does not make an external email or payment call transactional.
/// </para>
/// </remarks>
internal static class IdempotentService
{
    /// <summary>
    /// Runs the service when this executable is started with <c>--idempotent-service</c>.
    /// </summary>
    /// <param name="args">Host arguments after removing <c>--idempotent-service</c>.</param>
    public static async Task RunAsync(string[] args)
    {
        string databasePath = System.Environment.GetEnvironmentVariable("IDEMPOTENT_SERVICE_DATABASE_PATH")
            ?? Path.Combine(AppContext.BaseDirectory, "operations.db");
        var store = new SqliteOperationStore(databasePath);

        var builder = WebApplication.CreateBuilder(args);
        builder.Services.AddSingleton(store);

        await using var app = builder.Build();
        app.MapGet("/readiness", () => Results.Ok());

        app.MapPost("/operations/{scope}/{operationId:int}",
            async (
                string scope,
                int operationId,
                SqliteOperationStore operationStore,
                CancellationToken cancellationToken) =>
            {
                OperationResult operation = await operationStore.ExecuteAsync(scope, operationId, cancellationToken);
                return Results.Ok(operation);
            });

        app.MapGet("/operations/{scope}/count",
            async (string scope, SqliteOperationStore operationStore, CancellationToken cancellationToken)
                => Results.Ok(await operationStore.GetCountAsync(scope, cancellationToken)));

        await app.RunAsync();
    }

    private sealed record OperationResult(string Result, bool Created);

    private sealed class SqliteOperationStore
    {
        private readonly string _connectionString;

        public SqliteOperationStore(string databasePath)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(databasePath))!);
            this._connectionString = new SqliteConnectionStringBuilder
            {
                DataSource = databasePath,
            }.ToString();

            using var connection = new SqliteConnection(this._connectionString);
            connection.Open();
            using SqliteCommand command = connection.CreateCommand();
            command.CommandText =
                """
                CREATE TABLE IF NOT EXISTS operations (
                    scope TEXT NOT NULL,
                    operation_id INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    PRIMARY KEY (scope, operation_id)
                );
                """;
            command.ExecuteNonQuery();
        }

        public async Task<OperationResult> ExecuteAsync(string scope, int operationId, CancellationToken cancellationToken)
        {
            string result = operationId.ToString(CultureInfo.InvariantCulture);
            await using var connection = new SqliteConnection(this._connectionString);
            await connection.OpenAsync(cancellationToken);

            await using SqliteCommand insert = connection.CreateCommand();
            insert.CommandText =
                """
                INSERT OR IGNORE INTO operations (scope, operation_id, result)
                VALUES ($scope, $operationId, $result);
                """;
            insert.Parameters.AddWithValue("$scope", scope);
            insert.Parameters.AddWithValue("$operationId", operationId);
            insert.Parameters.AddWithValue("$result", result);
            bool created = await insert.ExecuteNonQueryAsync(cancellationToken) == 1;
            if (created)
            {
                Console.WriteLine($"Operation {scope}/{operationId} executed.");
                return new(result, Created: true);
            }

            await using SqliteCommand select = connection.CreateCommand();
            select.CommandText =
                """
                SELECT result
                FROM operations
                WHERE scope = $scope AND operation_id = $operationId;
                """;
            select.Parameters.AddWithValue("$scope", scope);
            select.Parameters.AddWithValue("$operationId", operationId);
            string storedResult = (string?)await select.ExecuteScalarAsync(cancellationToken)
                ?? throw new InvalidOperationException($"Operation {scope}/{operationId} exists without a stored result.");
            Console.WriteLine($"Duplicate operation {scope}/{operationId} ignored.");
            return new(storedResult, Created: false);
        }

        public async Task<int> GetCountAsync(string scope, CancellationToken cancellationToken)
        {
            await using var connection = new SqliteConnection(this._connectionString);
            await connection.OpenAsync(cancellationToken);
            await using SqliteCommand command = connection.CreateCommand();
            command.CommandText =
                """
                SELECT COUNT(*)
                FROM operations
                WHERE scope = $scope;
                """;
            command.Parameters.AddWithValue("$scope", scope);
            return Convert.ToInt32(await command.ExecuteScalarAsync(cancellationToken), CultureInfo.InvariantCulture);
        }
    }
}
