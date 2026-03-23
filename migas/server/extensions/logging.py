import logging

from graphql import OperationDefinitionNode
from strawberry.extensions import SchemaExtension

from migas.server.graphql import _extract_field, _extract_from_ast

logger = logging.getLogger('migas.server')


class LoggingExtension(SchemaExtension):
    """Log GraphQL operation details: type, name, project, version, status."""

    async def on_operation(self):
        yield

        ctx = self.execution_context
        op_type = ctx.operation_type.value if ctx.operation_type else 'unknown'
        op_name = ctx.operation_name
        document = ctx.graphql_document

        if not op_name and document:
            for defn in document.definitions:
                if isinstance(defn, OperationDefinitionNode) and defn.selection_set:
                    selections = defn.selection_set.selections
                    if selections:
                        op_name = f'[{selections[0].name.value}]'
                        break

        op_name = op_name or '<anonymous>'
        variables = ctx.variables or {}

        def _extract(field, nested_key=None):
            "Helper for variable / AST extraction"
            return _extract_field(variables, field, nested_key=nested_key) or _extract_from_ast(
                document, field, nested_key=nested_key
            )

        parts = [f'{op_type.upper()} {op_name}']
        log_vals = [('project', None), ('project_version', None), ('status', 'proc')]

        for field, nested_key in log_vals:
            val = _extract(field, nested_key)
            parts.append(f'{field}={val}')

        logger.info(' | '.join(parts))
