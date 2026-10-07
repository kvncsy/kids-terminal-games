#!/usr/bin/env python3
"""
ROBOT COMMANDER - a first taste of programming for kids.

Line up arrow keys as a program, press ENTER, and the robot follows it to
collect every star. Rocks go BONK. Later levels only have a few program slots,
so you need repeats: press a number, then an arrow (3 then -> means
"go right 3 times"). After the 10 levels come endless random missions.

  arrows     add a step to the program
  2-9        then an arrow: repeat that step
  BACKSPACE  take back the last step
  ENTER      run the program
  SPACE      robot dance
  Esc        quit

Progress is saved in ~/.robot_commander. Sounds come from Bleep Bloop Band
(bleep_bloop.py in the same folder) when it is there.

  python3 robot_commander.py             play from the saved level
  python3 robot_commander.py --level 5   jump to a level
  python3 robot_commander.py --reset     start over at level 1
  python3 robot_commander.py --mute      no sound
"""
import argparse
import curses
import json
import locale
import os
import random
import sys
import time
from collections import deque

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bleep_bloop as bb
except Exception:       # the robot works fine without sound
    bb = None

COLS, ROWS = 10, 6
STEP_TIME = 0.28
SAVE_FILE = os.path.expanduser("~/.robot_commander")
DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# name, hint, program slots (None = as many as you like), map
# map: R robot, * star, # rock, . empty
LEVELS = [
    ("HELLO, ROBOT!", "Press {R} {R} {R}, then press ENTER!", None, [
        "..........",
        "..........",
        ".R..*.....",
        "..........",
        "..........",
        ".........."]),
    ("UP, UP, UP", "Stars can be up high. Try {U}!", None, [
        "..........",
        "....*.....",
        "..........",
        "..........",
        "....R.....",
        ".........."]),
    ("AROUND THE CORNER", "Go right, then go up.", None, [
        ".......*..",
        "..........",
        "..........",
        "..R.......",
        "..........",
        ".........."]),
    ("TWO STARS", "Get BOTH stars in one program.", None, [
        "..........",
        ".R..*.....",
        "..........",
        "....*.....",
        "..........",
        ".........."]),
    ("ROCKY ROAD", "Rocks go BONK! Find a way around.", None, [
        "..........",
        "..........",
        ".R..#..*..",
        "..........",
        "..........",
        ".........."]),
    ("COUNT IT!", "Only 1 slot! Press 8, then {R}.", 1, [
        "..........",
        "..........",
        ".R.......*",
        "..........",
        "..........",
        ".........."]),
    ("BIG STEPS", "Just 2 slots. Numbers make big steps!", 2, [
        ".........*",
        "..........",
        "..........",
        "..........",
        "..........",
        "R........."]),
    ("THE STAIRCASE", "Right, up, right, up... like stairs.", None, [
        "......*...",
        "..........",
        "....*.....",
        "..........",
        "..*.......",
        "R........."]),
    ("THE MAZE", "A maze! Find the path before you start.", None, [
        "R.#......*",
        "..#.####..",
        "..#.#..#..",
        "....#..#..",
        "#####..#..",
        ".........."]),
    ("STAR PARTY", "Four stars! Can you get them all?", None, [
        "*........*",
        "..........",
        "....R.....",
        "..........",
        "..........",
        "*........*"]),
]
MISSION_HINTS = ["A brand new mission!", "Plan your path, then press ENTER.",
                 "Use numbers for long trips!", "Watch out for rocks!", "You can do it, commander!"]


def random_level(n):
    """An endless supply of missions, always solvable."""
    rng = random.Random(n * 7919)
    while True:
        cells = [(x, y) for x in range(COLS) for y in range(ROWS)]
        rng.shuffle(cells)
        start = cells.pop()
        rocks = set(cells[:rng.randint(6, 14)])
        rest = cells[len(rocks):]
        stars = set(rest[:rng.randint(2, 4)])
        seen, todo = {start}, deque([start])
        while todo:
            x, y = todo.popleft()
            for dx, dy in DIRS.values():
                c = (x + dx, y + dy)
                if 0 <= c[0] < COLS and 0 <= c[1] < ROWS and c not in rocks and c not in seen:
                    seen.add(c)
                    todo.append(c)
        if stars <= seen:
            rows = []
            for y in range(ROWS):
                rows.append("".join("R" if (x, y) == start else "*" if (x, y) in stars
                                    else "#" if (x, y) in rocks else "." for x in range(COLS)))
            return ("MISSION %d" % n, rng.choice(MISSION_HINTS), None, rows)


def get_level(num):
    return LEVELS[num - 1] if num <= len(LEVELS) else random_level(num - len(LEVELS))


def load_progress():
    try:
        with open(SAVE_FILE) as f:
            return max(1, int(json.load(f)["level"]))
    except (OSError, ValueError, KeyError, TypeError):
        return 1


def save_progress(level):
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump({"level": level}, f)
    except OSError:
        pass


# ================================================================ sound
class Sounds:
    def __init__(self, enabled):
        self.eng = None
        if enabled and bb:
            self.eng = bb.Engine(sound=True)
            self.eng.start()

    def play(self, make):
        if self.eng:
            self.eng.play(make())

    def blip(self, direction):
        f = {"U": 880, "R": 660, "L": 550, "D": 440}[direction]
        self.play(lambda: bb.Voice([bb.tone(bb.SQUARE, f, .4)], .22, .002, .12))

    def step(self):
        self.play(lambda: bb.Voice([bb.tone(bb.TRIANGLE, 330, .6)], .3, .002, .09))

    def star(self):
        for i, f in enumerate((1047, 1319, 1568)):
            self.play(lambda f=f, i=i: bb.bell(f, delay=i * 0.06))

    def bonk(self):
        self.play(lambda: bb.drum(5))
        self.play(lambda: bb.Voice([bb.tone(bb.SAW, 160, .5)], .3, .005, .3, sweep_from=1.6, sweep_time=.25))

    def undo(self):
        self.play(lambda: bb.Voice([bb.tone(bb.SINE, 300, .7)], .3, .01, .25, sweep_from=2, sweep_time=.2))

    def win(self):
        for i, n in enumerate((0, 4, 7, 12, 7, 12, 16)):
            self.play(lambda n=n, i=i: bb.bell(bb.mtof(72 + n), delay=i * 0.1))
        self.play(lambda: bb.drum(0))

    def dance(self):
        for i, n in enumerate((0, 7, 4, 9, 12, 9)):
            self.play(lambda n=n, i=i: bb.Voice([bb.tone(bb.SQUARE, bb.mtof(60 + n), .5)], .3, .005, .2,
                                                delay=i * 0.15))

    def letter(self):
        n = random.choice((0, 2, 4, 7, 9, 12))
        self.play(lambda: bb.bell(bb.mtof(72 + n)))

    def stop(self):
        if self.eng:
            self.eng.stop()


# ================================================================ screen
RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]

ROBOT = ["  _|_ ", " [o_o]", " /|_|\\"]
ROBOT_HAPPY = ["  _|_ ", " [^_^]", " \\|_|/"]
ROBOT_BONK = ["  *|* ", " [x_x]", " /|_|\\"]
STAR = ["  \\|/ ", "  -*- ", "  /|\\ "]
ROCK = [" .--. ", "(    )", " '--' "]


def put(win, y, x, s, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w or not s:
        return
    if x < 0:
        s, x = s[-x:], 0
    s = s[: w - x]
    if y == h - 1 and x + len(s) >= w:
        s = s[: w - x - 1]
    if s:
        try:
            win.addstr(y, x, s, attr)
        except curses.error:
            pass


class App:
    def __init__(self, scr, sounds, level):
        self.scr = scr
        self.snd = sounds
        utf = locale.getpreferredencoding().lower().replace("-", "") == "utf8"
        self.utf = utf
        fancy = utf and os.environ.get("TERM") != "linux"
        self.arrow = {"U": "↑", "D": "↓", "L": "←", "R": "→"} if fancy else {"U": "^", "D": "v", "L": "<", "R": ">"}
        self.parts = []
        self.parts_pending = []    # sparkle bursts waiting to be placed on screen
        self.load(level)

    def attr(self, pair, bold=True):
        return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)

    # ------------------------------------------------------------ level state
    def load(self, level):
        self.level = level
        self.name, hint, self.slots, rows = get_level(level)
        self.hint = hint.format(**self.arrow)
        self.rocks, self.all_stars = set(), set()
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == "R":
                    self.start = (x, y)
                elif c == "*":
                    self.all_stars.add((x, y))
                elif c == "#":
                    self.rocks.add((x, y))
        self.program = []          # [direction, times]
        self.pending = 1
        self.reset_board()
        self.mode = "edit"         # edit, run, bonk, win
        self.message = "Add arrows to the program, then press ENTER."
        self.bubble, self.bubble_until = "", 0.0
        self.dance_until = 0.0

    def reset_board(self):
        self.pos = self.start
        self.stars = set(self.all_stars)
        self.trail = set()
        self.pc, self.left = 0, 0

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if key == "\x1b":
            return False
        if isinstance(key, int):
            names = {curses.KEY_UP: "U", curses.KEY_DOWN: "D", curses.KEY_LEFT: "L", curses.KEY_RIGHT: "R",
                     curses.KEY_BACKSPACE: "BACK", curses.KEY_ENTER: "ENTER", curses.KEY_DC: "BACK"}
            name = names.get(key)
        elif key in "\n\r":
            name = "ENTER"
        elif key in "\x7f\b":
            name = "BACK"
        elif key == " ":
            name = "SPACE"
        elif key.isdigit():
            name = "NUM"
        else:
            name = "OTHER"
        if name is None:
            return True

        if self.mode == "win":
            if name == "ENTER":
                self.load(self.level + 1)
            return True
        if self.mode == "run":
            return True                  # let the robot finish
        if self.mode == "bonk":
            self.mode = "edit"
            self.reset_board()

        if name in DIRS:
            if self.slots is not None and len(self.program) >= self.slots:
                self.message = "No slots left! Use BACKSPACE, or a number for big steps."
                self.snd.bonk()
                return True
            if len(self.program) >= 30:
                return True
            self.program.append([name, self.pending])
            self.snd.blip(name)
            self.pending = 1
            self.reset_board()
            self.message = "Press ENTER to go!"
        elif name == "NUM":
            n = int(key)
            self.pending = n if n >= 2 else 1
            self.message = ("Now press an arrow: the robot will go %d times!" % n) if n >= 2 else "Numbers 2 to 9 make repeats."
            self.snd.letter()
        elif name == "BACK":
            if self.pending > 1:
                self.pending = 1
            elif self.program:
                self.program.pop()
            self.snd.undo()
            self.reset_board()
            self.message = "Oops, taken back." if self.program else "Add arrows to the program, then press ENTER."
        elif name == "ENTER":
            if not self.program:
                self.message = "The program is empty! Press some arrows first."
                self.snd.bonk()
            else:
                self.reset_board()
                self.mode, self.next_step = "run", now + STEP_TIME
                self.pc, self.left = 0, self.program[0][1]
                self.message = "Running your program..."
        elif name == "SPACE":
            self.dance_until = now + 1.2
            self.snd.dance()
        else:
            self.bubble, self.bubble_until = (key.upper() + "!" if key.isalpha() else "BEEP!"), now + 1.0
            self.snd.letter()
        return True

    # ------------------------------------------------------------ running
    def update(self, now):
        if self.mode != "run" or now < self.next_step:
            return
        self.next_step = now + STEP_TIME
        if self.left == 0:
            self.pc += 1
            if self.pc >= len(self.program):
                self.mode = "edit"
                n = len(self.stars)
                self.message = "Almost! %d star%s left. Change the program and try again." % (n, "" if n == 1 else "s")
                return
            self.left = self.program[self.pc][1]
        d = self.program[self.pc][0]
        dx, dy = DIRS[d]
        nx, ny = self.pos[0] + dx, self.pos[1] + dy
        if not (0 <= nx < COLS and 0 <= ny < ROWS) or (nx, ny) in self.rocks:
            self.mode = "bonk"
            self.message = "BONK! Press any key, fix the program, and try again."
            self.bubble, self.bubble_until = "BONK!", now + 1.5
            self.snd.bonk()
            return
        self.trail.add(self.pos)
        self.pos = (nx, ny)
        self.left -= 1
        self.snd.step()
        if self.pos in self.stars:
            self.stars.discard(self.pos)
            self.snd.star()
            self.sparkle(self.pos, 12)
            if not self.stars:
                self.mode = "win"
                self.snd.win()
                save_progress(self.level + 1)
                steps = sum(t for _, t in self.program)
                self.message = "You used %d command%s and %d steps. Press ENTER for the next mission!" % (
                    len(self.program), "" if len(self.program) == 1 else "s", steps)
                for _ in range(5):
                    self.sparkle((random.randrange(COLS), random.randrange(ROWS)), 14)

    def sparkle(self, cell, n):
        self.parts_pending.append((cell, n))

    # ------------------------------------------------------------ drawing
    def draw(self, now, dt):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        big = h >= 30 and w >= 66
        cw, ch = (6, 3) if big else (3, 1)
        bw, bh = COLS * cw + 2, ROWS * ch + 2
        bx, by = max(0, (w - bw) // 2), 4 if big else 3
        self.cell_origin = (bx + 1, by + 1, cw, ch)

        # header
        stars_txt = " STARS %d/%d " % (len(self.all_stars) - len(self.stars), len(self.all_stars))
        put(scr, 0, 0, " " * w, self.attr(ORANGE) | curses.A_REVERSE)
        put(scr, 0, 0, " ROBOT COMMANDER ", self.attr(WHITE) | curses.A_REVERSE)
        put(scr, 0, 18, " LEVEL %d: %s " % (self.level, self.name), self.attr(ORANGE) | curses.A_REVERSE)
        put(scr, 0, max(0, w - len(stars_txt) - 1), stars_txt, self.attr(YELLOW) | curses.A_REVERSE)
        put(scr, 2 if big else 1, max(0, (w - len(self.hint)) // 2), self.hint, self.attr(YELLOW))

        # board
        hz, vt, cs = ("─", "│", "┌┐└┘") if self.utf else ("-", "|", "++++")
        a = self.attr(BLUE)
        put(scr, by, bx, cs[0] + hz * (bw - 2) + cs[1], a)
        put(scr, by + bh - 1, bx, cs[2] + hz * (bw - 2) + cs[3], a)
        for y in range(by + 1, by + bh - 1):
            put(scr, y, bx, vt, a)
            put(scr, y, bx + bw - 1, vt, a)
        for y in range(ROWS):
            for x in range(COLS):
                self.draw_cell(x, y, now, big)

        # sparkles
        for cell, n in self.parts_pending:
            cx, cy = self.cell_center(cell)
            for _ in range(n):
                self.parts.append([cx, cy, random.uniform(-14, 14), random.uniform(-7, 3),
                                   now + random.uniform(.5, 1.1), random.choice("*+.o"), random.choice(RAINBOW)])
        self.parts_pending = []
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 10 * dt
            put(scr, int(p[1]), int(p[0]), p[5], self.attr(p[6]))
        self.parts = [p for p in self.parts if p[4] > now]

        # robot's speech bubble
        if now < self.bubble_until:
            cx, cy = self.cell_center(self.pos)
            b = " %s " % self.bubble
            put(scr, cy - (2 if big else 1), cx - len(b) // 2, b, self.attr(ORANGE) | curses.A_REVERSE)

        # program strip
        py = by + bh + 1
        self.draw_program(py, w)
        color = {"bonk": RED, "win": GREEN}.get(self.mode, WHITE)
        flash = self.mode == "win" and int(now * 4) % 2
        put(scr, py + 3, max(0, (w - len(self.message)) // 2), self.message,
            self.attr(color) | (curses.A_REVERSE if flash else 0))
        if self.mode == "win":
            banner = "  MISSION COMPLETE!  "
            put(scr, by + bh // 2, (w - len(banner)) // 2, banner,
                self.attr(RAINBOW[int(now * 6) % len(RAINBOW)]) | curses.A_REVERSE)
        help_txt = "arrows: add step   2-9: repeat   BACKSPACE: undo   ENTER: go   SPACE: dance   Esc: quit"
        put(scr, h - 1, max(0, (w - len(help_txt)) // 2), help_txt, self.attr(WHITE, False) | curses.A_DIM)
        scr.refresh()

    def cell_center(self, cell):
        ox, oy, cw, ch = self.cell_origin
        return ox + cell[0] * cw + cw // 2, oy + cell[1] * ch + ch // 2

    def draw_cell(self, x, y, now, big):
        ox, oy, cw, ch = self.cell_origin
        px, py = ox + x * cw, oy + y * ch
        cell = (x, y)
        if cell == self.pos:
            if self.mode == "bonk":
                art, color = ROBOT_BONK, RED
            elif self.mode == "win" or now < self.dance_until:
                art = ROBOT_HAPPY if int(now * 6) % 2 else ROBOT
                color = ORANGE
            else:
                art, color = ROBOT, ORANGE
            if big:
                for i, line in enumerate(art):
                    put(self.scr, py + i, px, line, self.attr(WHITE if i == 1 else color))
            else:
                put(self.scr, py, px, " R ", self.attr(color) | curses.A_REVERSE)
        elif cell in self.stars:
            color = YELLOW if int(now * 3 + x + y) % 3 else WHITE
            if big:
                for i, line in enumerate(STAR):
                    put(self.scr, py + i, px, line, self.attr(color))
            else:
                put(self.scr, py, px, " * ", self.attr(color))
        elif cell in self.rocks:
            if big:
                for i, line in enumerate(ROCK):
                    put(self.scr, py + i, px, line, self.attr(WHITE, False))
            else:
                put(self.scr, py, px, "###", self.attr(WHITE, False))
        else:
            mark = "o" if cell in self.trail else "."
            put(self.scr, py + ch // 2, px + cw // 2, mark,
                self.attr(GREEN) if cell in self.trail else self.attr(BLUE, False) | curses.A_DIM)

    def draw_program(self, y, w):
        tokens = []
        for i, (d, n) in enumerate(self.program):
            txt = "[%s%s]" % (self.arrow[d], "x%d" % n if n > 1 else "")
            active = self.mode in ("run", "bonk") and i == self.pc
            tokens.append((txt, self.attr(ORANGE) | curses.A_REVERSE if active else self.attr(CYAN)))
        if self.slots is not None:
            tokens += [("[  ]", self.attr(WHITE, False) | curses.A_DIM)] * max(0, self.slots - len(self.program))
        if self.pending > 1:
            tokens.append(("[%d x ?]" % self.pending, self.attr(YELLOW) | curses.A_REVERSE))
        label = "PROGRAM: "
        slots = "" if self.slots is None else "  (%d slot%s)" % (self.slots, "" if self.slots == 1 else "s")
        width = len(label) + sum(len(t) + 1 for t, _ in tokens) + len(slots)
        lines, x = 0, max(1, (w - min(width, w - 2)) // 2)
        start_x = x
        put(self.scr, y, x, label, self.attr(WHITE))
        x += len(label)
        if not tokens:
            put(self.scr, y, x, "(empty)", self.attr(WHITE, False) | curses.A_DIM)
        for txt, a in tokens:
            if x + len(txt) >= w - 1 and lines == 0:
                lines, x = 1, start_x + len(label)
            put(self.scr, y + lines, x, txt, a)
            x += len(txt) + 1
        put(self.scr, y + lines, x, slots, self.attr(WHITE, False))


# ================================================================ main loop
def drain(scr):
    got = False
    while True:
        try:
            if scr.get_wch() != "\x1b":     # more Escs (held key, quick taps) still mean Esc
                got = True
        except curses.error:
            return got


def main(scr, args):
    curses.curs_set(0)
    curses.raw()
    curses.noecho()
    scr.nodelay(True)
    scr.keypad(True)
    try:
        curses.set_escdelay(25)
    except AttributeError:
        pass
    curses.start_color()
    orange = 208 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    for pid, fg in {RED: curses.COLOR_RED, YELLOW: curses.COLOR_YELLOW, GREEN: curses.COLOR_GREEN,
                    CYAN: curses.COLOR_CYAN, BLUE: curses.COLOR_BLUE, MAGENTA: curses.COLOR_MAGENTA,
                    WHITE: curses.COLOR_WHITE, ORANGE: orange}.items():
        curses.init_pair(pid, fg, curses.COLOR_BLACK)
    scr.bkgd(" ", curses.color_pair(WHITE))

    sounds = Sounds(not args.mute)
    app = App(scr, sounds, args.level or load_progress())
    last = time.time()
    try:
        while True:
            t0 = time.time()
            while True:
                try:
                    key = scr.get_wch()
                except curses.error:
                    break
                if key == "\x1b" and drain(scr):
                    key = "?"             # Alt+key or an odd key sequence, not a lone Esc
                if not app.handle_key(key, time.time()):
                    return
            now = time.time()
            app.update(now)
            app.draw(now, min(0.1, now - last))
            last = now
            time.sleep(max(0, 1 / 30 - (time.time() - t0)))
    finally:
        sounds.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Program a robot with arrow keys. Esc quits.")
    p.add_argument("--level", type=int, help="start at this level")
    p.add_argument("--reset", action="store_true", help="start over at level 1")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        save_progress(1)
        print("Robot Commander will start again at level 1.")
        raise SystemExit
    locale.setlocale(locale.LC_ALL, "")
    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue
    print("Great work, commander!")
