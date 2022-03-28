from dataclasses import dataclass
from typing import Optional

@dataclass
class Project:
    id: str
    version: str
    language: str
    language_version: str

    context: Optional[int]
