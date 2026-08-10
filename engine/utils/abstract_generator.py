#!/usr/bin/env python3
"""
Abstract Generator Utility - Production-Grade Implementation

SOLID Principles:
- Single Responsibility: Only handles abstract generation
- Open/Closed: Extensible for new languages without modification
- Interface Segregation: Clean function interface
- Dependency Inversion: Depends on abstractions (model interface)

DRY Principle:
- Reusable by all draft generation scripts
- Centralized logic for abstract generation and replacement
"""

import re
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def detect_draft_language(draft_content: str) -> str:
    """
    Detect draft language from content.
    """
    # Check for Turkish indicators
    turkish_indicators = [
        '## Özet',
        '## İçindekiler',
        '## Giriş',
        '## Sonuç',
        'Anahtar Kelimeler:',
        'Literatür Taraması',
        'Metodoloji'
    ]
    if any(indicator in draft_content for indicator in turkish_indicators):
        return 'turkish'

    # Check for German indicators
    german_indicators = [
        '## Zusammenfassung',
        '## Inhaltsverzeichnis',
        '## Einleitung',
        '## Fazit',
        'Schlüsselwörter:'
    ]
    if any(indicator in draft_content for indicator in german_indicators):
        return 'german'

    # Default to English
    return 'english'


def has_placeholder_abstract(draft_content: str) -> bool:
    """
    Check if draft has a placeholder abstract that needs generation.
    """
    placeholders = [
        '[Abstract will be generated',
        '[Zusammenfassung wird',
        '[Özet üretilecek'
    ]

    return any(placeholder in draft_content for placeholder in placeholders) or '[Abstract' in draft_content


def extract_draft_for_abstract(draft_content: str, max_chars: int = 15000) -> str:
    """
    Extract relevant content for abstract generation (introduction + conclusion).
    """
    content_start = 0
    if draft_content.startswith('---'):
        end_frontmatter = draft_content.find('---', 3)
        if end_frontmatter != -1:
            content_start = end_frontmatter + 3

    main_content = draft_content[content_start:].strip()
    introduction = main_content[:7500]

    conclusion = ""
    conc_patterns = [
        r'# (Conclusion|Fazit|Schlussfolgerung|Sonuç)\n+(.*?)(?=\n---|$)',
        r'## (Conclusion|Fazit|Schlussfolgerung|Sonuç)\n+(.*?)(?=\n---|$)'
    ]

    for pattern in conc_patterns:
        conc_match = re.search(pattern, draft_content, re.DOTALL)
        if conc_match:
            conclusion = conc_match.group(2).strip()[:7500]
            break

    if not conclusion:
        conclusion = draft_content[-7500:].strip()

    context = f"{introduction}\n\n...\n\n{conclusion}"
    if len(context) > max_chars:
        context = context[:max_chars] + "..."

    return context


def replace_placeholder_with_abstract(draft_content: str, generated_abstract: str, language: str = 'english') -> str:
    """
    Replace placeholder abstract with generated content.
    """
    generated_abstract = re.sub(
        r'^(Here is the abstract|Hier ist die Zusammenfassung|İşte özet).*?\n+',
        '',
        generated_abstract,
        flags=re.IGNORECASE
    ).strip()

    if language in ['turkish', 'tr']:
        placeholder_pattern = r'^\s*## (?:Abstract|Özet)\n+\s*\[(?:Abstract|Özet).*?\]\n*\s*\\\\?newpage'
        replacement = f"## Özet\n\n{generated_abstract}\n\n\\\\newpage"
    elif language in ['german', 'de']:
        placeholder_pattern = r'^\s*## (?:Zusammenfassung|Abstract)\n+\s*\[(?:Zusammenfassung|Abstract).*?\]\n*\s*\\\\?newpage'
        replacement = f"## Zusammenfassung\n\n{generated_abstract}\n\n\\\\newpage"
    else:
        placeholder_pattern = r'^\s*## Abstract\n+\s*\[Abstract will be generated.*?\]\n*\s*\\\\?newpage'
        replacement = f"## Abstract\n\n{generated_abstract}\n\n\\\\newpage"

    # Replace placeholder (MULTILINE to match ^ at line start, DOTALL to match . across lines)
    updated_content = re.sub(placeholder_pattern, replacement, draft_content, flags=re.DOTALL | re.MULTILINE)

    # Verify replacement happened
    if updated_content == draft_content:
        logger.warning("Placeholder pattern not found - trying alternative patterns")

        # Try alternative patterns (account for optional leading whitespace from indented templates)
        alt_patterns = [
            # Match with \newpage (escaped in markdown as \\newpage) - with optional whitespace
            (r'^\s*## Abstract\n+\s*\[.*?\]\n+\s*\\\\newpage', f"## Abstract\n\n{generated_abstract}\n\n\\\\newpage"),
            (r'^\s*## Zusammenfassung\n+\s*\[.*?\]\n+\s*\\\\newpage', f"## Zusammenfassung\n\n{generated_abstract}\n\n\\\\newpage"),
            # Match with literal \newpage - with optional whitespace
            (r'^\s*## Abstract\n+\s*\[.*?\]\n+\s*\\newpage', f"## Abstract\n\n{generated_abstract}\n\n\\newpage"),
            (r'^\s*## Zusammenfassung\n+\s*\[.*?\]\n+\s*\\newpage', f"## Zusammenfassung\n\n{generated_abstract}\n\n\\newpage"),
            # Match without newpage - with optional whitespace
            (r'^\s*## Abstract\n+\s*\[.*?\]', f"## Abstract\n\n{generated_abstract}"),
            (r'^\s*## Zusammenfassung\n+\s*\[.*?\]', f"## Zusammenfassung\n\n{generated_abstract}"),
        ]

        for pattern, repl in alt_patterns:
            updated_content = re.sub(pattern, repl, draft_content, flags=re.DOTALL | re.MULTILINE)
            if updated_content != draft_content:
                logger.info("Alternative pattern matched successfully")
                break

    return updated_content


def generate_abstract_for_draft(
    draft_path: Path,
    model,
    run_agent_func,
    output_dir: Path,
    verbose: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Generate and integrate abstract for a draft.

    This is the main entry point for abstract generation. It:
    1. Reads the draft
    2. Checks if abstract generation is needed
    3. Calls the Abstract Generator agent
    4. Replaces the placeholder with generated content
    5. Saves the updated draft

    Args:
        draft_path: Path to draft markdown file
        model: LLM model instance
        run_agent_func: Function to run agent (from test_utils)
        output_dir: Output directory for intermediate files
        verbose: Print progress messages

    Returns:
        Tuple of (success: bool, updated_content: str or None)
    """
    # Read draft
    with open(draft_path, 'r', encoding='utf-8') as f:
        draft_content = f.read()

    # Detect language
    language = detect_draft_language(draft_content)

    # Check if abstract generation is needed
    if not has_placeholder_abstract(draft_content):
        if verbose:
            print("✅ Draft already has a full abstract - skipping generation")
        return True, draft_content

    if verbose:
        print(f"📝 Placeholder abstract detected ({language}) - generating full abstract...")

    # Extract context for abstract generation
    draft_context = extract_draft_for_abstract(draft_content)

    if verbose:
        print(f"  • Extracted {len(draft_context)} chars of context")
        print(f"  • Language: {language}")

    # Prepare user input for Abstract Generator agent
    user_input = f"""Generate an academic abstract for this draft.

**Language:** {language.title()}

**Draft Context:**
{draft_context}

**Instructions:**
- Generate a 4-paragraph abstract (250-300 words)
- Include 12-15 relevant keywords
- Follow standard academic abstract structure
- Output ONLY the abstract content (no meta-comments)
"""

    # Call Abstract Generator agent
    try:
        generated_abstract = run_agent_func(
            model=model,
            name="Abstract Generator (Agent #6.5)",
            prompt_path="prompts/06_enhance/abstract_generator.md",
            user_input=user_input,
            save_to=output_dir / "16_abstract_generated.md"
        )

        if not generated_abstract:
            if verbose:
                print("❌ Abstract generation failed - agent returned no content")
            return False, None

        # Count words in generated abstract
        word_count = len(generated_abstract.split())
        if verbose:
            print(f"✅ Abstract generated: {word_count} words")

        # Warn if word count is outside target range
        if word_count < 200 or word_count > 350:
            if verbose:
                print(f"⚠️  WARNING: Word count outside target range (250-300)")

        # Replace placeholder with generated abstract
        updated_content = replace_placeholder_with_abstract(draft_content, generated_abstract, language)

        if updated_content == draft_content:
            if verbose:
                print("❌ ERROR: Failed to replace placeholder abstract")
            return False, None

        # Save updated draft
        with open(draft_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)

        if verbose:
            print(f"✅ Abstract integrated into draft at {draft_path}")

        return True, updated_content

    except Exception as e:
        if verbose:
            print(f"❌ ERROR generating abstract: {e}")
        return False, None


