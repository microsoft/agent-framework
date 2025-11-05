// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Extension methods for converting ItemParam (input) to ItemResource (output).
/// </summary>
internal static class ItemParamExtensions
{
    /// <summary>
    /// Converts an ItemParam (input model) to an ItemResource (output model) by adding server-generated fields.
    /// </summary>
    /// <param name="param">The input item parameter.</param>
    /// <param name="idGenerator">The ID generator to use for creating item IDs.</param>
    /// <returns>An ItemResource with a generated ID.</returns>
    public static ItemResource ToItemResource(this ItemParam param, IdGenerator idGenerator)
    {
        ArgumentNullException.ThrowIfNull(param);
        ArgumentNullException.ThrowIfNull(idGenerator);

        string generatedId = idGenerator.GenerateMessageId();

        return param switch
        {
            ResponsesUserMessageItemParam userMessageParam => new ResponsesUserMessageItemResource
            {
                Id = generatedId,
                Content = userMessageParam.Content.ToItemContents(),
                Status = ResponsesMessageItemResourceStatus.Completed
            },
            ResponsesSystemMessageItemParam systemMessageParam => new ResponsesSystemMessageItemResource
            {
                Id = generatedId,
                Content = systemMessageParam.Content.ToItemContents(),
                Status = ResponsesMessageItemResourceStatus.Completed
            },
            ResponsesAssistantMessageItemParam assistantMessageParam => new ResponsesAssistantMessageItemResource
            {
                Id = generatedId,
                Content = assistantMessageParam.Content.ToItemContents(),
                Status = ResponsesMessageItemResourceStatus.Completed
            },
            ResponsesDeveloperMessageItemParam developerMessageParam => new ResponsesDeveloperMessageItemResource
            {
                Id = generatedId,
                Content = developerMessageParam.Content.ToItemContents(),
                Status = ResponsesMessageItemResourceStatus.Completed
            },
            FunctionToolCallItemParam functionCallParam => new FunctionToolCallItemResource
            {
                Id = generatedId,
                Name = functionCallParam.Name,
                CallId = functionCallParam.CallId,
                Arguments = functionCallParam.Arguments,
                Status = FunctionToolCallItemResourceStatus.Completed
            },
            FunctionToolCallOutputItemParam functionOutputParam => new FunctionToolCallOutputItemResource
            {
                Id = generatedId,
                CallId = functionOutputParam.CallId,
                Output = functionOutputParam.Output
            },
            FileSearchToolCallItemParam fileSearchParam => new FileSearchToolCallItemResource
            {
                Id = generatedId,
                Queries = fileSearchParam.Queries,
                Results = fileSearchParam.Results
            },
            ComputerToolCallItemParam computerCallParam => new ComputerToolCallItemResource
            {
                Id = generatedId,
                CallId = computerCallParam.CallId,
                Action = computerCallParam.Action,
                PendingSafetyChecks = computerCallParam.PendingSafetyChecks
            },
            ComputerToolCallOutputItemParam computerOutputParam => new ComputerToolCallOutputItemResource
            {
                Id = generatedId,
                CallId = computerOutputParam.CallId,
                AcknowledgedSafetyChecks = computerOutputParam.AcknowledgedSafetyChecks,
                Output = computerOutputParam.Output
            },
            WebSearchToolCallItemParam webSearchParam => new WebSearchToolCallItemResource
            {
                Id = generatedId,
                Action = webSearchParam.Action
            },
            ReasoningItemParam reasoningParam => new ReasoningItemResource
            {
                Id = generatedId,
                EncryptedContent = reasoningParam.EncryptedContent,
                Summary = reasoningParam.Summary
            },
            ItemReferenceItemParam => new ItemReferenceItemResource
            {
                Id = generatedId
            },
            ImageGenerationToolCallItemParam imageGenParam => new ImageGenerationToolCallItemResource
            {
                Id = generatedId,
                Result = imageGenParam.Result
            },
            CodeInterpreterToolCallItemParam codeInterpreterParam => new CodeInterpreterToolCallItemResource
            {
                Id = generatedId,
                ContainerId = codeInterpreterParam.ContainerId,
                Code = codeInterpreterParam.Code,
                Outputs = codeInterpreterParam.Outputs
            },
            LocalShellToolCallItemParam localShellParam => new LocalShellToolCallItemResource
            {
                Id = generatedId,
                CallId = localShellParam.CallId,
                Action = localShellParam.Action
            },
            LocalShellToolCallOutputItemParam localShellOutputParam => new LocalShellToolCallOutputItemResource
            {
                Id = generatedId,
                Output = localShellOutputParam.Output
            },
            MCPListToolsItemParam mcpListToolsParam => new MCPListToolsItemResource
            {
                Id = generatedId,
                ServerLabel = mcpListToolsParam.ServerLabel,
                Tools = mcpListToolsParam.Tools,
                Error = mcpListToolsParam.Error
            },
            MCPApprovalRequestItemParam mcpApprovalRequestParam => new MCPApprovalRequestItemResource
            {
                Id = generatedId,
                ServerLabel = mcpApprovalRequestParam.ServerLabel,
                Name = mcpApprovalRequestParam.Name,
                Arguments = mcpApprovalRequestParam.Arguments
            },
            MCPApprovalResponseItemParam mcpApprovalResponseParam => new MCPApprovalResponseItemResource
            {
                Id = generatedId,
                ApprovalRequestId = mcpApprovalResponseParam.ApprovalRequestId,
                Approve = mcpApprovalResponseParam.Approve,
                Reason = mcpApprovalResponseParam.Reason
            },
            MCPCallItemParam mcpCallParam => new MCPCallItemResource
            {
                Id = generatedId,
                ServerLabel = mcpCallParam.ServerLabel,
                Name = mcpCallParam.Name,
                Arguments = mcpCallParam.Arguments,
                Output = mcpCallParam.Output,
                Error = mcpCallParam.Error
            },
            // Fallback for unknown types
            _ => throw new InvalidOperationException($"Unknown ItemParam type: {param.GetType().Name}")
        };
    }
}
