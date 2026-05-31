from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any

from grammar_dsl.dsl.ast import AndExpr, FeatureExpr, OrExpr
from grammar_dsl.engine import VerbEngine


class ExerciseGenerator:
    DEFAULT_SENTENCE_FORM = "affirmative"
    SENTENCE_FORMS = {"affirmative", "negative", "interrogative"}
    TENSE_FEATURES = {
        "present simple",
        "past simple",
        "future simple",
        "present continuous",
        "past continuous",
        "future continuous",
        "present perfect",
        "past perfect",
        "future perfect",
        "present perfect continuous",
        "past perfect continuous",
        "future perfect continuous",
    }

    def __init__(self, repository, verb_engine: VerbEngine) -> None:
        self.repository = repository
        self.verb_engine = verb_engine
        self.feature_catalog = {entry["id"]: entry for entry in repository.feature_catalog}
        self.blueprints = repository.exercise_blueprints or []
        self.lexical_pools = repository.lexical_pools or {}
        self.realization_rules = repository.realization_rules or {}

    def generate(
        self,
        feature_expr,
        requested_count: int | None = None,
        singular_form_requested: bool = False,
    ) -> dict[str, Any]:
        bundles = [self._normalize_bundle(bundle) for bundle in self._expand_feature_expr(feature_expr)]
        bundles = self._dedupe_bundles(bundles)
        requested_total = 1 if singular_form_requested or requested_count is None else requested_count

        feature_labels = sorted({feature for bundle in bundles for feature in bundle})
        feature_strings = [" AND ".join(sorted(bundle)) for bundle in bundles]

        feature_text = "|".join(feature_strings)
        base_seed = int(hashlib.sha1(feature_text.encode("utf-8")).hexdigest(), 16) % 1000000

        # Try generating with Ollama first if enabled
        import os
        use_ollama = os.getenv("GRAMMAR_CHECK_USE_OLLAMA", "0").strip().lower() in {"1", "true", "yes", "on"}
        if use_ollama:
            ollama_items = self._generate_with_ollama(feature_labels, requested_total)
            if ollama_items:
                seed_text = "|".join(item["id"] for item in ollama_items)
                exercise_set_id = f"set-ollama-{hashlib.sha1(seed_text.encode('utf-8')).hexdigest()[:10]}"
                return {
                    "exercise_set_id": exercise_set_id,
                    "requested_count": requested_total,
                    "items": ollama_items,
                    "features": feature_labels,
                    "feature_bundles": [sorted(bundle) for bundle in bundles],
                }

        if False: # Disabling corpus generator
            pass
        else:
            selected = self._select_blueprints(bundles, requested_total)
            items = [self._realize_item(blueprint, base_seed + index) for index, blueprint in enumerate(selected)]

        seed_text = "|".join(item["id"] for item in items)
        exercise_set_id = f"set-{hashlib.sha1(seed_text.encode('utf-8')).hexdigest()[:10]}"
        return {
            "exercise_set_id": exercise_set_id,
            "requested_count": requested_total,
            "items": items,
            "features": feature_labels,
            "feature_bundles": [sorted(bundle) for bundle in bundles],
        }

    def _generate_with_ollama(self, features: list[str], count: int) -> list[dict[str, Any]]:
        import requests
        import json

        # Detect available models and pick the best one
        model_name = "qwen2.5-coder:latest"
        try:
            tags_resp = requests.get("http://localhost:11434/api/tags", timeout=1.5)
            if tags_resp.status_code == 200:
                available_models = [m["name"] for m in tags_resp.json().get("models", [])]
                if "qwen2.5-coder:latest" in available_models:
                    model_name = "qwen2.5-coder:latest"
                elif "llama3:latest" in available_models:
                    model_name = "llama3:latest"
                elif available_models:
                    model_name = available_models[0]
                else:
                    return []
            else:
                return []
        except Exception:
            return []

        features_str = ", ".join(features)
        system_prompt = (
            "You are an expert English Grammar Teacher. Your task is to generate high-quality, academic grammar exercises.\n"
            "You must return ONLY a raw JSON array of objects. Do not include any markdown formatting, backticks, or conversational text. Just the raw JSON."
        )

        user_prompt = (
            f"Generate exactly {count} English grammar exercise(s) targeting the following features: {features_str}.\n"
            f"Each exercise object in the JSON array must strictly contain these keys:\n"
            f'- "prompt": A clear instruction and sentence with a gap, e.g., "Fill in the blank with the correct past simple form: She ____ (go) to the library yesterday."\n'
            f'- "expected_answer": The exact correct word or phrase to fill in the blank, e.g., "went"\n'
            f'- "accepted_variants": A JSON list of acceptable alternative correct answers, e.g., ["went"]\n'
            f'- "answer_preview": The full correct completed sentence, e.g., "She went to the library yesterday."\n'
            f'- "difficulty": "intermediate"\n'
            f'- "features": ["{features[0]}"]\n'
            f"Double-check that the JSON is perfectly valid and matches the requested count."
        )

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": f"System: {system_prompt}\nUser: {user_prompt}",
                    "stream": False,
                    "options": {
                        "temperature": 0.3
                    }
                },
                timeout=20
            )
            if response.status_code != 200:
                return []

            response_text = response.json().get("response", "").strip()
            # Clean potential markdown wrapping
            if response_text.startswith("```"):
                parts = response_text.split("```")
                if len(parts) >= 3:
                    response_text = parts[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:].strip()
            response_text = response_text.strip()

            raw_items = json.loads(response_text)
            if not isinstance(raw_items, list):
                raw_items = [raw_items]

            items = []
            for idx, raw_item in enumerate(raw_items[:count]):
                items.append({
                    "id": f"ollama-{idx}",
                    "blueprint_id": f"ollama-gen-{idx}",
                    "type": "prompt",
                    "difficulty": raw_item.get("difficulty", "intermediate"),
                    "features": raw_item.get("features", features),
                    "prompt": raw_item.get("prompt", "Fill in the blank."),
                    "expected_answer": raw_item.get("expected_answer", ""),
                    "accepted_variants": raw_item.get("accepted_variants", [raw_item.get("expected_answer", "")]),
                    "answer_preview": raw_item.get("answer_preview", ""),
                })
            return items
        except Exception as e:
            print(f"Ollama generation failed: {e}")
            return []

    def _expand_feature_expr(self, expr) -> list[set[str]]:
        if isinstance(expr, FeatureExpr):
            return [{expr.name}]
        if isinstance(expr, AndExpr):
            left = self._expand_feature_expr(expr.left)
            right = self._expand_feature_expr(expr.right)
            return [left_bundle | right_bundle for left_bundle in left for right_bundle in right]
        if isinstance(expr, OrExpr):
            return self._expand_feature_expr(expr.left) + self._expand_feature_expr(expr.right)
        raise ValueError("Unsupported feature expression.")

    def _normalize_bundle(self, bundle: set[str]) -> set[str]:
        normalized = {item.lower() for item in bundle if item}
        if normalized & self.TENSE_FEATURES and not (normalized & self.SENTENCE_FORMS):
            normalized.add(self.DEFAULT_SENTENCE_FORM)
        return normalized

    @staticmethod
    def _dedupe_bundles(bundles: list[set[str]]) -> list[set[str]]:
        seen: set[tuple[str, ...]] = set()
        unique: list[set[str]] = []
        for bundle in bundles:
            key = tuple(sorted(bundle))
            if key in seen:
                continue
            seen.add(key)
            unique.append(bundle)
        return unique

    def _should_use_corpus_generator(self, bundles: list[set[str]]) -> bool:
        return False

    def _select_blueprints(self, bundles: list[set[str]], requested_total: int) -> list[dict[str, Any]]:
        bundle_matches: list[list[dict[str, Any]]] = []
        for bundle in bundles:
            matches = [
                blueprint
                for blueprint in self.blueprints
                if set(blueprint.get("required_features", [])) <= bundle
            ]
            if not matches:
                continue
            matches.sort(key=lambda item: item["id"])
            bundle_matches.append(matches)

        if not bundle_matches:
            return []

        selected: list[dict[str, Any]] = []
        pointer = 0
        while len(selected) < requested_total:
            matches = bundle_matches[pointer % len(bundle_matches)]
            # Use pointer to ensure we cycle through blueprints even if they match multiple bundles
            blueprint = matches[(pointer // len(bundle_matches)) % len(matches)]
            selected.append(blueprint)
            pointer += 1
        return selected

    def _realize_item(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        family = blueprint.get("family")
        if family == "tense-fill":
            payload = self._build_tense_fill(blueprint, seed_val)
        elif family == "tense-transform":
            payload = self._build_tense_transform(blueprint, seed_val)
        elif family == "agreement":
            payload = self._build_agreement_correction(blueprint, seed_val)
        elif family == "object-pronoun":
            payload = self._build_object_pronoun_correction(blueprint, seed_val)
        elif family == "verb-preposition":
            payload = self._build_verb_preposition_fill(blueprint, seed_val)
        elif family == "svo":
            payload = self._build_svo_fill(blueprint, seed_val)
        else:
            raise ValueError(f"Unsupported exercise family: {family}")

        payload.update(
            {
                "id": f"{blueprint['id']}-{seed_val}",
                "blueprint_id": blueprint["id"],
                "type": blueprint.get("item_type", "prompt"),
                "difficulty": blueprint.get("difficulty", "starter"),
                "features": blueprint.get("required_features", []),
            }
        )
        return payload

    def _build_tense_fill(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        features = set(blueprint.get("required_features", []))
        tense = self._pick_feature(blueprint, self.TENSE_FEATURES)
        subject = self._pick_subject(tense, blueprint, seed_val)
        
        collocation = self._pick_collocation(seed_val)
        if collocation:
            verb_base, obj = collocation["verb"], collocation["object"]
        else:
            verb_base = self._pick_from_pool("transitive_verbs", blueprint, seed_val)
            obj = self._pick_from_pool("objects", blueprint, seed_val)
            
        time_marker = self._pick_time_marker(tense, blueprint, seed_val)

        if "negative" in features:
            expected_list = self._negative_variants(tense, subject, verb_base, obj, time_marker)
            # Extract just the verb phrase from the full sentence (this is a simplified heuristic)
            expected = self._extract_verb_phrase(expected_list[0], subject["surface"], obj, time_marker)
            prompt = self._fill_sentence_template(subject["surface"], f"(not {verb_base}) ____", obj, time_marker)
            answer = expected_list[0]
        elif "interrogative" in features:
            expected_list = self._question_variants(tense, subject, verb_base, obj, time_marker)
            # For interrogatives, we keep the subject in the 'expected' phrase so that 
            # the gap replacement works (since the subject is often between auxiliary and verb)
            expected = self._extract_verb_phrase(expected_list[0], "", obj, time_marker)
            # For questions, the gap might be at the start or middle, so we use a different template
            prompt = expected_list[0].replace(expected, "____")
            prompt = f"({subject['surface']} {verb_base}) {prompt}"
            answer = expected_list[0]
        else:
            expected = self._affirmative_verb_phrase(tense, subject, verb_base)
            prompt = self._fill_sentence_template(subject["surface"], f"({verb_base}) ____", obj, time_marker)
            answer = self._affirmative_sentence(tense, subject, verb_base, obj, time_marker)

        return {
            "prompt": f"Fill in the missing verb form: {prompt}",
            "expected_answer": expected,
            "accepted_variants": [expected],
            "answer_preview": answer,
        }

    def _extract_verb_phrase(self, full_sentence: str, subject: str, obj: str, time_marker: str) -> str:
        # Simple extraction logic: remove subject and tail from sentence
        phrase = full_sentence
        
        # Handle case-insensitive subject removal (important for {subject_lower} templates)
        if subject:
            low_phrase = phrase.lower()
            low_sub = subject.lower()
            idx = low_phrase.find(low_sub)
            if idx != -1:
                phrase = phrase[:idx] + phrase[idx + len(subject):]

        if obj:
            phrase = phrase.replace(obj, "", 1)
        
        if time_marker:
            phrase = phrase.replace(time_marker, "", 1)
            
        return phrase.rstrip(".?").strip()

    def _build_tense_transform(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        features = set(blueprint.get("required_features", []))
        tense = self._pick_feature(blueprint, self.TENSE_FEATURES)
        subject = self._pick_subject(tense, blueprint, seed_val)
        
        # Use collocations if available for more sensible sentences
        collocation = self._pick_collocation(seed_val)
        if collocation:
            verb_base, obj = collocation["verb"], collocation["object"]
        else:
            verb_base = self._pick_from_pool("transitive_verbs", blueprint, seed_val)
            obj = self._pick_from_pool("objects", blueprint, seed_val)
            
        time_marker = self._pick_time_marker(tense, blueprint, seed_val)
        affirmative = self._affirmative_sentence(tense, subject, verb_base, obj, time_marker)

        if "negative" in features:
            accepted = self._negative_variants(tense, subject, verb_base, obj, time_marker)
            prompt = f"Rewrite this sentence in the negative form: {affirmative}"
        else:
            accepted = self._question_variants(tense, subject, verb_base, obj, time_marker)
            prompt = f"Rewrite this sentence as a question: {affirmative}"

        return {
            "prompt": prompt,
            "expected_answer": accepted[0],
            "accepted_variants": accepted,
            "answer_preview": accepted[0],
        }

    def _build_agreement_correction(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        agreement_nouns = self.lexical_pools.get("agreement_nouns", {})
        singular_subjects = agreement_nouns.get("singular", [])
        plural_subjects = agreement_nouns.get("plural", [])
        verb_base = self._pick_from_pool("transitive_verbs", blueprint, seed_val)
        obj = self._pick_from_pool("objects", blueprint, seed_val)

        if seed_val % 2 == 0 and plural_subjects:
            subject = plural_subjects[seed_val % len(plural_subjects)]
            wrong = f"{subject} {self.verb_engine.third_person_singular(verb_base)} {obj} every day."
            correct = f"{subject} {verb_base} {obj} every day."
        else:
            subject = singular_subjects[seed_val % len(singular_subjects)] if singular_subjects else "The student"
            wrong = f"{subject} {verb_base} {obj} every day."
            correct = f"{subject} {self.verb_engine.third_person_singular(verb_base)} {obj} every day."

        return {
            "prompt": f"Correct the subject-verb agreement error: {wrong}",
            "expected_answer": correct,
            "accepted_variants": [correct],
            "answer_preview": correct,
        }

    def _build_object_pronoun_correction(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        pair = self._pick_from_pool("pronoun_pairs", blueprint, seed_val)
        subject = "I"
        verb = "like"
        wrong = f"{subject} {verb} {pair['subject']}."
        correct = f"{subject} {verb} {pair['object']}."
        return {
            "prompt": f"Correct the pronoun form: {wrong}",
            "expected_answer": correct,
            "accepted_variants": [correct],
            "answer_preview": correct,
        }

    def _build_verb_preposition_fill(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        pair = self._pick_from_pool("verb_preposition_pairs", blueprint, seed_val)
        prompt = f"Fill in the missing preposition: {pair['subject']} {pair['verb']} ____ {pair['tail']}."
        expected = pair["preposition"]
        return {
            "prompt": prompt,
            "expected_answer": expected,
            "accepted_variants": [expected],
            "answer_preview": f"{pair['subject']} {pair['verb']} {expected} {pair['tail']}.",
        }

    def _build_svo_fill(self, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        svo_patterns = self.lexical_pools.get("svo_patterns", {})
        bucket = "missing_subject" if seed_val % 2 == 0 else "missing_verb"
        patterns = svo_patterns.get(bucket, [{}])
        pattern = patterns[seed_val % len(patterns)]
        return {
            "prompt": f"Fill in the missing word to complete the sentence: {pattern.get('prompt', '____')}",
            "expected_answer": pattern.get("answer", ""),
            "accepted_variants": [pattern.get("answer", "")],
            "answer_preview": pattern.get('prompt', "").replace("____", pattern.get("answer", "")),
        }

    def _pick_feature(self, blueprint: dict[str, Any], allowed: set[str]) -> str:
        for feature in blueprint.get("required_features", []):
            if feature in allowed:
                return feature
        raise ValueError(f"No supported tense feature found in blueprint '{blueprint.get('id')}' with features {blueprint.get('required_features')}. Allowed: {allowed}")

    def _pick_subject(self, tense: str, blueprint: dict[str, Any], seed_val: int) -> dict[str, Any]:
        subjects = self.lexical_pools.get("subjects", {})
        seed = seed_val
        if tense in {"present continuous", "past continuous", "future continuous"}:
            ordered_groups = ["first_person", "singular", "plural", "second_person"]
        elif tense in {"present simple", "present perfect", "present perfect continuous"}:
            ordered_groups = ["singular", "plural", "first_person", "second_person"]
        else:
            ordered_groups = ["first_person", "singular", "plural", "second_person"]

        candidates: list[dict[str, Any]] = []
        for group in ordered_groups:
            candidates.extend(subjects.get(group, []))
        if not candidates:
            return {"surface": "I", "subject_key": "i", "number": "singular"}
        return candidates[seed % len(candidates)]

    def _pick_from_pool(self, name: str, blueprint: dict[str, Any], seed_val: int):
        pool = self.lexical_pools.get(name, [])
        if not pool:
            raise ValueError(f"Missing lexical pool: {name}")
        return pool[seed_val % len(pool)]

    def _pick_time_marker(self, tense: str, blueprint: dict[str, Any], seed_val: int) -> str:
        markers = self.lexical_pools.get("time_markers", {}).get(tense, [])
        if not markers:
            return ""
        return markers[seed_val % len(markers)]

    def _pick_collocation(self, seed_val: int) -> dict[str, str] | None:
        pool = self.lexical_pools.get("verb_object_collocations", [])
        if not pool:
            return None
        return pool[seed_val % len(pool)]

    def _affirmative_sentence(
        self,
        tense: str,
        subject: dict[str, Any],
        verb_base: str,
        obj: str,
        time_marker: str,
    ) -> str:
        subject_surface = subject["surface"]
        subject_key = subject["subject_key"]
        verb_phrase = self._affirmative_verb_phrase(tense, subject, verb_base)
        return self._fill_sentence_template(subject_surface, verb_phrase, obj, time_marker)

    def _affirmative_verb_phrase(self, tense: str, subject: dict[str, Any], verb_base: str) -> str:
        subject_key = subject["subject_key"]
        tense_key = tense.replace(" ", "_")
        return self.verb_engine.suggest_for_tense(verb_base, tense_key, subject_key)

    def _negative_variants(self, tense: str, subject: dict[str, Any], verb_base: str, obj: str, time_marker: str) -> list[str]:
        subject_key = subject["subject_key"]
        subject_surface = subject["surface"]
        templates = self.realization_rules.get("negative_variants", {})
        template_key = tense
        if tense in {"present simple", "present perfect", "present perfect continuous"} and subject_key in {"he", "she", "it"}:
            template_key = f"{tense}-third-person"
        selected = templates.get(template_key, [])
        return [
            self._fill_template(
                template,
                subject_surface=subject_surface,
                subject_key=subject_key,
                verb_base=verb_base,
                obj=obj,
                time_marker=time_marker,
            )
            for template in selected
        ]

    def _question_variants(self, tense: str, subject: dict[str, Any], verb_base: str, obj: str, time_marker: str) -> list[str]:
        subject_key = subject["subject_key"]
        subject_surface = subject["surface"]
        rules = self.realization_rules.get("question_variants", {})
        template_key = tense
        if tense in {"present simple", "present perfect", "present perfect continuous"} and subject_key in {"he", "she", "it"}:
            template_key = f"{tense}-third-person"
        template = rules.get(template_key)
        if not template:
            return []
        return [
            self._fill_template(
                template,
                subject_surface=subject_surface,
                subject_key=subject_key,
                verb_base=verb_base,
                obj=obj,
                time_marker=time_marker,
            )
        ]

    def _fill_template(
        self,
        template: str,
        *,
        subject_surface: str,
        subject_key: str,
        verb_base: str,
        obj: str,
        time_marker: str,
    ) -> str:
        be_forms = self.realization_rules.get("be_forms", {}).get(subject_key, {})
        mapping = {
            "subject": subject_surface,
            "subject_lower": subject_surface.lower(),
            "verb_base": verb_base,
            "verb_past": self.verb_engine.past_form(verb_base, subject_key),
            "verb_participle": self.verb_engine.participle_form(verb_base),
            "verb_gerund": self.verb_engine.gerund(verb_base),
            "object": obj,
            "time_marker": time_marker,
            "be_positive": be_forms.get("positive", "is"),
            "be_negative": be_forms.get("negative", "is not"),
            "be_contracted_negative": be_forms.get("contracted_negative", "isn't"),
            "be_question": be_forms.get("question", "Is"),
        }
        filled = template.format(**mapping)
        return " ".join(filled.replace(" .", ".").replace(" ?", "?").split())

    @staticmethod
    def _fill_sentence_template(subject_surface: str, verb_phrase: str, obj: str, time_marker: str) -> str:
        core = f"{subject_surface.capitalize()} {verb_phrase} {obj}"
        if time_marker:
            core = f"{core} {time_marker}"
        return f"{core}."


def item_number_seed(text: str) -> int:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)
