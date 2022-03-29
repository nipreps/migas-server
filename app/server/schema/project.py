import strawberry

@strawberry.type
class Project:
    id: str
    version: str
    language: str
    language_version: str

    context: str = None
    environment: str = None

project_schema = strawberry.Schema(query=Project)
