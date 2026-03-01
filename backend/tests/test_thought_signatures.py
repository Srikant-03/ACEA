
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.state import AgentState, ThoughtSignature, ExecutionPlan
from app.core.thought_signature import SignatureGenerator
import logging

# Disable logging to avoid format errors in test capture
logging.disable(logging.CRITICAL)

@pytest.mark.asyncio
async def test_signature_generator():
    """Test parsing logic of SignatureGenerator."""
    generator = SignatureGenerator()
    
    # Test Explicit Parsing (JSON explicit)
    response_explicit = """
    Here is the plan.
    ```json
    {"foo": "bar"}
    ```
    
    THOUGHT_SIGNATURE:
    {
      "intent": "Test intent",
      "rationale": "Test rationale",
      "confidence": 0.95
    }
    """
    
    sig = await generator.generate_from_explicit(
        agent_name="TEST_AGENT",
        response=response_explicit
    )
    
    assert sig is not None
    assert sig.intent == "Test intent"
    assert sig.rationale == "Test rationale"
    assert sig.confidence == 0.95
    assert sig.agent == "TEST_AGENT"

@pytest.mark.asyncio
async def test_architect_signature_integration():
    """Verify ArchitectAgent captures signature."""
    from app.agents.architect import ArchitectAgent
    
    # Mock HybridModelClient - Architect uses local_model
    with patch('app.core.local_model.HybridModelClient') as MockClient:
        mock_instance = MockClient.return_value
        # Mock response with explicit signature
        mock_instance.generate = AsyncMock(return_value="""
        ```json
        {"project_name": "Test Project", "file_structure": []}
        ```
        
        THOUGHT_SIGNATURE:
        {
            "intent": "Design system",
            "rationale": "Because it is required",
            "confidence": 0.9
        }
        """)
        
        agent = ArchitectAgent()
        # Mock cache
        with patch('app.core.cache.cache') as MockCache:
            MockCache.get = AsyncMock(return_value=None)
            MockCache.set = AsyncMock()
            MockCache.init_redis = AsyncMock()
            
            blueprint = await agent.design_system("Make a generic app", "python")
            
            assert "thought_signature" in blueprint
            sig = blueprint["thought_signature"]
            assert sig["intent"] == "Design system"
            assert sig["confidence"] == 0.9

@pytest.mark.asyncio
async def test_virtuoso_signature_integration():
    """Verify VirtuosoAgent captures signature via __thought_signature__ key."""
    from app.agents.virtuoso import VirtuosoAgent
    import json
    
    # Mock HybridModelClient - Virtuoso uses local_model
    with patch('app.core.local_model.HybridModelClient') as MockClient:
        mock_instance = MockClient.return_value
        
        # Virtuoso returns straight JSON with __thought_signature__
        response_json = {
            "__thought_signature__": {
                "intent": "Generate code", 
                "rationale": "Standard pattern",
                "confidence": 0.8
            },
            "main.py": "print('hello')"
        }
        mock_instance.generate = AsyncMock(return_value=json.dumps(response_json))
        
        agent = VirtuosoAgent()
        
        with patch('app.core.socket_manager.SocketManager') as MockSocket:
            MockSocket.return_value.emit = AsyncMock()
            
            result = await agent.generate_from_blueprint({"file_structure": [{"path": "main.py", "description": "desc"}]})
            
            assert "files" in result
            assert "signature" in result
            
            assert result["files"]["main.py"] == "print('hello')"
            assert result["signature"] is not None
            assert result["signature"].intent == "Generate code"

@pytest.mark.asyncio
async def test_planner_signature_integration():
    """Verify PlannerAgent captures signature and returns tuple."""
    from app.agents.planner import PlannerAgent
    
    # Mock HybridModelClient - Planner uses app.core.HybridModelClient
    with patch('app.core.HybridModelClient.HybridModelClient') as MockClient:
        mock_instance = MockClient.return_value
        
        prompt_response = """
        ```json
        {
            "steps": [],
            "strategy": "Test"
        }
        ```
        
        THOUGHT_SIGNATURE:
        {
            "intent": "Create plan",
            "rationale": "Logical steps",
            "confidence": 0.85
        }
        """
        mock_instance.generate = AsyncMock(return_value=prompt_response)
        
        agent = PlannerAgent()
        
        context = {"repo_analysis": {}}
        plan, signature = await agent.create_plan("My objective", context)
        
        assert plan is not None
        assert signature is not None
        assert signature.intent == "Create plan"
        assert signature.confidence == 0.85
