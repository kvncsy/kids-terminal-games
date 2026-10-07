#!/usr/bin/env python3
"""
TIMES TABLES - big multiplication flash cards. Type the answer, press ENTER.

  1 WARM-UP      1-10 x 1-10
  2 BIG NUMBERS  11-20 x 1-10
  3 MEGA         11-20 x 11-20
  4 MIX          anything from 1-20 x 1-10
  5 LIGHTNING    60 seconds: how many can you get?
  6 MY CHART     every fact, colored by how well you know it

Facts you miss come back more often; facts you know well come back less.
H shows a hint that breaks a hard fact into easy pieces
(14 x 7 = 10 x 7 + 4 x 7 = 70 + 28). Progress is saved in ~/.times_tables.

  python3 times_tables.py           play
  python3 times_tables.py --reset   forget all progress
  python3 times_tables.py --mute    no sound
"""
import argparse
import json
import os
import random
import time

import kidslib
from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, best_scale,
                     big_width, box, color, curses, draw_big, draw_big_centered, footer, header, is_backspace,
                     is_enter, put, run)

SAVE_FILE = os.path.expanduser("~/.times_tables")
LIGHTNING_SECONDS = 60
MAX_LEVEL = 3              # 0 = still learning ... 3 = knows it really well
MODES = [
    ("WARM-UP", "1 to 10  times  1 to 10", (1, 10), (1, 10)),
    ("BIG NUMBERS", "11 to 20  times  1 to 10", (11, 20), (1, 10)),
    ("MEGA", "11 to 20  times  11 to 20", (11, 20), (11, 20)),
    ("MIX", "anything from 1 to 20  times  1 to 10", (1, 20), (1, 10)),
    ("LIGHTNING", "60 seconds! How many can you get?", (1, 20), (1, 10)),
    ("MY CHART", "see all the facts you know", None, None),
]
LEVEL_COLORS = {0: RED, 1: YELLOW, 2: GREEN, 3: CYAN}
STREAK_WORDS = {5: "FIVE IN A ROW!", 10: "TEN IN A ROW! ON FIRE!", 15: "FIFTEEN! UNSTOPPABLE!",
                20: "TWENTY IN A ROW! MATH CHAMPION!", 30: "THIRTY!!! LEGENDARY!"}


def fact_key(a, b):
    return "%dx%d" % (max(a, b), min(a, b))


def tip(a, b):
    """A friendly trick for a fact, if there is one."""
    big, small = max(a, b), min(a, b)
    if small == 1:
        return "Anything times 1 stays the same!"
    if small == 10 or big == 10:
        return "Times 10: just put a 0 on the end!"
    if small == 2:
        return "Times 2 is doubling: %d + %d" % (big, big)
    if big == 11 and small <= 9:
        return "11 times a small number: write the number twice!"
    if small == 5 and big <= 10:
        return "Times 5 is half of times 10."
    if 9 in (a, b) and big <= 10:
        return "Nines trick: the answer's digits add up to 9!"
    if big == 20:
        return "Times 20: do times 2, then put a 0 on the end!"
    return ""


def hint_lines(a, b):
    """Break a hard fact into easy pieces, without giving the answer away."""
    big, small = max(a, b), min(a, b)
    lines = []
    t = tip(a, b)
    if t:
        lines.append(t)
    if big >= 11 and big != 20 and not (big == 11 and small <= 9):
        ones = big - 10
        lines.append("Break %d into 10 + %d:" % (big, ones))
        lines.append("%d x %d  =  10 x %d  +  %d x %d" % (big, small, small, ones, small))
        lines.append("        =  %d  +  %d  =  ?" % (10 * small, ones * small))
    elif not t:
        counts = [str(small * i) for i in range(1, min(big, 5) + 1)]
        lines.append("Count by %ds: %s ..." % (small, ", ".join(counts)))
        lines.append("Keep counting until you have said %d numbers!" % big)
    return lines


def answer_lines(a, b):
    big, small = max(a, b), min(a, b)
    if big >= 11:
        ones = big - 10
        return ["10 x %d = %d   and   %d x %d = %d" % (small, 10 * small, ones, small, ones * small),
                "%d + %d = %d" % (10 * small, ones * small, big * small)]
    return ["%d groups of %d make %d" % (a, b, a * b)]


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.data = self.load()
        self.sparks = Sparkles()
        self.screen = "menu"
        self.mode = 0
        self.banner, self.banner_until = "", 0.0
        self.party = None             # (giant word, size: 1 a right answer, 2 a streak, 3 a whole table, ends at)
        self.fireworks = []           # (time, x, y) bursts still to come

    # ------------------------------------------------------------ saving
    def load(self):
        try:
            with open(SAVE_FILE) as f:
                d = json.load(f)
            d.setdefault("facts", {})
            d.setdefault("best", 0)
            d.setdefault("total", 0)
            return d
        except (OSError, ValueError):
            return {"facts": {}, "best": 0, "total": 0}

    def save(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.data, f)
        except OSError:
            pass

    def level(self, a, b):
        return self.data["facts"].get(fact_key(a, b), {}).get("level", -1)

    def record(self, a, b, result):
        """result: "right" (first try, no hint), "late" (after a hint or a second try) or "wrong"."""
        f = self.data["facts"].setdefault(fact_key(a, b), {"level": 0, "right": 0, "wrong": 0})
        if result == "right":
            f["right"] += 1
            f["level"] = min(MAX_LEVEL, f["level"] + 1)
            self.data["total"] += 1
        elif result == "wrong":
            f["wrong"] += 1
            f["level"] = 0
        else:
            f["level"] = max(0, f["level"] - 1)
        self.save()

    # ------------------------------------------------------------ cards
    def start(self, mode, now):
        self.mode = mode
        name = MODES[mode][0]
        if name == "MY CHART":
            self.screen = "chart"
            return
        self.screen = "card"
        self.streak = 0
        self.right_now = 0
        self.recent = []
        self.retry = []           # missed facts come back a few cards later
        self.lightning_end = now + LIGHTNING_SECONDS if name == "LIGHTNING" else None
        self.next_card(now)

    def next_card(self, now):
        _, _, ra, rb = MODES[self.mode]
        a = b = None
        for i, (due, fa, fb) in enumerate(self.retry):
            if due <= 0:
                a, b = fa, fb
                del self.retry[i]
                break
        self.retry = [(d - 1, fa, fb) for d, fa, fb in self.retry]
        if a is None:
            cards = [(x, y) for x in range(ra[0], ra[1] + 1) for y in range(rb[0], rb[1] + 1)
                     if fact_key(x, y) not in self.recent]
            weights = [(MAX_LEVEL + 1 - max(0, self.level(x, y))) ** 2 + (3 if self.level(x, y) < 0 else 0) + 1
                       for x, y in cards]
            a, b = random.choices(cards, weights)[0]
            if random.random() < 0.3:
                a, b = b, a
        self.recent = (self.recent + [fact_key(a, b)])[-4:]
        self.a, self.b = a, b
        self.typed = ""
        self.tries = 0
        self.hint = False
        self.state = "ask"          # ask, right, again, shown
        self.state_at = now
        self.shown_at = now

    def check(self, now):
        if not self.typed:
            return
        answer = self.a * self.b
        if int(self.typed) == answer:
            first = self.tries == 0 and not self.hint
            known_before = self.tables_known()
            self.record(self.a, self.b, "right" if first else "late")
            self.streak += 1
            self.right_now += 1
            self.state, self.state_at = "right", now
            new_tables = self.tables_known() - known_before
            if new_tables:
                self.celebrate(now, "YOU KNOW THE %dS!" % min(new_tables), 3)
            elif self.streak % 5 == 0:
                self.celebrate(now, "%d IN A ROW!" % self.streak, 2)
                self.say(STREAK_WORDS.get(self.streak, "KEEP GOING!"), now, 2.5)
            else:
                self.celebrate(now, random.choice(["YES!", "WOW!", "COOL!", "YAY!", "NICE!", "GREAT!"]), 1)
                if now - self.shown_at < 3 and first:
                    self.say("SPEEDY!", now, 1.0)
            return
        self.tries += 1
        self.streak = 0
        self.snd.no()
        if self.lightning_end:
            self.record(self.a, self.b, "wrong")
            self.state, self.state_at = "shown", now
        elif self.tries == 1:
            self.state, self.state_at = "again", now
            self.typed = ""
        else:
            self.record(self.a, self.b, "wrong")
            self.retry.append((3, self.a, self.b))
            self.state, self.state_at = "shown", now

    def say(self, text, now, secs):
        self.banner, self.banner_until = text, now + secs

    def question_text(self):
        return "%d*%d=" % (self.a, self.b)

    def tables_known(self):
        """Times tables (1-20) where every fact up to x10 is known well."""
        return {n for n in range(1, 21) if all(self.level(n, m) >= 2 for m in range(1, 11))}

    def celebrate(self, now, word, size):
        """Giant rainbow words, sparkles and fireworks. Bigger for streaks, biggest for a whole table."""
        h, w = self.scr.getmaxyx()
        length = {1: 1.1, 2: 2.6, 3: 3.6}[size]
        self.party = (word, size, now + length)
        for x in (w * 0.2, w * 0.5, w * 0.8):
            self.sparks.burst(x, h * 0.45, 25 + 15 * size, speed=26 + 6 * size, now=now)
        if size == 1:
            self.snd.yes(self.streak)
            self.snd.drum(0)
            return
        for i in range(6 if size == 2 else 12):          # fireworks popping all over the screen
            self.fireworks.append((now + 0.25 + i * (length - 0.6) / (6 if size == 2 else 12),
                                   random.uniform(w * 0.1, w * 0.9), random.uniform(h * 0.15, h * 0.7)))
        self.sparks.rain(w, 60 * size, now)
        self.snd.fanfare()
        if size == 3:
            self.snd.notes((0, 4, 7, 12, 16, 19, 24, 28), 0.12, 60)

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if self.screen != "menu" and isinstance(key, str) and key.lower() == "m":
            self.screen = "menu"              # M: back to the list of games (Esc leaves Times Tables)
            self.snd.slide(700, 350, 0.2)
            return True
        if self.screen == "menu":
            if isinstance(key, str) and key in "123456":
                self.snd.key_note(int(key))
                self.start(int(key) - 1, now)
            return True
        if self.screen in ("chart", "done"):
            if is_enter(key) or key == " ":
                self.screen = "menu"
            return True
        # a card is showing
        if self.state == "right" or self.state == "shown":
            if self.party and self.party[1] > 1 and now < self.party[2] - 0.5:
                return True                   # let the big party finish
            if now - self.state_at > 0.4 and (is_enter(key) or key == " " or (isinstance(key, str) and key.isdigit())):
                self.next_card(now)
                if isinstance(key, str) and key.isdigit():
                    self.handle_key(key, now)
            return True
        if isinstance(key, str) and key.isdigit():
            if len(self.typed) < 3:
                self.typed += key
                self.snd.key_note(int(key), 60)
            if self.state == "again":
                self.state = "ask"
        elif is_backspace(key):
            self.typed = self.typed[:-1]
        elif is_enter(key):
            self.check(now)
        elif isinstance(key, str) and key.lower() in "h?" and not self.lightning_end:
            if not self.hint:
                self.hint = True
                self.snd.notes((7, 4), 0.1)
        return True

    # ------------------------------------------------------------ update and draw
    def update(self, now, dt):
        while self.fireworks and self.fireworks[0][0] <= now:
            _, x, y = self.fireworks.pop(0)
            self.sparks.burst(x, y, 40, speed=30, now=now, chars="*+o.x#")
            self.snd.drum(random.choice((0, 4, 9)))
        if self.screen != "card":
            return
        party_over = self.party is None or now > self.party[2] - 0.3
        if self.state == "right" and now - self.state_at > (0.7 if self.lightning_end else 1.3) and party_over:
            self.next_card(now)
        if self.lightning_end and self.state == "shown" and now - self.state_at > 1.2:
            self.next_card(now)
        if self.lightning_end:
            left = self.lightning_end - now
            if left <= 0:
                self.finish_lightning(now)
            elif left < 10 and int(left) != getattr(self, "_tick", None):
                self._tick = int(left)
                self.snd.blip(880, 0.05, 0.12)

    def finish_lightning(self, now):
        self.screen = "done"
        self.new_record = self.right_now > self.data["best"]
        if self.new_record:
            self.data["best"] = self.right_now
            self.save()
            self.celebrate(now, "NEW RECORD!", 2)
        else:
            self.snd.yes()

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        if self.screen == "menu":
            self.draw_menu(now, h, w)
        elif self.screen == "chart":
            self.draw_chart(now, h, w)
        elif self.screen == "done":
            self.draw_done(now, h, w)
        else:
            self.draw_card(now, h, w)
        self.sparks.draw(self.scr, now, 1 / 30)
        if self.party and now < self.party[2]:
            self.draw_party(now, h, w)
        if now < self.banner_until:
            b = "  %s  " % self.banner
            put(self.scr, h // 2 - 7, (w - len(b)) // 2, b, color(RAINBOW[int(now * 6) % 7]) | curses.A_REVERSE)

    def draw_party(self, now, h, w):
        word, size, _ = self.party
        flash = lambda i: color(RAINBOW[(i + int(now * 8)) % 7])
        if size == 1:                                     # under the card, if there's room
            if self.screen != "card":
                return
            sx, sy = best_scale(self.question_text() + "999", w - 6, h - 12, 1)    # the card's size
            y = 3 + 5 * sy + 5
            gx, gy = best_scale(word, w - 4, h - y - 1, 0, ((3, 2), (2, 2), (2, 1), (1, 1)))
            if y + 5 * gy < h - 1:
                draw_big_centered(self.scr, word, y, w, gx, gy, colors=flash)
            return
        gx, gy = best_scale(word, w - 4, h - 4, 0, ((3, 3), (3, 2), (2, 2), (2, 1), (1, 1)))
        y = max(1, (h - 5 * gy) // 2)
        for r in range(y - 1, y + 5 * gy + 1):            # a dark stage so the giant word stands out
            put(self.scr, r, 0, " " * w)
        bar = "".join("*+o" [(i + int(now * 10)) % 3] for i in range(w))
        put(self.scr, y - 2, 0, bar, flash(0))
        put(self.scr, y + 5 * gy + 1, 0, bar, flash(3))
        draw_big_centered(self.scr, word, y, w, gx, gy, colors=flash)

    def knows(self):
        return sum(1 for f in self.data["facts"].values() if f["level"] >= 2)

    def draw_menu(self, now, h, w):
        header(self.scr, "TIMES TABLES", "  facts you know: %d   lightning record: %d " % (self.knows(), self.data["best"]),
               MAGENTA, w)
        sx, sy = best_scale("TIMES", w - 4, h - 16, 0, ((3, 2), (2, 1), (1, 1)))
        draw_big_centered(self.scr, "TIMES", 2, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 2)) % 7]))
        y = 3 + 5 * sy
        put(self.scr, y, (w - 28) // 2, "Press a number to pick a game:", color(WHITE))
        x = max(2, (w - 60) // 2)
        for i, (name, what, _, _) in enumerate(MODES):
            put(self.scr, y + 2 + i * 2, x, " %d " % (i + 1), color(YELLOW) | curses.A_REVERSE)
            put(self.scr, y + 2 + i * 2, x + 5, name.ljust(13), color(RAINBOW[i % 7]))
            put(self.scr, y + 2 + i * 2, x + 19, what, color(WHITE, False))
        footer(self.scr, "Esc: quit", w, h)

    def draw_card(self, now, h, w):
        name = MODES[self.mode][0]
        info = "  %s   streak: %d   right: %d " % (name, self.streak, self.right_now)
        if self.lightning_end:
            info += "  time left: %d " % max(0, int(self.lightning_end - now + 0.99))
        header(self.scr, "TIMES TABLES", info, MAGENTA, w)
        if self.lightning_end:
            frac = max(0.0, (self.lightning_end - now) / LIGHTNING_SECONDS)
            bar = int((w - 4) * frac)
            put(self.scr, 1, 2, "=" * bar, color(GREEN if frac > .3 else RED))

        question = self.question_text()
        answer = str(self.a * self.b)
        if self.state in ("right", "shown"):
            shown = answer
        else:
            shown = self.typed or ("?" if int(now * 2) % 2 else " ")
        sx, sy = best_scale(question + "999", w - 6, h - 12, 1)
        qw = big_width(question, sx)
        total = qw + sx * 6 + big_width("999", sx)
        x0 = max(1, (w - total) // 2)
        y0 = 3
        box(self.scr, y0 - 1, x0 - 3, 5 * sy + 3, total + 6, color(BLUE))
        draw_big(self.scr, question, y0 + 1, x0, sx, sy, colors=lambda i: color(YELLOW if i < len(question) - 1 else WHITE))
        acol = {"right": GREEN, "shown": ORANGE, "again": RED}.get(self.state, CYAN)
        draw_big(self.scr, shown, y0 + 1, x0 + qw + sx * 6, sx, sy, color(acol))

        y = y0 + 5 * sy + 3
        if self.state == "right":
            msg = random.Random(int(self.state_at)).choice(["YES!", "CORRECT!", "GREAT!", "YOU GOT IT!", "AWESOME!"])
            put(self.scr, y, (w - len(msg)) // 2, msg, color(GREEN) | curses.A_REVERSE)
        elif self.state == "again":
            msg = "Not quite! Try again.  (press H for a hint)"
            put(self.scr, y, (w - len(msg)) // 2, msg, color(RED))
        elif self.state == "shown":
            msg = "%d x %d = %d" % (self.a, self.b, self.a * self.b)
            put(self.scr, y, (w - len(msg)) // 2, msg, color(ORANGE) | curses.A_REVERSE)
            for i, line in enumerate(answer_lines(self.a, self.b)):
                put(self.scr, y + 2 + i, (w - len(line)) // 2, line, color(WHITE))
            if not self.lightning_end:
                more = "It will come back soon. Press ENTER for the next card."
                put(self.scr, y + 5, (w - len(more)) // 2, more, color(WHITE, False) | curses.A_DIM)
        if self.hint and self.state in ("ask", "again"):
            lines = hint_lines(self.a, self.b)
            for i, line in enumerate(lines):
                put(self.scr, y + 2 + i, (w - len(line)) // 2, line, color(CYAN))
            if max(self.a, self.b) <= 12 and y + 3 + len(lines) + min(self.a, self.b) < h - 1:
                self.draw_blocks(y + 3 + len(lines), w)
        lvl = self.level(self.a, self.b)
        stars = "" if lvl < 1 else "known " + "*" * lvl
        put(self.scr, y0 - 1, x0 + total, stars, color(YELLOW, False))
        footer(self.scr, "type the answer and press ENTER    H: hint    M: pick another game    Esc: quit", w, h)

    def draw_blocks(self, y, w):
        rows, cols = min(self.a, self.b), max(self.a, self.b)
        x = (w - cols * 2) // 2
        for r in range(rows):
            put(self.scr, y + r, x, "[]" * cols, color(RAINBOW[r % 7]))

    def draw_chart(self, now, h, w):
        header(self.scr, "TIMES TABLES", "  MY CHART   facts you know: %d " % self.knows(), MAGENTA, w)
        cw = 3 if w >= 70 else 2
        n = 20 if h >= 26 else 12
        x0 = max(5, (w - (n * cw + 6)) // 2)
        y0 = 2
        for c in range(1, n + 1):
            put(self.scr, y0, x0 + 4 + (c - 1) * cw, str(c).rjust(cw - 1), color(WHITE, False))
        cell = kidslib.BLOCK * (cw - 1)
        for r in range(1, n + 1):
            put(self.scr, y0 + r, x0, str(r).rjust(3), color(WHITE, False))
            mastered = True
            for c in range(1, n + 1):
                lvl = self.level(r, c)
                if c <= 10 and lvl < 2:
                    mastered = False
                if lvl < 0:
                    put(self.scr, y0 + r, x0 + 4 + (c - 1) * cw, ".".rjust(cw - 1), color(WHITE, False) | curses.A_DIM)
                else:
                    put(self.scr, y0 + r, x0 + 4 + (c - 1) * cw, cell, color(LEVEL_COLORS[lvl]))
            if mastered:
                put(self.scr, y0 + r, x0 + 4 + n * cw, "* the %ds!" % r, color(YELLOW))
        ly = y0 + n + 2
        legend = [("not tried", WHITE), ("still learning", RED), ("getting it", YELLOW), ("know it", GREEN), ("know it really well", CYAN)]
        x = max(1, (w - 72) // 2)
        for text, col in legend:
            put(self.scr, ly, x, kidslib.BLOCK * 2, color(col, col != WHITE))
            put(self.scr, ly, x + 3, text, color(WHITE, False))
            x += len(text) + 6
        footer(self.scr, "A star means you know that whole times table up to 10!    ENTER or M: back    Esc: quit", w, h)

    def draw_done(self, now, h, w):
        header(self.scr, "TIMES TABLES", "  LIGHTNING ROUND ", MAGENTA, w)
        text = str(self.right_now)
        sx, sy = best_scale(text, w - 4, h - 12)
        put(self.scr, 3, (w - 11) // 2, "TIME'S UP!", color(YELLOW))
        draw_big_centered(self.scr, text, 5, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 4)) % 7]))
        y = 6 + 5 * sy
        msg = "You got %d right in %d seconds!" % (self.right_now, LIGHTNING_SECONDS)
        put(self.scr, y, (w - len(msg)) // 2, msg, color(WHITE))
        if self.new_record:
            rec = "NEW RECORD!"
            put(self.scr, y + 2, (w - len(rec)) // 2, rec, color(RAINBOW[int(now * 6) % 7]) | curses.A_REVERSE)
        else:
            rec = "Your record is %d. Can you beat it?" % self.data["best"]
            put(self.scr, y + 2, (w - len(rec)) // 2, rec, color(CYAN))
        footer(self.scr, "ENTER: back to the games    Esc: quit", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Big multiplication flash cards. Esc quits.")
    p.add_argument("--reset", action="store_true", help="forget all progress")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("Times Tables progress is cleared. Every fact starts fresh!")
        raise SystemExit
    run(Game, args.mute, "Great math today!")
