from __future__ import annotations

from antlr4 import CommonTokenStream, InputStream

from .exceptions import DSLParseError
from .error_listener import ThrowingErrorListener
from .generated.GrammarDSLLexer import GrammarDSLLexer
from .generated.GrammarDSLParser import GrammarDSLParser
from .visitor.ast_builder import ASTBuilder


class ParserService:
    def __init__(self) -> None:
        self.builder = ASTBuilder()

    def tokenize(self, text: str) -> list[dict]:
        lexer = self._build_lexer(text)
        stream = CommonTokenStream(lexer)
        stream.fill()

        symbolic_names = getattr(lexer, "symbolicNames", [])
        tokens: list[dict] = []
        for raw_token in stream.tokens:
            if raw_token.type == -1:
                continue

            token_name = (
                symbolic_names[raw_token.type]
                if 0 <= raw_token.type < len(symbolic_names)
                else str(raw_token.type)
            )
            if token_name == "DOT":
                token_name = "PERIOD"
            tokens.append(
                {
                    "index": len(tokens),
                    "type": token_name,
                    "lexeme": raw_token.text,
                    "line": raw_token.line,
                    "column": raw_token.column,
                }
            )
        return tokens

    def inspect(self, text: str) -> dict:
        tokens = self.tokenize(text)
        inspection = {
            "source_text": text.strip(),
            "tokens": tokens,
            "token_count": len(tokens),
            "parsable": False,
            "command_type": None,
            "parse_error": None,
        }

        try:
            node = self.parse(text)
            inspection["parsable"] = True
            inspection["command_type"] = type(node).__name__
        except DSLParseError as error:
            inspection["parse_error"] = str(error)

        return inspection

    def parse(self, text: str):
        trimmed = text.strip()
        # Bulletproof bypass for check grammar to prevent ANTLR keyword collisions
        if trimmed.lower().startswith("check grammar "):
            from grammar_dsl.dsl.ast.nodes import GrammarCheckCommand
            paragraph = trimmed[14:].strip()
            return GrammarCheckCommand(paragraph=paragraph)

        # Bulletproof bypass for show tokens to prevent ANTLR keyword collisions in nested check grammar commands
        if trimmed.lower().startswith("show tokens "):
            from grammar_dsl.dsl.ast.nodes import ShowTokensCommand
            source_text = trimmed[12:].strip()
            return ShowTokensCommand(source_text=source_text)

        # Robust bypass for generate and create quiz commands to prevent ANTLR keyword collisions on custom features
        custom_node = self._parse_generate_or_quiz(trimmed)
        if custom_node is not None:
            return custom_node

        input_stream = InputStream(text.strip())
        error_listener = ThrowingErrorListener()

        lexer = GrammarDSLLexer(input_stream)
        lexer.removeErrorListeners()
        lexer.addErrorListener(error_listener)

        token_stream = CommonTokenStream(lexer)
        parser = GrammarDSLParser(token_stream)
        parser.removeErrorListeners()
        parser.addErrorListener(error_listener)

        tree = parser.command()
        return self.builder.visit(tree)

    @staticmethod
    def _build_lexer(text: str) -> GrammarDSLLexer:
        input_stream = InputStream(text.strip())
        error_listener = ThrowingErrorListener()
        lexer = GrammarDSLLexer(input_stream)
        lexer.removeErrorListeners()
        lexer.addErrorListener(error_listener)
        return lexer

    def _parse_generate_or_quiz(self, text: str):
        import re
        trimmed = text.strip()
        
        # 1. generate exercise with <feature-expr>
        m1 = re.match(r"^generate\s+exercise\s+with\s+(.+)$", trimmed, re.IGNORECASE)
        if m1:
            feature_str = m1.group(1).strip()
            try:
                expr = self._parse_feature_expr_from_text(feature_str)
                from grammar_dsl.dsl.ast.nodes import GenerateExerciseCommand
                return GenerateExerciseCommand(
                    requested_count=None,
                    feature_expr=expr,
                    raw_feature_text=self._render_expr_text(expr),
                    singular_form_requested=True
                )
            except Exception:
                return None
            
        # 2. generate <N> exercises with <feature-expr>
        m2 = re.match(r"^generate\s+(\d+)\s+exercises?\s+with\s+(.+)$", trimmed, re.IGNORECASE)
        if m2:
            count = int(m2.group(1))
            feature_str = m2.group(2).strip()
            try:
                expr = self._parse_feature_expr_from_text(feature_str)
                from grammar_dsl.dsl.ast.nodes import GenerateExerciseCommand
                return GenerateExerciseCommand(
                    requested_count=count,
                    feature_expr=expr,
                    raw_feature_text=self._render_expr_text(expr),
                    singular_form_requested=False
                )
            except Exception:
                return None
            
        # 3. create quiz "<title>" with/generate <N> exercises with <feature-expr>
        m3 = re.match(r"^create\s+quiz\s+\"([^\"]+)\"\s+(?:with|generate)\s+(\d+)\s+exercises?\s+with\s+(.+)$", trimmed, re.IGNORECASE)
        if m3:
            title = m3.group(1)
            count = int(m3.group(2))
            feature_str = m3.group(3).strip()
            try:
                expr = self._parse_feature_expr_from_text(feature_str)
                from grammar_dsl.dsl.ast.nodes import CreateQuizCommand
                return CreateQuizCommand(
                    title=title,
                    requested_count=count,
                    feature_expr=expr,
                    raw_feature_text=self._render_expr_text(expr)
                )
            except Exception:
                return None
            
        return None

    def _parse_feature_expr_from_text(self, text: str):
        import re
        token_pattern = re.compile(r'(\(|\)|(?:\bAND\b)|(?:\bOR\b)|[a-zA-Z0-9_-]+)', re.IGNORECASE)
        raw_tokens = token_pattern.findall(text)
        
        tokens = []
        for t in raw_tokens:
            t_strip = t.strip()
            if not t_strip:
                continue
            tokens.append(t_strip)
            
        idx = 0
        
        def parse_expr():
            nonlocal idx
            node = parse_term()
            while idx < len(tokens) and tokens[idx].upper() == 'OR':
                idx += 1
                right = parse_term()
                from grammar_dsl.dsl.ast import OrExpr
                node = OrExpr(left=node, right=right)
            return node

        def parse_term():
            nonlocal idx
            node = parse_factor()
            while idx < len(tokens) and tokens[idx].upper() == 'AND':
                idx += 1
                right = parse_factor()
                from grammar_dsl.dsl.ast import AndExpr
                node = AndExpr(left=node, right=right)
            return node

        def parse_factor():
            nonlocal idx
            if idx >= len(tokens):
                raise ValueError("Unexpected end of input")
            if tokens[idx] == '(':
                idx += 1
                node = parse_expr()
                if idx >= len(tokens) or tokens[idx] != ')':
                    raise ValueError("Expected ')'")
                idx += 1
                return node
            else:
                words = []
                while idx < len(tokens) and tokens[idx] not in ('(', ')', 'AND', 'OR', 'and', 'or', 'And', 'Or'):
                    words.append(tokens[idx])
                    idx += 1
                if not words:
                    raise ValueError("Expected feature name")
                from grammar_dsl.dsl.visitor.ast_builder import _canonical_feature_from_tokens
                from grammar_dsl.dsl.ast import FeatureExpr
                return FeatureExpr(name=_canonical_feature_from_tokens(words))
                
        return parse_expr()

    def _render_expr_text(self, expr) -> str:
        from grammar_dsl.dsl.ast import FeatureExpr, StatusExpr, ComparisonExpr, AndExpr, OrExpr
        if isinstance(expr, FeatureExpr):
            return expr.name
        if isinstance(expr, StatusExpr):
            return expr.status
        if isinstance(expr, ComparisonExpr):
            number = int(expr.value) if expr.value == int(expr.value) else expr.value
            return f"{expr.field} {expr.operator} {number}"
        if isinstance(expr, AndExpr):
            return f"({self._render_expr_text(expr.left)} AND {self._render_expr_text(expr.right)})"
        if isinstance(expr, OrExpr):
            return f"({self._render_expr_text(expr.left)} OR {self._render_expr_text(expr.right)})"
        return ""


