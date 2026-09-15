# Approval Workflow over AG-UI

This sample hosts a workflow containing one expense-review agent. The agent checks that the report has a
business purpose, an attached receipt, a positive amount no greater than 500 USD, and a plausible business
expense. If every check passes, it calls an approval-required `SubmitExpense` tool.

The AG-UI client sends the expense report, receives `ToolApprovalRequestContent`, creates the paired
`ToolApprovalResponseContent`, and resumes the same workflow thread through `IChatClient`.

The sample uses an in-memory session store without user isolation for local demonstration only. Production
hosts must isolate persisted sessions by authenticated principal.

## Run

```powershell
dotnet run --project Server --urls http://localhost:8888
dotnet run --project Client
```
