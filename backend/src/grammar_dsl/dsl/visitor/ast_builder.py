from __future__ import annotations

from grammar_dsl.dsl.ast.nodes import (
    AndExpr,
    AnswerEntry,
    ComparisonExpr,
    CreateQuizCommand,
    FeatureExpr,
    GenerateExerciseCommand,
    GrammarCheckCommand,
    HistoryCommand,
    HelpCommand,
    OrExpr,
    ResetHistoryCommand,
    RevisionPlanCommand,
    ShowClassCommand,
    ShowQuizCommand,
    ShowResultsCommand,
    ShowStudentsCommand,
    ShowTokensCommand,
    SpellLookupCommand,
    StatusExpr,
    SubmitAnswersCommand,
    SynonymLookupCommand,
    VerbLookupCommand,
)
from grammar_dsl.dsl.generated.GrammarDSLVisitor import GrammarDSLVisitor


PUNCTUATION = {".", ",", "?", "!", ";", ":", ")"}
STICKY_TOKENS = {"'", "-", '"'}
HYPHEN_TEXT = {"-", "\u2013", "\u2014"}


def merge_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""

    result = tokens[0]
    for index, token in enumerate(tokens[1:], start=1):
        previous = tokens[index - 1]
        if token in PUNCTUATION:
            result += token
        elif token in STICKY_TOKENS or previous in STICKY_TOKENS:
            result += token
        else:
            result += f" {token}"
    return result


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _canonical_feature_from_tokens(tokens: list[str]) -> str:
    lowered = [token.lower() for token in tokens if token.strip()]
    if not lowered:
        return ""

    compact = " ".join(token for token in lowered if token not in HYPHEN_TEXT)
    compact = " ".join(compact.split())
    feature_map = {
        "present simple": "present simple",
        "simple present": "present simple",
        "past simple": "past simple",
        "simple past": "past simple",
        "future simple": "future simple",
        "simple future": "future simple",
        "present continuous": "present continuous",
        "continuous present": "present continuous",
        "present progressive": "present continuous",
        "past continuous": "past continuous",
        "continuous past": "past continuous",
        "past progressive": "past continuous",
        "future continuous": "future continuous",
        "continuous future": "future continuous",
        "future progressive": "future continuous",
        "present perfect": "present perfect",
        "perfect present": "present perfect",
        "past perfect": "past perfect",
        "perfect past": "past perfect",
        "future perfect": "future perfect",
        "perfect future": "future perfect",
        "present perfect continuous": "present perfect continuous",
        "present perfect progressive": "present perfect continuous",
        "past perfect continuous": "past perfect continuous",
        "past perfect progressive": "past perfect continuous",
        "future perfect continuous": "future perfect continuous",
        "future perfect progressive": "future perfect continuous",
        "subject-verb agreement": "subject-verb agreement",
        "subject verb agreement": "subject-verb agreement",
        "object pronoun": "object pronoun",
        "verb-preposition": "verb-preposition",
        "verb preposition": "verb-preposition",
        "svo": "svo",
        "affirmative": "affirmative",
        "negative": "negative",
        "interrogative": "interrogative",
    }
    return feature_map.get(compact, compact)


def _fold_boolean_nodes(values: list, node_type):
    if not values:
        return None
    current = values[0]
    for value in values[1:]:
        current = node_type(left=current, right=value)
    return current


class ASTBuilder(GrammarDSLVisitor):
    def visitCommand(self, ctx):  # type: ignore[override]
        for child in ctx.getChildren():
            value = self.visit(child)
            if value is not None:
                return value
        return None

    def visitGrammarCheckCmd(self, ctx):  # type: ignore[override]
        return GrammarCheckCommand(paragraph=self.visit(ctx.paragraph()))

    def visitShowTokensCmd(self, ctx):  # type: ignore[override]
        return ShowTokensCommand(source_text=self.visit(ctx.paragraph()))

    def visitGenerateExerciseCmd(self, ctx):  # type: ignore[override]
        quantity_spec = ctx.quantitySpec()
        requested_count = None
        singular = False
        if quantity_spec is not None:
            if getattr(quantity_spec, "count", None):
                requested_count = int(quantity_spec.count.text)
            else:
                singular = True
        feature_expr = self.visit(ctx.featureExpr())
        return GenerateExerciseCommand(
            requested_count=requested_count,
            feature_expr=feature_expr,
            raw_feature_text=self._render_expr_text(feature_expr),
            singular_form_requested=singular,
        )

    def visitCreateQuizCmd(self, ctx):  # type: ignore[override]
        feature_expr = self.visit(ctx.featureExpr())
        return CreateQuizCommand(
            title=_strip_quotes(ctx.title.text),
            requested_count=int(ctx.count.text),
            feature_expr=feature_expr,
            raw_feature_text=self._render_expr_text(feature_expr),
        )

    def visitSubmitAnswersCmd(self, ctx):  # type: ignore[override]
        entries = [self.visit(entry) for entry in ctx.answerEntry()]
        return SubmitAnswersCommand(
            quiz_id=int(ctx.quizId.text),
            answers=entries,
        )

    def visitAnswerEntry(self, ctx):  # type: ignore[override]
        return AnswerEntry(
            question_id=int(ctx.questionId.text),
            answer_text=_strip_quotes(ctx.answerValue().getText()),
        )

    def visitShowStudentsCmd(self, ctx):  # type: ignore[override]
        quiz_id = None
        if getattr(ctx, "quizId", None):
            quiz_id = int(ctx.quizId.text)
        
        filter_expr = None
        if ctx.studentFilterExpr():
            filter_expr = self.visit(ctx.studentFilterExpr())
            
        return ShowStudentsCommand(filter_expr=filter_expr, quiz_id=quiz_id)

    def visitShowQuizCmd(self, ctx):  # type: ignore[override]
        return ShowQuizCommand(quiz_id=int(ctx.quizId.text))

    def visitShowClassCmd(self, ctx):  # type: ignore[override]
        return ShowClassCommand(class_id=int(ctx.classId.text))

    def visitShowResultsCmd(self, ctx):  # type: ignore[override]
        quiz_id = None
        if getattr(ctx, "quizId", None):
            quiz_id = int(ctx.quizId.text)
        return ShowResultsCommand(student_username=ctx.studentUsername.text, quiz_id=quiz_id)

    def visitStudentFilterExpr(self, ctx):  # type: ignore[override]
        return self.visit(ctx.studentFilterOrExpr())

    def visitStudentFilterOrExpr(self, ctx):  # type: ignore[override]
        exprs = ctx.studentFilterAndExpr()
        if not isinstance(exprs, list):
            exprs = [exprs]
        values = [self.visit(child) for child in exprs if child is not None]
        return _fold_boolean_nodes(values, OrExpr)

    def visitStudentFilterAndExpr(self, ctx):  # type: ignore[override]
        exprs = ctx.studentFilterPrimary()
        if not isinstance(exprs, list):
            exprs = [exprs]
        values = [self.visit(child) for child in exprs if child is not None]
        return _fold_boolean_nodes(values, AndExpr)

    def visitStudentFilterPrimary(self, ctx):  # type: ignore[override]
        if ctx.studentFilterExpr():
            return self.visit(ctx.studentFilterExpr())
        if ctx.comparisonExpr():
            return self.visit(ctx.comparisonExpr())
        return self.visit(ctx.statusExpr())

    def visitComparisonExpr(self, ctx):  # type: ignore[override]
        is_pct = False
        val_text = ""
        if getattr(ctx, "value", None):
            val_text = ctx.value.text
            if "%" in val_text:
                is_pct = True
                val_text = val_text.replace("%", "")
        
        return ComparisonExpr(
            field="score",
            operator=ctx.op.text,
            value=float(val_text or 0),
            is_percentage=is_pct
        )


    def visitStatusExpr(self, ctx):  # type: ignore[override]
        text = self._collect_rule_text(ctx).lower()
        if text == "not submitted":
            return StatusExpr(status="not submitted")
        return StatusExpr(status=text)

    def visitFeatureExpr(self, ctx):  # type: ignore[override]
        return self.visit(ctx.featureOrExpr())

    def visitFeatureOrExpr(self, ctx):  # type: ignore[override]
        exprs = ctx.featureAndExpr()
        if not isinstance(exprs, list):
            exprs = [exprs]
        values = [self.visit(child) for child in exprs if child is not None]
        return _fold_boolean_nodes(values, OrExpr)

    def visitFeatureAndExpr(self, ctx):  # type: ignore[override]
        exprs = ctx.featurePrimary()
        if not isinstance(exprs, list):
            exprs = [exprs]
        values = [self.visit(child) for child in exprs if child is not None]
        return _fold_boolean_nodes(values, AndExpr)

    def visitFeaturePrimary(self, ctx):  # type: ignore[override]
        if ctx.featureExpr():
            return self.visit(ctx.featureExpr())
        return self.visit(ctx.featureAtom())

    def visitFeatureAtom(self, ctx):  # type: ignore[override]
        tokens = [child.getText() for child in ctx.getChildren()]
        return FeatureExpr(name=_canonical_feature_from_tokens(tokens))

    def visitRevisionPlanCmd(self, ctx):  # type: ignore[override]
        return RevisionPlanCommand()

    def visitHistoryCmd(self, ctx):  # type: ignore[override]
        limit = 12
        if getattr(ctx, "limit", None):
            limit = int(ctx.limit.text)
        return HistoryCommand(limit=limit)

    def visitResetHistoryCmd(self, ctx):  # type: ignore[override]
        return ResetHistoryCommand()

    def visitVerbCmd(self, ctx):  # type: ignore[override]
        if getattr(ctx, "word", None):
            return VerbLookupCommand(word=ctx.word.text.lower())
        return VerbLookupCommand(word=self.visit(ctx.lookupWord()))

    def visitSpellCmd(self, ctx):  # type: ignore[override]
        if getattr(ctx, "word", None):
            return SpellLookupCommand(word=ctx.word.text.lower())
        return SpellLookupCommand(word=self.visit(ctx.lookupWord()))

    def visitSynonymCmd(self, ctx):  # type: ignore[override]
        if getattr(ctx, "word", None):
            return SynonymLookupCommand(word=ctx.word.text.lower())
        return SynonymLookupCommand(word=self.visit(ctx.lookupWord()))

    def visitHelpCmd(self, ctx):  # type: ignore[override]
        return HelpCommand()

    def _collect_terminal_tokens(self, ctx) -> list[str]:
        from antlr4.tree.Tree import TerminalNode
        tokens = []
        for i in range(ctx.getChildCount()):
            child = ctx.getChild(i)
            if isinstance(child, TerminalNode):
                tokens.append(child.getText())
            else:
                tokens.extend(self._collect_terminal_tokens(child))
        return tokens

    def visitParagraph(self, ctx):  # type: ignore[override]
        tokens = self._collect_terminal_tokens(ctx)
        return merge_tokens(tokens)

    def visitLookupWord(self, ctx):  # type: ignore[override]
        return ctx.getText().lower()

    def _collect_rule_text(self, ctx) -> str:
        tokens = [child.getText() for child in ctx.getChildren()]
        normalized_tokens: list[str] = []
        for token in tokens:
            if token in HYPHEN_TEXT:
                normalized_tokens.append("-")
            else:
                normalized_tokens.append(token)
        merged: list[str] = []
        for token in normalized_tokens:
            if token == "-":
                if merged:
                    merged[-1] = f"{merged[-1]}-"
                continue
            if merged and merged[-1].endswith("-"):
                merged[-1] = f"{merged[-1]}{token}"
            else:
                merged.append(token)
        return " ".join(merged)

    def _render_expr_text(self, expr) -> str:
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
