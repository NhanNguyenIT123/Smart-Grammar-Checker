from __future__ import annotations

import os
import re
from dataclasses import asdict
from typing import Any

from grammar_dsl.data import get_repository
from grammar_dsl.dsl import ParserService
from grammar_dsl.dsl.ast import (
    AndExpr,
    ComparisonExpr,
    CreateQuizCommand,
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
from grammar_dsl.dsl.exceptions import DSLParseError
from grammar_dsl.engine import GrammarChecker, SpellingChecker, SuggestionEngine, SynonymEngine, VerbEngine
from grammar_dsl.engine.types import CommandResponse
from grammar_dsl.learning import ExerciseGenerator, QuizGrader
from grammar_dsl.personalization import RevisionPlanner, UserProfileStore
from grammar_dsl.services.spacy_detector import SpacyGrammarDetector


class CommandService:
    MULTI_COMMAND_PATTERN = re.compile(
        r"(?:[\r\n]+|[.!?;:]\s+)(check\s+grammar|revision\s+plan|reset\s+history|history|spell\s+\S+|verb\s+\S+|synonym\s+\S+|help|generate\b|create\s+quiz|submit\s+answers|show\s+students)\b",
        re.IGNORECASE,
    )
    LOOKUP_FALLBACK_PATTERN = re.compile(r"^(spell|verb|synonym)\s+(.+)$", re.IGNORECASE)

    def __init__(self, profile_store: UserProfileStore | None = None) -> None:
        repository = get_repository()
        self.repository = repository
        self.parser = ParserService()
        self.suggestion_engine = SuggestionEngine()
        self.verb_engine = VerbEngine(repository.verbs)
        self.synonym_engine = SynonymEngine(repository.synonyms)
        self.spelling_checker = SpellingChecker(
            repository.dictionary_words,
            self.suggestion_engine,
            self.verb_engine,
        )
        self.grammar_checker = GrammarChecker(repository, self.spelling_checker, self.verb_engine)
        self.profile_store = profile_store or UserProfileStore()
        self.revision_planner = RevisionPlanner(self.profile_store)
        self.exercise_generator = ExerciseGenerator(repository, self.verb_engine)
        self.quiz_grader = QuizGrader()
        self.spacy_detector = SpacyGrammarDetector(repository.grammar_rules)

    def execute(self, raw_input: str, user_id: str | None = None, context: dict[str, Any] | None = None) -> CommandResponse:
        resolved_user = self._resolve_user(user_id)

        # --- Deduplication guard -------------------------------------------------
        # A textarea can accidentally produce multiple copies of the same command
        # (e.g. the user pressed Enter after typing then clicked Run, leaving two
        # identical lines).  If every non-empty line is the same string, silently
        # collapse them to one line so the command still succeeds.
        raw_lines = [ln.strip() for ln in raw_input.splitlines() if ln.strip()]
        if len(raw_lines) > 1 and len(set(ln.lower() for ln in raw_lines)) == 1:
            raw_input = raw_lines[0]
        # -------------------------------------------------------------------------

        text = raw_input.strip()
        safe_context = context or {}
        if not text:
            response = CommandResponse(False, "invalid", "Input is empty.", {})
            self._record_response(resolved_user["username"], raw_input, response)
            return response

        multi_command_error = self._build_multi_command_error(text)
        if multi_command_error is not None:
            self._record_response(resolved_user["username"], text, multi_command_error)
            return multi_command_error


        try:
            command = self.parser.parse(text)
        except DSLParseError:
            # Fallback for lookup commands whose argument collides with DSL keywords
            # (e.g. "spell generate", "verb show", "synonym create").
            lookup_match = self.LOOKUP_FALLBACK_PATTERN.match(text)
            if lookup_match:
                lookup_command = lookup_match.group(1).strip().lower()
                lookup_word = lookup_match.group(2).strip()
                if lookup_word:
                    if lookup_command == "spell":
                        response = self._handle_spell_lookup(lookup_word)
                    elif lookup_command == "verb":
                        response = self._handle_verb_lookup(lookup_word)
                    else:
                        response = self._handle_synonym_lookup(lookup_word)
                    self._record_response(resolved_user["username"], text, response)
                    return response

            suggestions = self.suggestion_engine.suggest_command_inputs(text)
            if text.lower().startswith("show token "):
                suggestions.append("show tokens " + text[11:])
            submit_format_suggestions = self._build_submit_answers_format_suggestions(text, safe_context)
            if submit_format_suggestions:
                submit_like = [
                    suggestion
                    for suggestion in suggestions
                    if suggestion.lower().startswith("submit answers for quiz")
                    and "{" in suggestion
                    and "}" in suggestion
                    and "=" in suggestion
                ]
                suggestions = [*submit_like, *submit_format_suggestions]
            suggestions = list(dict.fromkeys(suggestions))
            message = (
                f"Command not recognized. Did you mean: {' | '.join(suggestions)}?"
                if suggestions
                else "Command not recognized. Type 'help' to see the list of supported GrammarDSL commands."
            )
            response = CommandResponse(
                success=False,
                command="invalid",
                message=message,
                data={},
                suggestions=suggestions,
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, GrammarCheckCommand):
            analysis_dict = self._check_grammar_with_stable_backend(command.paragraph)
            total_issues = len(analysis_dict.get("grammar_errors", []))
            message = (
                f"Analyzed {analysis_dict.get('sentence_count', 1)} sentence(s) and found {total_issues} issue(s)."
                if total_issues
                else "No obvious grammar issues were found by the rule-based checker."
            )
            response = CommandResponse(
                True,
                "check grammar",
                message,
                self._with_pipeline_context(analysis_dict),
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, GenerateExerciseCommand):
            response = self._handle_generate(command, resolved_user, text)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, CreateQuizCommand):
            response = self._handle_create_quiz(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, SubmitAnswersCommand):
            response = self._handle_submit_answers(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, ShowStudentsCommand):
            response = self._handle_show_students(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, ShowQuizCommand):
            response = self._handle_show_quiz(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, ShowClassCommand):
            response = self._handle_show_class(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response


        if isinstance(command, ShowResultsCommand):
            response = self._handle_show_results(command, resolved_user, safe_context)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, RevisionPlanCommand):
            plan = self.revision_planner.build_plan(resolved_user["username"])
            reviewed_submissions = int(plan["summary"].get("reviewed_submissions", 0))
            response = CommandResponse(
                success=True,
                command="revision plan",
                message=(
                    "No personalized revision plan yet. Run a few check grammar commands first."
                    if reviewed_submissions == 0
                    else f"Built a personalized revision plan from {reviewed_submissions} checked submission(s)."
                ),
                data=plan,
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, HistoryCommand):
            history = self.profile_store.get_command_history(resolved_user["username"], limit=command.limit)
            response = CommandResponse(
                success=True,
                command="history",
                message=(
                    "No command history yet."
                    if history["total_commands"] == 0
                    else f'Loaded {len(history["entries"])} command(s) from your history.'
                ),
                data=history,
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, ResetHistoryCommand):
            deleted_runs = self.profile_store.clear_user_history(resolved_user["username"])
            return CommandResponse(
                success=True,
                command="reset history",
                message=(
                    "Your history was already empty."
                    if deleted_runs == 0
                    else f"Cleared {deleted_runs} tracked command run(s) for the current user."
                ),
                data={"deleted_runs": deleted_runs},
            )

        if isinstance(command, ShowTokensCommand):
            inspection = self.parser.inspect(command.source_text)
            response = CommandResponse(
                success=True,
                command="show tokens",
                message=f"Analyzed input syntax and generated {inspection['token_count']} token(s).",
                data=inspection,
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, VerbLookupCommand):
            response = self._handle_verb_lookup(command.word)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, SpellLookupCommand):
            response = self._handle_spell_lookup(command.word)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, SynonymLookupCommand):
            response = self._handle_synonym_lookup(command.word)
            self._record_response(resolved_user["username"], text, response)
            return response

        if isinstance(command, HelpCommand):
            response = CommandResponse(
                success=True,
                command="help",
                message="GrammarDSL command reference.",
                data={
                    "commands": self._help_commands(),
                    "common_commands": [entry for entry in self._help_commands() if entry["audience"] == "everyone"],
                    "tutor_commands": [entry for entry in self._help_commands() if entry["audience"] == "tutor"],
                    "student_commands": [entry for entry in self._help_commands() if entry["audience"] == "student"],
                    "coverage_matrix": self.repository.grammar_rules.get("coverage_matrix", []),
                    "pipeline_summary": self.repository.pipeline_summary,
                    "source_manifest": self.repository.source_manifest,
                    "rule_details": self.repository.phrase_index,
                },
            )
            self._record_response(resolved_user["username"], text, response)
            return response

        response = CommandResponse(False, "unknown", "Unsupported command node.", {})
        self._record_response(resolved_user["username"], text, response)
        return response

    def _resolve_user(self, user_id: str | None) -> dict[str, Any]:
        normalized = (user_id or "local-session").strip().lower() or "local-session"
        user = self.profile_store.get_user_by_username(normalized)
        if user is not None:
            return user
        return {
            "id": normalized,
            "username": normalized,
            "display_name": normalized.replace("-", " ").title(),
            "role": "student",
        }

    def _handle_generate(self, command: GenerateExerciseCommand, user: dict[str, Any], raw_input: str) -> CommandResponse:
        if command.requested_count is None and not command.singular_form_requested:
            return CommandResponse(
                success=False,
                command="generate",
                message='Use either "generate exercise with ..." or "generate <N> exercises with ...".',
                data={},
            )
        if command.requested_count is not None and command.requested_count < 1:
            return CommandResponse(
                success=False,
                command="generate",
                message="Exercise count must be at least 1.",
                data={},
            )
        payload = self.exercise_generator.generate(
            command.feature_expr,
            requested_count=command.requested_count,
            singular_form_requested=command.singular_form_requested,
        )
        payload["raw_feature_text"] = command.raw_feature_text
        payload["generated_by"] = user["username"]
        payload["mode"] = "playground"
        count = len(payload["items"])
        return CommandResponse(
            success=True,
            command="generate",
            message=f"Generated {count} exercise(s) from the requested grammar features.",
            data=payload,
        )

    def _handle_create_quiz(self, command: CreateQuizCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        if user.get("role") != "tutor":
            return CommandResponse(
                success=False,
                command="create quiz",
                message="Only tutors can create quizzes.",
                data={},
            )
        if command.requested_count < 1:
            return CommandResponse(
                success=False,
                command="create quiz",
                message="Quiz exercise count must be at least 1.",
                data={},
            )
        class_id = self._context_int(context, "classId")
        if class_id is None:
            return CommandResponse(
                success=False,
                command="create quiz",
                message="Select a class first, then run the create quiz command inside that class context.",
                data={},
            )
        generated = self.exercise_generator.generate(command.feature_expr, requested_count=command.requested_count)
        try:
            quiz = self.profile_store.create_quiz(
                class_id=class_id,
                created_by=user["username"],
                title=command.title,
                feature_expr_text=command.raw_feature_text,
                exercise_count=len(generated["items"]),
                exercise_payload=generated["items"],
                answer_key_payload=[
                    {
                        "question_id": index,
                        "expected_answer": item["expected_answer"],
                        "accepted_variants": item.get("accepted_variants", []),
                    }
                    for index, item in enumerate(generated["items"], start=1)
                ],
            )
        except ValueError as e:
            return CommandResponse(
                success=False,
                command="create quiz",
                message=str(e),
                data={},
            )
        return CommandResponse(
            success=True,
            command="create quiz",
            message=f'Created quiz "{quiz["title"]}" with {quiz["exercise_count"]} exercise(s).',
            data={
                "quiz_id": quiz["id"],
                "title": quiz["title"],
                "class_id": quiz["class_id"],
                "exercise_count": quiz["exercise_count"],
                "feature_expr_text": quiz["feature_expr_text"],
                "items": quiz["exercise_payload"],
                "created_at": quiz["created_at"],
            },
        )

    def _handle_submit_answers(self, command: SubmitAnswersCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        if user.get("role") != "student":
            return CommandResponse(
                success=False,
                command="submit answers",
                message="Only students can submit quiz answers.",
                data={},
            )
        context_quiz_id = self._context_int(context, "quizId")
        if context_quiz_id is not None and context_quiz_id != command.quiz_id:
            return CommandResponse(
                success=False,
                command="submit answers",
                message="The selected quiz does not match the quiz id in your DSL command.",
                data={},
            )
        quiz = self.profile_store.get_quiz_detail(command.quiz_id, user["username"], "student")
        if quiz is None:
            return CommandResponse(
                success=False,
                command="submit answers",
                message="Quiz not found for the current student context.",
                data={},
            )
        grading = self.quiz_grader.grade(
            quiz,
            [asdict(entry) for entry in command.answers],
            self.grammar_checker,
        )
        self.profile_store.save_quiz_attempt(
            quiz_id=command.quiz_id,
            student_username=user["username"],
            score=grading["score"],
            max_score=grading["max_score"],
            submission_payload={
                "answers": [asdict(entry) for entry in command.answers],
                "grading": grading,
            },
            item_results=grading["item_results"],
        )
        return CommandResponse(
            success=True,
            command="submit answers",
            message=f'Submitted quiz {command.quiz_id}. Score: {grading["score"]}/{grading["max_score"]}.',
            data=grading,
        )

    def _handle_show_students(self, command: ShowStudentsCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        if user.get("role") != "tutor":
            return CommandResponse(
                success=False,
                command="show students",
                message="Only tutors can inspect scorebook rows.",
                data={},
            )
        
        quiz_id = command.quiz_id or self._context_int(context, "quizId")
        if quiz_id is None:
            return CommandResponse(
                success=False,
                command="show students",
                message="Select a quiz first, or specify one (e.g. show students for quiz 12).",
                data={},
            )
        
        rows = self.profile_store.get_quiz_attempts(quiz_id, user["username"])
        
        if command.filter_expr:
            filtered = [row for row in rows if self._matches_student_filter(command.filter_expr, row)]
        else:
            filtered = rows
            
        return CommandResponse(
            success=True,
            command="show students",
            message=f"Loaded {len(filtered)} student row(s) for quiz {quiz_id}.",
            data={
                "quiz_id": quiz_id,
                "rows": filtered,
                "total_rows": len(rows),
                "matched_rows": len(filtered),
            },
        )

    def _handle_show_quiz(self, command: ShowQuizCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        quiz_id = command.quiz_id or self._context_int(context, "quizId")
        if quiz_id is None:
            return CommandResponse(
                success=False,
                command="show quiz",
                message="Select a quiz first, or specify one (e.g. show quiz 12).",
                data={},
            )
        
        detail = self.profile_store.get_quiz_detail(quiz_id, user["username"], user.get("role", "student"))
        if not detail:
            return CommandResponse(
                success=False,
                command="show quiz",
                message=f"Quiz {quiz_id} not found or access denied.",
                data={},
            )
            
        # Ensure items key is present for the frontend
        if detail and "exercise_payload" in detail and "items" not in detail:
            detail["items"] = detail["exercise_payload"]
            
        return CommandResponse(
            success=True,
            command="show quiz",
            message=f"Loaded details for quiz {quiz_id}: {detail.get('title')}",
            data=detail,
        )

    def _handle_show_class(self, command: ShowClassCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        class_id = command.class_id
        class_data = self.profile_store.get_class_detail(class_id, user["username"], user["role"])
        
        if not class_data:
            return CommandResponse(
                success=False,
                command="show class",
                message=f"Class with ID {class_id} not found or you don't have access.",
                data={},
            )

        rows = []
        for member in class_data.get("students", []):
            rows.append({
                "username": member["username"],
                "student_name": member["display_name"],
                "role": member["role"],
                "focus_hint": member["focus_hint"],
            })

        return CommandResponse(
            success=True,
            command="show class",
            message=f"Loaded roster for class {class_id}.",
            data={
                "class_id": class_id,
                "rows": rows,
                "total_students": len(rows),
            },
        )

    def _handle_show_results(self, command: ShowResultsCommand, user: dict[str, Any], context: dict[str, Any]) -> CommandResponse:
        if user.get("role") != "tutor":
            return CommandResponse(
                success=False,
                command="show results",
                message="Only tutors can inspect individual student results.",
                data={},
            )
        
        quiz_id = command.quiz_id or self._context_int(context, "quizId")
        if quiz_id is None:
            return CommandResponse(
                success=False,
                command="show results",
                message="Select a quiz first to inspect student results.",
                data={},
            )
            
        # Get attempt for this student
        rows = self.profile_store.get_quiz_attempts(quiz_id, user["username"])
        # In store.py, the row has "username", not "student_username"
        student_row = next((r for r in rows if r["username"].lower() == command.student_username.lower()), None)
        
        if not student_row or student_row["status"] != "submitted":
            return CommandResponse(
                success=False,
                command="show results",
                message=f"No submission found for student '{command.student_username}' in quiz {quiz_id}.",
                data={},
            )
            
        # The row already contains the submission_payload (which contains the grading)
        grading = student_row.get("submission_payload", {}).get("grading")
        
        return CommandResponse(
            success=True,
            command="show results",
            message=f"Loaded results for {student_row['student_name']} in quiz {quiz_id}.",
            data={
                "student_name": student_row["student_name"],
                "score": student_row["score"],
                "max_score": student_row["max_score"],
                "grading": grading,
            },
        )

    def _matches_student_filter(self, expr, row: dict[str, Any]) -> bool:
        if isinstance(expr, AndExpr):
            return self._matches_student_filter(expr.left, row) and self._matches_student_filter(expr.right, row)
        if isinstance(expr, OrExpr):
            return self._matches_student_filter(expr.left, row) or self._matches_student_filter(expr.right, row)
        if isinstance(expr, ComparisonExpr):
            score = row.get("score")
            max_score = row.get("max_score")
            if score is None:
                return False
            
            value = float(score)
            target = float(expr.value)
            
            if expr.is_percentage:
                if not max_score:
                    return False
                value = (value / float(max_score)) * 100
            
            if expr.operator == ">":
                return value > target
            if expr.operator == ">=":
                return value >= target
            if expr.operator == "<":
                return value < target
            if expr.operator == "<=":
                return value <= target
            return value == target
        if isinstance(expr, StatusExpr):
            status = expr.status.lower()
            row_status = str(row.get("status", "")).lower()
            if status == "submitted":
                return row_status == "submitted"
            if status == "not submitted":
                return row_status == "not submitted"
            score = row.get("score")
            max_score = row.get("max_score")
            if status == "passed":
                return score is not None and max_score and (float(score) / float(max_score)) >= QuizGrader.PASSING_RATIO
            if status == "failed":
                return score is not None and max_score and (float(score) / float(max_score)) < QuizGrader.PASSING_RATIO
            return False
        return False

    def _handle_verb_lookup(self, word: str) -> CommandResponse:
        forms = self.verb_engine.lookup(word)
        if forms is None:
            ranked = self.suggestion_engine.ranked_suggestions(word, self.repository.verbs.keys(), threshold=2, limit=3)
            message = f'No verb entry found for "{word}".'
            if ranked:
                message = f'No verb entry found for "{word}". Did you mean: {" | ".join(suggestion[0] for suggestion in ranked)}?'
            return CommandResponse(
                success=False,
                command="verb",
                message=message,
                data={},
                suggestions=[f"verb {suggestion[0]}" for suggestion in ranked],
            )

        return CommandResponse(
            success=True,
            command="verb",
            message="Verb forms loaded successfully.",
            data={
                "word": word.lower(),
                "forms": {"base": forms[0], "past": forms[1], "participle": forms[2]},
                "formatted": f"{forms[0]} - {forms[1]} - {forms[2]}",
            },
        )

    def _handle_spell_lookup(self, word: str) -> CommandResponse:
        normalized = word.lower()
        if normalized in self.repository.dictionary_words:
            return CommandResponse(
                success=True,
                command="spell",
                message=f'"{normalized}" is spelled correctly.',
                data={
                    "word": normalized,
                    "is_correct": True,
                    "closest_match": normalized,
                },
            )

        ranked = self.suggestion_engine.ranked_suggestions(normalized, self.repository.dictionary_words, threshold=2, limit=3)
        message = f'"{normalized}" is potentially misspelled.'
        if ranked:
            message = f'Did you mean: {" | ".join(suggestion[0] for suggestion in ranked)}?'
        return CommandResponse(
            success=True,
            command="spell",
            message=message,
            data={
                "word": normalized,
                "is_correct": False,
                "closest_match": ranked[0][0] if ranked else None,
                "distance": ranked[0][1] if ranked else None,
            },
            suggestions=[f"spell {suggestion[0]}" for suggestion in ranked],
        )

    def _handle_synonym_lookup(self, word: str) -> CommandResponse:
        synonyms = self.synonym_engine.lookup(word)
        if synonyms is None:
            ranked = self.suggestion_engine.ranked_suggestions(word, self.repository.synonyms.keys(), threshold=2, limit=3)
            message = f'No synonym entry found for "{word}".'
            if ranked:
                message = f'No synonym entry found for "{word}". Did you mean: {" | ".join(suggestion[0] for suggestion in ranked)}?'
            return CommandResponse(
                success=False,
                command="synonym",
                message=message,
                data={},
                suggestions=[f"synonym {suggestion[0]}" for suggestion in ranked],
            )

        return CommandResponse(
            success=True,
            command="synonym",
            message="Synonym list loaded successfully.",
            data={
                "word": word.lower(),
                "synonyms": synonyms,
                "formatted": ", ".join(synonyms),
            },
        )

    def _help_commands(self) -> list[dict[str, str]]:
        return [
            {
                "usage": "help",
                "description": "Show the supported GrammarDSL commands and pipeline coverage metrics.",
                "audience": "everyone",
            },
            {
                "usage": "check grammar <paragraph>",
                "description": "Run grammar, spelling, and semantic heuristics, then return a corrected version of the paragraph.",
                "audience": "everyone",
            },
            {
                "usage": "show tokens <command>",
                "description": "Display the token stream and parsing inspection payload for a given DSL command.",
                "audience": "everyone",
            },
            {
                "usage": "generate exercise with <feature-expr>",
                "description": "Generate one practice item from grammar features such as present simple, object pronoun, or subject-verb agreement.",
                "audience": "everyone",
            },
            {
                "usage": "generate <N> exercises with <feature-expr>",
                "description": "Generate multiple practice items with boolean feature conditions such as present simple AND affirmative.",
                "audience": "everyone",
            },
            {
                "usage": "revision plan",
                "description": "Show your recurring mistake patterns and a personalized revision checklist based on past grammar checks.",
                "audience": "everyone",
            },
            {
                "usage": "history",
                "description": "Show the recent DSL commands you have already run in this session profile.",
                "audience": "everyone",
            },
            {
                "usage": "reset history",
                "description": "Clear the stored command history and recurring-mistake profile for the current logged-in user.",
                "audience": "everyone",
            },
            {
                "usage": "spell <word>",
                "description": "Check whether a word matches the current dictionary and suggest the closest spelling.",
                "audience": "everyone",
            },
            {
                "usage": "verb <word>",
                "description": "Look up V1/V2/V3 for a verb.",
                "audience": "everyone",
            },
            {
                "usage": "synonym <word>",
                "description": "Look up synonyms for a word.",
                "audience": "everyone",
            },
            {
                "usage": 'create quiz "Title" with <N> exercises with <feature-expr>',
                "description": "Tutor-only command that creates a quiz inside the currently selected class.",
                "audience": "tutor",
            },
            {
                "usage": "show students with <filter-expr>",
                "description": "Tutor-only scorebook query inside the selected quiz, for example score > 8 AND submitted.",
                "audience": "tutor",
            },
            {
                "usage": "show class <id>",
                "description": "Display the full roster and focus hints for a specific class.",
                "audience": "tutor",
            },
            {
                "usage": "show quiz <id>",
                "description": "Inspect the structure and exercises of a specific quiz.",
                "audience": "tutor",
            },
            {
                "usage": "show students for quiz <quiz-id>",
                "description": "Tutor-only command to see participants and heatmap for a specific quiz.",
                "audience": "tutor",
            },
            {
                "usage": "show quiz <quiz-id>",
                "description": "Show the questions and metadata for a specific quiz.",
                "audience": "tutor",
            },
            {
                "usage": "show results for student <username>",
                "description": "Tutor-only command to see detailed grading for a specific student's submission.",
                "audience": "tutor",
            },
            {
                "usage": 'submit answers for quiz <quiz-id> { 1 = "..." ; 2 = "..." }',
                "description": "Student-only command that submits answers for the selected quiz.",
                "audience": "student",
            },
        ]

    def _with_pipeline_context(self, data: dict) -> dict:
        enriched = dict(data)
        enriched["pipeline_summary"] = self.repository.pipeline_summary
        enriched["source_manifest"] = self.repository.source_manifest
        return enriched

    def _check_grammar_with_stable_backend(self, paragraph: str) -> dict[str, Any]:
        only_ml = os.getenv("GRAMMAR_CHECK_ONLY_ML", "0").strip().lower() in {"1", "true", "yes", "on"}

        if only_ml:
            # Pure Local ML Mode: bypasses both static rulepack and SpaCy
            sentences = [s.strip() for s in re.split(r"[.!?]+", paragraph) if s.strip()]
            analysis_dict = {
                "paragraph": paragraph,
                "sentence_count": max(1, len(sentences)),
                "grammar_errors": [],
                "grammar_issues": [],
                "corrected_text": paragraph,
                "analysis_backend": "local-ml-only",
            }
            try:
                from grammar_dsl.services.local_ml import check_grammar_with_local_ml

                local_ml_result = check_grammar_with_local_ml(paragraph)
                local_errors = [
                    issue
                    for issue in local_ml_result.get("grammar_errors", [])
                    if issue.get("rule_id") != "SYSTEM_ERROR"
                ]

                if local_errors:
                    analysis_dict["grammar_errors"] = local_errors
                    analysis_dict["grammar_issues"] = local_errors
                    corrected_text = str(local_ml_result.get("corrected_text", "")).strip()
                    if corrected_text and corrected_text != paragraph:
                        analysis_dict["corrected_text"] = corrected_text
            except Exception:
                pass
            return analysis_dict

        # Always run deterministic local rules first so grammar checks stay available.
        analysis_dict = asdict(self.grammar_checker.check(paragraph))
        analysis_dict["analysis_backend"] = "rule-based"

        # Optional local-ML enrichment: disabled by default to keep startup fast/stable.
        enable_local_ml = os.getenv("GRAMMAR_CHECK_ENABLE_LOCAL_ML", "0").strip().lower() in {"1", "true", "yes", "on"}
        if enable_local_ml:
            try:
                from grammar_dsl.services.local_ml import check_grammar_with_local_ml

                local_ml_result = check_grammar_with_local_ml(paragraph)
                local_errors = [
                    issue
                    for issue in local_ml_result.get("grammar_errors", [])
                    if issue.get("rule_id") != "SYSTEM_ERROR"
                ]

                if local_errors:
                    analysis_dict["grammar_errors"] = [*analysis_dict.get("grammar_errors", []), *local_errors]
                    analysis_dict["grammar_issues"] = [*analysis_dict.get("grammar_issues", []), *local_errors]
                    corrected_text = str(local_ml_result.get("corrected_text", "")).strip()
                    if corrected_text and corrected_text != paragraph:
                        analysis_dict["corrected_text"] = corrected_text
                    analysis_dict["analysis_backend"] = "rule-based+local-ml"
            except Exception:
                # Any local-ML failure should degrade gracefully without breaking the command.
                pass

        enable_spacy_detector = os.getenv("GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if enable_spacy_detector:
            try:
                spacy_signals = self.spacy_detector.detect(paragraph, self.verb_engine)
                spacy_issues = self._resolve_spacy_signals(spacy_signals)
                if spacy_issues:
                    merged_errors = [*analysis_dict.get("grammar_errors", []), *spacy_issues]
                    deduped_errors = self._dedupe_issue_dicts(merged_errors)
                    analysis_dict["grammar_errors"] = deduped_errors
                    analysis_dict["grammar_issues"] = self._dedupe_issue_dicts(
                        [*analysis_dict.get("grammar_issues", []), *spacy_issues]
                    )
                    analysis_dict["analysis_backend"] = (
                        "rule-based+spacy"
                        if analysis_dict["analysis_backend"] == "rule-based"
                        else f'{analysis_dict["analysis_backend"]}+spacy'
                    )
            except Exception:
                pass

        return analysis_dict

    def _resolve_spacy_signals(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for signal in signals:
            detector_type = str(signal.get("detector_type", "")).strip().lower()
            evidence = str(signal.get("evidence", "")).strip()
            confidence = float(signal.get("confidence", 0.85))
            if not detector_type or not evidence:
                continue

            if detector_type == "auxiliary_base":
                auxiliary = str(signal.get("auxiliary", "do")).strip() or "do"
                suggestion = str(signal.get("suggested", "")).strip()
                if suggestion:
                    resolved.append(
                        {
                            "category": "Agreement",
                            "message": f'After "{auxiliary}", the main verb should be in base form.',
                            "rule_id": "SPACY-AUX-BASE",
                            "suggestion": suggestion,
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )
                continue

            if detector_type == "be_agreement":
                subject = str(signal.get("subject", "subject")).strip() or "subject"
                expected = str(signal.get("expected", "")).strip()
                if expected:
                    resolved.append(
                        {
                            "category": "Agreement",
                            "message": f'The subject "{subject}" should use "{expected}".',
                            "rule_id": "SPACY-BE-AGREEMENT",
                            "suggestion": expected,
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )
                continue

            if detector_type in {"sva_singular", "sva_plural"}:
                if detector_type == "sva_singular":
                    suggestion = str(signal.get("expected", "")).strip()
                    message = "Third-person singular subject likely needs singular verb form."
                    rule_id = "SPACY-SVA-SINGULAR"
                else:
                    base = str(signal.get("base", "")).strip()
                    suggestion = self.verb_engine.to_base(base) or base
                    message = "Plural subject likely needs base verb form."
                    rule_id = "SPACY-SVA-PLURAL"
                if suggestion:
                    resolved.append(
                        {
                            "category": "Agreement",
                            "message": message,
                            "rule_id": rule_id,
                            "suggestion": suggestion,
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )
                continue

            if detector_type == "article_usage":
                expected = str(signal.get("expected", "")).strip()
                next_token = str(signal.get("next_token", "")).strip()
                if expected:
                    message = f'Use "{expected}" before "{next_token}" here.' if next_token else f'Use "{expected}" here.'
                    resolved.append(
                        {
                            "category": "Determiner",
                            "message": message,
                            "rule_id": "SPACY-ARTICLE-USAGE",
                            "suggestion": expected,
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )
                continue

            if detector_type == "determiner_number":
                expected = str(signal.get("expected", "")).strip()
                noun = str(signal.get("noun", "")).strip()
                if expected:
                    message = f'Determiner should agree with noun "{noun}".' if noun else "Determiner should agree with noun number."
                    resolved.append(
                        {
                            "category": "Agreement",
                            "message": message,
                            "rule_id": "SPACY-DETERMINER-NUMBER",
                            "suggestion": expected,
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )
                continue

            if detector_type == "verb_preposition":
                verb = str(signal.get("verb", "")).strip() or "verb"
                expected_preposition = str(signal.get("expected_preposition", "")).strip()
                if expected_preposition:
                    resolved.append(
                        {
                            "category": "Preposition",
                            "message": f'"{verb}" usually takes a different preposition here.',
                            "rule_id": "SPACY-VERB-PREPOSITION",
                            "suggestion": f"{verb} {expected_preposition}",
                            "evidence": evidence,
                            "severity": "error",
                            "knowledge_source": "src-grammar-rulepack",
                            "confidence": confidence,
                        }
                    )

        return resolved

    @staticmethod
    def _dedupe_issue_dicts(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for issue in issues:
            key = (
                str(issue.get("category", "")).strip().lower(),
                str(issue.get("evidence", issue.get("token", ""))).strip().lower(),
                str(issue.get("suggestion", "")).strip().lower(),
                str(issue.get("message", "")).strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(issue)
        return deduped

    def _build_multi_command_error(self, text: str) -> CommandResponse | None:
        normalized = " ".join(text.split())
        lowered = normalized.lower()
        if not lowered.startswith("check grammar "):
            return None

        matches = list(self.MULTI_COMMAND_PATTERN.finditer(text))
        if not matches:
            return None

        first_command = self._extract_first_command_line(text)
        return CommandResponse(
            success=False,
            command="invalid_multi_command",
            message="It looks like you pasted multiple DSL commands into one input. Run one command at a time so history and revision plans stay accurate.",
            data={"detected_commands": [match.group(1) for match in matches[:4]]},
            suggestions=[first_command] if first_command else [],
        )

    @staticmethod
    def _extract_first_command_line(text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        return text.strip()

    def _build_submit_answers_format_suggestions(self, text: str, context: dict[str, Any]) -> list[str]:
        lowered = text.lower()
        if "submit" not in lowered and "answers" not in lowered:
            return []

        quiz_id = self._context_int(context, "quizId")
        if quiz_id is None:
            quiz_match = re.search(r"\bquiz\s+(\d+)\b", text, flags=re.IGNORECASE)
            if quiz_match:
                quiz_id = int(quiz_match.group(1))

        if quiz_id is None:
            return ['submit answers for quiz <quiz-id> { 1 = "..." ; 2 = "..." }']

        return [f'submit answers for quiz {quiz_id} {{ 1 = "..." ; 2 = "..." }}']

    def _record_response(self, user_id: str, raw_input: str, response: CommandResponse) -> None:
        if response.command in {"history", "help", "reset history", "unknown"}:
            return

        try:
            payload = self._build_history_payload(response)
            self.profile_store.log_command(
                user_id=user_id,
                command_text=raw_input,
                command_name=response.command,
                success=response.success,
                message=response.message,
                **payload,
            )
        except Exception:
            return

    def _build_history_payload(self, response: CommandResponse) -> dict:
        if response.command == "check grammar" and response.success:
            return self._analysis_log_payload(response.data, profile_eligible=True)

        return {
            "profile_eligible": False,
            "sentence_count": 0,
            "spelling_issue_count": 0,
            "grammar_error_count": 0,
            "semantic_warning_count": 0,
            "original_text": None,
            "corrected_text": None,
            "issues": [],
        }

    def _analysis_log_payload(self, analysis: dict, *, profile_eligible: bool) -> dict:
        spelling_issues = analysis.get("spelling_issues", [])
        grammar_errors = analysis.get("grammar_errors", [])
        semantic_warnings = analysis.get("semantic_warnings", [])

        issues = []
        for issue in grammar_errors:
            issues.append(
                {
                    "category": issue.get("category", "Grammar"),
                    "message": issue.get("message"),
                    "rule_id": issue.get("rule_id"),
                    "suggestion": issue.get("suggestion"),
                }
            )
        for warning in semantic_warnings:
            issues.append(
                {
                    "category": warning.get("category", "Semantic"),
                    "message": warning.get("message"),
                    "rule_id": warning.get("rule_id"),
                    "suggestion": warning.get("suggestion"),
                }
            )
        for suggestion in spelling_issues:
            issues.append(
                {
                    "category": "Spelling",
                    "message": f'{suggestion.get("token")} -> {suggestion.get("suggestion")}',
                    "rule_id": "SPELL-LEVENSHTEIN",
                    "suggestion": suggestion.get("suggestion"),
                }
            )

        return {
            "profile_eligible": profile_eligible,
            "sentence_count": analysis.get("sentence_count", 0),
            "spelling_issue_count": len(spelling_issues),
            "grammar_error_count": len(grammar_errors),
            "semantic_warning_count": len(semantic_warnings),
            "original_text": analysis.get("original_text"),
            "corrected_text": analysis.get("corrected_text"),
            "issues": issues,
        }

    @staticmethod
    def _context_int(context: dict[str, Any], key: str) -> int | None:
        value = context.get(key)
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
