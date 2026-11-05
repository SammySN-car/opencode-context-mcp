"""AST skeleton and symbol extraction engine.

Extracts concise structural outlines from source code by replacing implementation
bodies with Ellipsis (...), preserving class hierarchies, function signatures,
type annotations, and docstrings.
"""

from __future__ import annotations

import ast
import re
from typing import Optional


class SkeletonTransformer(ast.NodeTransformer):
    """AST transformer that strips function and method bodies while preserving signatures."""

    def __init__(self, max_depth: int = 3, preserve_docstring: bool = True):
        self.current_depth = 0
        self.max_depth = max_depth
        self.preserve_docstring = preserve_docstring

    def _create_stub_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
        """Create a stub body containing at most the first docstring line and an Ellipsis."""
        new_body: list[ast.stmt] = []
        if self.preserve_docstring:
            docstring = ast.get_docstring(node, clean=True)
            if docstring:
                first_line = docstring.strip().split("\n")[0].strip()
                if first_line:
                    new_body.append(ast.Expr(value=ast.Constant(value=first_line)))

        new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
        return new_body

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.current_depth += 1
        node.body = self._create_stub_body(node)
        self.current_depth -= 1
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        self.current_depth += 1
        node.body = self._create_stub_body(node)
        self.current_depth -= 1
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        self.current_depth += 1
        new_body: list[ast.stmt] = []

        if self.preserve_docstring:
            docstring = ast.get_docstring(node, clean=True)
            if docstring:
                first_line = docstring.strip().split("\n")[0].strip()
                if first_line:
                    new_body.append(ast.Expr(value=ast.Constant(value=first_line)))

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self.current_depth <= self.max_depth:
                    new_body.append(self.visit(item))
            elif isinstance(item, ast.ClassDef):
                if self.current_depth <= self.max_depth:
                    new_body.append(self.visit(item))
            elif isinstance(item, ast.AnnAssign):
                # Preserve typed class-level attributes: name: str = ...
                new_body.append(item)
            elif isinstance(item, ast.Assign):
                # Preserve simple constant assignments like __all__ or UPPERCASE constants
                for target in item.targets:
                    if isinstance(target, ast.Name) and (target.id.isupper() or target.id == "__all__"):
                        new_body.append(item)
                        break

        if not new_body:
            new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

        node.body = new_body
        self.current_depth -= 1
        return node

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: list[ast.stmt] = []

        # Preserve module-level docstring if available
        if self.preserve_docstring:
            doc = ast.get_docstring(node, clean=True)
            if doc:
                first_line = doc.strip().split("\n")[0].strip()
                if first_line:
                    new_body.append(ast.Expr(value=ast.Constant(value=first_line)))

        for item in node.body:
            if isinstance(item, (ast.Import, ast.ImportFrom)):
                new_body.append(item)
            elif isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self.visit(item))
            elif isinstance(item, ast.AnnAssign):
                new_body.append(item)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and (target.id.isupper() or target.id == "__all__"):
                        new_body.append(item)
                        break

        node.body = new_body
        return node


def _fallback_heuristic_skeleton(source_code: str) -> str:
    """Regex-based fallback for syntax errors or non-Python languages."""
    sig_re = re.compile(
        r'^\s*(?:'
        r'(?:async\s+)?def\s+[\w_]+|'
        r'class\s+[\w_]+|'
        r'(?:pub\s+)?(?:async\s+)?fn\s+[\w_]+|'
        r'func\s+(?:\([^)]+\)\s+)?[\w_]+|'
        r'export\s+(?:default\s+)?(?:class|function|interface|type)\s+[\w_]+|'
        r'(?:const|let|var)\s+[\w_]+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>'
        r')[^{:\n]*[:{]?',
        re.MULTILINE
    )
    matches = sig_re.findall(source_code)
    if matches:
        return "\n".join(m.strip() + " ..." for m in matches)
    # If no signatures found, return first 20 lines
    lines = source_code.splitlines()[:20]
    return "\n".join(lines) + ("\n..." if len(source_code.splitlines()) > 20 else "")


def generate_python_skeleton(
    source_code: str,
    max_depth: int = 3,
    preserve_docstring: bool = True
) -> str:
    """Generate a clean AST-based skeleton of Python source code.

    Replaces all implementation bodies with Ellipsis (...) while preserving
    imports, class structures, method signatures, argument types, and docstrings.
    """
    try:
        tree = ast.parse(source_code)
        transformer = SkeletonTransformer(max_depth=max_depth, preserve_docstring=preserve_docstring)
        slim_tree = transformer.visit(tree)
        ast.fix_missing_locations(slim_tree)
        return ast.unparse(slim_tree)
    except SyntaxError:
        return _fallback_heuristic_skeleton(source_code)


def extract_symbol(source_code: str, symbol_name: str) -> Optional[str]:
    """Extract the exact full definition of a symbol (class, function, or method).

    Supports qualified names like 'ClassName.method_name' or standalone names
    like 'method_name' or 'ClassName'.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    target_class: Optional[str] = None
    target_member: str = symbol_name

    if "." in symbol_name:
        parts = symbol_name.split(".", 1)
        target_class = parts[0]
        target_member = parts[1]

    for node in tree.body:
        # 1. Matching top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_class is None and node.name == target_member:
                return ast.unparse(node)

        # 2. Matching classes
        elif isinstance(node, ast.ClassDef):
            if target_class is None and node.name == target_member:
                return ast.unparse(node)

            if target_class is None or node.name == target_class:
                # Search within class methods
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if member.name == target_member:
                            # Return the member with enclosing class context
                            member_code = ast.unparse(member)
                            indented_member = "\n".join("    " + line for line in member_code.splitlines())
                            return f"class {node.name}:\n    # ... enclosing class context ...\n{indented_member}"

    return None
