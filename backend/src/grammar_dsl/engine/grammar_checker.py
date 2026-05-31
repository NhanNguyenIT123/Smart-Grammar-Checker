from __future__ import annotations

import re

from grammar_dsl.data import DataRepository

from .spelling_checker import SpellingChecker
from .types import (
    CorrectionEntry,
    CoverageEntry,
    GrammarAnalysis,
    GrammarExplanation,
    GrammarIssue,
    KnowledgeHit,
    RuleTrace,
    TenseSignal,
    VocabularyBand,
)
from .verb_engine import VerbEngine


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['’‘][A-Za-z]+|['’‘])*(?:\))?|\d+|[.,!?;:()\-\"“”\u2013\u2014]")
TOKEN_WORD_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
PUNCTUATION_TOKENS = {".", ",", "!", "?", ";", ":", "-", ")", "\"", "”"}
DURATION_UNITS = {
    "second",
    "seconds",
    "minute",
    "minutes",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "year",
    "years",
}
DURATION_MARKERS = {"a", "an", "few", "many", "several", "long", "short"}
CLAUSE_CONNECTORS = {
    "and",
    "but",
    "because",
    "although",
    "while",
    "however",
    "therefore",
    "meanwhile",
    "or",
    "so",
}
COLLOCATION_NOUNS = {
    "research", "report", "attention", "advice", "feedback", "response",
    "conversation", "summary", "decision", "mistake", "homework",
    "explanation", "complaint", "suggestion", "truth", "plan", "traffic",
    "presentation", "slides", "jacket", "speaker", "workshop", "draft", "evaluation"
}
SINGULAR_REFERENCE_WORDS = {"he", "she", "it", "this", "that"}
PLURAL_REFERENCE_WORDS = {"we", "they", "you", "these", "those"}
SINGULAR_S_ENDING_NOUNS = {
    "economics",
    "linguistics",
    "mathematics",
    "news",
    "physics",
    "politics",
    "statistics",
}
IRREGULAR_PLURAL_NOUNS = {
    "children",
    "feet",
    "geese",
    "men",
    "mice",
    "people",
    "teeth",
    "women",
}
SINGULAR_DETERMINERS = {"a", "an", "this", "that"}
PLURAL_DETERMINERS = {"these", "those"}
INVERTED_OPENERS = {"here", "neither", "nor", "there"}
WH_WORDS = {"what", "where", "when", "why", "how", "who", "whom", "whose", "which"}
NEGATED_AUXILIARY_MAP = {
    "aren't": "are",
    "arent": "are",
    "can't": "can",
    "cant": "can",
    "couldn't": "could",
    "couldnt": "could",
    "didn't": "did",
    "didnt": "did",
    "doesn't": "does",
    "doesnt": "does",
    "don't": "do",
    "dont": "do",
    "hadn't": "had",
    "hadnt": "had",
    "hasn't": "has",
    "hasnt": "has",
    "haven't": "have",
    "havent": "have",
    "isn't": "is",
    "isnt": "is",
    "shouldn't": "should",
    "shouldnt": "should",
    "wasn't": "was",
    "wasnt": "was",
    "weren't": "were",
    "werent": "were",
    "won't": "will",
    "wont": "will",
    "wouldn't": "would",
    "wouldnt": "would",
}
SUBJECT_FORM_TO_OBJECT_FORM = {
    "he": "him",
    "i": "me",
    "she": "her",
    "they": "them",
    "we": "us",
    "who": "whom",
}


class GrammarChecker:
    def __init__(
        self,
        repository: DataRepository,
        spelling_checker: SpellingChecker,
        verb_engine: VerbEngine,
    ) -> None:
        self.repository = repository
        self.spelling_checker = spelling_checker
        self.verb_engine = verb_engine
        self.rules = repository.grammar_rules
        self.preposition_words = set(self.rules["preposition_words"])
        self.auxiliaries = set(self.rules["auxiliaries"])
        self.modals = set(self.rules["modals"])
        self.determiners = set(self.rules["determiners"])
        self.uncountable_nouns = {token.lower() for token in self.rules.get("uncountable_nouns", [])}
        self.subject_words = {
            token.lower()
            for subject_group in self.rules.get("subjects", {}).values()
            for token in subject_group
        }
        self.semantic_patterns = self.rules.get("semantic_patterns", {})
        self.coverage_matrix = [CoverageEntry(**item) for item in self.rules.get("coverage_matrix", [])]
        self.source_manifest_by_id = {
            str(item.get("id")): item
            for item in repository.source_manifest
            if isinstance(item, dict) and item.get("id")
        }
        self.clause_connectors = CLAUSE_CONNECTORS | set(self.rules.get("linking_words", {}).get("subordinators", [])) | {"after", "before"}
        self.collocation_lead_verbs = {
            phrase_tokens[0]
            for rule in self.semantic_patterns.get("unlikely_phrases", [])
            for phrase_tokens in [self._normalize_phrase(str(rule.get("phrase", "")))]
            if len(phrase_tokens) >= 2
        }
        self.collocation_lead_verbs.update(
            phrase_tokens[0]
            for rule in self.semantic_patterns.get("unlikely_phrases", [])
            for phrase_tokens in [self._normalize_phrase(str(rule.get("replacement", "")))]
            if len(phrase_tokens) >= 2
        )
        self.time_expression_tokens = {
            token
            for expressions in self.rules.get("time_expressions", {}).values()
            for expression in expressions
            for token in self._normalize_phrase(expression)
        }
        self.pronoun_words = self.subject_words | {
            "me",
            "him",
            "her",
            "us",
            "them",
            "someone",
            "somebody",
            "something",
            "anyone",
            "anybody",
            "anything",
            "everyone",
            "everybody",
            "everything",
            "nothing",
        }
        self.semantic_stop_words = {
            "after",
            "before",
            "daily",
            "during",
            "everyday",
            "early",
            "evening",
            "late",
            "morning",
            "night",
            "outside",
            "inside",
            "through",
            "today",
            "tonight",
            "while",
        }
        self.semantic_boundary_words = (
            self.preposition_words
            | self.subject_words
            | self.auxiliaries
            | self.modals
            | self.time_expression_tokens
            | self.semantic_stop_words
            | self.clause_connectors
        )

    def check(self, text: str) -> GrammarAnalysis:
        sentences = self._split_sentences(text)
        spelling_issues = []
        grammar_issues = []
        grammar_errors = []
        semantic_warnings = []
        detected_tenses: list[TenseSignal] = []
        corrected_sentences: list[str] = []
        corrections: list[CorrectionEntry] = []

        for sentence in sentences:
            sentence_analysis = self._analyze_sentence(sentence)
            spelling_issues.extend(sentence_analysis["spelling_issues"])
            grammar_issues.extend(sentence_analysis["grammar_issues"])
            grammar_errors.extend(sentence_analysis["grammar_errors"])
            semantic_warnings.extend(sentence_analysis["semantic_warnings"])
            detected_tenses.extend(sentence_analysis["detected_tenses"])
            corrected_sentences.append(sentence_analysis["corrected_sentence"])
            corrections.extend(sentence_analysis["corrections"])

        normalized_text = " ".join(sentence.strip() for sentence in sentences if sentence.strip())
        corrected_text = " ".join(sentence.strip() for sentence in corrected_sentences if sentence.strip())
        vocabulary_profile = self._build_vocabulary_profile(corrected_text or normalized_text)
        knowledge_hits = self._build_knowledge_hits(
            spelling_issues=spelling_issues,
            grammar_errors=grammar_errors,
            semantic_warnings=semantic_warnings,
            detected_tenses=detected_tenses,
            corrections=corrections,
            vocabulary_profile=vocabulary_profile,
        )
        return GrammarAnalysis(
            original_text=text,
            normalized_text=normalized_text,
            corrected_text=corrected_text or normalized_text,
            sentence_count=len(sentences),
            spelling_issues=spelling_issues,
            grammar_issues=grammar_issues,
            grammar_errors=grammar_errors,
            semantic_warnings=semantic_warnings,
            detected_tenses=detected_tenses,
            corrections=corrections,
            vocabulary_profile=vocabulary_profile,
            knowledge_hits=knowledge_hits,
        )


    def _split_sentences(self, text: str) -> list[str]:
        if not text:
            return []
        parts = re.split(r'([.?!]+\s+)', text)
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            sentences.append(parts[i] + parts[i+1])
        if len(parts) % 2 == 1:
            sentences.append(parts[-1])
        return [s.strip() for s in sentences if s.strip()]

    def _analyze_sentence(self, sentence: str) -> dict:
        tokens = self._tokenize(sentence)
        words = [t for t in tokens if t and t[0].isalnum()]
        spelling_issues = self.spelling_checker.check_words(words)
        grammar_words = self._apply_spelling_to_words(words, spelling_issues)
        time_signals = self._detect_time_expressions(sentence)
        
        detected_tenses: list[TenseSignal] = []
        for clause in self._segment_clauses(sentence):
            clause_words = clause["words"]
            clause_tense = self._detect_surface_tense(clause_words)
            if clause_tense and not any(t.name == clause_tense.name for t in detected_tenses):
                detected_tenses.append(clause_tense)

        if not detected_tenses:
            whole_tense = self._detect_surface_tense(grammar_words)
            if whole_tense:
                detected_tenses.append(whole_tense)

        surface_tense = detected_tenses[0] if detected_tenses else None

        for sig in time_signals:
            if not any(t.name == sig.name for t in detected_tenses):
                detected_tenses.append(sig)
        
        grammar_issues = []
        grammar_issues.extend(self._check_sentence_capitalization(sentence, tokens))
        grammar_issues.extend(self._check_subject_verb_agreement(sentence, grammar_words, surface_tense))
        grammar_issues.extend(self._check_clause_tense_consistency(
            sentence=sentence,
            semantic_preview_sentence=sentence,
            sentence_time_signals=time_signals,
            existing_issues=grammar_issues
        ))
        grammar_issues.extend(self._check_negative_auxiliary_forms(sentence, grammar_words))
        grammar_issues.extend(self._check_prepositions(sentence, grammar_words))
        grammar_issues.extend(self._check_object_pronoun_case(sentence, grammar_words))
        grammar_issues.extend(self._check_determiner_noun_agreement(sentence, grammar_words))
        grammar_issues.extend(self._check_relative_clause_agreement(sentence, grammar_words))
        grammar_issues.extend(self._check_linking_words(sentence, tokens))
        grammar_issues.extend(self._check_auxiliary_main_verb_consistency(sentence, grammar_words))
        grammar_issues.extend(self._check_basic_svo(sentence, grammar_words))
        
        semantic_warnings = self._check_semantic_plausibility(sentence, grammar_words)
        
        corrected_sentence, corrections = self._build_corrected_sentence(
            sentence, tokens, spelling_issues, grammar_issues + semantic_warnings
        )
        
        return {
            "tokens": tokens,
            "words": words,
            "spelling_issues": spelling_issues,
            "grammar_issues": grammar_issues,
            "grammar_errors": [i for i in grammar_issues if i.severity == "error"],
            "semantic_warnings": semantic_warnings,
            "time_signals": time_signals,
            "surface_tense": surface_tense,
            "detected_tenses": detected_tenses,
            "corrected_sentence": corrected_sentence,
            "corrections": corrections,
        }

    def _tokenize(self, text: str) -> list[str]:
        return WORD_PATTERN.findall(text)

    def _detect_time_expressions(self, text: str) -> list[TenseSignal]:
        signals = []
        time_data = self.rules.get("time_expressions", {})
        for tense_name, patterns in time_data.items():
            for pattern in patterns:
                if re.search(r'\b' + re.escape(pattern) + r'\b', text, re.IGNORECASE):
                    if pattern.lower() == "for":
                        time_words = {
                            "hour", "hours", "minute", "minutes", "day", "days",
                            "week", "weeks", "month", "months", "year", "years",
                            "decade", "decades", "century", "centuries", "time", "long"
                        }
                        lowered_text = text.lower()
                        for_match = re.search(r'\bfor\b', lowered_text)
                        if for_match:
                            after_for = lowered_text[for_match.end():]
                            words_after = set(re.findall(r'\b[a-z]+\b', after_for))
                            if not (words_after & time_words):
                                continue
                    signals.append(TenseSignal(name=tense_name, source="time-expressions", evidence=pattern))
        
        # Remove sub-phrase duplicates
        filtered_signals = []
        for s1 in signals:
            is_sub = False
            for s2 in signals:
                if s1 is not s2 and s1.evidence.lower() in s2.evidence.lower():
                    is_sub = True
                    break
            if not is_sub:
                filtered_signals.append(s1)
        return filtered_signals

    def _detect_surface_tense(self, words: list[str]) -> TenseSignal | None:
        if not words:
            return None
        
        lowered = [w.lower() for w in words]
        
        # 1. Future compound tenses (highest priority to avoid greedy will + verb simple matching)
        for i, word in enumerate(lowered):
            if word == "will":
                # Future Perfect Continuous: will have been working
                if i + 3 < len(lowered) and lowered[i+1] == "have" and lowered[i+2] == "been" and self.verb_engine.is_gerund(lowered[i+3]):
                    return TenseSignal(name="future_perfect_continuous", source="auxiliary", evidence=f"will have been {words[i+3]}")
                
                # Future Perfect: will have worked
                if i + 2 < len(lowered) and lowered[i+1] == "have" and (self.verb_engine.is_participle(lowered[i+2]) or self.verb_engine.is_past_form(lowered[i+2])):
                    return TenseSignal(name="future_perfect", source="auxiliary", evidence=f"will have {words[i+2]}")
                
                # Future Continuous: will be working
                if i + 2 < len(lowered) and lowered[i+1] == "be" and self.verb_engine.is_gerund(lowered[i+2]):
                    return TenseSignal(name="future_continuous", source="auxiliary", evidence=f"will be {words[i+2]}")
                
                # Future Simple: will work (possibly with 'not' or adverb in between)
                for j in range(i + 1, min(i + 4, len(lowered))):
                    if self._looks_like_verb(lowered[j]) and lowered[j] not in {"be", "have"}:
                        return TenseSignal(name="future_simple", source="auxiliary", evidence=f"will {words[j]}")

        # 2. Perfect and continuous compound tenses
        for i, word in enumerate(lowered):
            if word in {"have", "has", "had"}:
                # Perfect Continuous: have/has/had been working
                if i + 2 < len(lowered) and lowered[i+1] == "been" and self.verb_engine.is_gerund(lowered[i+2]):
                    name = "past_perfect_continuous" if word == "had" else "present_perfect_continuous"
                    return TenseSignal(name=name, source="auxiliary", evidence=f"{words[i]} been {words[i+2]}")
                
                # Perfect: have/has/had worked
                for j in range(i + 1, min(i + 4, len(lowered))):
                    if lowered[j] != "been" and (self.verb_engine.is_participle(lowered[j]) or self.verb_engine.is_past_form(lowered[j])):
                        name = "past_perfect" if word == "had" else "present_perfect"
                        return TenseSignal(name=name, source="auxiliary", evidence=f"{words[i]} {words[j]}")

            if word in {"am", "is", "are", "was", "were"}:
                # Continuous: am/is/are/was/were working
                for j in range(i + 1, min(i + 4, len(lowered))):
                    if self.verb_engine.is_gerund(lowered[j]):
                        name = "past_continuous" if word in {"was", "were"} else "present_continuous"
                        return TenseSignal(name=name, source="auxiliary", evidence=f"{words[i]} {words[j]}")

        # 3. Simple tenses (lexical verb only)
        predicate = self._detect_clause_predicate(words)
        if predicate:
            surface = str(predicate["surface"]).lower()
            if self.verb_engine.is_past_form(surface):
                return TenseSignal(name="past_simple", source="lexical-verb", evidence=str(predicate["surface"]))
            
            base = self.verb_engine.to_base(surface)
            if base:
                return TenseSignal(name="present_simple", source="lexical-verb", evidence=str(predicate["surface"]))

        return None
    def _check_subject_verb_agreement(
        self,
        sentence: str,
        words: list[str],
        surface_tense: TenseSignal | None,
    ) -> list[GrammarIssue]:
        if len(words) < 2:
            return []

        lowered = [word.lower() for word in words]
        verb_index = self._find_agreement_verb_index(words)
        if verb_index is None:
            return []

        # Interrogative Detection (Inversion)
        # Patterns: [Auxiliary/Modal] + [Subject] + [Verb]
        # Example: "Does she go", "Are you happy"
        is_interrogative = False
        subject_tokens: list[str] = []
        
        lower_first = words[0].lower()
        if verb_index == 0 or (verb_index == 1 and (lower_first in self.clause_connectors or lower_first in WH_WORDS)):
            # Potential question if it starts with auxiliary/modal or Wh- word + auxiliary/modal
            if verb_index + 1 < len(words):
                # Search for a subject candidate after the leading verb
                for j in range(verb_index + 1, min(verb_index + 4, len(words))):
                    if words[j].lower() in self.subject_words or words[j].lower() in self.determiners:
                        is_interrogative = True
                        # Collect subject tokens until next verb or end
                        subject_tokens = words[verb_index + 1 : j + 1]
                        break

        if is_interrogative:
            subject_profile = self._infer_subject_profile_from_tokens(subject_tokens)
        else:
            leading_time_end = self._leading_time_expression_end(words)
            if verb_index <= leading_time_end:
                return []
            subject_tokens = words[leading_time_end:verb_index]
            subject_profile = self._infer_subject_profile_from_tokens(subject_tokens)

        if subject_profile is None:
            return []

        subject = str(subject_profile["agreement_subject"])
        verb_token = lowered[verb_index]
        verb = NEGATED_AUXILIARY_MAP.get(verb_token, verb_token)
        is_negated = verb_token in NEGATED_AUXILIARY_MAP

        def get_suggestion(target_verb: str) -> str:
            if not is_negated:
                return target_verb
            # Find the negated version of the target_verb
            for negated, canonical in NEGATED_AUXILIARY_MAP.items():
                if canonical == target_verb:
                    if ("'" in verb_token) == ("'" in negated):
                        return negated
            return f"{target_verb}n't"

        if surface_tense and surface_tense.name not in {"present_simple", "present_continuous"} and verb not in {"am", "is", "are", "was", "were", "have", "has", "do", "does"}:
            return []

        if subject in SINGULAR_REFERENCE_WORDS:
            if verb == "are":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Third-person singular subject should use "is".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="is",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "were":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Third-person singular subject should use "was".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="was",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "have":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Third-person singular subject should use "has".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="has",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "do":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Third-person singular subject should use "does".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion=get_suggestion("does"),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if self._looks_like_base_verb(verb):
                base = self.verb_engine.to_base(verb) or verb
                return [
                    GrammarIssue(
                        category="Agreement",
                        message="Third-person singular subject needs a singular verb form.",
                        sentence=sentence,
                        evidence=words[verb_index],
                        suggestion=self.verb_engine.third_person_singular(base),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]

        if subject == "i":
            if verb in {"is", "are"}:
                return [
                    GrammarIssue(
                        "Agreement",
                        'The subject "I" should use "am".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="am",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if self.verb_engine.is_third_person_form(verb) and verb not in {"is", "has", "does"}:
                base = self.verb_engine.to_base(verb) or verb.rstrip("s")
                return [
                    GrammarIssue(
                        category="Agreement",
                        message='The subject "I" should use the base verb form here.',
                        sentence=sentence,
                        evidence=words[verb_index],
                        suggestion=base,
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "has":
                return [
                    GrammarIssue(
                        "Agreement",
                        'The subject "I" should use "have".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion=get_suggestion("have"),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "does":
                return [
                    GrammarIssue(
                        "Agreement",
                        'The subject "I" should use "do".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion=get_suggestion("do"),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]

        if subject in PLURAL_REFERENCE_WORDS:
            if verb == "is":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Plural subjects should use "are".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="are",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "was":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Plural subjects should use "were".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion="were",
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "has":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Plural subjects should use "have".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion=get_suggestion("have"),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if verb == "does":
                return [
                    GrammarIssue(
                        "Agreement",
                        'Plural subjects should use "do".',
                        sentence,
                        evidence=words[verb_index],
                        suggestion=get_suggestion("do"),
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]
            if self.verb_engine.is_third_person_form(verb) and verb not in {"is", "has", "does"}:
                base = self.verb_engine.to_base(verb) or verb.rstrip("s")
                return [
                    GrammarIssue(
                        category="Agreement",
                        message="This subject likely needs the base verb form, not the third-person singular form.",
                        sentence=sentence,
                        evidence=words[verb_index],
                        suggestion=base,
                        rule_id="RULE-SUBJECT-VERB",
                        knowledge_source="src-grammar-rulepack",
                    )
                ]

        return []

    def _check_clause_tense_consistency(
        self,
        *,
        sentence: str,
        semantic_preview_sentence: str,
        sentence_time_signals: list[TenseSignal],
        existing_issues: list[GrammarIssue],
    ) -> list[GrammarIssue]:
        if not sentence_time_signals:
            return []

        dominant_signal = max(
            sentence_time_signals,
            key=lambda signal: (len(self._normalize_phrase(signal.evidence)), signal.evidence),
        )

        seen_evidence = {
            str(issue.evidence or "").lower()
            for issue in existing_issues
            if issue.category == "Tense" and issue.evidence
        }
        issues: list[GrammarIssue] = []

        for clause in self._segment_clauses(semantic_preview_sentence):
            clause_words = clause["words"]
            clause_text = clause["text"]
            if len(clause_words) < 2:
                continue

            surface_tense = self._detect_surface_tense(clause_words)
            if surface_tense is None:
                continue

            local_signals = self._detect_time_expressions(clause_text)
            if local_signals and any(signal.name == surface_tense.name for signal in local_signals):
                continue
            if local_signals and not any(signal.name == dominant_signal.name for signal in local_signals):
                continue
            if surface_tense.name == dominant_signal.name:
                continue

            predicate = self._detect_clause_predicate(clause_words)
            if predicate is None:
                continue

            # For non-simple or compound tenses, replace the whole verb phrase
            if dominant_signal.name not in {"past_simple", "present_simple"} or surface_tense.name not in {"past_simple", "present_simple"}:
                surface_phrase = surface_tense.evidence
                if surface_phrase.lower() in seen_evidence:
                    continue

                subject = self._infer_conjugation_subject(clause_words, int(predicate["word_index"]))
                suggestion = self.verb_engine.suggest_for_tense(str(predicate["base"]), dominant_signal.name, subject)
                if not suggestion or suggestion.lower() == surface_phrase.lower():
                    continue

                seen_evidence.add(surface_phrase.lower())
                issues.append(
                    GrammarIssue(
                        category="Tense",
                        message=(
                            f'Clause-level timeline still points to {self._humanize_tense(dominant_signal.name)} '
                            f'because of "{dominant_signal.evidence}", so "{surface_phrase}" should align too.'
                        ),
                        sentence=sentence,
                        evidence=surface_phrase,
                        suggestion=suggestion,
                        rule_id="RULE-CLAUSE-TENSE-PROPAGATION",
                        knowledge_source="src-grammar-rulepack",
                        target_tense=dominant_signal.name,
                        source_tense=surface_tense.name,
                    )
                )
            else:
                surface_phrase = str(predicate["surface"])
                if surface_phrase.lower() in seen_evidence:
                    continue

                subject = self._infer_conjugation_subject(clause_words, int(predicate["word_index"]))
                suggestion = self.verb_engine.suggest_for_tense(str(predicate["base"]), dominant_signal.name, subject)
                if not suggestion or suggestion.lower() == surface_phrase.lower():
                    continue

                seen_evidence.add(surface_phrase.lower())
                issues.append(
                    GrammarIssue(
                        category="Tense",
                        message=(
                            f'Clause-level timeline still points to {self._humanize_tense(dominant_signal.name)} '
                            f'because of "{dominant_signal.evidence}", so "{surface_phrase}" should align too.'
                        ),
                        sentence=sentence,
                        evidence=surface_phrase,
                        suggestion=suggestion,
                        rule_id="RULE-CLAUSE-TENSE-PROPAGATION",
                        knowledge_source="src-grammar-rulepack",
                        target_tense=dominant_signal.name,
                        source_tense=surface_tense.name,
                    )
                )

        return issues

    def _check_negative_auxiliary_forms(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        if len(words) < 3:
            return []

        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]

        for index, token in enumerate(lowered[:-1]):
            canonical_aux = NEGATED_AUXILIARY_MAP.get(token)
            if canonical_aux not in {"do", "does", "did"}:
                continue

            next_word = lowered[index + 1]
            if not self._looks_like_verb(next_word):
                continue

            base = self.verb_engine.to_base(next_word) or next_word
            if next_word == base or next_word in self.collocation_lead_verbs:
                continue

            issues.append(
                GrammarIssue(
                    category="Agreement",
                    message=f'After "{words[index]}", the main verb should stay in the base form.',
                    sentence=sentence,
                    evidence=words[index + 1],
                    suggestion=base,
                    rule_id="RULE-NEGATIVE-AUXILIARY-BASE",
                    knowledge_source="src-grammar-rulepack",
                )
            )

        return issues

    def _check_prepositions(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]
        mappings: dict[str, list[str]] = self.rules["prepositions"]

        for index in range(len(lowered) - 1):
            surface_word = words[index]
            word = lowered[index]
            base_word = self.verb_engine.to_base(word) or word
            next_word = lowered[index + 1]
            if base_word not in mappings:
                continue

            allowed = mappings[base_word]
            if next_word in self.preposition_words:
                if next_word in allowed:
                    continue
                issues.append(
                    GrammarIssue(
                        category="Preposition",
                        message=f'"{base_word}" usually goes with a different preposition.',
                        sentence=sentence,
                        evidence=f"{surface_word} {words[index + 1]}",
                        suggestion=f"{surface_word} {allowed[0]}",
                        rule_id="RULE-PREPOSITION",
                        knowledge_source="src-grammar-rulepack",
                    )
                )
                continue

            if next_word in self.determiners or next_word in self.subject_words or next_word not in self.auxiliaries:
                issues.append(
                    GrammarIssue(
                        category="Preposition",
                        message=f'"{base_word}" usually needs the preposition "{allowed[0]}" before its object.',
                        sentence=sentence,
                        evidence=surface_word,
                        suggestion=f"{surface_word} {allowed[0]}",
                        rule_id="RULE-PREPOSITION",
                        knowledge_source="src-grammar-rulepack",
                    )
                )

        return issues

    def _check_object_pronoun_case(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]

        for index in range(1, len(lowered)):
            token = lowered[index]
            replacement = SUBJECT_FORM_TO_OBJECT_FORM.get(token)
            if replacement is None:
                continue

            previous = lowered[index - 1]
            next_word = lowered[index + 1] if index + 1 < len(lowered) else ""

            is_after_preposition = previous in self.preposition_words
            is_after_verb = self._looks_like_verb(previous)
            starts_new_clause = bool(next_word) and (
                next_word in self.auxiliaries or next_word in self.modals or self._looks_like_verb(next_word)
            )

            if not (is_after_preposition or is_after_verb):
                continue
            if starts_new_clause:
                continue

            issues.append(
                GrammarIssue(
                    category="Pronoun",
                    message=f'After "{words[index - 1]}", use the object pronoun form instead of "{words[index]}".',
                    sentence=sentence,
                    evidence=words[index],
                    suggestion=self._match_token_case(words[index], replacement),
                    rule_id="RULE-OBJECT-PRONOUN",
                    knowledge_source="src-grammar-rulepack",
                )
            )

        return issues

    def _check_determiner_noun_agreement(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]

        for index, token in enumerate(lowered):
            if token not in {"these", "those"}:
                continue

            for noun_index in range(index + 1, min(len(lowered), index + 4)):
                candidate = lowered[noun_index]
                if candidate in self.uncountable_nouns:
                    replacement = "this" if token == "these" else "that"
                    evidence = " ".join(words[index:noun_index + 1])
                    suggestion_tokens = [self._match_token_case(words[index], replacement), *words[index + 1:noun_index + 1]]
                    issues.append(
                        GrammarIssue(
                            category="Agreement",
                            message=f'"{words[noun_index]}" is usually uncountable here, so it should take a singular determiner.',
                            sentence=sentence,
                            evidence=evidence,
                            suggestion=" ".join(suggestion_tokens),
                            rule_id="RULE-DETERMINER-NOUN-AGREEMENT",
                            knowledge_source="src-grammar-rulepack",
                        )
                    )
                    break

                if candidate in self.preposition_words or candidate in self.auxiliaries or candidate in self.modals:
                    break

        return issues

    def _check_relative_clause_agreement(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]
        verb_map = {"is": "are", "was": "were", "has": "have", "does": "do"}

        for index in range(1, len(lowered) - 1):
            if lowered[index] != "which":
                continue
            if lowered[index + 1] not in verb_map:
                continue

            antecedent = lowered[index - 1]
            if not self._is_probably_plural_noun(antecedent):
                continue

            replacement = verb_map[lowered[index + 1]]
            issues.append(
                GrammarIssue(
                    category="Agreement",
                    message=f'The antecedent "{words[index - 1]}" is plural, so the relative clause should use "{replacement}".',
                    sentence=sentence,
                    evidence=f"{words[index]} {words[index + 1]}",
                    suggestion=f"{words[index]} {replacement}",
                    rule_id="RULE-RELATIVE-CLAUSE-AGREEMENT",
                    knowledge_source="src-grammar-rulepack",
                )
            )

        return issues

    def _check_linking_words(self, sentence: str, tokens: list[str]) -> list[GrammarIssue]:
        if not tokens:
            return []

        first = tokens[0].lower()
        comma_after = set(self.rules["linking_words"]["comma_after"])

        if first in comma_after and len(tokens) > 1 and tokens[1] != ",":
            return [
                GrammarIssue(
                    category="Linking Word",
                    message=f'"{tokens[0]}" usually needs a comma when it opens a sentence.',
                    sentence=sentence,
                    evidence=tokens[0],
                    suggestion=f"{tokens[0]},",
                    severity="error",
                    rule_id="RULE-LINKING-WORD",
                    knowledge_source="src-grammar-rulepack",
                )
            ]

        return []

    def _check_basic_svo(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        if not words:
            return []

        lowered = [word.lower() for word in words]
        issues: list[GrammarIssue] = []
        leading_time_end = self._leading_time_expression_end(words)
        leading_index = leading_time_end if leading_time_end < len(lowered) else 0

        if self._looks_like_base_verb(lowered[leading_index]) and lowered[leading_index] not in {"be", "have", "do"}:
            issues.append(
                GrammarIssue(
                    category="SVO",
                    message="The sentence may be missing an explicit subject before the verb.",
                    sentence=sentence,
                    suggestion=f'Add a subject before "{words[leading_index]}".',
                    severity="error",
                    rule_id="RULE-SVO-HEURISTIC",
                    knowledge_source="src-grammar-rulepack",
                )
            )

        if not any(self._looks_like_verb(token) for token in lowered):
            issues.append(
                GrammarIssue(
                    category="SVO",
                    message="No clear verb was detected in the sentence.",
                    sentence=sentence,
                    severity="error",
                    rule_id="RULE-SVO-HEURISTIC",
                    knowledge_source="src-grammar-rulepack",
                )
            )

        return issues

    def _check_semantic_plausibility(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        issues: list[GrammarIssue] = []
        lowered = [self._normalize_word_token(word) for word in words]
        seen_phrases: set[str] = set()

        for rule in self.semantic_patterns.get("unlikely_phrases", []):
            phrase_tokens = self._normalize_phrase(rule["phrase"])
            if not phrase_tokens:
                continue
            for index in range(len(lowered) - len(phrase_tokens) + 1):
                if lowered[index:index + len(phrase_tokens)] != phrase_tokens:
                    continue
                phrase = " ".join(words[index:index + len(phrase_tokens)])
                seen_phrases.add(phrase.lower())
                issues.append(
                    GrammarIssue(
                        category="Semantic",
                        message=rule["message"],
                        sentence=sentence,
                        evidence=phrase,
                        suggestion=rule.get("suggestion"),
                        replacement=rule.get("replacement"),
                        severity="warning",
                        rule_id="RULE-SEMANTIC-COLLOCATION",
                        knowledge_source=self._semantic_rule_source(rule),
                    )
                )

        destination_rules = self.semantic_patterns.get("verb_destination_expectations", {})
        for rule in destination_rules.values():
            trigger = [token.lower() for token in rule.get("trigger", [])]
            if len(trigger) < 2:
                continue
            allowed_destinations = {token.lower() for token in rule.get("allowed_destinations", [])}
            skip_words = {token.lower() for token in rule.get("skip_words", [])}
            for index in range(len(lowered) - len(trigger)):
                if lowered[index:index + len(trigger)] != trigger:
                    continue

                object_candidate = self._extract_object_candidate(lowered, index + len(trigger), skip_words)
                if object_candidate is None:
                    continue

                object_start, object_end, head_index = object_candidate
                candidate = lowered[head_index]
                object_phrase = " ".join(words[object_start:object_end])
                if candidate in allowed_destinations or candidate in self.pronoun_words:
                    continue
                phrase = " ".join(words[index:object_end])
                if phrase.lower() in seen_phrases:
                    continue
                seen_phrases.add(phrase.lower())
                issues.append(
                    GrammarIssue(
                        category="Semantic",
                        message=rule["message"].format(object=object_phrase),
                        sentence=sentence,
                        evidence=phrase,
                        suggestion=rule.get("suggestion"),
                        severity="warning",
                        rule_id="RULE-SEMANTIC-DESTINATION",
                        knowledge_source="src-semantic-classes",
                    )
                )

        object_rules = self.semantic_patterns.get("verb_object_expectations", {})
        for rule in object_rules.values():
            trigger = [token.lower() for token in rule.get("trigger", [])]
            if not trigger:
                continue
            allowed_objects = {token.lower() for token in rule.get("allowed_objects", [])}
            skip_words = {token.lower() for token in rule.get("skip_words", [])}
            replacement_map = {key.lower(): value for key, value in rule.get("replacement_map", {}).items()}

            for index in range(len(lowered) - len(trigger) + 1):
                if lowered[index:index + len(trigger)] != trigger:
                    continue

                object_candidate = self._extract_object_candidate(lowered, index + len(trigger), skip_words)
                if object_candidate is None:
                    continue

                object_start, object_end, head_index = object_candidate
                object_head = lowered[head_index]
                object_phrase = " ".join(words[object_start:object_end])

                if object_head in allowed_objects or object_head in self.pronoun_words:
                    continue

                phrase = " ".join(words[index:object_end])
                if phrase.lower() in seen_phrases:
                    continue

                seen_phrases.add(phrase.lower())
                issues.append(
                    GrammarIssue(
                        category="Semantic",
                        message=rule["message"].format(object=object_phrase),
                        sentence=sentence,
                        evidence=phrase,
                        suggestion=rule.get("suggestion"),
                        replacement=replacement_map.get(object_head),
                        severity="warning",
                        rule_id="RULE-SEMANTIC-OBJECT",
                        knowledge_source="src-semantic-classes",
                    )
                )

        head_rules = self.semantic_patterns.get("head_noun_modifiers", {})
        for index in range(len(lowered) - 1):
            modifier = lowered[index]
            head = lowered[index + 1]
            rule = head_rules.get(head)
            if rule is None:
                continue
            flagged_modifiers = {token.lower() for token in rule.get("flagged_modifiers", [])}
            allowed_modifiers = {token.lower() for token in rule.get("allowed_modifiers", [])}
            if flagged_modifiers:
                if modifier not in flagged_modifiers:
                    continue
            elif modifier in allowed_modifiers:
                continue
            if (
                modifier in self.determiners
                or modifier in self.preposition_words
                or modifier in self.subject_words
                or modifier in self.auxiliaries
                or modifier in self.modals
                or modifier in self.time_expression_tokens
                or self._looks_like_verb(modifier)
            ):
                continue

            phrase = f"{words[index]} {words[index + 1]}"
            if phrase.lower() in seen_phrases:
                continue
            seen_phrases.add(phrase.lower())
            issues.append(
                GrammarIssue(
                    category="Semantic",
                    message=rule["message"].format(modifier=words[index], head=words[index + 1]),
                    sentence=sentence,
                    evidence=phrase,
                    suggestion=rule.get("suggestion"),
                    severity="warning",
                    rule_id="RULE-SEMANTIC-HEAD",
                    knowledge_source="src-semantic-classes",
                )
            )

        deduped: list[GrammarIssue] = []
        seen_issue_keys: set[tuple[str, str, str]] = set()
        for issue in issues:
            key = (
                self._normalize_word_token(issue.evidence or ""),
                self._normalize_word_token(issue.replacement or ""),
                issue.rule_id or issue.category,
            )
            if key in seen_issue_keys:
                continue
            seen_issue_keys.add(key)
            deduped.append(issue)

        return deduped

    def _check_auxiliary_main_verb_consistency(self, sentence: str, words: list[str]) -> list[GrammarIssue]:
        if len(words) < 2:
            return []
            
        lowered = [w.lower() for w in words]
        issues: list[GrammarIssue] = []
        
        for i in range(len(lowered) - 1):
            aux = lowered[i]
            # Check for do/does/did or modals
            if aux in {"do", "does", "did"} or aux in self.modals:
                # Find the next verb, skipping 'not'
                main_verb_idx = -1
                for j in range(i + 1, min(i + 4, len(lowered))):
                    if lowered[j] == "not":
                        continue
                    if self._looks_like_verb(lowered[j]):
                        # Avoid treating the subject noun as a verb if there is another verb later in the sequence
                        has_later_verb = False
                        for k in range(j + 1, min(j + 4, len(lowered))):
                            if self._looks_like_verb(lowered[k]) and lowered[k] not in self.preposition_words:
                                has_later_verb = True
                                break
                        if has_later_verb and lowered[j] not in {"have", "has", "had", "be", "been", "being", "am", "is", "are", "was", "were"}:
                            continue
                        main_verb_idx = j
                        break
                
                if main_verb_idx != -1:
                    main_verb = lowered[main_verb_idx]
                    base = self.verb_engine.to_base(main_verb) or main_verb
                    # Modals and Do-auxiliaries require base form
                    if main_verb != base and main_verb not in self.collocation_lead_verbs:
                        # Exclude cases where it's a participle after 'have' (handled elsewhere)
                        if i > 0 and lowered[i-1] in {"have", "has", "had"}:
                            continue
                            
                        issues.append(
                            GrammarIssue(
                                category="Agreement",
                                message=f'The auxiliary "{words[i]}" should be followed by the base verb form.',
                                sentence=sentence,
                                evidence=words[main_verb_idx],
                                suggestion=base,
                                rule_id="RULE-AUXILIARY-BASE",
                                knowledge_source="src-grammar-rulepack",
                            )
                        )
        return issues

    def _check_sentence_capitalization(self, sentence: str, tokens: list[str]) -> list[GrammarIssue]:
        if not tokens:
            return []
        
        # Find the first real alphanumeric token
        first_token_index = -1
        for i, token in enumerate(tokens):
            if token and token[0].isalnum():
                first_token_index = i
                break
        
        if first_token_index == -1:
            return []
            
        # Fragment detection: if it's very short and has no terminal punctuation, skip capitalization
        # This prevents annoying "Sentences should start with a capitalized letter" for quiz answers or single words.
        has_punctuation = any(t in {".", "!", "?"} for t in tokens[-2:])
        if len(tokens) <= 3 and not has_punctuation:
            return []
            
        first_token = tokens[first_token_index]
        # Skip if it's already capitalized or starts with a digit/special case
        if first_token[0].islower():
            suggestion = first_token[0].upper() + first_token[1:]
            return [
                GrammarIssue(
                    category="Capitalization",
                    message="Sentences should start with a capitalized letter.",
                    sentence=sentence,
                    evidence=first_token,
                    suggestion=suggestion,
                    rule_id="RULE-SENTENCE-START-CAPS",
                    knowledge_source="src-grammar-rulepack",
                )
            ]
        return []

    def _apply_spelling_to_words(self, words: list[str], spelling_issues: list) -> list[str]:
        corrected_words = list(words)
        offset = 0
        for issue in spelling_issues:
            target_position = issue.position + offset
            if target_position < len(corrected_words):
                if " " in issue.suggestion:
                    split_tokens = [token for token in issue.suggestion.split() if token]
                    if split_tokens:
                        corrected_words[target_position : target_position + 1] = split_tokens
                        offset += len(split_tokens) - 1
                        continue
                corrected_words[target_position] = issue.suggestion
        return corrected_words

    def _build_corrected_sentence(
        self,
        sentence: str,
        tokens: list[str],
        spelling_issues: list,
        grammar_issues: list[GrammarIssue],
    ) -> tuple[str, list[CorrectionEntry]]:
        corrected_tokens = list(tokens)
        corrections: list[CorrectionEntry] = []
        word_indexes = [index for index, token in enumerate(tokens) if token[0].isalnum()]
        for issue in spelling_issues:
            if issue.position < len(word_indexes):
                token_index = word_indexes[issue.position]
                original = corrected_tokens[token_index]
                corrected_tokens[token_index] = issue.suggestion
                if original != issue.suggestion:
                    corrections.append(
                        CorrectionEntry(
                            kind="spelling",
                            original=original,
                            corrected=issue.suggestion,
                            reason=f'Corrected the spelling of "{original}".',
                            knowledge_source="compiled-dictionary",
                        )
                    )

        corrected_sentence = self._untokenize(corrected_tokens)
        ordered_issues = sorted(
            grammar_issues,
            key=lambda issue: (
                0 if issue.category == "Semantic" else 1,
                0 if issue.category == "Linking Word" else 1,
                -(len(self._normalize_phrase(issue.evidence or issue.replacement or issue.suggestion or ""))),
            ),
        )
        for issue in ordered_issues:
            corrected_sentence, issue_corrections = self._apply_grammar_correction(corrected_sentence, issue)
            corrections.extend(issue_corrections)

        return corrected_sentence or sentence, corrections

    def _apply_grammar_correction(self, text: str, issue: GrammarIssue) -> tuple[str, list[CorrectionEntry]]:
        if issue.category == "Semantic":
            if not issue.replacement or not issue.evidence:
                return text, []
            updated = self._replace_phrase_once(text, issue.evidence, issue.replacement)
            correction = self._make_correction_entry(
                kind="semantic",
                original=issue.evidence,
                corrected=issue.replacement,
                issue=issue,
                changed=updated != text,
            )
            return updated, [correction] if correction else []

        if not issue.suggestion or issue.category == "SVO":
            return text, []

        if issue.category == "Tense":
            if issue.target_tense:
                return self._apply_clause_tense_propagation(text, issue)
            return text, []

        if issue.category == "Linking Word":
            evidence = issue.evidence or issue.suggestion.rstrip(",")
            pattern = rf"^\s*{re.escape(evidence)}\b(?!,)"
            updated = re.sub(pattern, issue.suggestion, text, count=1, flags=re.IGNORECASE)
            correction = self._make_correction_entry(
                kind="grammar",
                original=evidence,
                corrected=issue.suggestion,
                issue=issue,
                changed=updated != text,
              )
            return updated, [correction] if correction else []

        if issue.rule_id == "RULE-DETERMINER-NOUN-AGREEMENT":
            updated = self._replace_phrase_once(text, issue.evidence or "", issue.suggestion)
            if updated == text and issue.evidence and issue.suggestion:
                source_parts = issue.evidence.split()
                target_parts = issue.suggestion.split()
                if source_parts and target_parts:
                    replacement_head = self._match_token_case(source_parts[0], target_parts[0])
                    updated = re.sub(
                        rf"\b{re.escape(source_parts[0])}\b",
                        replacement_head,
                        text,
                        count=1,
                    )
            correction = self._make_correction_entry(
                kind="grammar",
                original=issue.evidence or "",
                corrected=issue.suggestion,
                issue=issue,
                changed=updated != text,
            )
            return updated, [correction] if correction else []

        if not issue.evidence:
            return text, []

        updated = self._replace_phrase_once(text, issue.evidence, issue.suggestion)
        correction = self._make_correction_entry(
            kind="grammar",
            original=issue.evidence,
            corrected=issue.suggestion,
            issue=issue,
            changed=updated != text,
        )
        return updated, [correction] if correction else []

    def _make_correction_entry(
        self,
        *,
        kind: str,
        original: str,
        corrected: str,
        issue: GrammarIssue,
        changed: bool,
    ) -> CorrectionEntry | None:
        if not changed or not original or not corrected or original == corrected:
            return None
        return CorrectionEntry(
            kind=kind,
            original=original,
            corrected=corrected,
            reason=issue.message,
            knowledge_source=issue.knowledge_source or "src-grammar-rulepack",
        )

    def _apply_clause_tense_propagation(
        self,
        text: str,
        issue: GrammarIssue,
    ) -> tuple[str, list[CorrectionEntry]]:
        target_tense = issue.target_tense
        if not target_tense:
            return text, []

        corrections: list[CorrectionEntry] = []
        carried_subject: str | None = None
        updated_text = text

        for clause in self._segment_clauses(updated_text):
            clause_text = clause["text"]
            clause_words = clause["words"]
            if len(clause_words) < 2:
                continue

            # If the target tense is not a simple narrative tense, only apply to the clause
            # that actually contains the evidence verb of the issue.
            if target_tense not in {"past_simple", "present_simple"}:
                if issue.evidence and issue.evidence.lower() not in clause_text.lower():
                    continue

            predicate = self._detect_clause_predicate(clause_words)
            if predicate is None:
                continue
            pred_idx = int(predicate["word_index"])

            # Skip verbs preceded by modals or infinitive marker 'to'
            if pred_idx > 0:
                prev_word = clause_words[pred_idx - 1].lower()
                if (prev_word in self.modals and prev_word != "will") or prev_word == "to":
                    continue

            local_signals = self._detect_time_expressions(clause_text)
            if local_signals and not any(signal.name == target_tense for signal in local_signals):
                carried_subject = self._infer_conjugation_subject(clause_words, pred_idx)
                continue

            surface_tense = self._detect_surface_tense(clause_words)
            if surface_tense is None:
                carried_subject = self._infer_conjugation_subject(clause_words, pred_idx) or carried_subject
                continue
            if surface_tense.name == target_tense:
                carried_subject = self._infer_conjugation_subject(clause_words, pred_idx) or carried_subject
                continue

            clause_subject = self._infer_conjugation_subject(clause_words, pred_idx) or carried_subject
            
            # Suggest the corrected verb phrase based on predicate base form
            suggestion = self.verb_engine.suggest_for_tense(str(predicate["base"]), target_tense, clause_subject)
            if not suggestion:
                carried_subject = clause_subject
                continue

            evidence = surface_tense.evidence
            if evidence.lower() == suggestion.lower():
                carried_subject = clause_subject
                continue

            # Guard against double-inserting auxiliaries when the clause already contains
            # the leading auxiliary chain for the target tense.  For example, if the
            # sentence is "We has been wait …" (already has "has been" as part of a
            # malformed present-perfect-continuous) the SVA rule will later correct
            # "has→have", but right now the tense-propagation sees "wait" as
            # present_simple and would replace it with "have been waiting", resulting in
            # "have been have been waiting".  Detect this case and trim the suggestion to
            # only the terminal component that is actually missing (gerund / participle).
            AUX_PREFIXES: dict[str, list[str]] = {
                "present_perfect_continuous": ["have been", "has been"],
                "past_perfect_continuous":    ["had been"],
                "future_perfect_continuous":  ["will have been"],
                "present_perfect":            ["have", "has"],
                "past_perfect":               ["had"],
                "future_perfect":             ["will have"],
                "present_continuous":         ["am", "is", "are"],
                "past_continuous":            ["was", "were"],
                "future_continuous":          ["will be"],
                "future_simple":              ["will"],
            }
            clause_lower = clause_text.lower()
            trimmed_suggestion = suggestion
            for prefix in AUX_PREFIXES.get(target_tense, []):
                prefix_words = prefix.split()
                # Check that the prefix appears before the predicate in the clause
                prefix_pattern = r"\b" + r"\s+".join(re.escape(w) for w in prefix_words) + r"\s+"
                if re.search(prefix_pattern, clause_lower):
                    # Trim the full "auxiliary + …" suggestion to just its terminal word(s)
                    suggestion_words = suggestion.split()
                    prefix_len = len(prefix_words)
                    if len(suggestion_words) > prefix_len and suggestion.lower().startswith(prefix + " "):
                        trimmed_suggestion = " ".join(suggestion_words[prefix_len:])
                    break

            # Replace the surface phrase precisely within the clause substring to avoid duplicate issues
            new_clause_text = self._replace_phrase_once(clause_text, evidence, trimmed_suggestion)
            if new_clause_text != clause_text:
                new_text = self._replace_phrase_once(updated_text, clause_text, new_clause_text)
                if new_text != updated_text:
                    correction = self._make_correction_entry(
                        kind="grammar",
                        original=evidence,
                        corrected=trimmed_suggestion,
                        issue=issue,
                        changed=True,
                    )
                    if correction:
                        corrections.append(correction)
                    updated_text = new_text

            carried_subject = clause_subject

        if not corrections:
            return text, []

        return updated_text, corrections

    def _rewrite_clause_simple_tense(
        self,
        *,
        tokens: list[str],
        token_indexes: list[int],
        target_tense: str,
        subject: str | None,
        issue: GrammarIssue,
    ) -> list[CorrectionEntry]:
        corrections: list[CorrectionEntry] = []
        clause_words = [tokens[index] for index in token_indexes]
        leading_time_end = self._leading_time_expression_end(clause_words)

        for relative_index, token_index in enumerate(token_indexes):
            if relative_index < leading_time_end:
                continue
            token = tokens[token_index]
            lowered = token.lower()
            previous = tokens[token_indexes[relative_index - 1]].lower() if relative_index > 0 else ""
            next_word = tokens[token_indexes[relative_index + 1]].lower() if relative_index + 1 < len(token_indexes) else ""

            if lowered in self.clause_connectors or lowered in self.determiners or lowered in self.preposition_words:
                continue
            if previous in self.determiners:
                continue
            if lowered in self.modals:
                continue
            if previous in self.modals or previous in {"to", "will", "would", "can", "could", "should", "may", "might", "must"}:
                continue
            if lowered in {"am", "is", "are", "was", "were", "be", "been", "being"}:
                continue
            if lowered in {"have", "has", "had"} and next_word and self.verb_engine.is_participle(next_word):
                continue
            if lowered in {"do", "does", "did"} and next_word and self._looks_like_base_verb(next_word) and next_word not in self.collocation_lead_verbs and next_word not in COLLOCATION_NOUNS:
                continue
            if not self._looks_like_verb(lowered):
                continue
            if self.verb_engine.is_gerund(lowered):
                continue

            base = self.verb_engine.to_base(lowered) or lowered
            if base not in self.collocation_lead_verbs and base not in COLLOCATION_NOUNS and previous in {"do", "does", "did", "have", "has", "had"}:
                continue

            replacement = self.verb_engine.suggest_for_tense(base, target_tense, subject)
            replacement_head = replacement.split()[0].lower()
            if replacement_head == lowered:
                continue

            tokens[token_index] = self._match_token_case(token, replacement_head)
            reason = (
                issue.message
                if issue.evidence and issue.evidence.lower() == lowered
                else f'Clause-level tense propagation aligned "{token}" with {self._humanize_tense(target_tense)}.'
            )
            corrections.append(
                CorrectionEntry(
                    kind="grammar",
                    original=token,
                    corrected=tokens[token_index],
                    reason=reason,
                    knowledge_source=issue.knowledge_source or "src-grammar-rulepack",
                )
            )

        return corrections

    def _segment_clauses(self, text: str) -> list[dict[str, object]]:
        tokens = self._tokenize(text)
        clauses: list[dict[str, object]] = []
        current: list[tuple[int, str]] = []

        for index, token in enumerate(tokens):
            lowered = token.lower()
            if token in {".", "!", "?", ";"}:
                self._push_clause(clauses, current)
                current = []
                continue
            if token == ",":
                self._push_clause(clauses, current)
                current = []
                continue
            if lowered in self.clause_connectors and current and self._next_clause_has_subject(tokens, index + 1):
                self._push_clause(clauses, current)
                current = []
                continue
            current.append((index, token))

        self._push_clause(clauses, current)
        return clauses

    def _push_clause(self, clauses: list[dict[str, object]], indexed_tokens: list[tuple[int, str]]) -> None:
        if not indexed_tokens:
            return
        clause_tokens = [token for _, token in indexed_tokens if token not in {",", ";"}]
        clause_indexes = [index for index, token in indexed_tokens if token[0].isalnum()]
        clause_words = [token for _, token in indexed_tokens if token[0].isalnum()]
        if not clause_words:
            return
        clauses.append(
            {
                "text": self._untokenize(clause_tokens),
                "indexes": clause_indexes,
                "words": clause_words,
            }
        )

    def _next_clause_has_subject(self, tokens: list[str], start_index: int) -> bool:
        inspected = 0
        for token in tokens[start_index:]:
            if not token or not token[0].isalnum():
                continue
            lowered = token.lower()
            if lowered in self.clause_connectors:
                continue
            if lowered in self.subject_words or lowered in self.determiners:
                return True
            inspected += 1
            if inspected >= 2:
                break
        return False

    def _leading_time_expression_end(self, words: list[str]) -> int:
        lowered = [word.lower() for word in words]
        longest_match = 0
        for expressions in self.rules.get("time_expressions", {}).values():
            for expression in expressions:
                expression_tokens = self._normalize_phrase(expression)
                if not expression_tokens or len(expression_tokens) > len(lowered):
                    continue
                if lowered[:len(expression_tokens)] == expression_tokens:
                    longest_match = max(longest_match, len(expression_tokens))
        return longest_match

    def _find_explicit_subject_index(self, words: list[str]) -> int | None:
        for index, word in enumerate(words):
            if word.lower() in self.subject_words:
                return index
        return None

    def _find_agreement_verb_index(self, words: list[str]) -> int | None:
        lowered = [word.lower() for word in words]
        start_index = self._leading_time_expression_end(words)

        for index in range(start_index, len(lowered)):
            token = lowered[index]
            previous = lowered[index - 1] if index > 0 else ""
            next_word = lowered[index + 1] if index + 1 < len(lowered) else ""

            if token in self.clause_connectors or token in self.preposition_words or token in self.modals:
                continue
            if previous in self.determiners:
                continue
            if previous in self.modals or previous in {"to"}:
                continue

            if token in {"am", "is", "are", "was", "were", "have", "has", "had"}:
                return index
            if token in {"do", "does", "did"} or token in NEGATED_AUXILIARY_MAP:
                return index
            if not self._looks_like_verb(token):
                continue
            if self.verb_engine.is_gerund(token):
                continue
            if self.verb_engine.is_participle(token) and previous in {"have", "has", "had"}:
                continue
            return index

        return None

    def _infer_subject_profile_from_tokens(self, subject_tokens: list[str]) -> dict[str, str] | None:
        if not subject_tokens:
            return None

        lowered = [self._normalize_word_token(token) for token in subject_tokens if token]
        if not lowered:
            return None
        filtered = [
            token
            for token in lowered
            if token not in NEGATED_AUXILIARY_MAP
            and token not in self.auxiliaries
            and token not in self.modals
            and token != "not"
        ]
        if not filtered:
            return None
        if filtered[0] in INVERTED_OPENERS:
            return None
        if "and" in filtered:
            return {"agreement_subject": "they", "number": "plural"}

        for token in filtered:
            if token in self.subject_words:
                if token == "i":
                    return {"agreement_subject": "i", "number": "singular"}
                if token in PLURAL_REFERENCE_WORDS:
                    return {"agreement_subject": "they", "number": "plural"}
                if token in SINGULAR_REFERENCE_WORDS:
                    return {"agreement_subject": "it", "number": "singular"}
                return {"agreement_subject": token, "number": "singular"}

        head = filtered[-1]
        if head in self.subject_words:
            if head == "i":
                return {"agreement_subject": "i", "number": "singular"}
            if head in PLURAL_REFERENCE_WORDS:
                return {"agreement_subject": "they", "number": "plural"}
            if head in SINGULAR_REFERENCE_WORDS:
                return {"agreement_subject": "it", "number": "singular"}
            return {"agreement_subject": head, "number": "singular"}

        determiner = next((token for token in filtered if token in self.determiners), None)
        if determiner in PLURAL_DETERMINERS:
            return {"agreement_subject": "they", "number": "plural"}
        if determiner in SINGULAR_DETERMINERS:
            return {"agreement_subject": "it", "number": "singular"}

        if head in self.uncountable_nouns or head in SINGULAR_S_ENDING_NOUNS:
            return {"agreement_subject": "it", "number": "singular"}
        if head in IRREGULAR_PLURAL_NOUNS or self._is_probably_plural_noun(head):
            return {"agreement_subject": "they", "number": "plural"}
        return {"agreement_subject": "it", "number": "singular"}

    def _infer_conjugation_subject(self, words: list[str], predicate_index: int | None = None) -> str | None:
        search_end = predicate_index if predicate_index is not None else len(words)
        leading_time_end = self._leading_time_expression_end(words[:search_end])
        profile = self._infer_subject_profile_from_tokens(words[leading_time_end:search_end])
        if profile is not None:
            return str(profile["agreement_subject"])

        for index in range(search_end):
            word = words[index]
            if not word or not word[0].isalnum():
                continue
                
            lowered = word.lower()
            if lowered in self.clause_connectors or lowered in self.time_expression_tokens or lowered.endswith("ly"):
                continue
            if lowered in NEGATED_AUXILIARY_MAP or lowered == "not":
                continue
            if lowered in self.subject_words:
                return lowered
            if lowered in self.determiners:
                if index + 1 < search_end:
                    candidate = words[index + 1].lower()
                    if candidate[0].isalnum() and candidate not in self.clause_connectors and candidate not in self.preposition_words:
                        return "they" if self._is_probably_plural_noun(candidate) else "it"
                continue
            if lowered in self.preposition_words or lowered in self.auxiliaries or lowered in self.modals:
                continue
            return "they" if self._is_probably_plural_noun(lowered) else "it"
        return None

    def _detect_clause_predicate(self, words: list[str]) -> dict[str, object] | None:
        predicate_subject = self._infer_conjugation_subject(words)
        leading_time_end = self._leading_time_expression_end(words)
        subject_index = self._find_explicit_subject_index(words)
        start_index = leading_time_end
        if subject_index is not None:
            start_index = max(start_index, subject_index + 1)

        for index in range(start_index, len(words)):
            word = words[index]
            lowered = word.lower()
            previous = words[index - 1].lower() if index > 0 else ""
            next_word = words[index + 1].lower() if index + 1 < len(words) else ""

            if lowered in self.clause_connectors or lowered in self.determiners or lowered in self.preposition_words:
                continue
            if lowered in self.modals:
                continue
            if previous in self.determiners:
                continue
            if previous in {"to"}:
                continue
            if lowered in {"am", "is", "are", "was", "were", "be", "been", "being"}:
                continue
            if lowered in {"have", "has", "had"} and next_word and self.verb_engine.is_participle(next_word):
                continue
            if lowered in {"do", "does", "did"} and next_word and self._looks_like_base_verb(next_word) and next_word not in self.collocation_lead_verbs and next_word not in COLLOCATION_NOUNS:
                continue
            if self.verb_engine.is_gerund(lowered) and previous in {"am", "is", "are", "was", "were", "be", "been", "being"}:
                base = self.verb_engine.to_base(lowered) or lowered
                return {
                    "surface": word,
                    "base": base,
                    "word_index": index,
                    "subject": predicate_subject,
                }
            if self.verb_engine.is_participle(lowered) and previous in {"have", "has", "had"}:
                base = self.verb_engine.to_base(lowered) or lowered
                return {
                    "surface": word,
                    "base": base,
                    "word_index": index,
                    "subject": predicate_subject,
                }
            if not self._looks_like_verb(lowered):
                continue
            if self.verb_engine.is_gerund(lowered):
                continue

            base = self.verb_engine.to_base(lowered) or lowered
            if base not in self.collocation_lead_verbs and base not in COLLOCATION_NOUNS and previous in {"do", "does", "did", "have", "has", "had"}:
                continue

            return {
                "surface": word,
                "base": base,
                "word_index": index,
                "subject": predicate_subject,
            }

        return None

    def _match_token_case(self, original: str, replacement: str) -> str:
        if original.isupper():
            return replacement.upper()
        if original[:1].isupper():
            return replacement.capitalize()
        return replacement

    def _build_vocabulary_profile(self, text: str) -> list[VocabularyBand]:
        tokens = set(self._normalize_phrase(text))
        profile: list[VocabularyBand] = []
        for level, words in sorted(self.repository.cefr_vocabulary.items()):
            matches = sorted(tokens & {word.lower() for word in words})
            if not matches:
                continue
            profile.append(
                VocabularyBand(
                    level=level,
                    match_count=len(matches),
                    words=matches[:12],
                )
            )
        return profile

    def _build_knowledge_hits(
        self,
        *,
        spelling_issues: list,
        grammar_errors: list[GrammarIssue],
        semantic_warnings: list[GrammarIssue],
        detected_tenses: list[TenseSignal],
        corrections: list[CorrectionEntry],
        vocabulary_profile: list[VocabularyBand],
    ) -> list[KnowledgeHit]:
        grouped_examples: dict[str, list[str]] = {}
        grouped_counts: dict[str, int] = {}

        def add_hit(source_id: str, example: str | None = None, count: int = 1) -> None:
            grouped_counts[source_id] = grouped_counts.get(source_id, 0) + count
            if example:
                grouped_examples.setdefault(source_id, [])
                if example not in grouped_examples[source_id]:
                    grouped_examples[source_id].append(example)

        if spelling_issues:
            add_hit("compiled-dictionary", example="dictionary-backed spelling repair", count=len(spelling_issues))

        if detected_tenses or any(issue.knowledge_source == "src-grammar-rulepack" for issue in grammar_errors):
            add_hit(
                "src-grammar-rulepack",
                example="tense patterns and grammar heuristics",
                count=len(detected_tenses) + sum(1 for issue in grammar_errors if issue.knowledge_source == "src-grammar-rulepack"),
            )

        for issue in semantic_warnings:
            add_hit(issue.knowledge_source or "src-grammar-rulepack", example=issue.evidence or issue.category)

        for correction in corrections:
            if correction.knowledge_source in {"compiled-dictionary", "src-grammar-rulepack"}:
                continue
            add_hit(correction.knowledge_source, example=f'{correction.original} -> {correction.corrected}')

        if vocabulary_profile:
            add_hit(
                "src-cambridge-cefr-imported",
                example=", ".join(sorted({band.level for band in vocabulary_profile})),
                count=sum(band.match_count for band in vocabulary_profile),
            )

        hits: list[KnowledgeHit] = []
        for source_id, match_count in grouped_counts.items():
            label = self._knowledge_hit_label(source_id)
            detail = self._knowledge_hit_detail(source_id, match_count, grouped_examples.get(source_id, []), vocabulary_profile)
            hits.append(
                KnowledgeHit(
                    source_id=source_id,
                    label=label,
                    detail=detail,
                    match_count=match_count,
                    examples=grouped_examples.get(source_id, [])[:5],
                )
            )
        return sorted(hits, key=lambda item: (-item.match_count, item.source_id))

    def _extract_object_candidate(
        self,
        words: list[str],
        start_index: int,
        skip_words: set[str] | None = None,
        max_span: int = 5,
    ) -> tuple[int, int, int] | None:
        skip_words = skip_words or set()
        index = start_index

        while index < len(words) and words[index] in skip_words:
            index += 1

        if index >= len(words):
            return None

        end = index
        span_length = 0
        while end < len(words) and span_length < max_span:
            token = words[end]
            if span_length > 0 and (token in self.semantic_boundary_words or self._looks_like_verb(token)):
                break
            end += 1
            span_length += 1

        if end <= index:
            return None

        head_index = None
        for candidate_index in range(end - 1, index - 1, -1):
            token = words[candidate_index]
            if token in skip_words or token in self.determiners or token in self.pronoun_words:
                continue
            if token in self.semantic_boundary_words or self._looks_like_verb(token):
                continue
            head_index = candidate_index
            break

        if head_index is None:
            return None

        return index, end, head_index

    def _replace_phrase_once(self, text: str, source: str, target: str) -> str:
        source_tokens = self._normalize_phrase(source)
        if not source_tokens:
            return text
        pattern_tokens = [re.escape(token).replace("'", "['’‘]") for token in source_tokens]
        pattern = r"(?<!\w)" + r"\s+".join(pattern_tokens) + r"(?!\w)"
        return re.sub(pattern, target, text, count=1, flags=re.IGNORECASE)

    def _semantic_rule_source(self, rule: dict[str, object]) -> str:
        source_label = str(rule.get("source_label") or "").strip().lower()
        if source_label:
            return "src-collocation-imported"
        return "src-grammar-rulepack"

    def _knowledge_hit_label(self, source_id: str) -> str:
        labels = {
            "compiled-dictionary": "Compiled Dictionary",
            "src-grammar-rulepack": "Core Grammar Rulepack",
            "src-cambridge-cefr-imported": "Cambridge CEFR Starter Pack",
            "src-collocation-imported": "Starter Collocation Pack",
            "src-semantic-classes": "Semantic Class Pack",
        }
        if source_id in labels:
            return labels[source_id]
        source = self.source_manifest_by_id.get(source_id)
        if source and source.get("id"):
            return str(source["id"]).replace("src-", "").replace("-", " ").title()
        return source_id.replace("-", " ").title()

    def _knowledge_hit_detail(
        self,
        source_id: str,
        match_count: int,
        examples: list[str],
        vocabulary_profile: list[VocabularyBand],
    ) -> str:
        if source_id == "compiled-dictionary":
            return f"Produced {match_count} spelling-aware correction(s) from the compiled dictionary."
        if source_id == "src-grammar-rulepack":
            return f"Activated {match_count} grammar-pattern match(es) from the core rule pack."
        if source_id == "src-cambridge-cefr-imported":
            levels = ", ".join(band.level for band in vocabulary_profile)
            return f"Matched {match_count} CEFR anchor word(s) across imported level list(s): {levels}."
        if source_id == "src-collocation-imported":
            return f"Triggered {match_count} imported collocation warning(s) from the starter collocation pack."
        if source_id == "src-semantic-classes":
            return f"Triggered {match_count} semantic plausibility warning(s) from semantic-class rules."
        if examples:
            return f"Matched {match_count} item(s). Examples: {', '.join(examples[:3])}."
        return f"Matched {match_count} knowledge-backed signal(s)."

    def _untokenize(self, tokens: list[str]) -> str:
        text = ""
        for token in tokens:
            if not text:
                text = token
                continue
            if token in PUNCTUATION_TOKENS:
                text += token
                continue
            text += f" {token}"
        return text

    def _find_lexical_verb(self, words: list[str]) -> str | None:
        predicate = self._detect_clause_predicate(words)
        if predicate is not None:
            return str(predicate["surface"]).lower()

        for word in words[1:]:
            lowered = word.lower()
            if lowered in self.auxiliaries or lowered in self.modals:
                continue
            if self._looks_like_verb(lowered):
                return lowered
        for word in words:
            lowered = word.lower()
            if self._looks_like_verb(lowered):
                return lowered
        return None

    def _find_subject_index(self, words: list[str]) -> int | None:
        for index, word in enumerate(words):
            if word.lower() in self.subject_words:
                return index
        return 0 if words else None

    def _find_subject(self, words: list[str]) -> str | None:
        subject_index = self._find_subject_index(words)
        if subject_index is None:
            return None
        return words[subject_index].lower()

    def _surface_phrase(self, words: list[str], surface_tense: TenseSignal) -> str:
        lowered = [word.lower() for word in words]

        if surface_tense.name == "future_perfect_continuous":
            match = self._find_sequence(lowered, ["will", "have", "been"], 4, lambda token: self.verb_engine.is_gerund(token))
            if match is not None:
                return " ".join(words[match:match + 4])
        if surface_tense.name == "future_perfect":
            match = self._find_sequence(lowered, ["will", "have"], 3, lambda token: self.verb_engine.is_participle(token))
            if match is not None:
                return " ".join(words[match:match + 3])
        if surface_tense.name == "future_continuous":
            match = self._find_sequence(lowered, ["will", "be"], 3, lambda token: self.verb_engine.is_gerund(token))
            if match is not None:
                return " ".join(words[match:match + 3])
        if surface_tense.name == "past_perfect_continuous":
            match = self._find_sequence(lowered, ["had", "been"], 3, lambda token: self.verb_engine.is_gerund(token))
            if match is not None:
                return " ".join(words[match:match + 3])
        if surface_tense.name == "present_perfect_continuous":
            for auxiliary in ("have", "has"):
                match = self._find_sequence(lowered, [auxiliary, "been"], 3, lambda token: self.verb_engine.is_gerund(token))
                if match is not None:
                    return " ".join(words[match:match + 3])
        if surface_tense.name == "past_continuous":
            for auxiliary in ("was", "were"):
                match = self._find_sequence(lowered, [auxiliary], 2, lambda token: self.verb_engine.is_gerund(token))
                if match is not None:
                    return " ".join(words[match:match + 2])
        if surface_tense.name == "present_continuous":
            for auxiliary in ("am", "is", "are"):
                match = self._find_sequence(lowered, [auxiliary], 2, lambda token: self.verb_engine.is_gerund(token))
                if match is not None:
                    return " ".join(words[match:match + 2])
        if surface_tense.name == "past_perfect":
            match = self._find_sequence(lowered, ["had"], 2, lambda token: self.verb_engine.is_participle(token))
            if match is not None:
                return " ".join(words[match:match + 2])
        if surface_tense.name == "present_perfect":
            for auxiliary in ("have", "has"):
                match = self._find_sequence(lowered, [auxiliary], 2, lambda token: self.verb_engine.is_participle(token))
                if match is not None:
                    return " ".join(words[match:match + 2])
        if surface_tense.name == "future_simple":
            match = self._find_sequence(lowered, ["will"], 2, lambda token: self._looks_like_base_verb(token))
            if match is not None:
                return " ".join(words[match:match + 2])

        lexical_verb = self._find_lexical_verb(words)
        return lexical_verb or surface_tense.evidence

    def _find_sequence(self, words: list[str], prefix: list[str], span_length: int, validator) -> int | None:
        if len(words) < span_length:
            return None
        prefix_length = len(prefix)
        for index in range(len(words) - span_length + 1):
            if words[index:index + prefix_length] != prefix:
                continue
            if validator(words[index + prefix_length]):
                return index
        return None

    def _looks_like_base_verb(self, word: str) -> bool:
        lowered = word.lower()
        base = self.verb_engine.to_base(lowered)
        return base is not None and lowered == base

    def _looks_like_verb(self, word: str) -> bool:
        lowered = word.lower()
        return (
            self.verb_engine.is_known_verb(lowered)
            or self.verb_engine.is_past_form(lowered)
            or self.verb_engine.is_participle(lowered)
            or self.verb_engine.is_gerund(lowered)
            or lowered in self.auxiliaries
            or lowered in self.modals
        )

    def _normalize_word_token(self, word: str) -> str:
        return word.lower().replace("’", "'").replace("‘", "'")

    def _normalize_phrase(self, text: str) -> list[str]:
        normalized = text.lower().replace("’", "'").replace("‘", "'")
        return TOKEN_WORD_PATTERN.findall(normalized)

    def _is_probably_plural_noun(self, word: str) -> bool:
        if word in IRREGULAR_PLURAL_NOUNS:
            return True
        if word in self.uncountable_nouns or word in SINGULAR_S_ENDING_NOUNS:
            return False
        if word in SINGULAR_REFERENCE_WORDS:
            return False
        if word in PLURAL_REFERENCE_WORDS:
            return True
        return word.endswith("s") and not word.endswith("ss")

    def _humanize_tense(self, tense_name: str) -> str:
        return tense_name.replace("_", " ")

    def _issues_to_trace(
        self,
        rule_id: str,
        stage: str,
        sentence: str,
        detail: str,
        issues: list[GrammarIssue],
    ) -> RuleTrace:
        evidence = ", ".join(issue.message for issue in issues) or None
        return RuleTrace(
            rule_id=rule_id,
            stage=stage,
            matched=bool(issues),
            sentence=sentence,
            detail=detail,
            evidence=evidence,
        )

    def _relevant_coverage(self, analysis: GrammarAnalysis) -> list[CoverageEntry]:
        categories = {issue.category for issue in analysis.grammar_issues}
        if analysis.spelling_issues:
            categories.add("Spelling")
        if analysis.detected_tenses:
            categories.add("Tense")

        matched: list[CoverageEntry] = []
        for entry in self.coverage_matrix:
            if any(category in entry.categories for category in categories):
                matched.append(entry)
        return matched
