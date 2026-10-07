#!/usr/bin/env python3
"""
ALPHABET RAIN - a gentle typing game for kids.

Big letters fall from the rain clouds. Type a letter to pop it into fireworks.
Nobody loses: a missed letter bounces into the puddle and waits there, and it
can still be popped. Every 25 pops is a new level with more letters, a little
more speed, and numbers from level 3. Golden letters are worth a bonus.

  letters / numbers   pop them
  Esc                 quit

Letter shapes come from Hacker Keys and sounds from Bleep Bloop Band
(hacker_keys.py and bleep_bloop.py in the same folder).

  python3 letter_rain.py          play
  python3 letter_rain.py --mute   no sound
"""
import argparse
import curses
import locale
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hacker_keys import FONT      # 5x5 block letters
try:
    import bleep_bloop as bb
except Exception:                 # the game works fine without sound
    bb = None

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
POPS_PER_LEVEL = 25
FLOOR_WAIT = 7.0                  # seconds a missed letter waits in the puddle
PENTATONIC = [0, 2, 4, 7, 9]
CHEERS = ["NICE!", "YES!", "POP!", "WOW!", "SUPER!", "YAY!"]
STREAK_WORDS = {5: "FIVE IN A ROW!", 10: "TEN IN A ROW! AMAZING!", 20: "TWENTY! YOU'RE A TYPING STAR!"}

RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]
ROBOT = [" .-^-. ", "/_/_\\_\\", "   |   ", " [o_o] ", " /|_|  ", "  / \\  "]
ROBOT_CHEER = [" .-^-. ", "/_/_\\_\\", "   |   ", " [^o^] ", " \\|_|/ ", "  / \\  "]


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


class Sounds:
    def __init__(self, enabled):
        self.eng = None
        if enabled and bb:
            self.eng = bb.Engine(sound=True)
            self.eng.start()

    def play(self, make):
        if self.eng:
            self.eng.play(make())

    def pop(self, ch):
        idx = (LETTERS + DIGITS).index(ch)
        note = 72 + PENTATONIC[idx % 5] + 12 * ((idx // 5) % 2)
        self.play(lambda: bb.bell(bb.mtof(note)))
        self.play(lambda: bb.Voice([bb.hiss(bb.HISS, 1.0, .5)], .12, .001, .08))

    def golden(self):
        for i, n in enumerate((0, 4, 7, 12, 16)):
            self.play(lambda n=n, i=i: bb.bell(bb.mtof(72 + n), delay=i * 0.06))

    def wrong(self):
        self.play(lambda: bb.Voice([bb.tone(bb.TRIANGLE, 196, .6)], .25, .005, .18))

    def splash(self):
        self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .35, .5)], .12, .01, .25))

    def level_up(self):
        for i, n in enumerate((0, 2, 4, 7, 9, 12, 16, 19)):
            self.play(lambda n=n, i=i: bb.bell(bb.mtof(72 + n), delay=i * 0.07))
        self.play(lambda: bb.drum(0))

    def stop(self):
        if self.eng:
            self.eng.stop()


class Drop:
    def __init__(self, ch, x, speed, golden):
        self.ch, self.x, self.y = ch, x, 1.0     # starts in the clouds
        self.vy = speed
        self.golden = golden
        self.color = random.choice(RAINBOW)
        self.landed_at = None
        self.bounce_v = None      # speed of the little bounce after landing


class App:
    def __init__(self, scr, sounds):
        self.scr = scr
        self.snd = sounds
        utf = locale.getpreferredencoding().lower().replace("-", "") == "utf8"
        self.block = "█" if utf else "#"
        self.floor_ch = "▀" if utf else "="
        self.drops = []
        self.parts = []
        self.rain = []
        self.popped = 0           # points (golden letters are worth 5)
        self.letters = 0          # letters popped; this sets the level
        self.level = 1
        self.streak = 0
        self.next_spawn = 0.0
        self.banner, self.banner_until = "", 0.0
        self.bubble, self.bubble_until = "", 0.0
        self.robot_cheer_until = 0.0
        self.recent = []
        self.passed = None        # the level just finished, while the "level passed" box is showing
        self.passed_at = 0.0
        self.level_start = 0      # letters popped when this level began
        self.level_best = 0       # best streak in this level

    def attr(self, pair, bold=True):
        return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)

    # ------------------------------------------------------------ rules
    def max_drops(self):
        return min(4, 1 + self.level // 2)

    def speed(self):
        return min(5.0, 2.2 + 0.3 * (self.level - 1))

    def alphabet(self):
        return LETTERS + (DIGITS if self.level >= 3 else "")

    def glyph_size(self):
        h, w = self.scr.getmaxyx()
        if w >= 90 and h >= 28:
            return 2, 5          # each letter pixel is 2 columns wide, 5 rows tall
        if w >= 50 and h >= 20:
            return 1, 5
        return 0, 1              # tiny screens: plain characters

    def glyph_width(self):
        sx, _ = self.glyph_size()
        return 5 * sx if sx else 1

    def spawn(self, now):
        h, w = self.scr.getmaxyx()
        gw = self.glyph_width()
        taken = {d.ch for d in self.drops}
        choices = [c for c in self.alphabet() if c not in taken and c not in self.recent[-4:]]
        if not choices:
            return
        ch = random.choice(choices)
        for _ in range(20):      # find a spot that doesn't overlap another letter
            x = random.randint(2, max(2, w - gw - 12))
            if all(abs(x - d.x) > gw + 3 for d in self.drops):
                break
        else:
            return
        self.recent.append(ch)
        golden = self.popped > 3 and random.random() < 0.12
        self.drops.append(Drop(ch, x, self.speed() * random.uniform(0.85, 1.15), golden))

    def handle_key(self, key, now):
        if key == "\x1b":
            return False
        if self.passed is not None:
            if now - self.passed_at < 1.5:       # so mashing can't skip the box unread
                return True
            if key in ("\n", "\r", curses.KEY_ENTER):
                self.next_level(now, self.passed + 1)
            elif isinstance(key, str) and key.lower() == "r":
                self.next_level(now, self.passed)
            return True
        if not isinstance(key, str) or not key.strip():
            return True
        ch = key.upper()
        targets = [d for d in self.drops if d.ch == ch]
        if targets:
            d = max(targets, key=lambda d: d.y)      # the lowest one first
            self.pop(d, now)
        else:
            self.streak = 0
            shown = ch if ch.isprintable() and len(ch) == 1 else "?"
            self.bubble, self.bubble_until = "that's %s!" % shown, now + 1.2
            self.snd.wrong()
        return True

    def pop(self, d, now):
        self.drops.remove(d)
        gw = self.glyph_width()
        _, gh = self.glyph_size()
        cx, cy = d.x + gw / 2, d.y + gh / 2
        n = 45 if d.golden else 22
        for _ in range(n):
            color = random.choice(RAINBOW) if d.golden else random.choice([d.color, d.color, WHITE, YELLOW])
            self.parts.append([cx, cy, random.uniform(-26, 26), random.uniform(-14, 6),
                               now + random.uniform(.5, 1.2), random.choice("*+o.x"), color])
        self.popped += 5 if d.golden else 1
        self.letters += 1
        self.streak += 1
        self.level_best = max(self.level_best, self.streak)
        if d.golden:
            self.snd.golden()
            self.say("GOLDEN %s! +5" % d.ch, now, 1.6)
        else:
            self.snd.pop(d.ch)
        if self.streak in STREAK_WORDS:
            self.say(STREAK_WORDS[self.streak], now, 2.0)
        if random.random() < 0.35:
            self.robot_cheer_until = now + 0.8
            self.bubble, self.bubble_until = random.choice(CHEERS), now + 0.8
        if self.letters - self.level_start >= POPS_PER_LEVEL:
            self.finish_level(now)

    def finish_level(self, now):
        """The rain stops and a box asks: move on, or play this level again?"""
        self.passed, self.passed_at = self.level, now
        self.drops = []
        self.snd.level_up()
        self.robot_cheer_until = now + 3
        h, w = self.scr.getmaxyx()
        for _ in range(80):
            self.parts.append([random.uniform(0, w), random.uniform(-4, 2), random.uniform(-3, 3), random.uniform(3, 10),
                               now + random.uniform(1.5, 3), random.choice("*+o~^"), random.choice(RAINBOW)])

    def next_level(self, now, level):
        again = level == self.passed
        self.level = level
        self.passed = None
        self.level_start = self.letters
        self.level_best = 0
        self.streak = 0
        self.next_spawn = now + 1.0
        if again:
            self.say("LEVEL %d AGAIN! Here we go!" % level, now, 2.4)
        else:
            self.say("LEVEL %d!%s" % (level, " NUMBERS TOO!" if level == 3 else ""), now, 2.4)
        self.snd.golden()

    def say(self, text, now, secs):
        self.banner, self.banner_until = text, now + secs

    # ------------------------------------------------------------ update
    def update(self, now, dt):
        h, w = self.scr.getmaxyx()
        _, gh = self.glyph_size()
        floor_y = h - 3
        rest_y = floor_y - gh
        falling = [d for d in self.drops if d.landed_at is None]
        if self.passed is None and len(self.drops) < self.max_drops() + 2 and len(falling) < self.max_drops() and now > self.next_spawn:
            self.spawn(now)
            self.next_spawn = now + random.uniform(1.2, 2.5) / (1 + 0.15 * self.level)
        for d in list(self.drops):
            if d.landed_at is None:
                d.y += d.vy * dt
                if d.y >= rest_y:
                    d.y, d.landed_at, d.bounce_v = rest_y, now, -4.0   # a little bounce into the puddle
                    self.snd.splash()
                    self.streak = 0
            elif d.bounce_v is not None:
                d.bounce_v += 12 * dt
                d.y += d.bounce_v * dt
                if d.y >= rest_y:
                    d.y, d.bounce_v = rest_y, None
            elif now - d.landed_at > FLOOR_WAIT:
                self.drops.remove(d)
        # background rain
        if len(self.rain) < w // 4:
            self.rain.append([random.uniform(0, w), random.uniform(2, floor_y), random.uniform(10, 18)])
        for r in self.rain:
            r[1] += r[2] * dt
            if r[1] >= floor_y:
                r[0], r[1] = random.uniform(0, w), 2.0
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 14 * dt
        self.parts = [p for p in self.parts if p[4] > now]

    # ------------------------------------------------------------ drawing
    def draw(self, now):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        floor_y = h - 3

        for x, y, _ in self.rain:
            put(scr, int(y), int(x), "|", self.attr(BLUE, False))
        # clouds
        for cx in range(2, w - 10, 16):
            off = int(now * 0.8 + cx) % 3
            put(scr, 1, cx + off, " .--.  .-. ", self.attr(WHITE, False))
            put(scr, 2, cx + off, "(    )(   )", self.attr(WHITE, False))

        for d in self.drops:
            self.draw_drop(d, now)
        for p in self.parts:
            put(scr, int(p[1]), int(p[0]), p[5], self.attr(p[6]))

        # puddle and the umbrella robot
        put(scr, floor_y, 0, self.floor_ch * w, self.attr(BLUE))
        robot = ROBOT_CHEER if now < self.robot_cheer_until else ROBOT
        rx = w - 10
        for i, line in enumerate(robot):
            put(scr, floor_y - len(robot) + i, rx, line, self.attr(WHITE if i == 3 else ORANGE))
        if now < self.bubble_until:
            b = " %s " % self.bubble
            put(scr, floor_y - len(robot) - 1, max(0, rx + 3 - len(b) // 2), b, self.attr(ORANGE) | curses.A_REVERSE)

        # header
        head = " ALPHABET RAIN "
        info = "  LEVEL %d (%d/%d)   points: %d   streak: %d " % (
            self.level, min(POPS_PER_LEVEL, self.letters - self.level_start), POPS_PER_LEVEL, self.popped, self.streak)
        put(scr, 0, 0, " " * w, self.attr(CYAN) | curses.A_REVERSE)
        put(scr, 0, 0, head, self.attr(WHITE) | curses.A_REVERSE)
        put(scr, 0, len(head), info, self.attr(CYAN) | curses.A_REVERSE)
        hint = "Type the letters you see!   Esc: quit"
        put(scr, h - 2, max(0, (w - len(hint)) // 2), hint, self.attr(WHITE, False) | curses.A_DIM)

        if now < self.banner_until:
            b = "  %s  " % self.banner
            color = RAINBOW[int(now * 6) % len(RAINBOW)]
            put(scr, h // 2 - 4, max(0, (w - len(b)) // 2), b, self.attr(color) | curses.A_REVERSE)
        if self.passed is not None:
            self.draw_passed(now, h, w)
        scr.refresh()

    def draw_passed(self, now, h, w):
        p = self.passed
        ready = now - self.passed_at >= 1.5
        lines = [("* LEVEL %d PASSED! *" % p, RAINBOW[int(now * 6) % len(RAINBOW)]), ("", WHITE),
                 ("You popped %d letters!   Best streak: %d" % (POPS_PER_LEVEL, self.level_best), WHITE), ("", WHITE)]
        if p + 1 == 3:
            lines += [("Next level: numbers join in!", MAGENTA), ("", WHITE)]
        if ready:
            lines += [("ENTER   move on to level %d" % (p + 1), GREEN), ("R       play level %d again" % p, CYAN)]
        else:
            lines += [("", WHITE), ("", WHITE)]
        bw = max(len(t) for t, _ in lines) + 8
        bh = len(lines) + 2
        bx, by = max(0, (w - bw) // 2), max(1, (h - bh) // 2 - 2)
        frame = self.attr(YELLOW)
        put(self.scr, by, bx, "+" + "=" * (bw - 2) + "+", frame)
        for i, (text, col) in enumerate(lines):
            put(self.scr, by + 1 + i, bx, "|" + " " * (bw - 2) + "|", frame)
            put(self.scr, by + 1 + i, bx + (bw - len(text)) // 2, text, self.attr(col))
        put(self.scr, by + bh - 1, bx, "+" + "=" * (bw - 2) + "+", frame)

    def draw_drop(self, d, now):
        sx, gh = self.glyph_size()
        waiting = d.landed_at is not None
        if d.golden:
            color = RAINBOW[int(now * 8) % len(RAINBOW)]
        else:
            color = d.color
        a = self.attr(color)
        if waiting and now - d.landed_at > FLOOR_WAIT - 2 and int(now * 4) % 2:
            a = self.attr(color, False) | curses.A_DIM          # blinks before it melts away
        y = int(d.y)
        if sx == 0:
            put(self.scr, y, d.x, d.ch, a | curses.A_REVERSE)
            return
        for r, row in enumerate(FONT[d.ch]):
            line = "".join((self.block * sx) if px == "#" else " " * sx for px in row)
            for c, cell in enumerate(line):
                if cell != " ":
                    put(self.scr, y + r, d.x + c, cell, a)


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
    app = App(scr, sounds)
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
                    key = -1              # Alt+key or an odd key sequence, not a lone Esc
                if not app.handle_key(key, time.time()):
                    return
            now = time.time()
            app.update(now, min(0.1, now - last))
            app.draw(now)
            last = now
            time.sleep(max(0, 1 / 30 - (time.time() - t0)))
    finally:
        sounds.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pop the falling letters by typing them. Esc quits.")
    p.add_argument("--mute", action="store_true", help="run without sound")
    p.add_argument("--reset", action="store_true", help="(nothing is saved, so there is nothing to reset)")
    args = p.parse_args()
    if args.reset:
        print("Every game of Alphabet Rain starts fresh, so there is nothing to reset!")
        raise SystemExit
    locale.setlocale(locale.LC_ALL, "")
    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue
    print("Great typing!")
