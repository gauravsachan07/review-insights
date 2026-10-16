"""Constraint checks for generated artifacts (architecture stage 5)."""

from __future__ import annotations

from typing import Iterable

from src.models import FeeExplainer, IntelligenceResult, WeeklyPulse

PULSE_MAX_WORDS = 250
PULSE_REQUIRED_SECTIONS = ("themes", "quote", "observation", "action")
EXPLAINER_MAX_BULLETS = 6
EXPLAINER_REQUIRED_LINKS = 2


def word_count(text: str) -> int:
    return len(text.split())


def validate_pulse(pulse: WeeklyPulse, max_words: int = PULSE_MAX_WORDS) -> list[str]:
    errors: list[str] = []
    count = word_count(pulse.markdown)
    if count > max_words:
        errors.append(f"pulse is {count} words (max {max_words})")

    lowered = pulse.markdown.lower()
    for section in PULSE_REQUIRED_SECTIONS:
        if section not in lowered:
            errors.append(f"pulse is missing required section: {section}")
    return errors


def validate_intelligence(
    intelligence: IntelligenceResult, max_themes: int = 5
) -> list[str]:
    errors: list[str] = []
    if len(intelligence.themes) > max_themes:
        errors.append(f"more than {max_themes} themes")
    if len(intelligence.quotes) > 3:
        errors.append("more than 3 quotes")
    return errors


def validate_explainer(
    explainer: FeeExplainer, allowed_urls: Iterable[str]
) -> list[str]:
    errors: list[str] = []
    if len(explainer.bullets) > EXPLAINER_MAX_BULLETS:
        errors.append(
            f"explainer has {len(explainer.bullets)} bullets "
            f"(max {EXPLAINER_MAX_BULLETS})"
        )
    if len(explainer.source_links) != EXPLAINER_REQUIRED_LINKS:
        errors.append(
            f"explainer needs exactly {EXPLAINER_REQUIRED_LINKS} links, "
            f"got {len(explainer.source_links)}"
        )
    allowed = set(allowed_urls)
    for link in explainer.source_links:
        if link not in allowed:
            errors.append(f"link not in source allowlist: {link}")
    return errors
