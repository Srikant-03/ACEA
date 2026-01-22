from app.core.config import settings
from app.core.key_manager import KeyManager

class AdvisorAgent:
    def __init__(self):
        self.km = KeyManager()

    async def analyze_deployment(self, project_details: dict) -> dict:
        """
        Recommends deployment strategies and estimates costs.
        """
        from app.core.key_manager import KeyManager
        km = KeyManager()
        
        prompt = f"""
        You are The Deployment Advisor.
        Analyze the following project and recommend a deployment strategy (Vercel, Railway, etc.).
        
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
            client = km.get_client()
            response = await client.aio.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt
            )
            # Basic JSON parsing or string return
            return {"recommendation": response.text}
        except Exception as e:
            return {"error": str(e)}
