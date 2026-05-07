// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

/// <summary>
/// Executor for the <see cref="HttpRequestAction"/> action.
/// Dispatches the request through the configured <see cref="IHttpRequestHandler"/> and assigns
/// the response body and headers to the declared property paths.
/// </summary>
internal sealed class HttpRequestExecutor(
    HttpRequestAction model,
    IHttpRequestHandler httpRequestHandler,
    ResponseAgentProvider agentProvider,
    WorkflowFormulaState state) :
    DeclarativeActionExecutor<HttpRequestAction>(model, state)
{
    /// <inheritdoc/>
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string method = this.GetMethod();
        string url = this.GetUrl();
        Dictionary<string, string>? headers = this.GetHeaders();
        Dictionary<string, string>? queryParameters = this.GetQueryParameters();
        (string? body, string? contentType) = this.GetBody();
        TimeSpan? timeout = this.GetTimeout();
        string? conversationId = this.GetConversationId();
        string? connectionName = this.GetConnectionName();

        HttpRequestInfo requestInfo = new()
        {
            Method = method,
            Url = url,
            Headers = headers,
            QueryParameters = queryParameters,
            Body = body,
            BodyContentType = contentType,
            Timeout = timeout,
            ConnectionName = connectionName,
        };

        HttpRequestResult result;
        try
        {
            result = await httpRequestHandler.SendAsync(requestInfo, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw this.Exception($"HTTP request to '{url}' timed out.");
        }
        catch (Exception exception) when (exception is not DeclarativeActionException)
        {
            throw this.Exception($"HTTP request to '{url}' failed: {exception.Message}", exception);
        }

        if (result.IsSuccessStatusCode)
        {
            await this.AssignResponseAsync(context, result.Body).ConfigureAwait(false);
            await this.AssignResponseHeadersAsync(context, result.Headers).ConfigureAwait(false);
            await this.AddResponseToConversationAsync(conversationId, result.Body, cancellationToken).ConfigureAwait(false);
            return default;
        }

        // Non-success status code - throw.
        // Also publish response headers for diagnostic purposes.
        await this.AssignResponseHeadersAsync(context, result.Headers).ConfigureAwait(false);

        string bodyPreview = FormatBodyForDiagnostics(result.Body);
        string message = bodyPreview.Length == 0
            ? $"HTTP request to '{url}' failed with status code {result.StatusCode}."
            : $"HTTP request to '{url}' failed with status code {result.StatusCode}. Body: '{bodyPreview}'";

        throw this.Exception(message);
    }

    // Response bodies can echo secrets (tokens, PII) and may be very large (multi-MB HTML error pages).
    // Exception messages are often logged and persisted, so we clip the body to bound both exposure
    // and message size. Full bodies are still available via the success path (assigned to Response).
    private const int MaxBodyDiagnosticLength = 256;
    private const string BodyTruncationSuffix = " \u2026 [truncated]";

    private static string FormatBodyForDiagnostics(string? body)
    {
        if (string.IsNullOrEmpty(body))
        {
            return string.Empty;
        }

        int sourceLen = body!.Length;
        bool truncated = sourceLen > MaxBodyDiagnosticLength;
        int copyLen = truncated ? MaxBodyDiagnosticLength : sourceLen;
        int finalLen = copyLen + (truncated ? BodyTruncationSuffix.Length : 0);

        // Size the buffer for the final string so we only allocate once for the chars
        // and once for the string itself. For a 10 KB error body we touch 256 chars instead of 10,000.
        char[] buffer = new char[finalLen];
        for (int i = 0; i < copyLen; i++)
        {
            char c = body[i];
            buffer[i] = c is '\r' or '\n' or '\t' ? ' ' : c;
        }

        if (truncated)
        {
            BodyTruncationSuffix.CopyTo(0, buffer, copyLen, BodyTruncationSuffix.Length);
        }

        return new string(buffer);
    }

    private async ValueTask AddResponseToConversationAsync(string? conversationId, string? responseBody, CancellationToken cancellationToken)
    {
        if (conversationId is null || string.IsNullOrEmpty(responseBody))
        {
            return;
        }

        ChatMessage message = new(ChatRole.Assistant, responseBody);
        await agentProvider.CreateMessageAsync(conversationId, message, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask AssignResponseAsync(IWorkflowContext context, string? responseBody)
    {
        if (this.Model.Response is not { Path: { } responsePath })
        {
            return;
        }

        await this.AssignAsync(responsePath, ParseResponseBody(responseBody), context).ConfigureAwait(false);
    }

    private async ValueTask AssignResponseHeadersAsync(IWorkflowContext context, IReadOnlyDictionary<string, IReadOnlyList<string>>? responseHeaders)
    {
        if (this.Model.ResponseHeaders is not { Path: { } headersPath })
        {
            return;
        }

        if (responseHeaders is null || responseHeaders.Count == 0)
        {
            await this.AssignAsync(headersPath, FormulaValue.NewBlank(), context).ConfigureAwait(false);
            return;
        }

        // Flatten multi-value headers by joining with commas (standard HTTP header folding).
        Dictionary<string, object?> flattened = new(StringComparer.OrdinalIgnoreCase);
        foreach (KeyValuePair<string, IReadOnlyList<string>> header in responseHeaders)
        {
            flattened[header.Key] = string.Join(",", header.Value);
        }

        await this.AssignAsync(headersPath, flattened.ToFormula(), context).ConfigureAwait(false);
    }

    private static FormulaValue ParseResponseBody(string? responseBody)
    {
        if (string.IsNullOrEmpty(responseBody))
        {
            return FormulaValue.NewBlank();
        }

        // Attempt to parse as JSON so records/tables are exposed naturally to the workflow.
        try
        {
            using JsonDocument jsonDocument = JsonDocument.Parse(responseBody);

            object? parsedValue = jsonDocument.RootElement.ValueKind switch
            {
                JsonValueKind.Object => jsonDocument.ParseRecord(VariableType.RecordType),
                JsonValueKind.Array => jsonDocument.ParseList(jsonDocument.RootElement.GetListTypeFromJson()),
                JsonValueKind.String => jsonDocument.RootElement.GetString(),
                JsonValueKind.Number => jsonDocument.RootElement.TryGetInt64(out long l)
                    ? l
                    : jsonDocument.RootElement.GetDouble(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                JsonValueKind.Null => null,
                _ => responseBody,
            };

            return parsedValue.ToFormula();
        }
        catch (JsonException)
        {
            // Not valid JSON — return the raw string.
            return FormulaValue.New(responseBody);
        }
    }

    private string GetMethod()
    {
        EnumExpression<HttpMethodTypeWrapper>? methodExpression = this.Model.Method;
        if (methodExpression is null)
        {
            return "GET";
        }

        HttpMethodTypeWrapper wrapper = this.Evaluator.GetValue(methodExpression).Value;
        return !string.IsNullOrEmpty(wrapper.UnknownValue) ? wrapper.UnknownValue! : wrapper.Value.ToString().ToUpperInvariant();
    }

    private string GetUrl() =>
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.Model.Url,
                $"{nameof(this.Model)}.{nameof(this.Model.Url)}")).Value;

    private Dictionary<string, string>? GetHeaders()
    {
        if (this.Model.Headers is null || this.Model.Headers.Count == 0)
        {
            return null;
        }

        Dictionary<string, string> result = new(StringComparer.OrdinalIgnoreCase);
        foreach (KeyValuePair<string, StringExpression> header in this.Model.Headers)
        {
            string value = this.Evaluator.GetValue(header.Value).Value;
            if (!string.IsNullOrEmpty(value))
            {
                result[header.Key] = value;
            }
        }

        return result.Count == 0 ? null : result;
    }

    private (string? Body, string? ContentType) GetBody()
    {
        switch (this.Model.Body)
        {
            case null:
            case NoRequestContent:
                return (null, null);

            case JsonRequestContent jsonContent when jsonContent.Content is not null:
            {
                FormulaValue formula = this.Evaluator.GetValue(jsonContent.Content).Value.ToFormula();
                string json = formula.ToJson().ToJsonString();
                return (json, "application/json");
            }

            case RawRequestContent rawContent:
            {
                string? content = rawContent.Content is null
                        ? null
                        : this.Evaluator.GetValue(rawContent.Content).Value;

                string? contentType = rawContent.ContentType is null
                        ? null
                        : this.Evaluator.GetValue(rawContent.ContentType).Value;

                return (content, string.IsNullOrEmpty(contentType) ? null : contentType);
            }

            default:
                return (null, null);
        }
    }

    private TimeSpan? GetTimeout()
    {
        if (this.Model.RequestTimeoutInMilliseconds is null || this.Model.RequestTimeoutInMillisecondsIsDefaultValue)
        {
            return null;
        }

        long value = this.Evaluator.GetValue(this.Model.RequestTimeoutInMilliseconds).Value;
        return value > 0 ? TimeSpan.FromMilliseconds(value) : null;
    }

    private Dictionary<string, string>? GetQueryParameters()
    {
        if (this.Model.QueryParameters is null || this.Model.QueryParameters.Count == 0)
        {
            return null;
        }

        Dictionary<string, string> result = new(StringComparer.Ordinal);
        foreach (KeyValuePair<string, ValueExpression> parameter in this.Model.QueryParameters)
        {
            if (string.IsNullOrEmpty(parameter.Key) || parameter.Value is null)
            {
                continue;
            }

            object? rawValue = this.Evaluator.GetValue(parameter.Value).Value.ToObject();
            string? formatted = FormatQueryValue(rawValue);
            if (formatted is not null)
            {
                result[parameter.Key] = formatted;
            }
        }

        return result.Count == 0 ? null : result;
    }

    private static string? FormatQueryValue(object? value) =>
        value switch
        {
            null => null,
            string s => s,
            bool b => b ? "true" : "false",
            IFormattable formattable => formattable.ToString(null, System.Globalization.CultureInfo.InvariantCulture),
            _ => value.ToString(),
        };

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        string value = this.Evaluator.GetValue(this.Model.ConversationId).Value;
        return value.Length == 0 ? null : value;
    }

    private string? GetConnectionName()
    {
        RemoteConnection? connection = this.Model.Connection;
        if (connection is null)
        {
            return null;
        }

        string? name = connection.Name is null
            ? null
            : this.Evaluator.GetValue(connection.Name).Value;

        return string.IsNullOrEmpty(name) ? null : name;
    }
}
