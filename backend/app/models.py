from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime

class Project(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    name: str
    description: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"

class AgentLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    agent_name: str
    action: str
    details: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
