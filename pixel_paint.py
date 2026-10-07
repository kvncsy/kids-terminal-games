#!/usr/bin/env python3
"""
PIXEL PAINTER - paint pictures one square at a time.

  arrows      move the brush
  SPACE       paint one square
  ENTER       pen down / pen up (when the pen is down, moving paints)
  1 to 8      pick a color      9  rainbow      0  eraser

Letters are tools:
  F fill   M mirror   U undo   S save   O open   C clear (press twice)
...and there are 4 secret tools hidden on other letters. Can you find them?

Pictures are saved as text files in the "My Pictures" folder in your home
folder, so you can open them again later.

  python3 pixel_paint.py          paint
  python3 pixel_paint.py --reset  hide the secret tools again (pictures are kept)
  python3 pixel_paint.py --mute   no sound
"""
import argparse
import glob
import json
import os
import random
import time

import kidslib
from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, color,
                     curses, footer, header, is_backspace, is_enter, put, run)

PICTURES = os.path.expanduser("~/My Pictures")
SAVE_FILE = os.path.expanduser("~/.pixel_paint")
PALETTE = [None, RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE]      # 1-8
NAMES = [None, "red", "orange", "yellow", "green", "light blue", "blue", "purple", "white"]
SECRETS = {"k": "KALEIDOSCOPE", "b": "BIG BRUSH", "x": "SPRAY CAN", "p": "PAINT SPLAT"}
SECRET_HELP = {"k": "Everything you paint is copied four ways!", "b": "The brush is 3 squares wide!",
               "x": "Press SPACE to spray paint dots!", "p": "Press SPACE for a big paint splat!"}
MAX_UNDO = 60
TOOL_NAMES = {"x": "spray", "p": "splat", "b": "big dab", "k": "4 ways"}   # the SPACE label for each secret tool
CELL = 10                       # width of one button on the toolbar
BIG_ICONS = {                   # a big picture for each secret tool once it's found: 5 lines of 10
    "k": [" \\  |  / ", "  \\ | /  ", " ---*---  ", "  / | \\  ", " /  |  \\ "],
    "b": ["    ||    ", "    ||    ", "   /##\\   ", "  /####\\  ", "  ######  "],
    "x": ["   . :.   ", "  _[] .:  ", " |   |.   ", " |   |    ", " |___|    "],
    "p": [" .  __  . ", "  _/  \\_  ", " (      ) ", "  \\_  _/. ", " .  \\/    "],
}
BIG_COLORS = {"k": MAGENTA, "b": ORANGE, "x": CYAN, "p": GREEN}


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        h, w = scr.getmaxyx()
        self.cols = max(8, min(64, (w - 4) // 2))
        self.rows = max(6, min(32, h - 6))
        self.grid = [[0] * self.cols for _ in range(self.rows)]
        self.cx, self.cy = self.cols // 2, self.rows // 2
        self.brush = 1
        self.rainbow = False
        self.rainbow_i = 0
        self.pen = False
        self.mirror = False
        self.tool = None               # a secret tool, when one is picked
        self.undo = []
        self.clear_armed = 0.0
        self.open_index = -1
        self.note, self.note_until, self.note_color = "", 0.0, WHITE
        self.lit, self.lit_until = "", 0.0          # the toolbar button that just got pressed
        self.sparks = Sparkles()
        self.found = self.load_found()
        self.say("Arrows move, SPACE paints, ENTER puts the pen down. Letters are tools!", time.time(), 6, CYAN)

    # ------------------------------------------------------------ helpers
    def load_found(self):
        try:
            with open(SAVE_FILE) as f:
                return set(json.load(f).get("found", []))
        except (OSError, ValueError, AttributeError):
            return set()

    def save_found(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump({"found": sorted(self.found)}, f)
        except OSError:
            pass

    def say(self, text, now, secs=3.0, col=WHITE):
        self.note, self.note_until, self.note_color = text, now + secs, col

    def checkpoint(self):
        self.undo.append([row[:] for row in self.grid])
        self.undo = self.undo[-MAX_UNDO:]

    def current_color(self):
        if self.brush == 0:
            return 0
        if self.rainbow:
            self.rainbow_i = (self.rainbow_i + 1) % 7
            return self.rainbow_i + 1
        return self.brush

    def spots(self, x, y):
        """Where one dab of paint lands, with mirror, kaleidoscope and big brush."""
        base = [(x, y)]
        if self.tool == "b":
            base = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        out = set()
        for px, py in base:
            out.add((px, py))
            if self.mirror or self.tool == "k":
                out.add((self.cols - 1 - px, py))
            if self.tool == "k":
                out.add((px, self.rows - 1 - py))
                out.add((self.cols - 1 - px, self.rows - 1 - py))
        return [(px, py) for px, py in out if 0 <= px < self.cols and 0 <= py < self.rows]

    def dab(self, x, y, c=None):
        c = self.current_color() if c is None else c
        for px, py in self.spots(x, y):
            self.grid[py][px] = c

    def paint(self, now):
        self.checkpoint()
        if self.tool == "x":
            for _ in range(10):
                x, y = self.cx + random.randint(-3, 3), self.cy + random.randint(-2, 2)
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    self.dab(x, y)
            self.snd.noise(0.15, 0.2, 1.0)
        elif self.tool == "p":
            for _ in range(40):
                dx, dy = random.gauss(0, 2.2), random.gauss(0, 1.3)
                x, y = int(round(self.cx + dx)), int(round(self.cy + dy))
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    self.dab(x, y)
            self.snd.drum(0)
        else:
            self.dab(self.cx, self.cy)
            self.snd.key_note(max(0, self.brush - 1), 60)

    def fill(self, now):
        target = self.grid[self.cy][self.cx]
        c = self.current_color()
        if target == c:
            return
        self.checkpoint()
        todo, seen = [(self.cx, self.cy)], set()
        while todo:
            x, y = todo.pop()
            if (x, y) in seen or not (0 <= x < self.cols and 0 <= y < self.rows) or self.grid[y][x] != target:
                continue
            seen.add((x, y))
            self.grid[y][x] = self.current_color() if self.rainbow else c
            todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        self.snd.slide(200, 1200, 0.35, 0.25)
        self.say("Filled %d squares!" % len(seen), now, 2, GREEN)

    def save_picture(self, now):
        os.makedirs(PICTURES, exist_ok=True)
        n = 1
        while os.path.exists(os.path.join(PICTURES, "picture-%02d.txt" % n)):
            n += 1
        path = os.path.join(PICTURES, "picture-%02d.txt" % n)
        lines = ["# Pixel Painter picture",
                 "# 1 red, 2 orange, 3 yellow, 4 green, 5 light blue, 6 blue, 7 purple, 8 white, . empty"]
        lines += ["".join(str(c) if c else "." for c in row) for row in self.grid]
        try:
            with open(path, "w") as f:
                f.write("\n".join(lines) + "\n")
            self.say("Saved! It's picture %d in the My Pictures folder." % n, now, 4, GREEN)
            self.snd.notes((0, 4, 7, 12), 0.08)
            self.open_index = len(self.saved()) - 1
        except OSError as e:
            self.say("Couldn't save: %s" % e, now, 4, RED)

    def saved(self):
        return sorted(glob.glob(os.path.join(PICTURES, "picture-*.txt")))

    def open_next(self, now):
        files = self.saved()
        if not files:
            self.say("No saved pictures yet. Press S to save one!", now, 3, YELLOW)
            return
        self.open_index = (self.open_index + 1) % len(files)
        self.checkpoint()
        self.grid = [[0] * self.cols for _ in range(self.rows)]
        try:
            with open(files[self.open_index]) as f:
                rows = [l.rstrip("\n") for l in f if not l.startswith("#")]
        except OSError:
            rows = []
        for y, row in enumerate(rows[: self.rows]):
            for x, ch in enumerate(row[: self.cols]):
                self.grid[y][x] = int(ch) if ch.isdigit() and 0 < int(ch) <= 8 else 0
        name = os.path.basename(files[self.open_index])
        self.say("Opened %s (%d of %d). Press O again for the next one." % (name, self.open_index + 1, len(files)), now, 4, CYAN)
        self.snd.notes((7, 4), 0.08)

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        self.light(key, now)
        moves = {curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0)}
        if key in moves:
            dx, dy = moves[key]
            self.cx = max(0, min(self.cols - 1, self.cx + dx))
            self.cy = max(0, min(self.rows - 1, self.cy + dy))
            if self.pen:
                self.checkpoint()
                self.dab(self.cx, self.cy)
                self.snd.blip(300 + 40 * self.brush, 0.04, 0.12, "TRIANGLE")
            return True
        if key == " ":
            self.paint(now)
        elif is_enter(key):
            self.pen = not self.pen
            self.say("Pen DOWN: moving paints!" if self.pen else "Pen UP: moving doesn't paint.", now, 2, YELLOW)
            self.snd.blip(660 if self.pen else 330, 0.1, 0.2)
        elif is_backspace(key):
            self.do_undo(now)
        elif isinstance(key, str) and key.isdigit():
            n = int(key)
            self.rainbow = n == 9
            self.brush = 0 if n == 0 else (1 if n == 9 else n)
            label = "RAINBOW" if n == 9 else ("ERASER" if n == 0 else NAMES[n].upper())
            self.say("Brush: %s" % label, now, 1.5, PALETTE[n] if 1 <= n <= 8 else WHITE)
            self.snd.key_note(n)
        elif isinstance(key, str) and key.isalpha():
            self.letter(key.lower(), now)
        return True

    def light(self, key, now):
        """Flash the toolbar button for this key."""
        if key == " ":
            self.lit = "SPACE"
        elif is_enter(key):
            self.lit = "ENTER"
        elif is_backspace(key):
            self.lit = "U"
        elif isinstance(key, str) and key.upper() in "FMUSOC" and key.isalpha():
            self.lit = key.upper()
        else:
            return
        self.lit_until = now + 0.4

    def toolbar(self, now, y, w):
        """Big buttons for every key, so you can see what they do (and whether the pen is down)."""
        brush = RAINBOW[int(now * 6) % 7] if self.rainbow else (PALETTE[self.brush] if self.brush else WHITE)
        clearing = now - self.clear_armed < 2.0
        mirror = self.mirror or self.tool == "k"
        buttons = [     # key, picture, picture color, words, is it switched on
            ("ENTER", "=>", YELLOW, "PEN DOWN" if self.pen else "pen up", self.pen),
            ("SPACE", "[]", brush, TOOL_NAMES.get(self.tool, "paint"), bool(self.tool)),
            ("F", "\\_/", brush, "fill", False),
            ("M", "><", MAGENTA, "MIRROR" if mirror else "mirror", mirror),
            ("U", "<-", CYAN, "undo", False),
            ("S", "[v]", GREEN, "save", False),
            ("O", "[^]", CYAN, "open", False),
            ("C", "XX", RED, "CLEAR?" if clearing else "clear", clearing),
        ]
        x = max(0, (w - CELL * len(buttons)) // 2)
        for key, pic, col, words, on in buttons:
            lit = self.lit == key and now < self.lit_until
            pad = (CELL - len(key) - 1 - len(pic)) // 2
            put(self.scr, y, x + pad, key, color(WHITE) | curses.A_REVERSE)
            put(self.scr, y, x + pad + len(key) + 1, pic, color(col) | (curses.A_REVERSE if lit else 0))
            words_at = x + (CELL - len(words)) // 2
            if on:
                put(self.scr, y + 1, words_at, words, color(YELLOW if key == "ENTER" else col) | curses.A_REVERSE)
            else:
                put(self.scr, y + 1, words_at, words, color(WHITE, False))
            x += CELL

    def trophies(self, now, y, w):
        """The secret tools you've found, as big pictures that stay on the screen."""
        found = [k for k in SECRETS if k in self.found]
        x = max(0, (w - 16 * len(found)) // 2)
        for k in found:
            on = self.tool == k
            frame = color(YELLOW) if on else color(WHITE, False)
            put(self.scr, y, x, "+" + "-" * 12 + "+", frame)
            for i, line in enumerate(BIG_ICONS[k]):
                col = RAINBOW[(i + int(now * 4)) % 7] if k == "k" else BIG_COLORS[k]
                put(self.scr, y + 1 + i, x, "|", frame)
                put(self.scr, y + 1 + i, x + 2, line, color(col))
                put(self.scr, y + 1 + i, x + 13, "|", frame)
            put(self.scr, y + 6, x, "+" + ("  ON  " if on else "").center(12, "-") + "+", frame)
            put(self.scr, y + 7, x + (14 - len(SECRETS[k]) - 2) // 2, k.upper(), color(WHITE) | curses.A_REVERSE)
            put(self.scr, y + 7, x + (14 - len(SECRETS[k]) - 2) // 2 + 2, SECRETS[k], color(BIG_COLORS[k]))
            x += 16

    def do_undo(self, now):
        if self.undo:
            self.grid = self.undo.pop()
            self.snd.slide(700, 300, 0.2)
        else:
            self.say("Nothing to undo.", now, 1.5)

    def letter(self, k, now):
        if k == "f":
            self.fill(now)
        elif k == "m":
            self.mirror = not self.mirror
            self.say("Mirror ON: both sides paint the same!" if self.mirror else "Mirror OFF", now, 3, MAGENTA)
            self.snd.notes((0, 7) if self.mirror else (7, 0), 0.08)
        elif k == "u":
            self.do_undo(now)
        elif k == "s":
            self.save_picture(now)
        elif k == "o":
            self.open_next(now)
        elif k == "e":
            self.brush, self.rainbow = 0, False
            self.say("Brush: ERASER", now, 1.5)
        elif k == "c":
            if now - self.clear_armed < 2.0:
                self.checkpoint()
                self.grid = [[0] * self.cols for _ in range(self.rows)]
                self.say("All clean! (U brings it back)", now, 3, YELLOW)
                self.snd.slide(900, 100, 0.5, 0.3)
                self.clear_armed = 0.0
            else:
                self.clear_armed = now
                self.say("Press C again to clear the whole picture.", now, 2, RED)
        elif k in SECRETS:
            if self.tool == k:
                self.tool = None
                self.say("%s put away." % SECRETS[k].title(), now, 2)
                self.snd.blip(300, 0.1)
                return
            self.tool = k
            if k not in self.found:
                self.found.add(k)
                self.save_found()
                self.say("You found a SECRET TOOL: the %s! (%d of %d)  %s" % (SECRETS[k], len(self.found), len(SECRETS),
                                                                             SECRET_HELP[k]), now, 6, YELLOW)
                self.snd.fanfare()
                h, w = self.scr.getmaxyx()
                self.sparks.rain(w, 80, now)
            else:
                self.say("%s! %s  (press %s again to put it away)" % (SECRETS[k], SECRET_HELP[k], k.upper()), now, 4, YELLOW)
                self.snd.notes((0, 4, 7), 0.07)
        else:
            self.say("Letters are tools! Try F, M, U, S, O or C... and look for secret ones.", now, 3, CYAN)
            self.snd.blip(180, 0.08, 0.15, "TRIANGLE")

    # ------------------------------------------------------------ drawing
    def update(self, now, dt):
        pass

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        block = kidslib.BLOCK * 2
        tool = ("  tool: %s" % SECRETS[self.tool]) if self.tool else ""
        info = "  pen: %s   mirror: %s   secret tools found: %d/%d%s " % (
            "DOWN" if self.pen else "up", "ON" if self.mirror else "off", len(self.found), len(SECRETS), tool)
        header(self.scr, "PIXEL PAINTER", info, MAGENTA, w)
        ox, oy = max(1, (w - self.cols * 2) // 2), 2
        edge = color(WHITE, False) | curses.A_DIM
        put(self.scr, oy - 1, ox - 1, "+" + "-" * (self.cols * 2) + "+", edge)
        put(self.scr, oy + self.rows, ox - 1, "+" + "-" * (self.cols * 2) + "+", edge)
        for y, row in enumerate(self.grid):
            put(self.scr, oy + y, ox - 1, "|", edge)
            put(self.scr, oy + y, ox + self.cols * 2, "|", edge)
            for x, c in enumerate(row):
                if c:
                    put(self.scr, oy + y, ox + x * 2, block, color(PALETTE[c]))
                elif (x + y) % 2 == 0:
                    put(self.scr, oy + y, ox + x * 2, " .", color(WHITE, False) | curses.A_DIM)
        blink = int(now * 3) % 2
        cursor_col = RAINBOW[int(now * 6) % 7] if self.rainbow else (PALETTE[self.brush] if self.brush else WHITE)
        put(self.scr, oy + self.cy, ox + self.cx * 2, "[]" if blink else "<>", color(cursor_col) | curses.A_REVERSE)
        if self.mirror or self.tool == "k":
            put(self.scr, oy - 1, ox + self.cols - 1, "||", color(MAGENTA))

        # palette
        py = oy + self.rows + 1
        x = max(0, (w - 56) // 2)
        for n in range(1, 9):
            chosen = self.brush == n and not self.rainbow
            put(self.scr, py, x, "%d" % n, color(WHITE) | (curses.A_REVERSE if chosen else 0))
            put(self.scr, py, x + 1, block, color(PALETTE[n]))
            x += 5
        put(self.scr, py, x, "9", color(WHITE) | (curses.A_REVERSE if self.rainbow else 0))
        for i in range(3):
            put(self.scr, py, x + 1 + i, kidslib.BLOCK, color(RAINBOW[(i + int(now * 4)) % 7]))
        x += 6
        put(self.scr, py, x, "0 eraser", color(WHITE) | (curses.A_REVERSE if self.brush == 0 else 0))
        if now < self.note_until:                     # messages sit on the bottom edge of the picture
            note = " %s " % self.note
            put(self.scr, oy + self.rows, max(0, (w - len(note)) // 2), note, color(self.note_color))
        self.sparks.draw(self.scr, now, 1 / 30)
        if py + 2 < h and w >= CELL * 8:
            self.toolbar(now, py + 1, w)
            if py + 12 < h and w >= 64:
                self.trophies(now, py + 4, w)
        else:
            footer(self.scr, "arrows move  SPACE paint  ENTER pen  F fill  M mirror  U undo  S save  O open  C clear  Esc quit", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Paint pictures one square at a time. Esc quits.")
    p.add_argument("--reset", action="store_true", help="hide the secret tools again (pictures are kept)")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("The secret tools are hidden again. (Your pictures are still in the My Pictures folder.)")
        raise SystemExit
    run(Game, args.mute, "Beautiful work! Bye!")
