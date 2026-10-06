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

### How cards are made (for now)

Cards come from a basic **offline generator**. It never invents anything and
only reuses wording from your transcripts:

- `Term: meaning`, `Term - meaning` and `Term = meaning` lines become a
  definition card and a reverse "which term is this?" card. The two never
  appear in the same round.
- Other lines with 4 or more words become fill-in-the-blank cards. The
  generator hides one key word, preferring acronyms and technical-looking
  words.
- Very short lines (like a single word) don't become cards.

Because it is rule-based, cards can be plain or occasionally odd. Hide those.
Better question writing comes later, when we choose an AI option.

When you edit a transcript, the matching cards update the next time you open
Flashcards. Cards for lines you removed are retired but keep their review
history. If a line comes back, its card returns with its history.

PNGs placed directly in the main folder (not in a topic subfolder) are
skipped. Hidden files and folders (names starting with `.`) are ignored.

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
- flashcards:
  - cards only use words from the slides
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
  ocr.py          Apple Vision text recognition (local)
  generators/     turns slide text into study material (swappable)
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
