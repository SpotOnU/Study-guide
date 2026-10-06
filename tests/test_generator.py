"""Quality rules for generated study items."""

import pytest
from conftest import APP_SLIDE, FOOTER, FS_SLIDE, MALWARE_SLIDE

from studyguide.generators import SOURCE_CONTEXT, SOURCE_SLIDE, SlideText, StudyItem
from studyguide.generators.offline import OfflineGenerator, parse_slide
from studyguide.generators.validate import legacy_card_problems, validate_item, words
from studyguide.knowledge.core2 import CONCEPTS

BAD_SLIDE = """Installing applications
• Find the application you need
• Download from the vendor"""


def generate(*texts, topic="Core 2"):
    slides = [SlideText(i + 1, topic, f"{topic}/slide{i + 1}.png", t) for i, t in enumerate(texts)]
    return OfflineGenerator().generate_topic(slides)


# ------------------------------------------------------------- the exact bad card

def test_exact_bad_example_is_rejected():
    bad = StudyItem(
        image_id=1, kind="cloze", concept="application",
        prompt="Fill in the blank: Find the _____ you need",
        answer="application",
        explanation="",
        source=SOURCE_SLIDE, slide_support="Find the application you need",
    )
    problems = validate_item(bad, BAD_SLIDE)
    assert any("instruction" in p for p in problems)
    assert any("fragment" in p for p in problems)
    assert any("too vague" in p for p in problems)
    assert any("explanation" in p for p in problems)
    # ...even with an explanation attached, an instruction fragment is still rejected
    bad.explanation = "The slide says to find the application you need before installing it on the computer."
    assert validate_item(bad, BAD_SLIDE)


def test_old_card_with_the_exact_bad_wording_is_flagged():
    problems = legacy_card_problems("Installing applications\n\nFill in the blank:\nFind the _____ you need",
                                    "application")
    assert any("instruction" in p or "fragment" in p for p in problems)


def test_generator_never_blanks_words_out_of_instructions():
    result = generate(BAD_SLIDE)
    for item in result.items:
        assert "Find the" not in item.prompt
        assert item.kind != "cloze" or "_____ you need" not in item.prompt


def test_instruction_slide_gets_a_real_concept_question_instead():
    result = generate(APP_SLIDE)
    prompts = [i.prompt for i in result.items]
    assert "Which type of software lets a user perform a specific task, such as editing a document?" in prompts
    item = next(i for i in result.items if i.answer == "Application software")
    assert item.source == SOURCE_CONTEXT          # clearly labelled as added context
    assert "Added CompTIA A+ Core 2 context" in item.added_context
    assert item.slide_support == "Installing applications"  # linked to where the slide mentions it
    assert "Operating system" in item.why_wrong   # explains a plausible alternative


# ------------------------------------------------------------- accepted items are meaningful

@pytest.mark.parametrize("text", [APP_SLIDE, MALWARE_SLIDE, FS_SLIDE])
def test_every_accepted_item_is_meaningful(text):
    result = generate(text)
    assert result.items, "a content-rich slide should produce questions"
    for item in result.items:
        assert validate_item(item, parse_slide(SlideText(1, "Core 2", "x.png", text)).text) == []
        assert len(words(item.prompt)) >= 5
        assert item.prompt.endswith("?") or item.prompt.startswith("Fill in the blank:")
        assert item.answer.strip()
        assert len(words(item.explanation)) >= 10
        assert item.answer.lower() not in item.prompt.lower()
        assert item.slide_support, "every item links back to a slide line"
        if item.options:
            assert item.answer in item.options
            assert set(item.why_wrong) == set(item.options) - {item.answer}


def test_slide_facts_and_added_context_are_kept_apart():
    result = generate(MALWARE_SLIDE, topic="Security")
    slide_items = [i for i in result.items if i.source == SOURCE_SLIDE]
    context_items = [i for i in result.items if i.source == SOURCE_CONTEXT]
    assert slide_items and context_items
    for item in slide_items:
        # answers to slide-based items really are on the slide
        assert item.answer.lower() in MALWARE_SLIDE.lower()
    for item in context_items:
        assert item.added_context.startswith("Added CompTIA A+ Core 2 context")
        assert any(m.lower() in item.slide_support.lower() for m in item.mentions)


def test_slide_definitions_become_which_term_questions_with_reasons():
    result = generate(MALWARE_SLIDE, topic="Security")
    item = next(i for i in result.items if i.kind == "term_mc" and i.answer == "Worm")
    assert "self-replicates across the network" in item.prompt
    assert set(item.options) == {"Ransomware", "Worm", "Trojan horse"}
    assert "encrypts your data" in item.why_wrong["Ransomware"]


def test_acronyms_are_tested_with_their_expansion():
    result = generate("Encryption\n• EFS (Encrypting File System) protects individual files", topic="Security")
    item = next(i for i in result.items if i.kind == "acronym")
    assert item.prompt == "What does the acronym EFS stand for?"
    assert item.answer == "Encrypting File System"


def test_not_enough_information_means_no_question():
    result = generate("Agenda\n• Questions\n• Next steps\n• Thanks for watching", topic="Misc")
    assert result.items == []
    assert result.skipped_slides == ["Misc/slide1.png"]


def test_footer_never_appears_in_generated_items():
    result = generate(APP_SLIDE, MALWARE_SLIDE, FS_SLIDE)
    for item in result.items:
        blob = " ".join([item.prompt, item.answer, item.explanation, item.slide_support,
                         item.added_context, *item.options, *item.why_wrong.values()])
        assert "messer" not in blob.lower()
        assert FOOTER not in blob


def test_concepts_are_not_repeated_within_a_topic():
    result = generate(MALWARE_SLIDE, MALWARE_SLIDE.replace("Malware", "Malware review"), topic="Security")
    keys = [(i.concept.lower(), i.kind) for i in result.items]
    assert len(keys) == len(set(keys))


def test_generic_word_in_passing_does_not_pull_in_a_concept_question():
    # "application" appears once, not in the title: not enough to ask about application software
    result = generate("Event Viewer logs\n• Application log shows program errors\n• Security log shows audits")
    assert all(i.answer != "Application software" for i in result.items)


def test_validator_rejects_common_problems():
    slide = "Encryption\n• BitLocker encrypts the entire volume"
    good = StudyItem(1, "cloze", "BitLocker", "Fill in the blank: _____ encrypts the entire storage volume",
                     "BitLocker", "The full statement is “BitLocker encrypts the entire volume”, so the "
                     "blank is BitLocker.", SOURCE_SLIDE, "BitLocker encrypts the entire volume")
    # the support line must really be on the slide
    assert any("backed by a line" in p for p in validate_item(good, "Different slide"))
    no_context_label = StudyItem(1, "concept_mc", "BitLocker", "Which Windows feature encrypts a whole drive?",
                                 "BitLocker", "BitLocker provides full-volume encryption for Windows drives.",
                                 SOURCE_CONTEXT, "BitLocker encrypts the entire volume",
                                 options=["BitLocker", "EFS", "UAC"],
                                 why_wrong={"EFS": "Files only.", "UAC": "Elevation prompts."})
    assert any("isn't labelled" in p for p in validate_item(no_context_label, slide))
    giveaway = StudyItem(1, "concept_mc", "BitLocker", "What does BitLocker do to the drive?", "BitLocker",
                         "BitLocker provides full-volume encryption for Windows drives.", SOURCE_CONTEXT,
                         "BitLocker encrypts the entire volume", added_context="Added CompTIA A+ Core 2 context")
    assert any("gives away" in p for p in validate_item(giveaway, slide))
    dangling = StudyItem(1, "definition", "it", "What does it do on this slide?", "It encrypts things well",
                         "It encrypts things on the drive so nobody else can read the data stored there.",
                         SOURCE_SLIDE, "BitLocker encrypts the entire volume")
    problems = validate_item(dangling, slide)
    assert any("pronoun" in p for p in problems) and any("refers to the slide" in p for p in problems)


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda c: c.key)
def test_every_concept_bank_entry_passes_validation(concept):
    alias = (concept.aliases + concept.generic_aliases)[0]
    slide = f"{alias} overview\n• Notes about {alias} for the exam"
    result = generate(slide, topic="Bank")
    assert any(i.concept == concept.term for i in result.items), [r.problems for r in result.rejected]
