"""One short flashcard round: cards, answers, points and a summary at the end.

Cards you miss come back once at the end of the round, so you get a second
chance straight away.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from . import flashcards, progress

CHEERS = ["Nice! 🎉", "You got it! ✨", "Great job! 🙌", "Nailed it! 💪", "Brilliant! 🌟", "Spot on! 🎯"]
EASY_CHEERS = ["Too easy! 😎", "Crushed it! 🚀", "Like a pro! 🏆"]
ENCOURAGE = [
    "No worries, this one will come back in a moment. 💜",
    "Mistakes help you learn. You'll see it again soon. 🌱",
    "Almost! Take another look at the answer. You've got this. 💪",
]


@dataclass
class Feedback:
    correct: bool
    xp: int
    message: str
    next_review: str
    retry_later: bool


@dataclass
class Summary:
    total: int
    correct: int
    xp: int
    bonus: int
    perfect: bool
    streak: int
    new_badges: List[str]
    missed: List[int] = field(default_factory=list)  # card ids missed on first try


class Round:
    def __init__(self, conn, card_ids: List[int], topic_id: Optional[int] = None,
                 now: Callable[[], datetime] = progress.local_now, rng: Optional[random.Random] = None):
        self.conn = conn
        self.topic_id = topic_id
        self.now = now
        self.rng = rng or random.Random()
        self.queue: List[int] = list(card_ids)
        self.unique = len(card_ids)
        self.position = 0
        self.first_try: dict = {}  # card id -> correct on first attempt?
        self.retried: set = set()
        self.xp = 0
        self.started = now()
        self.finished = False

    @property
    def current(self) -> Optional[int]:
        return self.queue[self.position] if self.position < len(self.queue) else None

    @property
    def done_count(self) -> int:
        return self.position

    @property
    def length(self) -> int:
        return len(self.queue)

    def answer(self, grade: str) -> Feedback:
        card_id = self.current
        if card_id is None:
            raise RuntimeError("Round is already finished")
        card = flashcards.get_card(self.conn, card_id)
        state = flashcards.grade_card(self.conn, card_id, grade, self.now())
        correct = grade != "again"
        self.first_try.setdefault(card_id, correct)
        points = progress.XP_CORRECT if correct else progress.XP_TRY
        progress.add_xp(self.conn, points, f"flashcard:{grade}", card["topic_id"], self.now())
        self.xp += points
        retry = False
        if not correct and card_id not in self.retried:
            self.retried.add(card_id)
            self.queue.append(card_id)
            retry = True
        if correct:
            message = self.rng.choice(EASY_CHEERS if grade == "easy" else CHEERS)
            if card_id in self.retried:
                message = "You learned it! That's how it's done. 🌈"
        else:
            message = self.rng.choice(ENCOURAGE)
        self.position += 1
        return Feedback(correct, points, message, flashcards.describe_interval(state["interval_days"]), retry)

    def skip(self) -> None:
        """Drop the current card from this round without grading it (e.g. after hiding it)."""
        card_id = self.current
        if card_id is None:
            return
        # drop it from the rest of the queue (including any pending retry)
        self.queue = self.queue[: self.position] + [
            c for c in self.queue[self.position :] if c != card_id
        ]

    def finish(self) -> Summary:
        if self.finished:
            raise RuntimeError("Round already finished")
        self.finished = True
        correct = sum(1 for ok in self.first_try.values() if ok)
        total = len(self.first_try)
        perfect = total >= 5 and correct == total
        bonus = 0
        if total:
            bonus += progress.XP_ROUND_DONE
            if perfect:
                bonus += progress.XP_PERFECT_BONUS
            progress.add_xp(self.conn, bonus, "round-bonus", self.topic_id, self.now())
            progress.record_round(self.conn, "flashcards", self.topic_id, self.started, self.now(),
                                  total, correct, self.xp + bonus)
        new_badges = progress.check_badges(self.conn, self.now())
        streak, _ = progress.streaks(self.conn, self.now().date())
        missed = [cid for cid, ok in self.first_try.items() if not ok]
        return Summary(total, correct, self.xp + bonus, bonus, perfect, streak, new_badges, missed)
