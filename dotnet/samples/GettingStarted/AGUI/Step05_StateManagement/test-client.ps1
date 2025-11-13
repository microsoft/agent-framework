$env:AGUI_SERVER_URL="http://localhost:8888"
Set-Location "d:\work\agent-framework-docs\Validation\AGUI\Step01_GettingStarted\Client"

# Test with a simple question
$input = @"
What is 2 + 2?
quit
"@

$input | dotnet run
