from graphql import OperationDefinitionNode
from graphql.language.ast import EnumValueNode, ObjectValueNode, StringValueNode


def _extract_field(variables: dict, field: str, nested_key: str | None = None) -> str | None:
    """Extract a field from GraphQL variables, checking top-level and nested input objects.

    Handles both flat input shapes (e.g. `add_breadcrumb(project=..., proc=...)`)
    and object inputs (e.g. `add_project(p=ProjectInput(...))`).
    """
    if not variables:
        return None
    if field in variables:
        return str(variables[field])

    # Needed due to `add_project`
    # TODO: Remove once dropped
    for val in variables.values():
        if isinstance(val, dict) and field in val:
            return str(val[field])

    # Check a specific nested key (e.g. `proc.status` for add_breadcrumb)
    if nested_key and nested_key in variables:
        nested = variables[nested_key]
        if isinstance(nested, dict) and field in nested:
            return str(nested[field])


def _extract_from_ast(document, field: str, nested_key: str | None = None) -> str | None:
    """Fallback: extract an inline literal argument value from the GraphQL AST.

    Used when queries are written with inline values instead of $variables.
    """
    if document is None:
        return None
    for defn in document.definitions:
        if not isinstance(defn, OperationDefinitionNode):
            continue
        for selection in defn.selection_set.selections:
            for arg in selection.arguments:
                if arg.name.value == field:
                    if isinstance(arg.value, (StringValueNode, EnumValueNode)):
                        return arg.value.value

                # Nested object match (e.g. p: {project: "..."} or proc: {status: R})
                if isinstance(arg.value, ObjectValueNode):
                    if nested_key and arg.name.value != nested_key:
                        continue
                    for obj_field in arg.value.fields:
                        if obj_field.name.value == field:
                            if isinstance(obj_field.value, (StringValueNode, EnumValueNode)):
                                return obj_field.value.value
