from __future__ import annotations

from typing import Any

# Lazy import to avoid startup crashes if torch/spacy is broken
# import spacy


class SpacyGrammarDetector:
    def __init__(self, grammar_rules: dict[str, Any] | None = None) -> None:
        self._nlp = None
        safe_rules = grammar_rules or {}
        self._preposition_mappings = {
            str(key).lower(): [str(value).lower() for value in values]
            for key, values in (safe_rules.get("prepositions", {}) or {}).items()
            if isinstance(values, list)
        }

    def _get_nlp(self):
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm")
            except Exception as e:
                # Fallback to a dummy object that returns an empty list or similar
                # to avoid breaking the grammar checker entirely.
                print(f"Warning: Could not load spacy ('en_core_web_sm'). {e}")
                self._nlp = lambda text: []
        return self._nlp

    def detect(self, text: str, verb_engine) -> list[dict[str, Any]]:
        try:
            doc = self._get_nlp()(text)
        except Exception:
            return []

        signals: list[dict[str, Any]] = []
        signals.extend(self._detect_auxiliary_base_issues(doc, verb_engine))
        signals.extend(self._detect_pronoun_verb_agreement_issues(doc, verb_engine))
        signals.extend(self._detect_article_usage_issues(doc))
        signals.extend(self._detect_determiner_number_issues(doc))
        signals.extend(self._detect_verb_preposition_issues(doc, verb_engine))
        return signals

    def _detect_auxiliary_base_issues(self, doc, verb_engine) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        auxiliaries = {"do", "does", "did"}
        for token in doc:
            if token.lower_ not in auxiliaries:
                continue
            head = token.head
            if head is None or head == token:
                continue
            if head.pos_ != "VERB":
                continue
            suggested = verb_engine.to_base(head.text.lower()) or head.lemma_.lower()
            if not suggested or suggested == head.text.lower():
                continue
            signals.append(
                {
                    "detector_type": "auxiliary_base",
                    "auxiliary": token.text,
                    "suggested": suggested,
                    "evidence": head.text,
                    "confidence": 0.94,
                }
            )
        return signals

    def _detect_article_usage_issues(self, doc) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        vowels = {"a", "e", "i", "o", "u"}
        for token in doc:
            if token.lower_ not in {"a", "an"}:
                continue
            next_token = token.nbor(1) if token.i + 1 < len(doc) else None
            if next_token is None or not next_token.text:
                continue
            starts_with_vowel = next_token.text[0].lower() in vowels
            expected = "an" if starts_with_vowel else "a"
            if token.lower_ == expected:
                continue
            signals.append(
                {
                    "detector_type": "article_usage",
                    "expected": expected,
                    "next_token": next_token.text,
                    "evidence": token.text,
                    "confidence": 0.92,
                }
            )
        return signals

    def _detect_determiner_number_issues(self, doc) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for token in doc:
            if token.pos_ != "DET":
                continue
            noun = token.head
            if noun is None or noun == token or noun.pos_ not in {"NOUN", "PROPN"}:
                continue
            number = noun.morph.get("Number")
            is_plural = "Plur" in number
            if token.lower_ in {"this", "that"} and is_plural:
                suggestion = "these" if token.lower_ == "this" else "those"
                signals.append(
                    {
                        "detector_type": "determiner_number",
                        "noun": noun.text,
                        "expected": suggestion,
                        "evidence": token.text,
                        "confidence": 0.9,
                    }
                )
            if token.lower_ in {"these", "those"} and not is_plural:
                suggestion = "this" if token.lower_ == "these" else "that"
                signals.append(
                    {
                        "detector_type": "determiner_number",
                        "noun": noun.text,
                        "expected": suggestion,
                        "evidence": token.text,
                        "confidence": 0.9,
                    }
                )
        return signals

    def _detect_verb_preposition_issues(self, doc, verb_engine) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        if not self._preposition_mappings:
            return signals

        for token in doc:
            if token.pos_ not in {"VERB", "AUX"}:
                continue
            lemma = (verb_engine.to_base(token.lemma_.lower()) or token.lemma_.lower()).strip()
            allowed = self._preposition_mappings.get(lemma)
            if not allowed:
                continue
            prep_children = [child for child in token.children if child.dep_ == "prep"]
            if not prep_children:
                continue
            for prep in prep_children:
                if prep.lower_ in allowed:
                    continue
                signals.append(
                    {
                        "detector_type": "verb_preposition",
                        "verb": token.text,
                        "expected_preposition": allowed[0],
                        "evidence": f"{token.text} {prep.text}",
                        "confidence": 0.88,
                    }
                )
        return signals

    def _detect_pronoun_verb_agreement_issues(self, doc, verb_engine) -> list[dict[str, Any]]:
        singular = {"he", "she", "it"}
        plural = {"we", "they", "you"}
        be_map = {
            "i": "am",
            "he": "is",
            "she": "is",
            "it": "is",
            "we": "are",
            "they": "are",
            "you": "are",
        }
        signals: list[dict[str, Any]] = []

        for token in doc:
            if token.dep_ not in {"nsubj", "nsubjpass"}:
                continue
            subject = token.text.lower()
            verb = token.head
            if verb is None or verb.pos_ not in {"VERB", "AUX"}:
                continue

            verb_surface = verb.text.lower()
            if verb_surface in {"am", "is", "are"}:
                expected = be_map.get(subject)
                if expected and expected != verb_surface:
                    signals.append(
                        {
                            "detector_type": "be_agreement",
                            "subject": token.text,
                            "expected": expected,
                            "evidence": verb.text,
                            "confidence": 0.96,
                        }
                    )
                continue

            if verb.pos_ != "VERB":
                continue

            if subject in singular:
                base = verb_engine.to_base(verb_surface) or verb.lemma_.lower()
                singular_form = verb_engine.third_person_singular(base)
                if singular_form and singular_form != verb_surface:
                    signals.append(
                        {
                            "detector_type": "sva_singular",
                            "subject": token.text,
                            "base": base,
                            "expected": singular_form,
                            "evidence": verb.text,
                            "confidence": 0.9,
                        }
                    )
            elif subject in plural:
                if verb_engine.is_third_person_form(verb_surface) and verb_surface not in {"is", "has", "does"}:
                    base = verb_engine.to_base(verb_surface) or verb.lemma_.lower()
                    if base != verb_surface:
                        signals.append(
                            {
                                "detector_type": "sva_plural",
                                "subject": token.text,
                                "base": base,
                                "evidence": verb.text,
                                "confidence": 0.9,
                            }
                        )

        return signals
