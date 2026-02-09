
# A2A Client Sample
Show how to create an A2A Client with a command line interface which invokes agents using the A2A protocol.

## Run the Sample

To run the sample, follow these steps:

1. Run the A2A client:
    ```bash
    cd A2AClient
    dotnet run
    ```  
2. Enter your request e.g. "Show me all invoices for Contoso?"

## Set Environment Variables

The agent urls are provided as a ` ` delimited list of strings

```powershell
cd dotnet/samples/A2AClientServer/A2AClient

$env:OPENAI_MODEL="gpt-4o-mini"
$env:OPENAI_API_KEY="<Your OPENAI api key>"
$env:AGENT_URLS="http://localhost:5000/policy;http://localhost:5000/invoice;http://localhost:5000/logistics"
```
