# Multi-Agent Orchestration with Conditionals Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create a multi-agent orchestration workflow that includes conditional logic. The workflow implements a spam detection system that processes emails and takes different actions based on whether the email is identified as spam or legitimate.

## Key Concepts Demonstrated

- Multi-agent orchestration with conditional logic and different processing paths
- Spam detection using AI agent analysis
- Structured output from agents for reliable processing
- Activity functions for integrating non-agentic workflow actions

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request with email data to the orchestration.

You can use the `demo.http` file to send email data to the agents, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
# Test with a legitimate email
curl -X POST http://localhost:7071/api/spamdetection/run \
    -H "Content-Type: application/json" \
    -d '{
      "email_id": "email-001",
      "email_content": "Hi John, I hope you are doing well. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!"
    }'

# Test with a spam email
curl -X POST http://localhost:7071/api/spamdetection/run \
    -H "Content-Type: application/json" \
    -d '{
      "email_id": "email-002",
      "email_content": "URGENT! You have won $1,000,000! Click here now to claim your prize! Limited time offer! Do not miss out!"
    }'
```

PowerShell:

```powershell
# Test with a legitimate email
$body = @{
    email_id = "email-001"
    email_content = "Hi John, I hope you are doing well. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/spamdetection/run `
    -ContentType application/json `
    -Body $body

# Test with a spam email
$body = @{
    email_id = "email-002"
    email_content = "URGENT! You have won $1,000,000! Click here now to claim your prize! Limited time offer! Do not miss out!"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/spamdetection/run `
    -ContentType application/json `
    -Body $body
```

The response from either input will be a JSON object that looks something like the following, which indicates that the orchestration has started.

```json
{
  "message": "Spam detection orchestration started.",
  "emailId": "email-001",
  "instanceId": "555dbbb63f75406db2edf9f1f092de95",
  "statusQueryGetUri": "http://localhost:7071/api/spamdetection/status/555dbbb63f75406db2edf9f1f092de95"
}
```

The orchestration will:

1. Analyze the email content using the SpamDetectionAgent
2. If spam: Mark the email as spam with a reason
3. If legitimate: Use the EmailAssistantAgent to draft a professional response and "send" it

Once the orchestration has completed, you can get the status of the orchestration by sending a GET request to the `statusQueryGetUri` URL. The response for the legitimate email will be a JSON object that looks something like the following:

```json
{
  "failureDetails": null,
  "input": {
    "email_content": "Hi John, I hope you're doing well. I wanted to follow up on our meeting yesterday about the quarterly report. Could you please send me the updated figures by Friday? Thanks!",
    "email_id": "email-001"
  },
  "instanceId": "555dbbb63f75406db2edf9f1f092de95",
  "output": "Email sent: Subject: Re: Follow-Up on Quarterly Report\n\nHi [Recipient's Name],\n\nI hope this message finds you well. Thank you for your patience. I will ensure the updated figures for the quarterly report are sent to you by Friday.\n\nIf you have any further questions or need additional information, please feel free to reach out.\n\nBest regards,\n\nJohn",
  "runtimeStatus": "Completed"
}
```

The response for the spam email will be a JSON object that looks something like the following, which indicates that the email was marked as spam:

```json
{
  "failureDetails": null,
  "input": {
    "email_content": "URGENT! You have won $1,000,000! Click here now to claim your prize! Limited time offer! Do not miss out!",
    "email_id": "email-002"
  },
  "instanceId": "555dbbb63f75406db2edf9f1f092de95",
  "output": "Email marked as spam: The email contains misleading claims of winning a large sum of money and encourages immediate action, which are common characteristics of spam.",
  "runtimeStatus": "Completed"
}
```
