"""Quality checks every study item must pass before it is saved.

The checks answer the questions:

* Does the question make sense on its own (no "this slide", no dangling "it")?
* Is it testing an actual concept, not a random word from a fragment?
* Does the answer directly answer the question?
* Does the explanation teach why the answer is correct?
* Is the content supported by the slide, or clearly labelled as added
  CompTIA context and linked to a slide that mentions it?
* Is it free of footer text?

``validate_item`` returns a list of problems; an empty list means the item
is acceptable. ``legacy_card_problems`` applies the structural checks to
cards made by the old generator, which have no explanation or source info.
"""

from __future__ import annotations

import re
from typing import List

from .. import cleanup
from . import SOURCE_CONTEXT, SOURCE_SLIDE, StudyItem

BLANK = "_____"
BLANK_RE = re.compile(r"_{3,}")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’+.#/-]*")

# Sentences that start with these are instructions or steps, not facts to learn.
IMPERATIVES = set(
    """find click select choose open close go use download install uninstall check make run type press
    enter see look get try keep set add remove read follow consider ensure verify configure update
    restart reboot boot plug connect disconnect save copy paste drag drop launch start stop scroll
    navigate visit browse search test confirm review note remember avoid always never don't do be
    let put take give call ask tell show watch wait log sign create delete rename move""".split()
)

# Words that make a statement assert a relationship (X *is* / *provides* / *stores* ...).
RELATIONAL = set(
    """is are was were be been being provides provide allows allow lets let enables enable uses use
    stores store encrypts encrypt protects protect requires require prevents prevent connects connect
    manages manage runs run contains contain includes include means mean refers refer defines define
    describes describe identifies identify controls control supports support creates create converts
    convert replaces replace removes remove copies copy limits limit blocks block scans scan repairs
    repair records record displays display shows show checks check spreads spread hides hide
    restores restore backs secures secure authenticates authenticate grants grant assigns assign
    translates translate resolves resolve sends send receives receive transfers transfer""".split()
)

# Answers that are too vague to be worth learning on their own.
GENERIC_ANSWERS = set(
    """application applications app apps thing things item items one ones way ways information data
    file files system systems user users computer computers device devices option options feature
    features setting settings process processes step steps type types part parts tool tools program
    programs software hardware need needs use uses something someone example examples""".split()
)

DEICTIC = re.compile(
    r"\b(?:this|these|the|that|above|below|following|previous|next)\s+"
    r"(?:slide|slides|list|diagram|image|picture|screenshot|table|figure|bullet|bullets)\b"
    r"|\bas shown\b|\bsee (?:above|below)\b|\bthe following\b",
    re.IGNORECASE,
)
DANGLING_START = re.compile(r"^\s*(?:it|they|this|these|that|those|he|she|its|their)\b", re.IGNORECASE)
# "What does it do?" / "Why are they used?" - the question's subject is an unexplained pronoun
DANGLING_SUBJECT = re.compile(
    r"\b(?:what|how|why|which|when|where|who)\s+(?:does|do|did|is|are|was|were|can|should|would)\s+"
    r"(?:it|they|this|these|that|those)\b",
    re.IGNORECASE,
)
ARTICLES = re.compile(r"^(?:the|a|an|to)\s+", re.IGNORECASE)

MIN_PROMPT_WORDS = 5
MIN_EXPLANATION_WORDS = 10
MAX_TERM_ANSWER_WORDS = 10


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s+#./-]", " ", text.lower())).strip()


def words(text: str) -> List[str]:
    return WORD_RE.findall(text)


def contains(haystack: str, needle: str) -> bool:
    n = norm(needle)
    return bool(n) and n in norm(haystack)


def answer_variants(answer: str) -> List[str]:
    """Ways an explanation may refer to the answer: "User Account Control (UAC)" can be
    called "User Account Control" or "UAC"; "The operating system" can be "operating system"."""
    variants = {answer, ARTICLES.sub("", answer)}
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", answer)
    if m:
        variants |= {m.group(1), ARTICLES.sub("", m.group(1)), m.group(2)}
    return [v for v in variants if v.strip()]


def connects(explanation: str, answer: str, concept: str) -> bool:
    if any(contains(explanation, v) for v in answer_variants(answer) + [concept]):
        return True
    # a longer answer may be paraphrased: most of its key words should appear
    key = [w.lower() for w in words(answer) if len(w) >= 4]
    if len(key) >= 3:
        found = sum(1 for w in key if w[:6] in norm(explanation))
        return found / len(key) >= 0.5
    return False


def cloze_sentence(prompt: str) -> str:
    return re.sub(r"^\s*fill in the blank\s*:?\s*", "", prompt, flags=re.IGNORECASE).strip()


def cloze_problems(sentence: str, answer: str) -> List[str]:
    """Checks for a fill-in-the-blank sentence (shared by new and old cards)."""
    problems = []
    if len(BLANK_RE.findall(sentence)) != 1:
        problems.append("a fill-in-the-blank needs exactly one blank")
    filled = BLANK_RE.sub(answer, sentence)
    ws = [w.lower().strip(".,;:") for w in words(filled)]
    if len(ws) < 6:
        problems.append("the sentence is a fragment (too short to teach anything)")
    if ws and ws[0] in IMPERATIVES:
        problems.append("the sentence is an instruction or step, not a fact or definition")
    if not RELATIONAL.intersection(ws):
        problems.append("the sentence doesn't state a relationship or definition (no linking verb)")
    if norm(answer) in GENERIC_ANSWERS or len(norm(answer)) < 2:
        problems.append(f"the blanked word “{answer}” is too vague to be a key term")
    if DANGLING_START.match(sentence):
        problems.append("the sentence starts with a pronoun that refers to something not shown")
    return problems


def validate_item(item: StudyItem, slide_text: str) -> List[str]:
    """Return a list of problems with the item. Empty list = acceptable."""
    problems: List[str] = []
    prompt, answer, explanation = item.prompt.strip(), item.answer.strip(), item.explanation.strip()

    # --- every field must be present and free of footer text
    if not prompt or not answer:
        return ["missing question or answer"]
    for name, value in (("question", prompt), ("answer", answer), ("explanation", explanation),
                        ("source line", item.slide_support), ("added context", item.added_context),
                        *[("option", o) for o in item.options]):
        if value and cleanup.contains_footer(value):
            problems.append(f"the {name} contains slide-footer text")

    # --- the question must make sense on its own
    if len(words(prompt)) < MIN_PROMPT_WORDS:
        problems.append("the question is too short to be clear")
    if DEICTIC.search(prompt):
        problems.append("the question refers to the slide/list instead of standing on its own")
    if DANGLING_START.match(cloze_sentence(prompt)) or DANGLING_SUBJECT.search(prompt):
        problems.append("the question uses a pronoun that refers to something not shown")

    # --- question form
    if item.kind == "cloze":
        problems += cloze_problems(cloze_sentence(prompt), answer)
    elif not prompt.endswith("?"):
        problems.append("the question isn't phrased as a question")

    # --- the answer must directly answer the question, without giving itself away
    if item.kind != "definition" and contains(prompt, answer):
        problems.append("the question gives away the answer")
    if item.kind in ("cloze", "term_mc", "concept_mc") and len(words(answer)) > MAX_TERM_ANSWER_WORDS:
        problems.append("the answer is too long for a 'which term' question")
    if item.kind == "definition":
        if len(words(answer)) < 3:
            problems.append("the definition answer is too thin to teach the concept")
        if norm(answer) == norm(item.concept):
            problems.append("the answer just repeats the term")
    if norm(answer) in GENERIC_ANSWERS:
        problems.append(f"the answer “{answer}” is too vague")

    # --- multiple choice must be well-formed
    if item.options:
        if len(item.options) < 3:
            problems.append("multiple choice needs at least 3 options")
        if len({norm(o) for o in item.options}) != len(item.options):
            problems.append("multiple-choice options repeat")
        if answer not in item.options:
            problems.append("the correct answer isn't one of the options")
        for option in item.options:
            if option != answer and not item.why_wrong.get(option, "").strip():
                problems.append(f"no explanation for why “{option}” is wrong")

    # --- the explanation must teach why
    if len(words(explanation)) < MIN_EXPLANATION_WORDS:
        problems.append("the explanation is missing or too short to teach why")
    elif not connects(explanation, answer, item.concept):
        problems.append("the explanation doesn't connect to the answer")
    if norm(explanation) == norm(answer):
        problems.append("the explanation only repeats the answer")

    # --- support: slide facts must be on the slide; added context must be labelled and linked
    if item.source == SOURCE_SLIDE:
        if not item.slide_support or not contains(slide_text, item.slide_support):
            problems.append("the item isn't backed by a line on the slide")
        elif item.kind in ("definition", "acronym") and not contains(slide_text, answer):
            problems.append("the answer isn't supported by the slide")
        elif item.kind in ("cloze", "term_mc") and not contains(slide_text, answer):
            problems.append("the answer term isn't on the slide")
    elif item.source == SOURCE_CONTEXT:
        if not item.added_context.strip():
            problems.append("added CompTIA context isn't labelled")
        if not item.slide_support or not contains(slide_text, item.slide_support):
            problems.append("added context isn't linked to a slide line")
        elif item.mentions and not any(contains(item.slide_support, m) for m in item.mentions):
            problems.append("the linked slide line doesn't mention the concept")
    else:
        problems.append(f"unknown source “{item.source}”")
    return problems


def legacy_card_problems(front: str, back: str) -> List[str]:
    """Structural checks for cards made by the old generator (no explanation/source info)."""
    prompt = front.rpartition("\n\n")[2].strip()  # old cards put the slide title first
    problems: List[str] = []
    if cleanup.contains_footer(front) or cleanup.contains_footer(back):
        problems.append("contains slide-footer text")
    if prompt.lower().startswith("fill in the blank"):
        problems += cloze_problems(cloze_sentence(prompt), back)
    if DEICTIC.search(prompt) or re.search(r"\bwhich term is this\b", prompt, re.IGNORECASE):
        problems.append("refers to the slide instead of standing on its own")
    problems.append("has no explanation of why the answer is correct")
    return problems
