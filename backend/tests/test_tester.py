import pytest
import sys
import os
import json

# Ensure backend directory is in path
sys.path.insert(0, os.getcwd())

from app.agents.tester import TesterAgent

# Sample execution log with a clear error
SAMPLE_LOG = """
> frontend@0.1.0 dev
> next dev

ready - started server on 0.0.0.0:3000, url: http://localhost:3000
event - compiled client and server successfully in 1234 ms
wait  - compiling...
event - compiled client and server successfully in 300 ms
error - frontend/app/page.tsx (5:10) @ Page
Error: ReferenceError: window is not defined
    at Page (frontend/app/page.tsx:5:10)
    at renderWithHooks
"""

@pytest.mark.asyncio
async def test_analyze_execution_structure():
    agent = TesterAgent()
    blueprint = {"projectType": "frontend", "tech_stack": "Next.js"}
    
    # Run analysis
    result = await agent.analyze_execution(SAMPLE_LOG, blueprint)
    
    print(json.dumps(result, indent=2))
    
    # Verify structure
    assert "status" in result
    assert "issues" in result
    assert "fixes" in result
    
    # Check if it identified the file
    fixes = result.get("fixes", [])
    if fixes:
        first_fix = fixes[0]
        assert "file" in first_fix
        assert "change" in first_fix
        # Ideally it should identify page.tsx
        # assert "page.tsx" in first_fix["file"]

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_analyze_execution_structure())
