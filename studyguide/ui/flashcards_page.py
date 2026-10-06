"""Flashcards screen: home (stats, topics, badges), a card round, and a round summary."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import flashcards, library, progress
from ..knowledge.core2 import SOURCE_LABEL
from ..rounds import Feedback, Round, Summary
from . import theme
from .widgets import button, card, chip, clear_layout, label


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


class FlashcardsPage(QWidget):
    progress_changed = Signal()
    open_library = Signal()

    def __init__(self, conn, get_library_id: Callable[[], Optional[int]]):
        super().__init__()
        self.conn = conn
        self.get_library_id = get_library_id
        self.round: Optional[Round] = None
        self.round_topic_name: Optional[str] = None
        self.colors: Dict[str, str] = {}
        self.revealed = False
        self.feedback: Optional[Feedback] = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.stack.addWidget(self._build_home())
        self.stack.addWidget(self._build_card_view())
        self.stack.addWidget(self._build_summary())

        for key, handler in (
            (Qt.Key_Space, self._space),
            (Qt.Key_Return, self._continue_key),
            (Qt.Key_Enter, self._continue_key),
            (Qt.Key_1, lambda: self._grade_key("again")),
            (Qt.Key_2, lambda: self._grade_key("good")),
            (Qt.Key_3, lambda: self._grade_key("easy")),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

    # ================================================================ home
    def _build_home(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.home_layout = QVBoxLayout(inner)
        self.home_layout.setContentsMargins(0, 0, 6, 0)
        self.home_layout.setSpacing(16)
        scroll.setWidget(inner)
        return scroll

    def refresh_home(self) -> None:
        """Rebuild the home view. Also creates cards for any new or edited transcripts."""
        clear_layout(self.home_layout)
        lib = self.get_library_id()
        if lib is None:
            return
        flashcards.sync_cards(self.conn, lib)
        topics = library.list_topics(self.conn, lib)
        self.colors = {t["name"]: theme.topic_color(i) for i, t in enumerate(topics)}
        overview = flashcards.topic_overview(self.conn, lib)

        # ---- stats row
        xp = progress.total_xp(self.conn)
        lvl = progress.level_for(xp)
        streak, best = progress.streaks(self.conn)
        badges = progress.earned_badges(self.conn)
        stats = QHBoxLayout()
        stats.setSpacing(14)
        if streak:
            today = progress.studied_today(self.conn)
            streak_sub = "Keep it going!" if today else "Study today to keep it! 🔥"
            stats.addWidget(self._stat_tile("🔥", f"{streak}-day streak", streak_sub, theme.CORAL))
        else:
            stats.addWidget(self._stat_tile("🔥", "Start a streak", "Study today to begin one", theme.CORAL))
        level_tile, level_layout = self._stat_tile_layout("⭐", f"Level {lvl.level}", f"{xp} XP total", theme.SUNNY_DARK)
        bar = QProgressBar()
        bar.setObjectName("XpBar")
        bar.setMaximum(lvl.needed)
        bar.setValue(lvl.into_level)
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        level_layout.addWidget(bar)
        level_layout.addWidget(label(f"{lvl.needed - lvl.into_level} XP to level {lvl.level + 1}", "Muted"))
        stats.addWidget(level_tile)
        stats.addWidget(self._stat_tile("🏅", f"{len(badges)} of {len(progress.BADGES)} badges",
                                        f"Best streak: {plural(best, 'day')}", theme.PURPLE))
        self.home_layout.addLayout(stats)

        # ---- old fragment-based cards: paused, with an offer to regenerate
        old = flashcards.old_cards_status(self.conn, lib)
        if old.total:
            banner, bl = card(name="UpgradeBanner")
            row = QHBoxLayout()
            words = QVBoxLayout()
            words.addWidget(label("🛠️ Some older cards need an upgrade", "HeroTitle"))
            example = ""
            if old.examples:
                e = old.examples[0]
                example = f" Example: “{e['front'].rpartition(chr(10) * 2)[2]}” → “{e['back']}”."
            words.addWidget(label(
                f"{old.paused} of {old.total} older cards are paused because they copy slide fragments "
                f"instead of testing a concept, and have no explanation.{example} "
                "You can preview better questions made from the same slides.", "HeroText", wrap=True))
            row.addLayout(words, 1)
            go = button("👀  Preview & regenerate", "Purple")
            go.clicked.connect(self.open_upgrade)
            row.addWidget(go, 0, Qt.AlignVCenter)
            bl.addLayout(row)
            self.home_layout.addWidget(banner)

        # ---- today's round
        total_due = sum(r["due"] or 0 for r in overview)
        total_new = sum(r["new"] or 0 for r in overview)
        total_cards = sum(r["total"] or 0 for r in overview)
        hero, hero_layout = card(name="Hero")
        row = QHBoxLayout()
        text = QVBoxLayout()
        if total_cards == 0:
            text.addWidget(label("No flashcards yet 🌱", "HeroTitle"))
            text.addWidget(label("Cards are made from your slide transcripts. Read the text from "
                                 "some slides in the Library and they'll show up here.", "HeroText", wrap=True))
            go = button("📚  Go to Library", "Big")
            go.clicked.connect(self.open_library.emit)
        elif total_due or total_new:
            parts = []
            if total_due:
                parts.append(f"{plural(total_due, 'card')} to review")
            if total_new:
                parts.append(f"{total_new} new")
            text.addWidget(label("Ready for a quick round? 🃏", "HeroTitle"))
            text.addWidget(label(" · ".join(parts) + " across all topics. A round takes about 3 minutes.",
                                 "HeroText", wrap=True))
            go = button("▶  Start a round", "Big")
            go.clicked.connect(lambda: self.start_round(None))
        else:
            nxt = flashcards.next_due_at(self.conn, lib)
            when = nxt.astimezone().strftime("%a %-d %b, %H:%M") if nxt else "later"
            text.addWidget(label("All caught up! 🌈", "HeroTitle"))
            text.addWidget(label(f"You've reviewed everything that's due. Next cards are ready {when}.",
                                 "HeroText", wrap=True))
            go = button("🔁  Practice anyway", "Big")
            go.clicked.connect(lambda: self.start_round(None, practice=True))
        row.addLayout(text, 1)
        row.addWidget(go, 0, Qt.AlignVCenter)
        hero_layout.addLayout(row)
        self.home_layout.addWidget(hero)

        # ---- topics
        self.home_layout.addWidget(label("Your topics", "SectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(14)
        for index, r in enumerate(overview):
            grid.addWidget(self._topic_tile(r), index // 3, index % 3)
        if not overview:
            grid.addWidget(label("Topics appear here once their slides have text.", "Muted"), 0, 0)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        self.home_layout.addLayout(grid)

        # ---- badges
        self.home_layout.addWidget(label("Badges", "SectionTitle"))
        shelf = QGridLayout()
        shelf.setSpacing(12)
        for index, (badge_id, (emoji, name, how)) in enumerate(progress.BADGES.items()):
            shelf.addWidget(self._badge_tile(emoji, name, how, badge_id in badges), index // 4, index % 4)
        for col in range(4):
            shelf.setColumnStretch(col, 1)
        self.home_layout.addLayout(shelf)
        self.home_layout.addStretch(1)

    def open_upgrade(self) -> None:
        from .upgrade_dialog import UpgradeDialog

        lib = self.get_library_id()
        if lib is None:
            return
        dialog = UpgradeDialog(self.conn, lib, self)
        if dialog.exec():
            self.refresh_home()
            self.progress_changed.emit()

    def _stat_tile_layout(self, emoji: str, title: str, sub: str, color: str):
        frame, layout = card(name="Stat")
        top = QHBoxLayout()
        icon = label(emoji, "StatEmoji")
        top.addWidget(icon)
        words = QVBoxLayout()
        words.setSpacing(0)
        t = label(title, "StatTitle")
        t.setStyleSheet(f"color: {color};")
        words.addWidget(t)
        if sub:
            words.addWidget(label(sub, "Muted"))
        top.addLayout(words, 1)
        layout.addLayout(top)
        return frame, layout

    def _stat_tile(self, emoji: str, title: str, sub: str, color: str) -> QFrame:
        frame, layout = self._stat_tile_layout(emoji, title, sub, color)
        layout.addStretch(1)
        return frame

    def _topic_tile(self, r) -> QFrame:
        color = self.colors.get(r["name"], theme.PURPLE)
        frame, layout = card(name="TopicTile")
        frame.setStyleSheet(f"QFrame#TopicTile {{ border-color: {color}; }}")
        top = QHBoxLayout()
        top.addWidget(chip(r["name"], color))
        top.addStretch(1)
        layout.addLayout(top)
        total = r["total"] or 0
        learned = r["learned"] or 0
        bar = QProgressBar()
        bar.setObjectName("TopicBar")
        bar.setStyleSheet(f"QProgressBar#TopicBar::chunk {{ background: {color}; }}")
        bar.setMaximum(max(total, 1))
        bar.setValue(learned)
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        layout.addWidget(bar)
        layout.addWidget(label(
            f"<b>{r['due'] or 0}</b> to review · <b>{r['new'] or 0}</b> new · <b>{learned}</b>/{total} learned",
            "TopicStats"))
        practice = button("Practice", "Plain")
        practice.setStyleSheet(
            f"QPushButton#Plain {{ color: {color}; border-color: {color}; }}"
        )
        practice.clicked.connect(lambda _=False, tid=r["topic_id"], name=r["name"]: self.start_round(tid, name))
        layout.addWidget(practice, 0, Qt.AlignLeft)
        return frame

    def _badge_tile(self, emoji: str, name: str, how: str, earned: bool) -> QFrame:
        frame, layout = card(name="Badge" if earned else "BadgeLocked")
        layout.setSpacing(2)
        layout.addWidget(label(emoji if earned else "🔒", "BadgeEmoji", align=Qt.AlignCenter))
        layout.addWidget(label(name, "BadgeName", align=Qt.AlignCenter))
        layout.addWidget(label(how, "BadgeHow", wrap=True, align=Qt.AlignCenter))
        frame.setToolTip(("Earned! " if earned else "Not yet: ") + how)
        return frame

    # ============================================================ card view
    def _build_card_view(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        top = QHBoxLayout()
        self.quit_button = button("✕  End round", "Plain")
        self.quit_button.clicked.connect(self.end_round)
        self.round_bar = QProgressBar()
        self.round_bar.setTextVisible(False)
        self.round_bar.setFixedHeight(18)
        self.round_count = label("", "ProgressText")
        self.round_xp = label("", "XpPill")
        top.addWidget(self.quit_button)
        top.addSpacing(8)
        top.addWidget(self.round_bar, 1)
        top.addWidget(self.round_count)
        top.addWidget(self.round_xp)
        outer.addLayout(top)

        self.flash_frame, fl = card(name="FlashCard")
        fl.setContentsMargins(34, 26, 34, 26)
        fl.setSpacing(12)
        head = QHBoxLayout()
        self.card_topic = chip("", theme.PURPLE)
        self.card_source = label("", "Muted")
        self.card_new = label("", "NewPill")
        head.addWidget(self.card_topic)
        head.addWidget(self.card_source, 1)
        head.addWidget(self.card_new)
        fl.addLayout(head)
        # everything below the header scrolls, so long explanations always fit
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 8, 0)
        bl.setSpacing(12)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setWidget(body)
        fl.addWidget(scroller, 1)

        self.card_heading = label("", "CardHeading", wrap=True)
        bl.addWidget(self.card_heading)
        self.card_front = label("", "Front", wrap=True)
        self.card_front.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(self.card_front)
        self.card_options = label("", "Options", wrap=True)
        self.card_options.setTextFormat(Qt.RichText)
        bl.addWidget(self.card_options)

        self.answer_box = QWidget()
        al = QVBoxLayout(self.answer_box)
        al.setContentsMargins(0, 6, 0, 0)
        al.setSpacing(8)
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(2)
        al.addWidget(divider)
        al.addWidget(label("ANSWER", "Eyebrow"))
        self.card_answer = label("", "Answer", wrap=True)
        self.card_answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        al.addWidget(self.card_answer)

        src_row = QHBoxLayout()
        src_row.setSpacing(16)
        src_text = QVBoxLayout()
        src_text.setSpacing(6)
        self.why_title = label("WHY THIS IS RIGHT", "Eyebrow")
        self.card_explanation = label("", "Explanation", wrap=True)
        self.card_explanation.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.wrong_title = label("WHY NOT THE OTHERS", "Eyebrow")
        self.card_why_wrong = label("", "WhyWrong", wrap=True)
        self.card_why_wrong.setTextFormat(Qt.RichText)
        self.added_box = label("", "AddedContext", wrap=True)
        self.added_box.setTextFormat(Qt.RichText)
        self.source_title = label("FROM YOUR SLIDE", "Eyebrow")
        self.card_context = label("", "Context", wrap=True)
        for w in (self.why_title, self.card_explanation, self.wrong_title, self.card_why_wrong,
                  self.added_box, self.source_title, self.card_context):
            src_text.addWidget(w)
        self.hide_button = button("🙈  Hide this card", "Link")
        self.hide_button.setToolTip("Not a useful card? Hide it. Nothing is deleted.")
        self.hide_button.clicked.connect(self.hide_current)
        src_text.addWidget(self.hide_button, 0, Qt.AlignLeft)
        src_text.addStretch(1)
        src_row.addLayout(src_text, 1)
        self.card_thumb = QLabel()
        self.card_thumb.setObjectName("Thumb")
        self.card_thumb.setAlignment(Qt.AlignCenter)
        src_row.addWidget(self.card_thumb, 0, Qt.AlignTop)
        al.addLayout(src_row)
        bl.addWidget(self.answer_box)
        bl.addStretch(1)
        outer.addWidget(self.flash_frame, 1)

        # bottom area: reveal button / grade buttons / feedback bar
        self.bottom = QStackedWidget()
        self.bottom.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        reveal_row = QWidget()
        rl = QHBoxLayout(reveal_row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addStretch(1)
        self.reveal_button = button("👀  Show answer   (space)", "Big")
        self.reveal_button.clicked.connect(self.reveal)
        rl.addWidget(self.reveal_button)
        rl.addStretch(1)
        self.bottom.addWidget(reveal_row)

        grade_row = QWidget()
        gl = QHBoxLayout(grade_row)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(label("How did you do?", "GradePrompt"))
        gl.addStretch(1)
        self.grade_buttons = {}
        for grade, text, style in (
            ("again", "😅  Still learning  (1)", "Coral"),
            ("good", "🙂  Got it  (2)", "Primary"),
            ("easy", "😎  Easy  (3)", "Sky"),
        ):
            b = button(text, style)
            b.clicked.connect(lambda _=False, g=grade: self.grade(g))
            self.grade_buttons[grade] = b
            gl.addWidget(b)
        self.bottom.addWidget(grade_row)

        self.feedback_bar = QFrame()
        self.feedback_bar.setObjectName("FeedbackGood")
        fb = QHBoxLayout(self.feedback_bar)
        fb.setContentsMargins(20, 12, 14, 12)
        words = QVBoxLayout()
        words.setSpacing(0)
        self.feedback_title = label("", "FeedbackTitle")
        self.feedback_sub = label("", "FeedbackSub")
        words.addWidget(self.feedback_title)
        words.addWidget(self.feedback_sub)
        fb.addLayout(words, 1)
        self.continue_button = button("Continue  ⏎", "Primary")
        self.continue_button.clicked.connect(self.next_card)
        fb.addWidget(self.continue_button)
        self.bottom.addWidget(self.feedback_bar)
        outer.addWidget(self.bottom)
        # keyboard control goes through the shortcuts only, so a key never counts twice
        for b in [self.reveal_button, self.continue_button, *self.grade_buttons.values()]:
            b.setFocusPolicy(Qt.NoFocus)
        return page

    def start_round(self, topic_id: Optional[int], topic_name: Optional[str] = None,
                    practice: bool = False) -> None:
        lib = self.get_library_id()
        if lib is None:
            return
        flashcards.sync_cards(self.conn, lib, topic_id)
        ids = flashcards.build_round(self.conn, lib, topic_id)
        if not ids and (practice or topic_id):
            ids = self._practice_ids(lib, topic_id)
        if not ids:
            self.refresh_home()
            return
        self.round = Round(self.conn, ids, topic_id)
        self.round_topic_name = topic_name
        self.stack.setCurrentIndex(1)
        self._show_card()

    def _practice_ids(self, lib: int, topic_id: Optional[int]):
        """Extra practice when nothing is due: the cards reviewed longest ago."""
        sql = ("SELECT c.id " + flashcards.ACTIVE + ("AND i.topic_id = ? " if topic_id else "")
               + "GROUP BY i.id, c.context ORDER BY s.last_reviewed LIMIT 10")
        args = [lib, topic_id] if topic_id else [lib]
        return [r["id"] for r in self.conn.execute(sql, args)]

    def _show_card(self) -> None:
        r = self.round
        if r.current is None:
            self.finish_round()
            return
        c = flashcards.get_card(self.conn, r.current)
        self.revealed = False
        self.feedback = None
        color = self.colors.get(c["topic_name"], theme.PURPLE)
        self.card_topic.setText(c["topic_name"])
        self.card_topic.setStyleSheet(f"background: {color};")
        self.flash_frame.setStyleSheet(f"QFrame#FlashCard {{ border-top: 8px solid {color}; }}")
        self.card_source.setText("  " + c["rel_path"].split("/", 1)[1])
        retry = r.position >= r.unique
        self.card_new.setText("🔁 Second try" if retry else ("✨ New" if c["reps"] is None else ""))
        self.card_new.setVisible(bool(self.card_new.text()))
        heading, _, prompt = c["front"].rpartition("\n\n")
        self.card_heading.setText(heading)
        self.card_heading.setVisible(bool(heading))
        self.card_front.setText(prompt)
        self._fill_answer(c)
        pix = QPixmap(str(Path(c["root_path"]) / c["rel_path"]))
        self.card_thumb.setPixmap(pix.scaledToWidth(300, Qt.SmoothTransformation) if not pix.isNull() else QPixmap())
        self.card_thumb.setToolTip(c["rel_path"])
        self.answer_box.hide()
        self.bottom.setCurrentIndex(0)
        self._update_round_header()
        self.setFocus()

    def _fill_answer(self, c) -> None:
        """Answer, explanation, why the alternatives are wrong, and where it came from."""
        d = flashcards.card_details(c)
        options = d.get("options") or []
        letters = "ABCDEFG"
        self.card_options.setText("<br>".join(
            f"<b>{letters[i]}.</b>&nbsp; {html.escape(o)}" for i, o in enumerate(options)))
        self.card_options.setVisible(bool(options))
        answer = c["back"]
        if options and answer in options:
            answer = f"{letters[options.index(answer)]}. {answer}"
        self.card_answer.setText(answer)

        self.card_explanation.setText(c["explanation"] or "")
        for w in (self.why_title, self.card_explanation):
            w.setVisible(bool(c["explanation"]))
        wrong = d.get("why_wrong") or {}
        self.card_why_wrong.setText("<br>".join(
            f"<b>{html.escape(o)}:</b> {html.escape(why)}" for o, why in wrong.items()))
        for w in (self.wrong_title, self.card_why_wrong):
            w.setVisible(bool(wrong))

        context_only = d.get("source") == "context"
        added = d.get("added_context") or ""
        prefix = SOURCE_LABEL + ": "
        if context_only:
            note = ("This question and its explanation come from general CompTIA A+ Core 2 knowledge. "
                    "Your slide mentions the topic but doesn't explain it in this detail.")
        elif added.startswith(prefix):
            note = html.escape(added[len(prefix):])
        else:
            note = ""
        self.added_box.setText(f"<b>🎓 Added CompTIA A+ Core 2 context (not from your slide)</b><br>{note}")
        self.added_box.setVisible(bool(note))
        self.source_title.setText("YOUR SLIDE MENTIONS IT HERE" if context_only else "FROM YOUR SLIDE")
        self.card_context.setText(f"“{c['context']}”" if c["context"] else "")
        self.source_title.setVisible(bool(c["context"]))

    def _update_round_header(self) -> None:
        r = self.round
        self.round_bar.setMaximum(max(r.length, 1))
        self.round_bar.setValue(r.done_count)
        self.round_count.setText(f"{min(r.done_count + 1, r.length)} / {r.length}")
        self.round_xp.setText(f"⭐ {r.xp} XP")

    def reveal(self) -> None:
        if self.round is None or self.revealed:
            return
        self.revealed = True
        self.answer_box.show()
        self.bottom.setCurrentIndex(1)

    def grade(self, grade: str) -> None:
        if self.round is None or not self.revealed or self.feedback is not None:
            return
        fb = self.round.answer(grade)
        self.feedback = fb
        self.feedback_bar.setObjectName("FeedbackGood" if fb.correct else "FeedbackTry")
        self.feedback_bar.style().unpolish(self.feedback_bar)
        self.feedback_bar.style().polish(self.feedback_bar)
        self.feedback_title.setStyleSheet(f"color: {theme.GREEN_DARK if fb.correct else theme.PURPLE_DARK};")
        self.feedback_title.setText(fb.message)
        if fb.correct:
            sub = f"+{fb.xp} XP · You'll see this again {fb.next_review}."
        else:
            sub = f"+{fb.xp} XP for trying · It comes back at the end of this round."
        self.feedback_sub.setText(sub)
        self.bottom.setCurrentIndex(2)
        self._update_round_header()
        self.round_count.setText(f"{self.round.done_count} / {self.round.length}")
        self.progress_changed.emit()

    def next_card(self) -> None:
        if self.round is not None:
            self._show_card()

    def hide_current(self) -> None:
        if self.round is None or self.round.current is None:
            return
        flashcards.hide_card(self.conn, self.round.current)
        self.round.skip()
        self._show_card()

    def end_round(self) -> None:
        if self.round is None:
            return
        if self.round.first_try:
            self.finish_round()
        else:
            self.round = None
            self.show_home()

    # ============================================================== summary
    def _build_summary(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.summary_layout = QVBoxLayout(inner)
        self.summary_layout.setContentsMargins(0, 0, 6, 0)
        self.summary_layout.setSpacing(16)
        scroll.setWidget(inner)
        return scroll

    def finish_round(self) -> None:
        summary = self.round.finish()
        self.round = None
        self.progress_changed.emit()
        self._render_summary(summary)
        self.stack.setCurrentIndex(2)

    def _render_summary(self, s: Summary) -> None:
        clear_layout(self.summary_layout)
        frame, layout = card(name="Hero")
        layout.setSpacing(6)
        if s.perfect:
            emoji, title = "💯", "Perfect round!"
        elif s.total and s.correct / s.total >= 0.7:
            emoji, title = "🎉", "Round complete. Great work!"
        else:
            emoji, title = "🌱", "Round complete. Every round makes you stronger!"
        layout.addWidget(label(emoji, "WelcomeEmoji", align=Qt.AlignCenter))
        layout.addWidget(label(title, "WelcomeTitle", align=Qt.AlignCenter, wrap=True))
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        tiles.addWidget(self._stat_tile("⭐", f"+{s.xp} XP", "bonus +%d" % s.bonus if s.bonus else "", theme.SUNNY_DARK))
        tiles.addWidget(self._stat_tile("🎯", f"{s.correct} / {s.total}", "right first time", theme.GREEN))
        tiles.addWidget(self._stat_tile("🔥", plural(s.streak, "day"), "streak", theme.CORAL))
        layout.addSpacing(8)
        layout.addLayout(tiles)
        self.summary_layout.addWidget(frame)

        if s.new_badges:
            self.summary_layout.addWidget(label("🎊 New badge" + ("s" if len(s.new_badges) > 1 else "") + "!",
                                                "SectionTitle"))
            row = QHBoxLayout()
            row.setSpacing(12)
            for badge_id in s.new_badges:
                emoji, name, how = progress.BADGES[badge_id]
                row.addWidget(self._badge_tile(emoji, name, how, True))
            row.addStretch(1)
            self.summary_layout.addLayout(row)

        if s.missed:
            self.summary_layout.addWidget(label("💡 Learn from these", "SectionTitle"))
            self.summary_layout.addWidget(label(
                "You missed these the first time. Here's what the slides say.", "Muted"))
            for card_id in s.missed:
                c = flashcards.get_card(self.conn, card_id)
                f, fl = card(name="MissedCard")
                fl.setSpacing(4)
                head = QHBoxLayout()
                head.addWidget(chip(c["topic_name"], self.colors.get(c["topic_name"], theme.PURPLE)))
                head.addWidget(label("  " + c["rel_path"].split("/", 1)[1], "Muted"), 1)
                fl.addLayout(head)
                fl.addWidget(label(c["front"].split("\n\n", 1)[-1], "MissedFront", wrap=True))
                fl.addWidget(label(f"✅  {c['back']}", "MissedAnswer", wrap=True))
                if c["explanation"]:
                    fl.addWidget(label(c["explanation"], "Explanation", wrap=True))
                d = flashcards.card_details(c)
                where = "Your slide mentions it" if d.get("source") == "context" else "From your slide"
                if d.get("source") == "context":
                    fl.addWidget(label("🎓 Added CompTIA A+ Core 2 context (not from your slide)", "ContextTag"))
                if c["context"]:
                    fl.addWidget(label(f"{where}: “{c['context']}”", "Context", wrap=True))
                self.summary_layout.addWidget(f)

        buttons = QHBoxLayout()
        again = button("▶  Another round", "Big")
        again.clicked.connect(lambda: self.start_round(None, practice=True))
        home = button("🏠  Back to topics", "Plain")
        home.clicked.connect(self.show_home)
        buttons.addStretch(1)
        buttons.addWidget(home)
        buttons.addWidget(again)
        buttons.addStretch(1)
        self.summary_layout.addLayout(buttons)
        self.summary_layout.addStretch(1)

    # ============================================================== helpers
    def show_home(self) -> None:
        self.refresh_home()
        self.stack.setCurrentIndex(0)

    def in_round(self) -> bool:
        return self.round is not None

    def _space(self) -> None:
        if self.stack.currentIndex() == 1:
            if not self.revealed:
                self.reveal()
            elif self.feedback is not None:
                self.next_card()

    def _continue_key(self) -> None:
        if self.stack.currentIndex() == 1 and self.feedback is not None:
            self.next_card()

    def _grade_key(self, grade: str) -> None:
        if self.stack.currentIndex() == 1 and self.revealed:
            self.grade(grade)
