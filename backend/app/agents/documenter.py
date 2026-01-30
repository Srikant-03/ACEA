# ACEA Sentinel - Documenter Agent
# Generates README.md and documentation

import json
from typing import Dict, List


class DocumenterAgent:
    """Generates project documentation."""
    
    def __init__(self):
        pass
    
    async def generate_readme(self, blueprint: dict, files: List[str], user_prompt: str) -> str:
        """
        Generate comprehensive README.md.
        
        Returns: README content as markdown string
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "DOCUMENTER", "message": "Generating README.md..."})
        
        prompt = f"""
Generate a professional README.md for this project.

Original Request: {user_prompt}

Project Details:
- Name: {blueprint.get('project_name', 'Project')}
- Type: {blueprint.get('projectType', 'application')}
- Stack: {blueprint.get('tech_stack', 'Unknown')}
- Files: {files[:15]}

Create a comprehensive README with these sections:

# {blueprint.get('project_name', 'Project Name')}

## Description
Brief overview of what this project does

## Features
- Key feature 1
- Key feature 2

## Tech Stack
List technologies used

## Project Structure
Show file tree

## Installation
Installation commands

## Running the Project
How to run

## Usage
How to use the application

---

Make it professional, clear, and beginner-friendly.
Return ONLY the markdown content, no code blocks.
"""
        
        try:
            readme = await client.generate(prompt)
            
            # Clean up any markdown code blocks
            readme = readme.replace("```markdown", "").replace("```", "").strip()
            
            await sm.emit("agent_log", {"agent_name": "DOCUMENTER", "message": "✅ README.md generated"})
            return readme
            
        except Exception as e:
            await sm.emit("agent_log", {"agent_name": "DOCUMENTER", "message": f"⚠️ Generation error: {str(e)[:50]}"})
            return self._fallback_readme(blueprint, files, user_prompt)
    
    def _fallback_readme(self, blueprint: dict, files: List[str], user_prompt: str) -> str:
        """Generate basic README without API call."""
        name = blueprint.get('project_name', 'Project')
        stack = blueprint.get('tech_stack', 'Unknown')
        
        file_tree = "\n".join(f"├── {f}" for f in files[:15])
        
        return f"""# {name}

## Description
{blueprint.get('description', user_prompt)}

## Tech Stack
{stack}

## Project Structure
```
{file_tree}
```

## Installation
```bash
npm install   # For Node.js projects
pip install -r requirements.txt   # For Python projects
```

## Running the Project
```bash
npm start   # For Node.js projects
python main.py   # For Python projects
```

## License
MIT
"""
