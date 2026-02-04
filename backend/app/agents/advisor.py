from app.core.config import settings
import json

class AdvisorAgent:
    def __init__(self):
        pass

    async def analyze_deployment(self, project_details: dict) -> dict:
        """
        Recommends deployment strategies and estimates costs.
        """
        from app.core.local_model import HybridModelClient
        client = HybridModelClient()
        
        prompt = f"""
        You are The Deployment Advisor.
        Analyze the following project and recommend a deployment strategy.
        
        Project:
        {project_details}
        
        Output JSON:
        {{
            "platform": "string",
            "cost_estimate": "string",
            "config_files": ["string"]
        }}
        """
        try:
            response = await client.generate(prompt, json_mode=True)
            return json.loads(response)
        except Exception as e:
            return {"error": str(e)}
