# Study Guide

A personal, offline study app for macOS. It builds study materials from PNG
screenshots of lecture slides.

Point it at your main study folder. Each subfolder is a **topic**, and every
PNG inside it is a **slide**. The app reads the text on each slide, and you
can correct that text. Later steps will build flashcards, quizzes, summaries
and practice exams from it.

## Privacy and your files

- **Your images are never changed.** The app only reads them. It never
  modifies, moves, renames or deletes anything in your study folder, and it
  doesn't write any files there. Automated tests check this.
- **Everything stays on your Mac.** Transcripts, progress and settings live in
  `~/Library/Application Support/StudyGuide/studyguide.sqlite3`.
- **No internet, accounts or API keys.** The app reads text using Apple's
  Vision framework, which is built into macOS and runs locally.

## Setup (one time)

You need Python 3.9 or newer. To check, open Terminal and run
`python3 --version`. If Python is missing or older than 3.9, install it from
<https://www.python.org/downloads/macos/>.

```bash
cd path/to/Study-guide
./setup.sh
```

This creates a private `.venv` folder in this project and installs PySide6
(the window toolkit) and Apple Vision bindings. It doesn't install anything
system-wide.

## Running

```bash
./run.sh
```

You can also double-click **`Study Guide.command`** in Finder. The first
time, macOS may ask you to confirm; if so, right-click the file → Open.

## Using it: Library (step 1)

1. Click **Choose Study Folder…** and pick your main study folder. The app
   remembers it for next time.
2. The left panel lists topics, for example `Biology (3/10 transcribed)`, with
   their slides underneath:
   - `○` not transcribed yet
   - `✓` text was read automatically (worth checking)
   - `✎` you have edited the transcript
   - `⚠` the image file changed since its text was read
3. Click **Read Text from New Slides** to transcribe every slide that has no
   text yet. This runs in the background and the window stays usable.
4. Click a slide to see the image next to its transcript. The header shows
   which topic and file the text came from.
5. Fix mistakes in the text box. Click **Save** (⌘S). The app also saves
   automatically when you switch slides or quit.
6. Added new screenshots? Click **Refresh Library** (⌘R), then **Read Text
   from New Slides**.
   - Existing transcripts and edits are always kept.
   - If you remove a slide from the folder, it's hidden but its transcript is
     kept. If you put it back, the transcript returns too.
   - Re-reading never overwrites text you edited. **Re-read Text from Image**
     on one slide asks before replacing your edits.

## Flashcards (step 2)

Click **🃏 Flashcards** at the top.

- **Your stats:** your 🔥 streak, ⭐ level and XP, and 🏅 badges are at the
  top.
- **Start a round:** a short round of about 10 cards, with cards due for
  review first and then a few new ones. **Practice** on a topic tile studies
  just that topic.
- **Each card:** read the question, press **Show answer** (space), then pick
  one of:
  - **😅 Still learning** (1): the card comes back at the end of the round,
    and again in about 10 minutes.
  - **🙂 Got it** (2): see it again tomorrow, then in 3 days, with longer
    gaps after that.
  - **😎 Easy** (3): a bigger jump.
- **Where the answer comes from:** every answer shows the slide line it came
  from and a thumbnail of the slide.
- **Points:**
  - 10 XP for each right answer, and 2 XP for trying when you miss.
  - A bonus at the end of the round, and a bigger one for a perfect round.
  - You never lose points.
- **Streak:** your streak counts days in a row with at least one card. It
  survives until the end of the day after you last studied.
- **Round summary:** XP, score, streak and new badges, plus a "Learn from
  these" list showing what the slides say about the cards you missed.
- **Hiding cards:** hide a card that isn't useful with **🙈 Hide this
  card**. Nothing is deleted.

### How questions are made

Questions are made offline, on your Mac, in three steps:

1. **Find the concept.** For each slide (with footers removed), the generator
   looks for:
   - explicit definitions (`Term: meaning`, `Term - meaning`, `Term = meaning`,
     `Term is a …`)
   - acronyms with their expansion, like `EFS (Encrypting File System)`
   - CompTIA A+ Core 2 concepts the slide mentions
   - complete statements about a key term
2. **Write questions about that concept.** These include multiple choice
   ("Which term is defined as…?"), definitions, acronyms and, only for
   complete, meaningful statements, fill-in-the-blank.
3. **Check every question before saving it** (`generators/validate.py`). The
   checker asks:
   - Does the question make sense without seeing the slide?
   - Does it test a concept, rather than a random word from an instruction or
     fragment?
   - Does the answer actually answer the question, without being given away?
   - Does the explanation teach why the answer is right, and say why each
     other option is wrong?
   - Is it backed by a line on the slide, or clearly labelled as added
     context?

   If a question fails, the generator tries a different kind of question for
   the same concept. If none pass, it skips that concept. A slide without
   enough useful information gets no questions at all, rather than weak ones.

**Added CompTIA A+ Core 2 context.** `knowledge/core2.py` is a hand-checked
bank of about 45 Core 2 concepts: file systems, Windows tools, commands,
malware, social engineering, backups, operational procedures and remote
access. Each has a clear question, an explanation and reasons why the
alternatives are wrong.

A concept is used only when your slide mentions it. An everyday word like
"application" must appear in the slide title or more than once. In the app
these questions are always labelled **🎓 Added CompTIA A+ Core 2 context (not
from your slide)**, and they show the slide line that mentions the concept.
Slide-based questions show **From your slide** with the exact line.

**Limits.** The offline generator can only ask about what it recognises:
defined terms, acronyms, and concepts in the bank. It can't yet write
scenario or troubleshooting questions about every bullet on a slide. That
needs an AI option, which we haven't chosen yet, and its output would go
through the same checks.

**Preview on your own slides first.** This is read-only and saves nothing:

```bash
.venv/bin/python -m studyguide.preview                       # every topic
.venv/bin/python -m studyguide.preview --topic "File Systems" --rejected
.venv/bin/python -m studyguide.preview > preview.txt         # save to a file
```

**Older cards.** Cards made by the first version of the app, which blanked out
a word from any line (for example "Find the _____ you need" → "application"),
are checked when you open Flashcards. Cards that fail the new checks are
**paused**, so they no longer appear in rounds. A yellow banner offers
**Preview & regenerate**: it shows the paused cards, why each one failed, and
the new questions from the same slides. Nothing changes until you click
**Regenerate from my slides**. Old cards are then retired, not deleted, so
their review history is kept.

When you edit a transcript, its questions update the next time you open
Flashcards. Questions for lines you removed are retired but keep their review
history. If a line comes back, its question returns with its history.

### Removing slide footers

The Professor Messer footer, `https://ProfessorMesser.com © 2025 Messer
Studios, LLC`, is removed from transcripts and can never become study
material. Detection tolerates OCR mistakes, for example:

- `@` or `e` read instead of `©`
- a missing `//`, or a comma instead of a dot
- `O` read for `0`, or `Studlos` for `Studios`
- different capitalization or a different year
- the footer split over two lines

If the footer is glued onto the end of a real line, only the footer part is
removed and the rest of the line stays. Real copyright notices such as
`© 2024 …` or `All rights reserved` are removed too, but content that only
mentions copyright, like "Copyright law protects software", is kept. Nothing is
removed just because it sits near the bottom of a slide.

- **New readings** are cleaned automatically. The raw text reading is kept in
  the database.
- **Existing transcripts** were cleaned once automatically when you first
  opened this version.
- **🧹 Ignore Text** in the Library lets you:
  - preview exactly which lines would be removed
  - add your own phrases (case, spacing and punctuation are ignored)
  - switch the built-in rules off
  - **undo the last cleanup**

  Every cleanup backs up the previous transcript text first. Your PNG files
  are never changed.

## Running the tests

```bash
.venv/bin/python -m pytest
```

The tests use temporary folders and a temporary data directory, so they never
touch your real study folder or app data. They cover:

- scanning topics and PNGs
- rescanning: new, changed, removed and restored slides
- keeping transcripts and IDs across rescans and restarts
- manual edits surviving re-reading
- checking that the study folder is byte-for-byte unchanged, including file
  dates, after every operation
- a run of the real window using a fake text reader
- footer removal: the exact Professor Messer footer and OCR-mangled
  variations, footers split over lines or glued onto content, useful
  "copyright" content kept, and cleanup backup and undo
- question quality:
  - "Find the _____ you need" → "application" is rejected
  - accepted questions are self-contained and have a clear answer and an
    explanation
  - slide facts are kept apart from added context
  - footer text never becomes study content
  - every concept-bank entry passes validation
- old cards: fragment cards are paused, previewed and regenerated, and
  their history is kept
- flashcards:
  - edits and rescans keep review history
  - the review schedule
  - round rules: missed cards return, no giveaway pairs
  - XP, levels, streaks and badges
  - a full round played in the real window

## Project layout

```
studyguide/
  paths.py        where app data is stored
  db.py           SQLite schema and migrations
  library.py      scanning the study folder (read-only)
  transcripts.py  editable transcripts; protects manual edits
  cleanup.py      removes slide footers (OCR-tolerant), with backup/undo
  knowledge/      hand-checked CompTIA A+ Core 2 concept bank (added context)
  preview.py      read-only preview of generated questions
  ocr.py          Apple Vision text recognition (local)
  generators/     concept -> question -> validation (offline.py, validate.py)
  flashcards.py   cards, review schedule, picking rounds
  rounds.py       one flashcard round: answers, points, summary
  progress.py     XP, levels, streaks and badges
  ui/             the desktop window (PySide6)
    theme.py      colours, font and styling
  assets/fonts/   Nunito font (SIL Open Font License, see OFL.txt)
tests/            automated tests
```

## Roadmap

1. ✅ Choose a folder, scan topics, view slides, edit transcripts
2. ✅ Flashcards with spaced review, points, streaks, levels and badges
3. Topic quizzes with explanations linked back to slides
4. Topic summaries
5. Practice exams: topic selection, question count, difficulty, optional
   timer, review afterward
6. Progress dashboard: strong and weak areas, trends over time

**AI generation is not decided yet.** Study materials will be generated
through one swappable "generator" component. Options include a simple offline
generator, a free local model, or a cloud service. A cloud service would only
be added with your explicit approval, and its API key would never be stored in
the code.
