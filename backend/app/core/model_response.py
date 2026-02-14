from dataclasses import dataclass

@dataclass
class ModelResponse:
    output: str
    thought_signature: str
