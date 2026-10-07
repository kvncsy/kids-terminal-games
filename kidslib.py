"""
Shared pieces for the Kids Computer games: screen drawing, colors, big block
letters and numbers, sparkles, sounds and the main loop.

A game is a class with handle_key(key, now), update(now, dt) and draw(now).
handle_key returns False to quit. Esc quits, unless the game has an
escape(now) method that returns True (for example "go back a screen").
"""
import curses
import locale
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hacker_keys import FONT as _LETTER_FONT        # 5x5 A-Z, 0-9, - ! and space
try:
    import bleep_bloop as bb
except Exception:            # every game still works without sound
    bb = None

RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]
PENTATONIC = [0, 2, 4, 7, 9]

FONT = dict(_LETTER_FONT)
FONT.update({
    "+": ["     ", "  #  ", "#####", "  #  ", "     "],
    "*": ["     ", " # # ", "  #  ", " # # ", "     "],      # the times sign
    "/": ["    #", "   # ", "  #  ", " #   ", "#    "],
    "=": ["     ", "#####", "     ", "#####", "     "],
    "?": [" ### ", "#   #", "  ## ", "     ", "  #  "],
    ".": ["     ", "     ", "     ", "     ", "  #  "],
    ",": ["     ", "     ", "     ", "  #  ", " #   "],
    "(": ["   # ", "  #  ", "  #  ", "  #  ", "   # "],
    ")": [" #   ", "  #  ", "  #  ", "  #  ", " #   "],
    ":": ["     ", "  #  ", "     ", "  #  ", "     "],
    "_": ["     ", "     ", "     ", "     ", "#####"],
})


# ---------------------------------------------------------------- screen
def put(win, y, x, s, attr=0):
    """addstr that never crashes at the edges of the screen."""
    h, w = win.getmaxyx()
    y, x = int(y), int(x)
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


def color(pair, bold=True):
    return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)


def on_blue(pair, bold=True):
    return curses.color_pair(8 + pair) | (curses.A_BOLD if bold else 0)


def utf8():
    return locale.getpreferredencoding().lower().replace("-", "") == "utf8"


def fancy():
    """Music notes, arrows and hearts only where the font has them (not the plain Linux console)."""
    return utf8() and (os.environ.get("TERM") != "linux" or os.environ.get("KIDS_FANCY") == "1")


BLOCK = "#"


def big_width(text, sx=1):
    return (len(text) * 6 - 1) * sx if text else 0


def draw_big(win, text, y, x, sx=1, sy=1, attr=0, colors=None):
    """Draw text in 5x5 block letters. colors(i) can give each character its own look."""
    for i, ch in enumerate(text):
        glyph = FONT.get(ch.upper(), FONT["?"])
        a = colors(i) if colors else attr
        for r, row in enumerate(glyph):
            for c, px in enumerate(row):
                if px == "#":
                    for dy in range(sy):
                        put(win, y + r * sy + dy, x + (i * 6 + c) * sx, BLOCK * sx, a)


def draw_big_centered(win, text, y, w, sx=1, sy=1, attr=0, colors=None):
    draw_big(win, text, y, (w - big_width(text, sx)) // 2, sx, sy, attr, colors)


def best_scale(text, width, height, extra_rows=0, choices=((3, 2), (2, 2), (2, 1), (1, 1))):
    """The biggest letter size that fits text in width x (height - extra_rows)."""
    for sx, sy in choices:
        if big_width(text, sx) <= width and 5 * sy + extra_rows <= height:
            return sx, sy
    return 1, 1


def box(win, y, x, h, w, attr):
    if w < 2 or h < 2:
        return
    tl, tr, bl, br, hz, vt = ("┌", "┐", "└", "┘", "─", "│") if utf8() else ("+", "+", "+", "+", "-", "|")
    put(win, y, x, tl + hz * (w - 2) + tr, attr)
    for r in range(1, h - 1):
        put(win, y + r, x, vt, attr)
        put(win, y + r, x + w - 1, vt, attr)
    put(win, y + h - 1, x, bl + hz * (w - 2) + br, attr)


def header(win, title, info, pair, w):
    put(win, 0, 0, " " * w, color(pair) | curses.A_REVERSE)
    put(win, 0, 0, " %s " % title, color(WHITE) | curses.A_REVERSE)
    put(win, 0, len(title) + 3, info, color(pair) | curses.A_REVERSE)


def footer(win, text, w, h):
    put(win, h - 1, max(0, (w - len(text)) // 2), text, color(WHITE, False) | curses.A_DIM)


# keys
def is_enter(key):
    return key in ("\n", "\r") or key == curses.KEY_ENTER


def is_backspace(key):
    return key in ("\x7f", "\b") or key in (curses.KEY_BACKSPACE, curses.KEY_DC)


# ---------------------------------------------------------------- sparkles
class Sparkles:
    def __init__(self):
        self.parts = []

    def burst(self, x, y, n=20, colors=None, speed=24, now=None, chars="*+o.x"):
        now = now or time.time()
        colors = colors or RAINBOW
        for _ in range(n):
            self.parts.append([x, y, random.uniform(-speed, speed), random.uniform(-speed / 2, speed / 4),
                               now + random.uniform(.5, 1.2), random.choice(chars), random.choice(colors)])

    def rain(self, w, n=80, now=None):
        now = now or time.time()
        for _ in range(n):
            self.parts.append([random.uniform(0, w), random.uniform(-6, 0), random.uniform(-3, 3),
                               random.uniform(4, 12), now + random.uniform(1.5, 3), random.choice("*+o~^%"),
                               random.choice(RAINBOW)])

    def draw(self, win, now, dt):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 12 * dt
            put(win, p[1], p[0], p[5], color(p[6]))
        self.parts = [p for p in self.parts if p[4] > now][-500:]


# ---------------------------------------------------------------- sound
class Sounds:
    """Little sounds made with the Bleep Bloop Band synth engine."""

    def __init__(self, enabled=True):
        self.eng = None
        if enabled and bb:
            self.eng = bb.Engine(sound=True)
            self.eng.start()

    def play(self, make):
        if self.eng:
            try:
                self.eng.play(make())
            except Exception:
                pass

    def bell(self, midi, delay=0.0):
        self.play(lambda: bb.bell(bb.mtof(midi), delay=delay))

    def notes(self, steps, gap=0.07, base=72):
        for i, n in enumerate(steps):
            self.bell(base + n, i * gap)

    def blip(self, freq, length=0.12, vol=0.22, shape="SQUARE", delay=0.0):
        self.play(lambda: bb.Voice([bb.tone(getattr(bb, shape), freq, .5)], vol, .002, length, delay=delay))

    def slide(self, f0, f1, length=0.4, vol=0.3, shape="SINE"):
        self.play(lambda: bb.Voice([bb.tone(getattr(bb, shape), f1, .6)], vol, .01, length + .1,
                                   sweep_from=f0 / f1, sweep_time=length))

    def noise(self, length=0.3, vol=0.25, speed=0.6):
        self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, speed, .6)], vol, .005, length))

    def drum(self, n, delay=0.0):
        self.play(lambda: bb.drum(n, delay))

    def key_note(self, i, base=72):
        """A pleasant note for key number i (always in tune with the others)."""
        self.bell(base + PENTATONIC[i % 5] + 12 * ((i // 5) % 2))

    def yes(self, level=0):
        self.notes((0, 4, 7, 12), 0.07, 72 + min(level, 12))

    def no(self):
        self.blip(196, 0.25, 0.25, "TRIANGLE")
        self.blip(147, 0.3, 0.25, "TRIANGLE", delay=0.15)

    def fanfare(self):
        self.notes((0, 4, 7, 12, 7, 12, 16, 19, 24), 0.1)
        self.drum(0)

    def stop(self):
        if self.eng:
            self.eng.stop()


# ---------------------------------------------------------------- main loop
def _drain(scr):
    got = False
    while True:
        try:
            if scr.get_wch() != "\x1b":     # more Escs (held key, quick taps) still mean Esc
                got = True
        except curses.error:
            return got


def _setup(scr):
    global BLOCK
    BLOCK = "█" if utf8() else "#"
    curses.curs_set(0)
    curses.raw()                 # Ctrl+C and Ctrl+Z become ordinary keys
    curses.noecho()
    scr.nodelay(True)
    scr.keypad(True)
    try:
        curses.set_escdelay(25)
    except AttributeError:
        pass
    curses.start_color()
    orange = 208 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    fgs = {RED: curses.COLOR_RED, YELLOW: curses.COLOR_YELLOW, GREEN: curses.COLOR_GREEN,
           CYAN: curses.COLOR_CYAN, BLUE: curses.COLOR_BLUE, MAGENTA: curses.COLOR_MAGENTA,
           WHITE: curses.COLOR_WHITE, ORANGE: orange}
    for pid, fg in fgs.items():
        curses.init_pair(pid, fg, curses.COLOR_BLACK)
        curses.init_pair(8 + pid, fg if fg != curses.COLOR_BLUE else curses.COLOR_CYAN, curses.COLOR_BLUE)
    scr.bkgd(" ", curses.color_pair(WHITE))


def run(make_game, mute=False, goodbye=""):
    """Start a game: make_game(scr, sounds) returns the game object."""
    locale.setlocale(locale.LC_ALL, "")

    def main(scr):
        _setup(scr)
        sounds = Sounds(not mute)
        game = make_game(scr, sounds)
        last = time.time()
        try:
            while True:
                t0 = time.time()
                while True:
                    try:
                        key = scr.get_wch()
                    except curses.error:
                        break
                    if key == curses.KEY_RESIZE:
                        continue
                    if key == "\x1b":
                        if _drain(scr):
                            key = -1          # Alt+key or an odd key sequence, not a lone Esc
                        else:
                            if getattr(game, "escape", None) and game.escape(time.time()):
                                continue
                            if getattr(game, "quit", None):
                                game.quit()
                            return
                    if game.handle_key(key, time.time()) is False:
                        if getattr(game, "quit", None):
                            game.quit()
                        return
                now = time.time()
                game.update(now, min(0.1, now - last))
                scr.erase()
                game.draw(now)
                scr.refresh()
                last = now
                time.sleep(max(0, 1 / 30 - (time.time() - t0)))
        finally:
            sounds.stop()

    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main)
            break
        except KeyboardInterrupt:
            continue
    if goodbye:
        print(goodbye)
