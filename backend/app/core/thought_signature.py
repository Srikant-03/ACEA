"""
Thought Signature Generator
Extracts and structures AI reasoning from responses.
"""

import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import re

from app.agents.state import ThoughtSignature

logger = logging.getLogger(__name__)


class SignatureGenerator:
    """
    Generates thought signatures from AI responses.
    
    Methods:
    1. Explicit extraction (AI returns structured signature)
    2. Implicit parsing (extract from response text)
    """
    
    @staticmethod
    async def generate_from_explicit(
        agent_name: str,
        response: str,
        step_id: Optional[str] = None
    ) -> Optional[ThoughtSignature]:
        """
        Extract signature from explicit JSON in response.
        
        Expected format in response:
        THOUGHT_SIGNATURE:
        {
          "intent": "...",
          "rationale": "...",
          ...
        }
        
        Args:
            agent_name: Name of agent
            response: AI response text
            step_id: Associated plan step
            
        Returns:
            ThoughtSignature or None
        """
        try:
            # Look for THOUGHT_SIGNATURE marker
            if "THOUGHT_SIGNATURE:" not in response:
                return None
            
            # Extract JSON after marker
            parts = response.split("THOUGHT_SIGNATURE:", 1)
            if len(parts) < 2:
                return None
            
            json_text = parts[1].strip()
            
            # Find JSON object
            start = json_text.find("{")
            end = json_text.rfind("}") + 1
            
            if start == -1 or end == 0:
                return None
            
            try:
                sig_data = json.loads(json_text[start:end])
            except json.JSONDecodeError:
                # Try to clean up markdown code blocks if present
                clean_json = json_text[start:end].replace("```json", "").replace("```", "")
                sig_data = json.loads(clean_json)
            
            # Create signature
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            signature_id = f"sig_{agent_name.lower()}_{timestamp}"
            
            return ThoughtSignature(
                signature_id=signature_id,
                agent=agent_name,
                step_id=step_id,
                timestamp=datetime.now().isoformat(),
                intent=sig_data.get("intent", ""),
                rationale=sig_data.get("rationale", ""),
                confidence=float(sig_data.get("confidence", 0.5)),
                alternatives_considered=sig_data.get("alternatives_considered", []),
                context_used=sig_data.get("context_used", []),
                predicted_outcome=sig_data.get("predicted_outcome", ""),
                token_usage=sig_data.get("token_usage", 0),
                model_used=sig_data.get("model_used", "unknown")
            )
            
        except Exception as e:
            logger.error(f"Failed to parse explicit signature: {e}")
            return None
    
    @staticmethod
    async def generate_from_implicit(
        agent_name: str,
        prompt: str,
        response: str,
        step_id: Optional[str] = None,
        token_usage: int = 0,
        model_used: str = "unknown"
    ) -> ThoughtSignature:
        """
        Generate signature by analyzing prompt and response.
        
        Extracts reasoning implicitly when explicit signature absent.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        signature_id = f"sig_{agent_name.lower()}_{timestamp}"
        
        # Extract intent from prompt
        intent = SignatureGenerator._extract_intent(prompt)
        
        # Extract rationale from response
        rationale = SignatureGenerator._extract_rationale(response)
        
        # Estimate confidence (implicit = lower confidence)
        confidence = 0.6
        
        # Hash prompt for deduplication
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
        
        return ThoughtSignature(
            signature_id=signature_id,
            agent=agent_name,
            step_id=step_id,
            timestamp=datetime.now().isoformat(),
            intent=intent,
            rationale=rationale,
            confidence=confidence,
            alternatives_considered=[],
            context_used=SignatureGenerator._extract_context(prompt),
            predicted_outcome="",
            token_usage=token_usage,
            model_used=model_used,
            prompt_hash=prompt_hash
        )
    
    @staticmethod
    def _extract_intent(prompt: str) -> str:
        """Extract intent from prompt text."""
        # Look for task descriptions
        patterns = [
            r"(?:TASK|OBJECTIVE|GOAL):\s*(.+?)(?:\n|$)",
            r"(?:Generate|Create|Design|Implement)\s+(.+?)(?:\n|\.)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]
        
        # Fallback: first meaningful line
        lines = [l.strip() for l in prompt.split("\n") if l.strip()]
        if lines:
            return lines[0][:200]
        
        return "Unknown intent"
    
    @staticmethod
    def _extract_rationale(response: str) -> str:
        """Extract rationale from response."""
        # Look for reasoning phrases
        patterns = [
            r"(?:because|since|due to|rationale)\s+(.+?)(?:\n|\.)",
            r"(?:I chose|I selected|I decided)\s+(.+?)(?:\n|\.)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:300]
        
        # Fallback: try to grab the first paragraph if it looks like reasoning?
        # Or just default text
        return "Implicit reasoning captured from response."
    
    @staticmethod
    def _extract_context(prompt: str) -> List[str]:
        """Extract context clues from prompt."""
        context = []
        
        # Look for tech stack mentions
        if "tech stack" in prompt.lower():
            match = re.search(r"tech stack:\s*(.+?)(?:\n|$)", prompt, re.IGNORECASE)
            if match:
                context.append(f"Tech Stack: {match.group(1).strip()}")
        
        # Look for file mentions
        file_count = len(re.findall(r"\.(py|js|tsx|java|go|html|css)", prompt))
        if file_count > 0:
            context.append(f"Files referenced: {file_count}")
        
        return context


# Helper functions for agents
async def capture_signature(
    agent_name: str,
    prompt: str,
    response: str,
    step_id: Optional[str] = None,
    token_usage: int = 0,
    model_used: str = "unknown"
) -> ThoughtSignature:
    """
    Convenience function to capture signature from any agent.
    
    Tries explicit extraction first, falls back to implicit.
    """
    generator = SignatureGenerator()
    
    # Try explicit first
    explicit_sig = await generator.generate_from_explicit(
        agent_name, response, step_id
    )
    
    if explicit_sig:
        explicit_sig.token_usage = token_usage
        explicit_sig.model_used = model_used
        return explicit_sig
    
    # Fallback to implicit
    return await generator.generate_from_implicit(
        agent_name, prompt, response, step_id, token_usage, model_used
    )
