"""AST skeleton and symbol extraction engine.

Extracts concise structural outlines from source code by replacing implementation
bodies with Ellipsis (...), preserving class hierarchies, function signatures,
type annotations, constants, and docstrings.
"""

from __future__ import annotations

import ast
import re
from typing import Optional, List


class SkeletonTransformer(ast.NodeTransformer):
    """AST transformer that strips function and method bodies while preserving signatures."""

    def __init__(self, max_depth: int = 3, preserve_docstring: bool = True):
        self.current_depth = 0
        self.max_depth = max_depth
        self.preserve_docstring = preserve_docstring

    def _create_stub_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
        """Create a stub body with line-range anchors, docstrings, and Ellipsis.

        Prevents agent edit-rejection loops by explicitly marking omitted line counts
        and steering models to use `symbol_slice` before attempting code modifications.
        """
        new_body: list[ast.stmt] = []
        start_line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)

        range_str = ""
        lines_omitted = 0
        if start_line is not None and end_line is not None:
            lines_omitted = max(0, end_line - start_line)
            range_str = f" [L{start_line}-{end_line}: {lines_omitted} lines omitted]"

        docstring = ast.get_docstring(node, clean=True) if self.preserve_docstring else None
        if docstring:
            first_line = docstring.strip().split("\n")[0].strip()
            comment_text = f"{first_line}{range_str}"
        else:
            comment_text = f"...{range_str}. Use symbol_slice to view implementation."

        new_body.append(ast.Expr(value=ast.Constant(value=comment_text)))
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
                # Preserve simple assignments, uppercase constants, or __all__
                for target in item.targets:
                    if isinstance(target, ast.Name) and (target.id.isupper() or target.id == "__all__" or target.id.startswith("_")):
                        new_body.append(item)
                        break

        if not new_body:
            new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

        node.body = new_body
        self.current_depth -= 1
        return node

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: list[ast.stmt] = []

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
    """Multi-language regex skeleton extractor for TypeScript, JavaScript, Go, Rust, and Java."""
    lines = source_code.splitlines()
    skeleton_lines: list[str] = []

    sig_re = re.compile(
        r'^\s*(?:'
        r'export\s+(?:default\s+)?(?:class|interface|type|function|enum)\s+[\w_]+|'
        r'(?:public|private|protected|static|readonly|async)*\s*(?:class|interface|enum)\s+[\w_]+|'
        r'(?:public|private|protected|static|async)*\s*[\w_]+\s*\([^)]*\)\s*[:\w<>[\]\s]*\{?|'
        r'(?:const|let|var)\s+[\w_]+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|'
        r'type\s+[\w_]+\s*=|'
        r'(?:pub\s+)?(?:async\s+)?fn\s+[\w_]+|'
        r'(?:pub\s+)?struct\s+[\w_]+|'
        r'(?:pub\s+)?trait\s+[\w_]+|'
        r'(?:pub\s+)?enum\s+[\w_]+|'
        r'impl(?:<[^>]+>)?\s+[\w_]+|'
        r'func\s+(?:\([^)]+\)\s+)?[\w_]+|'
        r'type\s+[\w_]+\s+(?:struct|interface)|'
        r'(?:async\s+)?def\s+[\w_]+|'
        r'class\s+[\w_]+'
        r')',
        re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue

        if sig_re.match(line):
            clean_sig = stripped.rstrip("{:").strip()
            # Retain leading indentation for structure
            indent = len(line) - len(line.lstrip())
            skeleton_lines.append(" " * indent + clean_sig + " { ... }")

    if skeleton_lines:
        return "\n".join(skeleton_lines)

    # If no structural signatures found, return first 25 lines
    head = lines[:25]
    return "\n".join(head) + ("\n[... remaining content omitted ...]" if len(lines) > 25 else "")


def generate_python_skeleton(
    source_code: str,
    max_depth: int = 3,
    preserve_docstring: bool = True
) -> str:
    """Generate a clean AST-based skeleton of Python source code.

    Replaces all implementation bodies with Ellipsis (...) while preserving
    imports, class structures, method signatures, argument types, and docstrings.
    Falls back to language-aware heuristic parsing for non-Python or syntax-error files.
    """
    if not source_code or not source_code.strip():
        return ""

    try:
        tree = ast.parse(source_code)
        transformer = SkeletonTransformer(max_depth=max_depth, preserve_docstring=preserve_docstring)
        slim_tree = transformer.visit(tree)
        ast.fix_missing_locations(slim_tree)
        return ast.unparse(slim_tree)
    except SyntaxError:
        return _fallback_heuristic_skeleton(source_code)


def extract_symbol(source_code: str, symbol_name: str) -> Optional[str]:
    """Extract the exact full definition of a symbol (class, function, method, or constant).

    Supports:
    - Qualified names: 'ClassName.method_name' or 'ClassName.ATTRIBUTE'
    - Standalone names: 'method_name', 'ClassName', 'CONSTANT_NAME'
    - Property getters and setters: extracts all definitions matching the name
    """
    if not source_code or not symbol_name:
        return None

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    target_class: Optional[str] = None
    target_member: str = symbol_name.strip()

    if "." in symbol_name:
        parts = symbol_name.split(".", 1)
        target_class = parts[0].strip()
        target_member = parts[1].strip()

    matches: List[str] = []

    for node in tree.body:
        # 1. Matching top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_class is None and node.name == target_member:
                matches.append(ast.unparse(node))

        # 2. Matching classes
        elif isinstance(node, ast.ClassDef):
            if target_class is None and node.name == target_member:
                matches.append(ast.unparse(node))

            if target_class is None or node.name == target_class:
                class_matches: List[str] = []
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if member.name == target_member:
                            class_matches.append(ast.unparse(member))
                    elif isinstance(member, ast.AnnAssign):
                        if isinstance(member.target, ast.Name) and member.target.id == target_member:
                            class_matches.append(ast.unparse(member))
                    elif isinstance(member, ast.Assign):
                        for tgt in member.targets:
                            if isinstance(tgt, ast.Name) and tgt.id == target_member:
                                class_matches.append(ast.unparse(member))
                                break

                if class_matches:
                    indented = "\n\n".join(
                        "\n".join("    " + line for line in cm.splitlines())
                        for cm in class_matches
                    )
                    matches.append(f"class {node.name}:\n    # ... enclosing class context ...\n{indented}")

        # 3. Matching top-level variable/constant assignments
        elif target_class is None:
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == target_member:
                    matches.append(ast.unparse(node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == target_member:
                        matches.append(ast.unparse(node))
                        break

    if matches:
        return "\n\n".join(matches)

    return None
