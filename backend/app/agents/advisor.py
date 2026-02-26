# ACEA Sentinel - The Advisor Agent
# Tech-stack-aware deployment analysis with cost estimation

from app.core.config import settings
import json


class AdvisorAgent:
    """Recommends deployment strategies based on project analysis."""
    
    # Known deployment targets keyed by tech indicators
    PLATFORM_MAP = {
        "next": {"platform": "Vercel", "tier": "Hobby (free) / Pro ($20/mo)", "config": "vercel.json"},
        "react": {"platform": "Vercel or Netlify", "tier": "Free tier available", "config": "vercel.json or netlify.toml"},
        "vue": {"platform": "Netlify or Vercel", "tier": "Free tier available", "config": "netlify.toml"},
        "angular": {"platform": "Firebase Hosting or Netlify", "tier": "Free tier (Spark)", "config": "firebase.json"},
        "svelte": {"platform": "Vercel or Netlify", "tier": "Free tier available", "config": "vercel.json"},
        "flask": {"platform": "Railway or Render", "tier": "$5-7/mo starter", "config": "Procfile + railway.toml"},
        "fastapi": {"platform": "Railway or Render", "tier": "$5-7/mo starter", "config": "Procfile + Dockerfile"},
        "django": {"platform": "Railway or Render", "tier": "$5-7/mo starter", "config": "Procfile + Dockerfile"},
        "express": {"platform": "Railway or Render", "tier": "$5-7/mo starter", "config": "Procfile"},
        "node": {"platform": "Railway or Render", "tier": "$5-7/mo starter", "config": "Procfile"},
        "static": {"platform": "GitHub Pages or Netlify", "tier": "Free", "config": "None required"},
    }

    def __init__(self):
        pass

    def _detect_platform(self, project_details: dict) -> dict:
        """Detect best deployment platform from project metadata (zero API calls)."""
        tech_stack = project_details.get("tech_stack")
        if isinstance(tech_stack, list):
            tech_stack = " ".join(tech_stack)
        tech_stack = (tech_stack or "").lower()
        
        # Check blueprint tech stack first
        blueprint = project_details.get("blueprint", {})
        bp_stack = blueprint.get("tech_stack")
        if isinstance(bp_stack, list):
            bp_stack = " ".join(bp_stack)
        bp_stack = (bp_stack or "").lower()
        
        project_type = (blueprint.get("project_type") or "frontend").lower()
        
        combined = f"{tech_stack} {bp_stack}"
        
        for key, info in self.PLATFORM_MAP.items():
            if key in combined:
                return info
        
        # Fallback based on project type
        if project_type == "backend":
            return self.PLATFORM_MAP["fastapi"]
        return self.PLATFORM_MAP["static"]

    async def analyze_deployment(self, project_details: dict) -> dict:
        """
        Recommends deployment strategies and estimates costs.
        Uses local heuristic detection first, then optionally enhances with LLM.
        """
        # Step 1: Fast local detection (zero API calls)
        platform_info = self._detect_platform(project_details)
        
        result = {
            "platform": platform_info["platform"],
            "cost_estimate": platform_info["tier"],
            "config_files": [platform_info["config"]],
            "file_count": project_details.get("file_count", 0),
            "issues_found": len(project_details.get("issues", [])),
            "errors_found": len(project_details.get("errors", [])),
        }
        
        # Step 2: Try LLM enhancement for richer recommendations (non-blocking)
        try:
            from app.core.local_model import HybridModelClient
            client = HybridModelClient()
            
            prompt = f"""You are a deployment advisor. Given this project analysis, provide deployment recommendations.

Project Details:
- Tech Stack: {project_details.get('tech_stack', 'Auto-detect')}
- File Count: {project_details.get('file_count', 0)}
- Issues: {len(project_details.get('issues', []))}
- Errors: {len(project_details.get('errors', []))}
- Blueprint: {json.dumps(project_details.get('blueprint', {}), indent=2)}

Respond with JSON:
{{
    "platform": "recommended platform name",
    "cost_estimate": "pricing tier estimate",
    "config_files": ["list of config files needed"],
    "deployment_notes": "any special deployment considerations",
    "scaling_advice": "advice for scaling if needed"
}}"""
            
            response = await client.generate(prompt, json_mode=True)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            llm_result = json.loads(cleaned, strict=False)
            
            # Capture thought signature for decision provenance
            try:
                from app.core.thought_signature import capture_signature
                signature = await capture_signature(
                    agent="advisor",
                    intent="deployment platform recommendation",
                    decision=f"Recommended {llm_result.get('platform', 'unknown')}",
                    confidence=0.8,
                    input_summary=f"tech={project_details.get('tech_stack','')}, files={project_details.get('file_count',0)}"
                )
                result["thought_signature"] = signature.to_dict() if hasattr(signature, 'to_dict') else signature
            except Exception:
                pass  # Signature capture is non-blocking
            
            # Merge LLM insights with local detection
            result["platform"] = llm_result.get("platform", result["platform"])
            result["cost_estimate"] = llm_result.get("cost_estimate", result["cost_estimate"])
            result["config_files"] = llm_result.get("config_files", result["config_files"])
            result["deployment_notes"] = llm_result.get("deployment_notes", "")
            result["scaling_advice"] = llm_result.get("scaling_advice", "")
            
        except Exception as e:
            # LLM enhancement is optional — local detection already provides a solid answer
            result["deployment_notes"] = f"LLM enhancement unavailable: {str(e)[:80]}"
        
        return result
