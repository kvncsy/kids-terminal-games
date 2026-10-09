#!/usr/bin/env python3
"""
Quest Editor: change the Quest boards, or make new ones, a bit like ZZT's editor.

  python3 quest_edit.py      (or type "quest edit" on the kids' computer)

Pick a board, move the cursor with the arrows and type a map symbol to put it
there: # wall, T tree, L lion, 1 a robot... Space rubs out. Ctrl+E has the
board's settings (title, exits, robot words), and Ctrl+T tries the board out
in Quest without touching anybody's saved game.

The boards stay plain text files in quest_boards/. The editor keeps their
names right (level-name-where.txt) and puts a copy of the old file in
quest_boards/old/ every time it saves over one.
"""
import curses
import locale
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time

import quest as q
from quest import BOARD_W, BOARD_H, SCREEN_W, SCREEN_H, color, on_blue, put
from quest import RED, YELLOW, GREEN, CYAN, MAGENTA, WHITE

OLD_DIR = os.path.join(q.BOARD_DIR, "old")
EXIT_NAMES = ("north", "south", "east", "west", "up", "down")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
START_INFO = (("adventure", "Level name"), ("goal", "Goal (find ...)"), ("intro", "Words at the start"),
              ("opening", "Movie at the start"), ("ending", "Movie at the end"))
UNDO_LIMIT = 300

NAMES = {
    " ": "ground", "#": "wall", "%": "weak wall (zap it)", "&": "hedge", "~": "water", "=": "bridge",
    ":": "rainbow road", "T": "tree", "O": "boulder (push it)", "*": "gem", "$": "gold", "a": "ammo",
    "+": "heart", "l": "lamp", "?": "surprise box", "!": "the goal (wins the level)", "@": "where you start",
    "L": "lion", "H": "ghost", "E": "leprechaun", "F": "fairy", "V": "crow", "A": "witch", ",": "rat",
    "K": "Leprechaun King", "Q": "Queen Maeve", ">": "way down", "<": "way up",
}
for k, name in q.KEYS.items():
    NAMES[k] = "%s key" % name
    NAMES[k.upper()] = "%s door" % name
for d in "123456789":
    NAMES[d] = "robot %s (talks)" % d
PALETTE = [c for c in " #%&~=:TO*$a+l?!@LHEFVA,KQ><rbygpcRBYGPC123456789"]
assert set(PALETTE) == q.LEGEND, set(PALETTE) ^ q.LEGEND

KEY_HELP = [("type", "put a symbol"), ("Space", "rub out"), ("Enter", "brush again"), ("Tab", "all symbols"),
            ("^D", "draw lines"), ("^F", "fill"), ("^Z", "undo"), ("^E", "settings"), ("^T", "try it"),
            ("^S", "save"), ("Esc", "back")]
CTRL_D, CTRL_E, CTRL_F, CTRL_S, CTRL_T, CTRL_Z = "\x04", "\x05", "\x06", "\x13", "\x14", "\x1a"
ENTER = ("\n", "\r", curses.KEY_ENTER)
BACKSPACE = ("\x7f", "\b", curses.KEY_BACKSPACE)


def keep_old(file_name, move=False):
    """Put a copy of a board file in quest_boards/old/ (with the time in its name) before it changes."""
    os.makedirs(OLD_DIR, exist_ok=True)
    src = os.path.join(q.BOARD_DIR, file_name)
    base = os.path.join(OLD_DIR, "%s-%s" % (file_name[:-4], time.strftime("%Y%m%d-%H%M%S")))
    dst, n = base + ".txt", 2
    while os.path.exists(dst):
        dst, n = "%s-%d.txt" % (base, n), n + 1
    (shutil.move if move else shutil.copy2)(src, dst)


# ================================================================ one level's boards, in memory
class Level:
    """All the boards of one level, as the editor changes them."""

    def __init__(self, number):
        self.number = number
        boards, _ = q.load_world(number)
        self.boards = boards
        for b in boards.values():                  # the editor keeps the @ on the map
            if b.start:
                b.set(*b.start, "@")
        self.dirty = set()

    def start(self):
        return next((b for b in self.boards.values() if has_start(b)), None)

    def file_names(self):
        """What each board's file should be called, from where its exits put it."""
        start = self.start()
        spots = {}
        if start:
            spots = q.board_spots(self.boards, start)
        out = {}
        for name, b in self.boards.items():
            where = q.where_name(*spots[name]) if name in spots else b.info.get("where", "")
            out[name] = "%d-%s%s.txt" % (self.number, name, "-" + where if where else "")
        return out

    def save(self):
        """Write the changed boards (and rename any whose place changed). Returns what happened."""
        names = self.file_names()
        done = []
        for name, b in self.boards.items():
            new = names[name]
            old = getattr(b, "file", None)
            if name not in self.dirty and old == new:
                continue
            if old and os.path.exists(os.path.join(q.BOARD_DIR, old)):
                keep_old(old)
            with open(os.path.join(q.BOARD_DIR, new), "w", encoding="utf-8") as f:
                f.write(board_text(b))
            if old and old != new and os.path.exists(os.path.join(q.BOARD_DIR, old)):
                os.remove(os.path.join(q.BOARD_DIR, old))
                done.append("%s is now %s" % (old, new))
            b.file = new
            b.info["where"] = new[:-4].split("-", 2)[2] if new.count("-") >= 2 else ""
        self.dirty.clear()
        return done


def has_start(b):
    return any("@" in row for row in b.grid)


def board_text(b):
    lines = ["title: " + b.title]
    if b.dark:
        lines.append("dark: yes")
    if b.info.get("box"):
        lines.append("box: " + b.info["box"])
    for key, _ in START_INFO:
        if b.info.get(key):
            lines.append("%s: %s" % (key, b.info[key]))
    for d in EXIT_NAMES:
        if b.exits.get(d):
            lines.append("%s: %s" % (d, b.exits[d]))
    for k in sorted(b.messages):
        lines.append("%s: %s" % (k, b.messages[k]))
    lines.append("map:")
    lines += ["".join(r) for r in b.grid]
    return "\n".join(lines) + "\n"


def blank_board(name, title, level):
    rows = ["#" * BOARD_W] + ["#" + " " * (BOARD_W - 2) + "#" for _ in range(BOARD_H - 2)] + ["#" * BOARD_W]
    b = q.Board(name, title, {}, {}, rows, False, {"level": level})
    b.file = None
    return b


def carve_gap(b, direction):
    """Open a doorway in a wall, where Quest's boards usually have them."""
    if " " in q.edge_of(b, direction):
        return False
    if direction in ("north", "south"):
        y = 0 if direction == "north" else BOARD_H - 1
        inner = 1 if direction == "north" else BOARD_H - 2
        for x in range(28, 32):
            b.set(x, y, " ")
            if b.at(x, inner) == "#":
                b.set(x, inner, " ")
    else:
        x = 0 if direction == "west" else BOARD_W - 1
        inner = 1 if direction == "west" else BOARD_W - 2
        for y in range(9, 12):
            b.set(x, y, " ")
            if b.at(inner, y) == "#":
                b.set(inner, y, " ")
    return True


# ================================================================ the editor
class Editor:
    def __init__(self, scr):
        self.scr = scr
        self.look = q.pick_look()
        self.wait_ms = 250
        self.pick = 0                 # the highlighted line in the board list
        self.msg, self.msg_until, self.msg_color = "", 0.0, WHITE

    # ------------------------------------------------------------ little helpers
    def origin(self):
        h, w = self.scr.getmaxyx()
        return (w - SCREEN_W) // 2, max(0, (h - SCREEN_H) // 2)

    def say(self, text, col=WHITE, secs=3.0):
        self.msg, self.msg_until, self.msg_color = text, time.time() + secs, col

    def wait(self, ms):
        """How long get_key waits for a key (-1: until there is one)."""
        self.wait_ms = ms
        self.scr.timeout(ms)

    def get_key(self):
        """Wait for one key. Esc is Esc, not the start of an arrow key or Alt+something."""
        while True:
            try:
                key = self.scr.get_wch()
            except curses.error:
                return None
            if key == "\x1b":
                self.scr.timeout(25)                       # anything right behind it? (only look, don't wait)
                more = q.drain(self.scr)
                self.scr.timeout(self.wait_ms)
                if more:
                    continue
            if key == curses.KEY_RESIZE:
                return None
            return key

    def too_small(self):
        h, w = self.scr.getmaxyx()
        if w < SCREEN_W or h < SCREEN_H:
            self.scr.erase()
            put(self.scr, 0, 0, "Please make the window bigger (80 x 24).", color(YELLOW))
            self.scr.refresh()
            return True
        return False

    def ask(self, prompt, default=""):
        """Type a line of words at the bottom. Enter is OK, Esc is never mind."""
        text = default
        self.wait(-1)
        try:
            while True:
                ox, oy = self.origin()
                y = oy + SCREEN_H - 1
                put(self.scr, y, ox, " " * (SCREEN_W - 1), color(WHITE))
                shown = (prompt + " " + text)[-(SCREEN_W - 2):]
                put(self.scr, y, ox, shown, color(YELLOW))
                put(self.scr, y, ox + len(shown), "_", color(WHITE) | curses.A_BLINK)
                self.scr.refresh()
                key = self.get_key()
                if key == "\x1b":
                    return None
                if key in ENTER:
                    return text.strip()
                if key in BACKSPACE:
                    text = text[:-1]
                elif isinstance(key, str) and key.isprintable():
                    text += key
        finally:
            self.wait(250)

    def yes_no(self, prompt):
        """y or n (Esc is "never mind": None)."""
        self.wait(-1)
        try:
            while True:
                ox, oy = self.origin()
                put(self.scr, oy + SCREEN_H - 1, ox, (prompt + " (y/n)").ljust(SCREEN_W - 1), color(YELLOW))
                self.scr.refresh()
                key = self.get_key()
                if key == "\x1b":
                    return None
                if isinstance(key, str) and key.lower() in "yn":
                    return key.lower() == "y"
        finally:
            self.wait(250)

    def choose(self, title, options, start=0):
        """Pick one line from a list with the arrows. Returns its number, or None for Esc."""
        i = min(start, len(options) - 1)
        self.wait(-1)
        try:
            while True:
                if self.too_small():
                    self.get_key()
                    continue
                ox, oy = self.origin()
                self.scr.erase()
                width = min(SCREEN_W - 4, max(len(title), *(len(o) for o in options)) + 6)
                rows = min(len(options), SCREEN_H - 6)
                top = min(max(0, i - rows // 2), len(options) - rows)
                bx, by = ox + (SCREEN_W - width) // 2, oy + 1
                a = color(WHITE)
                put(self.scr, by, bx, "+" + "-" * (width - 2) + "+", a)
                put(self.scr, by + 1, bx, "|" + title.center(width - 2) + "|", color(YELLOW))
                put(self.scr, by + 2, bx, "|" + " " * (width - 2) + "|", a)
                for r in range(rows):
                    n = top + r
                    line = (" > " if n == i else "   ") + options[n]
                    put(self.scr, by + 3 + r, bx, "|" + line[:width - 3].ljust(width - 2) + "|",
                        color(YELLOW if n == i else WHITE) | (curses.A_REVERSE if n == i else 0))
                put(self.scr, by + 3 + rows, bx, "|" + "ENTER picks, Esc goes back".center(width - 2) + "|",
                    color(WHITE, False))
                put(self.scr, by + 4 + rows, bx, "+" + "-" * (width - 2) + "+", a)
                self.scr.refresh()
                key = self.get_key()
                if key == "\x1b":
                    return None
                if key in ENTER:
                    return i
                if key == curses.KEY_UP:
                    i = (i - 1) % len(options)
                elif key == curses.KEY_DOWN:
                    i = (i + 1) % len(options)
                elif key == curses.KEY_PPAGE:
                    i = max(0, i - rows)
                elif key == curses.KEY_NPAGE:
                    i = min(len(options) - 1, i + rows)
        finally:
            self.wait(250)

    # ------------------------------------------------------------ the list of boards
    def board_list(self):
        """Every level and its boards. Returns when you press Esc."""
        while True:
            boards, problems = q.load_world()
            levels = sorted({lv for lv, _ in boards})
            rows = []                                       # (text, what, level, board name)
            for lv in levels:
                start = next((b for (l, n), b in boards.items() if l == lv and b.start), None)
                name = start.adventure or start.title if start else "(no start yet)"
                rows.append(("LEVEL %d  %s" % (lv, name), "level", lv, None))
                here = sorted((b for (l, n), b in boards.items() if l == lv), key=lambda b: (not b.start, b.file))
                for b in here:
                    rows.append(("   %-12s %-26s %s" % (b.name, b.title[:26], b.file), "board", lv, b.name))
                rows.append(("   + a new board in level %d" % lv, "new board", lv, None))
            rows.append(("+ a new level", "new level", None, None))
            self.pick = min(self.pick, len(rows) - 1)
            if rows[self.pick][1] == "level":
                self.pick += 1
            key = self.list_screen(rows, problems)
            what, lv, name = rows[self.pick][1:]
            if key == "\x1b":
                return
            if key in ENTER:
                if what == "board":
                    self.edit(lv, name)
                elif what == "new board":
                    self.new_board(lv)
                elif what == "new level":
                    self.new_level(levels)
            elif key == CTRL_T and what == "board":
                self.try_board(lv, name)
            elif key == curses.KEY_DC and what == "board":
                self.delete_board(lv, name)

    def list_screen(self, rows, problems):
        self.wait(250)
        while True:
            if self.too_small():
                self.get_key()
                continue
            ox, oy = self.origin()
            self.scr.erase()
            put(self.scr, oy, ox + (SCREEN_W - 12) // 2, "QUEST EDITOR", color(YELLOW))
            space = SCREEN_H - 7
            top = min(max(0, self.pick - space // 2), max(0, len(rows) - space))
            for r, (text, what, lv, name) in enumerate(rows[top:top + space]):
                n = top + r
                col = YELLOW if what == "level" else (GREEN if what.startswith("new") else WHITE)
                a = color(col, what != "board" or n == self.pick)
                if n == self.pick:
                    a |= curses.A_REVERSE
                put(self.scr, oy + 2 + r, ox + 1, text[:SCREEN_W - 2], a)
            if problems:
                put(self.scr, oy + SCREEN_H - 5, ox + 1, ("quest check: " + problems[0])[:SCREEN_W - 2], color(RED))
                if len(problems) > 1:
                    put(self.scr, oy + SCREEN_H - 4, ox + 1, "  ...and %d more" % (len(problems) - 1), color(RED, False))
            else:
                put(self.scr, oy + SCREEN_H - 5, ox + 1, "quest check: no problems found", color(GREEN, False))
            help_ = "ARROWS pick   ENTER edit   ^T try it   Delete removes a board   Esc quit"
            put(self.scr, oy + SCREEN_H - 2, ox + (SCREEN_W - len(help_)) // 2, help_, color(WHITE, False))
            if time.time() < self.msg_until:
                put(self.scr, oy + SCREEN_H - 3, ox + 1, self.msg[:SCREEN_W - 2].center(SCREEN_W - 2), color(self.msg_color))
            self.scr.refresh()
            key = self.get_key()
            if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE):
                step = {curses.KEY_UP: -1, curses.KEY_DOWN: 1, curses.KEY_PPAGE: -space, curses.KEY_NPAGE: space}[key]
                n = min(max(0, self.pick + step), len(rows) - 1)
                if rows[n][1] == "level":                   # skip the level headings
                    n = n + (1 if step > 0 else -1)
                    n = min(max(1, n), len(rows) - 1)
                self.pick = n
            elif key is not None:
                return key

    def new_name(self, level):
        while True:
            name = self.ask("A short name for the board file (like cave or bigtree):")
            if not name:
                return None
            name = name.lower().replace(" ", "")
            if not re.match(r"^[a-z0-9_]+$", name):
                self.say("Use only letters and numbers, like cave2.", RED)
                continue
            if name in level.boards:
                self.say("Level %d already has a board called %s." % (level.number, name), RED)
                continue
            return name

    def new_board(self, lv):
        level = Level(lv)
        name = self.new_name(level)
        if not name:
            return
        title = self.ask("Its title (shown in the sidebar):", name.title()) or name.title()
        b = blank_board(name, title, lv)
        level.boards[name] = b
        level.dirty.add(name)
        others = sorted(n for n in level.boards if n != name)
        if others:
            i = self.choose("Which board does it join on to?", others + ["none yet"])
            if i is not None and i < len(others):
                d = self.choose("Which way from %s is the new board?" % others[i], list(EXIT_NAMES))
                if d is not None:
                    self.link(level, level.boards[others[i]], EXIT_NAMES[d], name)
        level.save()
        self.say("Made %s. Now draw it!" % name, GREEN)
        self.edit(lv, name, level)

    def new_level(self, levels):
        lv = (max(levels) if levels else 0) + 1
        adventure = self.ask("The name of level %d (like Dragon Mountain):" % lv)
        if not adventure:
            return
        goal = self.ask("What do you find to win it? (like the Dragon's Egg):", "the Golden Crown") or "the Golden Crown"
        level = Level(lv)
        name = self.new_name(level)
        if not name:
            return
        b = blank_board(name, adventure, lv)
        b.info.update(adventure=adventure, goal=goal)
        b.set(BOARD_W // 2, BOARD_H // 2, "@")
        level.boards[name] = b
        level.dirty.add(name)
        level.save()
        self.say("Level %d is ready. The @ is where the player starts; put a ! somewhere to win." % lv, GREEN, 5)
        self.edit(lv, name, level)

    def delete_board(self, lv, name):
        level = Level(lv)
        b = level.boards[name]
        if has_start(b):
            self.say("That's where the level starts, so it has to stay.", RED)
            return
        if not self.yes_no("Remove %s? (a copy goes in quest_boards/old)" % b.file):
            return
        keep_old(b.file, move=True)
        for other in level.boards.values():               # and the ways into it
            for d, target in list(other.exits.items()):
                if target == name:
                    del other.exits[d]
                    level.dirty.add(other.name)
        del level.boards[name]
        level.save()
        self.say("Removed %s." % name, YELLOW)

    def try_board(self, lv, name):
        """Play the board in Quest, then come back."""
        if not Level(lv).start():
            self.say("Level %d needs an @ (where the player starts) before you can try it." % lv, RED)
            return
        curses.endwin()
        subprocess.call([sys.executable, os.path.join(q.HERE, "quest.py"), "--try", str(lv), name])
        self.scr.clear()
        self.scr.refresh()

    # ------------------------------------------------------------ exits
    def link(self, level, b, direction, target):
        """b's exit goes to target, and target's exit comes back (with doorways in the walls)."""
        b.exits[direction] = target
        level.dirty.add(b.name)
        notes = []
        if direction in q.DIRS and carve_gap(b, direction):
            notes.append("opened the %s wall" % direction)
        t = level.boards.get(target)
        back = OPPOSITE[direction]
        if t and not t.exits.get(back):
            t.exits[back] = b.name
            level.dirty.add(t.name)
            notes.append("%s's %s exit comes back here" % (target, back))
            if back in q.DIRS:
                carve_gap(t, back)
        return notes

    # ------------------------------------------------------------ editing one board
    def edit(self, lv, name, level=None):
        self.level = level or Level(lv)
        self.board = self.level.boards[name]
        self.cx, self.cy = BOARD_W // 2, BOARD_H // 2
        self.brush = "#"
        self.drawing = False
        self.undo = []
        self.wait(250)
        while True:
            self.draw()
            key = self.get_key()
            if key is None:
                continue
            if key == "\x1b":
                if self.level.dirty:
                    ans = self.yes_no("Save your changes before going back?")
                    if ans is None:
                        continue
                    if ans:
                        self.save()
                return
            self.edit_key(key)

    def change(self):
        """Remember the board before a change, for Ctrl+Z."""
        self.undo.append([row[:] for row in self.board.grid])
        del self.undo[:-UNDO_LIMIT]
        self.level.dirty.add(self.board.name)

    def edit_key(self, key):
        b = self.board
        moves = {curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0)}
        if key in moves:
            dx, dy = moves[key]
            self.cx = min(max(0, self.cx + dx), BOARD_W - 1)
            self.cy = min(max(0, self.cy + dy), BOARD_H - 1)
            if self.drawing:
                self.place(self.brush)
        elif key in (curses.KEY_HOME, curses.KEY_END):
            self.cx = 0 if key == curses.KEY_HOME else BOARD_W - 1
        elif key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            self.cy = 0 if key == curses.KEY_PPAGE else BOARD_H - 1
        elif key == " ":
            self.place(" ")
        elif key in ENTER:
            self.place(self.brush)
        elif key == "\t":
            i = self.choose("All the symbols (or just type one on the map)",
                            ["%s  %s" % ("space" if c == " " else c + "    ", NAMES[c]) for c in PALETTE],
                            PALETTE.index(self.brush))
            if i is not None:
                self.brush = PALETTE[i]
                self.place(self.brush)
        elif key == CTRL_D:
            self.drawing = not self.drawing
            if self.drawing:
                self.place(self.brush)
            self.say("Drawing lines with %s: move to draw. ^D again to stop." % NAMES[self.brush]
                     if self.drawing else "Stopped drawing.", CYAN)
        elif key == CTRL_F:
            self.fill()
        elif key in (CTRL_Z, curses.KEY_SUSPEND):            # (some terminals send Ctrl+Z as "suspend")
            if self.undo:
                b.grid = self.undo.pop()
                self.level.dirty.add(b.name)
                self.say("Undone.", CYAN, 1.5)
            else:
                self.say("Nothing to undo.", CYAN, 1.5)
        elif key == CTRL_E:
            self.settings()
        elif key == CTRL_S:
            self.save()
        elif key == CTRL_T:
            if self.level.dirty:
                self.save()
            self.try_board(self.level.number, b.name)
        elif isinstance(key, str) and key in q.LEGEND:
            self.brush = key
            self.place(key)
        elif isinstance(key, str) and key.isprintable():
            self.say("%r isn't a map symbol. Tab shows them all." % key, RED)

    def place(self, c):
        b = self.board
        if b.at(self.cx, self.cy) == "@" and c != "@":
            self.say("That's where the player starts. To move it, type @ somewhere else.", RED)
            return
        if c == "@" and not has_start(b):
            start = self.level.start()
            if start:
                self.say("The level starts on %s. Only one @ per level." % start.name, RED)
                return
        if b.at(self.cx, self.cy) == c:
            return
        self.change()
        if c == "@":                                        # one start: move it here
            for y in range(BOARD_H):
                for x in range(BOARD_W):
                    if b.at(x, y) == "@":
                        b.set(x, y, " ")
        b.set(self.cx, self.cy, c)
        if c in "123456789" and c not in b.messages:
            words = self.ask("What does robot %s say? (like  Bolt: Hello!)" % c)
            b.messages[c] = words or "Bot: Hello!"
        if c in q.STAIRS and not b.exits.get(q.STAIRS[c]):
            self.pick_exit(q.STAIRS[c])


    def fill(self):
        """Fill the patch of the same thing under the cursor with the brush."""
        b = self.board
        old = b.at(self.cx, self.cy)
        if old == self.brush or self.brush == "@":
            return
        self.change()
        todo, n = [(self.cx, self.cy)], 0
        while todo:
            x, y = todo.pop()
            if 0 <= x < BOARD_W and 0 <= y < BOARD_H and b.at(x, y) == old:
                b.set(x, y, self.brush)
                n += 1
                todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        self.say("Filled %d squares with %s." % (n, NAMES[self.brush]), CYAN)

    def save(self):
        notes = self.level.save()
        _, problems = q.load_world(self.level.number)
        mine = [p for p in problems if p.startswith(("%d-" % self.level.number, "level %d" % self.level.number))] or problems
        if mine:
            self.say("Saved. But: " + mine[0], RED, 6)
        else:
            self.say("Saved! " + "; ".join(notes) if notes else "Saved!", GREEN, 4)

    # ------------------------------------------------------------ settings
    def pick_exit(self, direction):
        """Choose where an exit goes."""
        b = self.board
        others = sorted(n for n in self.level.boards if n != b.name)
        options = ["nowhere"] + others + ["a new board..."]
        now = b.exits.get(direction)
        i = self.choose("The %s exit goes to..." % direction, options, options.index(now) if now in options else 0)
        if i is None:
            return
        if i == 0:
            if direction in b.exits:
                del b.exits[direction]
                self.level.dirty.add(b.name)
                self.say("No %s exit now. (Any gap in the wall is still there.)" % direction, CYAN)
            return
        if i == len(options) - 1:
            name = self.new_name(self.level)
            if not name:
                return
            title = self.ask("Its title:", name.title()) or name.title()
            nb = blank_board(name, title, self.level.number)
            self.level.boards[name] = nb
            self.level.dirty.add(name)
            target = name
        else:
            target = options[i]
        notes = self.link(self.level, b, direction, target)
        self.say("The %s exit goes to %s%s." % (direction, target, ("; " + "; ".join(notes)) if notes else ""), GREEN, 5)

    def settings(self):
        b = self.board
        i = 0
        while True:
            items = [("title", "Title", b.title), ("dark", "Dark (needs the lamp)", "yes" if b.dark else "no"),
                     ("box", "The ? box hides a key", q.KEYS.get(b.info.get("box"), "no key"))]
            for d in EXIT_NAMES:
                items.append(("exit " + d, "%s exit" % d.title(), b.exits.get(d, "-")))
            for d in "123456789":
                items.append(("robot " + d, "Robot %s says" % d, b.messages.get(d, "-")))
            if has_start(b):
                for key, label in START_INFO:
                    items.append(("info " + key, label, b.info.get(key, "-")))
            options = ["%-22s %s" % (label, value)[:70] for _, label, value in items]
            i = self.choose("Settings for %s (%s)" % (b.name, b.file or "not saved yet"), options, i)
            if i is None:
                return
            what = items[i][0]
            if what == "title":
                t = self.ask("Title:", b.title)
                if t:
                    b.title = t
            elif what == "dark":
                b.dark = not b.dark
            elif what == "box":
                keys = ["no key"] + list(q.KEYS)
                k = self.choose("The ? box on this board hides...", ["no key"] + ["the %s key" % n for n in q.KEYS.values()])
                if k is not None:
                    if k == 0:
                        b.info.pop("box", None)
                    else:
                        b.info["box"] = keys[k]
            elif what.startswith("exit "):
                self.pick_exit(what[5:])
            elif what.startswith("robot "):
                d = what[6:]
                words = self.ask("Robot %s says (like  Bolt: Hello!), empty to remove:" % d, b.messages.get(d, ""))
                if words is not None:
                    if words:
                        b.messages[d] = words
                    else:
                        b.messages.pop(d, None)
            elif what.startswith("info "):
                key = what[5:]
                if key in ("opening", "ending"):
                    scenes = ["none"] + sorted(getattr(q.quest_scenes, "SCENES", {}))
                    k = self.choose("Which movie?", scenes)
                    if k is not None:
                        if k == 0:
                            b.info.pop(key, None)
                        else:
                            b.info[key] = scenes[k]
                else:
                    words = self.ask(dict(START_INFO)[key] + ":", b.info.get(key, ""))
                    if words is not None:
                        if words:
                            b.info[key] = words
                        else:
                            b.info.pop(key, None)
            self.level.dirty.add(b.name)

    # ------------------------------------------------------------ drawing
    def draw(self):
        if self.too_small():
            return
        scr, b, now = self.scr, self.board, time.time()
        ox, oy = self.origin()
        scr.erase()
        for y in range(BOARD_H):
            for x in range(BOARD_W):
                t = b.at(x, y)
                if t == " ":
                    continue
                if t == "@":
                    ch, a = self.look["player"], on_blue(WHITE)
                elif t in "123456789":                       # robots show their number here
                    ch, a = t, color(MAGENTA) | curses.A_REVERSE
                else:
                    ch, a = q.glyph(self.look, t, now)
                put(scr, oy + y, ox + x, ch, a)
        here = b.at(self.cx, self.cy)
        ch = " " if here == " " else (q.glyph(self.look, here, now)[0] if here not in "@123456789" else here)
        cur = color(YELLOW) | curses.A_REVERSE if int(now * 4) % 2 else color(WHITE) | curses.A_REVERSE
        put(scr, oy + self.cy, ox + self.cx, ch if ch != " " else "+", cur)
        # the sidebar
        x = ox + BOARD_W
        blank = " " * (SCREEN_W - BOARD_W)
        for r in range(SCREEN_H - 1):
            put(scr, oy + r, x, blank, on_blue(WHITE))
        for r, line in enumerate(textwrap.wrap(b.title, 18)[:2]):
            put(scr, oy + r, x + 1, line, on_blue(YELLOW))
        put(scr, oy + 2, x + 1, ("Level %d  %s%s" % (self.level.number, b.name, "*" if b.name in self.level.dirty else ""))[:19],
            on_blue(CYAN))
        put(scr, oy + 3, x + 1, "x %-2d y %-2d %s" % (self.cx, self.cy, "dark" if b.dark else ""), on_blue(WHITE, False))
        put(scr, oy + 5, x + 1, "Here:", on_blue(WHITE, False))
        put(scr, oy + 6, x + 1, ("%s %s" % ("" if here == " " else here, NAMES[here]))[:19], on_blue(WHITE))
        put(scr, oy + 7, x + 1, "Brush:" + ("  DRAWING" if self.drawing else ""), on_blue(YELLOW if self.drawing else WHITE, self.drawing))
        put(scr, oy + 8, x + 1, ("%s %s" % ("" if self.brush == " " else self.brush, NAMES[self.brush]))[:19], on_blue(WHITE))
        for r, (k, what) in enumerate(KEY_HELP):
            put(scr, oy + 10 + r, x + 1, "%-6s%s" % (k, what), on_blue(WHITE, False))
        # what's under the cursor: a robot's words, or where an exit goes
        info = ""
        if here in b.messages:
            info = "Robot %s: %s" % (here, b.messages[here])
        elif here in q.STAIRS:
            info = "Goes %s to %s" % (q.STAIRS[here], b.exits.get(q.STAIRS[here], "nowhere yet! (^E settings)"))
        elif self.cx in (0, BOARD_W - 1) or self.cy in (0, BOARD_H - 1):
            side = "north" if self.cy == 0 else "south" if self.cy == BOARD_H - 1 else "west" if self.cx == 0 else "east"
            info = "The %s exit goes to %s" % (side, b.exits.get(side, "nowhere"))
        if now < self.msg_until:
            put(scr, oy + BOARD_H, ox, self.msg[:BOARD_W].center(BOARD_W), color(self.msg_color))
        elif info:
            put(scr, oy + BOARD_H, ox, info[:BOARD_W], color(WHITE, False))
        scr.refresh()


def main(scr):
    curses.curs_set(0)
    curses.raw()
    curses.noecho()
    scr.keypad(True)
    try:
        curses.set_escdelay(25)
    except AttributeError:
        pass
    q.setup_colors(scr)
    Editor(scr).board_list()


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    if os.environ.get("TERM") == "linux" and sys.stdout.isatty():
        sys.stdout.write("\033[?8h")                        # key repeat on, so holding an arrow moves the cursor
        sys.stdout.flush()
    try:
        curses.wrapper(main)
    finally:
        if os.environ.get("TERM") == "linux" and sys.stdout.isatty():
            sys.stdout.write("\033[?8l")
    print("Bye! Type  quest  to play your boards.")
