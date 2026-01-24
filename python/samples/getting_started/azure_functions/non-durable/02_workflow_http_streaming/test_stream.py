"""Simple test script for streaming endpoints."""
import httpx
import json

async def test_workflow_stream():
    url = "http://localhost:7071/api/workflow/stream"
    data = {"message": "What's the weather in Seattle?"}
    
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, json=data, timeout=60.0) as response:
            print(f"Status: {response.status_code}")
            print(f"Headers: {response.headers}")
            print("\nStreaming response:\n")
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    try:
                        data_obj = json.loads(data_str)
                        print(f"  {data_obj}")
                    except:
                        print(f"  {data_str}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_workflow_stream())
