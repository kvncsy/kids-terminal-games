"""
Cutscenes for Quest: little ASCII movies with music, sparkles and fireworks
that play when a level starts and when it is won.

A scene is a list of beats: (seconds, paint(stage, t, now), start(stage, now)).
t goes from 0 to 1 during the beat. ENTER or SPACE skips to the next beat.
The start board of a level names its scenes:  opening: town   ending: crown
"""
import math
import random

import curses

RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]
W, H = 80, 24

try:
    from hacker_keys import FONT
except Exception:
    FONT = {}


# ================================================================ drawing on the stage
class Stage:
    """An 80 x 24 picture: text, ASCII art, big letters, rainbows and sparkles."""

    def __init__(self, scr, ox, oy, fancy, sounds):
        self.scr, self.ox, self.oy, self.fancy, self.snd = scr, ox, oy, fancy, sounds
        self.parts = []
        self.next_firework = 0.0

    def attr(self, col, bold=True):
        return curses.color_pair(col) | (curses.A_BOLD if bold else 0)

    def put(self, y, x, s, attr):
        y, x = int(y), int(x)
        if not 0 <= y < H or not s:
            return
        if x < 0:
            s, x = s[-x:], 0
        s = s[: W - x]
        if not s:
            return
        h, w = self.scr.getmaxyx()
        if self.oy + y >= h or self.ox + x >= w:
            return
        if self.oy + y == h - 1 and self.ox + x + len(s) >= w:
            s = s[: w - self.ox - x - 1]
        try:
            self.scr.addstr(self.oy + y, self.ox + x, s, attr)
        except curses.error:
            pass

    def text(self, y, s, col=WHITE, bold=True, x=None):
        self.put(y, (W - len(s)) // 2 if x is None else x, s, self.attr(col, bold))

    def typed(self, y, s, t, col=WHITE):
        """Text that types itself out as t goes from 0 to 1."""
        self.text(y, s[: int(len(s) * min(1.0, t))].ljust(len(s)), col)

    def art(self, y, x, lines, colors=WHITE):
        """ASCII art. colors is one color, or {character: color} with a "default".
        Gaps inside a line are painted black so a rainbow behind doesn't show through."""
        for i, line in enumerate(lines):
            first, last = len(line) - len(line.lstrip()), len(line.rstrip())
            for j, ch in enumerate(line):
                if ch == " ":
                    if first < j < last:
                        self.put(y + i, x + j, " ", self.attr(WHITE))
                    continue
                col = colors if isinstance(colors, int) else colors.get(ch, colors.get("default", WHITE))
                self.put(y + i, x + j, ch, self.attr(col))

    def big(self, word, y, colors=None, x=None, now=0.0):
        """Big block letters, each letter its own rainbow color unless colors(i) says otherwise."""
        block = "█" if self.fancy else "#"
        width = len(word) * 6 - 1
        x = (W - width) // 2 if x is None else x
        for i, ch in enumerate(word):
            col = colors(i) if colors else RAINBOW[(i + int(now * 6)) % len(RAINBOW)]
            for r, row in enumerate(FONT.get(ch, FONT.get(" ", [" " * 5] * 5))):
                for c, px in enumerate(row):
                    if px == "#":
                        self.put(y + r, x + i * 6 + c, block, self.attr(col))

    def rainbow(self, cx, base, rx, ry, grow=1.0, thick=1):
        """A rainbow arc of seven colored bands. grow (0 to 1) draws it from the left."""
        block = "█" if self.fancy else "#"
        for band, col in enumerate(RAINBOW):
            r_x, r_y = rx - band * 2, ry - band
            if r_x <= 0 or r_y <= 0:
                continue
            for x in range(int(cx - r_x), int(cx - r_x + 2 * r_x * grow) + 1):
                d = (x - cx) / r_x
                if abs(d) > 1:
                    continue
                y = base - r_y * math.sqrt(1 - d * d)
                for k in range(thick):
                    self.put(y + k, x, block, self.attr(col))

    def stars(self, now, n=40, seed=7):
        rng = random.Random(seed)
        for i in range(n):
            x, y = rng.randrange(W), rng.randrange(H - 2)
            if int(now * 2 + i) % 5:
                self.put(y, x, "." if i % 3 else "*", self.attr(WHITE, i % 2 == 0))

    def burst(self, x, y, n=30, colors=None, now=0.0, chars="*+o.x", speed=18):
        colors = colors or RAINBOW
        for _ in range(n):
            a = random.uniform(0, 6.28)
            v = random.uniform(speed * 0.3, speed)
            self.parts.append([x, y, math.cos(a) * v * 2, math.sin(a) * v, now + random.uniform(.6, 1.4),
                               random.choice(chars), random.choice(colors)])

    def fountain(self, x, y, n=6, now=0.0, chars="$", colors=(YELLOW, ORANGE)):
        for _ in range(n):
            self.parts.append([x, y, random.uniform(-14, 14), random.uniform(-16, -9), now + 2.0,
                               random.choice(chars), random.choice(colors)])

    def fireworks(self, now, every=0.45):
        if now >= self.next_firework:
            self.next_firework = now + every
            self.burst(random.uniform(10, 70), random.uniform(2, 10), 35, now=now)
            self.snd.boom()

    def draw_parts(self, now, dt):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 14 * dt
            self.put(p[1], p[0], p[5], self.attr(p[6]))
        self.parts = [p for p in self.parts if p[4] > now and p[1] < H][-600:]


# ================================================================ the cast
HERO = [" ___ ", "(^_^)", "/|_|\\", " / \\ "]
HERO_WALK = [" ___ ", "(^_^)", "\\|_|/", " | | "]
CROWN = [" * * * ", "/\\/\\/\\/", "|  ()  |", "|______|"]
CROWN_SMALL = ["*.*.*", "\\/\\/\\/"]
KING = ["   \\|/   ", "  [^_^]  ", " /|___|\\ ", "  _| |_  "]
THRONE = ["  _____  ", " |     | ", " |     | ", "_|_____|_"]
ROBOT = [["  _|_ ", " [o_o]", " /|_|\\", "  / \\ "], ["  _|_ ", " [^_^]", " \\|_|/", "  | | "]]
HOUSE = ["   /\\   ", "  /  \\  ", " /____\\ ", " | [] | ", " |____| "]
SUN = ["   \\ | /   ", " -- (  ) --", "   / | \\   "]
GHOST = [["  .-.  ", " (o o) ", " | O | ", " '~~~' "], ["  .-.  ", " (^ ^) ", " | v | ", " '~~~' "]]
CHEST_SHUT = ["  ________  ", " /________\\ ", " |   ()   | ", " |________| "]
CHEST_OPEN = [" $ $ $ $ $  ", " \\$$$$$$$$/ ", " |   ()   | ", " |________| "]
SHIP = ["       |\\    ", "       | \\   ", "   .-. |__\\  ", "  (o o)|     ", "\\===========/"]
WAVES = ["~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~"]
LEPRECHAUN = [["  _===_ ", "  (^o^) ", " /|[]|\\ ", "  d  b  "], ["  _===_ ", "  (^o^) ", " \\|[]|/ ", "   db   "]]
POT = ["  $ $ $ $  ", " ($$$$$$$) ", "  \\_____/  "]
FAIRY = [[" \\ * / ", "  (o)  ", " / | \\ "], [" / * \\ ", "  (o)  ", " \\ | / "]]
MOON = ["  _.._ ", " .' .-'", "/  /   ", "|  |   ", "\\  '.__", " '._  '", "    `''"]

HERO_COL = {"^": WHITE, "_": WHITE, "(": WHITE, ")": WHITE, "default": YELLOW}
ROBOT_COL = {"o": WHITE, "^": WHITE, "[": WHITE, "]": WHITE, "_": WHITE, "default": ORANGE}
GHOST_COL = {"o": CYAN, "O": CYAN, "^": CYAN, "v": CYAN, "default": WHITE}
LEP_COL = {"=": GREEN, "_": GREEN, "^": WHITE, "o": WHITE, "(": WHITE, ")": WHITE, "[": YELLOW, "]": YELLOW,
           "default": GREEN}


def bob(now, speed=4):
    return int(now * speed) % 2


# ================================================================ the scenes
def opening_town(stage):
    """Level 1: the sun comes up over Robot Town and the robots wave."""
    def sunrise(s, t, now):
        sky = YELLOW if t > .5 else ORANGE
        s.art(int(14 - 8 * t), 66, SUN, sky)                 # the sun comes up behind the town
        if t > .45:
            s.big("ROBOT", 0, now=now, x=4)
            s.big("TOWN", 0, now=now + 1, x=36)
        for i in range(6):
            s.art(13, 2 + i * 13, HOUSE, {"[": YELLOW, "]": YELLOW, "default": RED if i % 2 else MAGENTA})
            if t > .3 + i * .08:                            # robots pop out of their houses and wave
                s.art(8, 4 + i * 13, ROBOT[bob(now + i)], ROBOT_COL)
        s.text(18, "=" * 78, GREEN)
        if t > .45:
            s.typed(20, "Good morning, Robot Town!", (t - .45) * 3, YELLOW)

    def quest(s, t, now):
        s.big("A QUEST!", 1, now=now)
        s.art(8, 36, CROWN, YELLOW)
        if bob(now, 3):
            s.burst(40, 9, 3, [YELLOW, WHITE], now)
        s.art(14, 38, HERO if bob(now, 2) else HERO_WALK, HERO_COL)
        s.typed(20, "Find the GOLDEN CROWN!", t * 3, YELLOW)

    return [(4.5, sunrise, lambda s, now: s.snd.melody("morning")),
            (4.0, quest, lambda s, now: s.snd.melody("quest"))]


def ending_crown(stage):
    """Level 1 won: the crowning."""
    def walk_in(s, t, now):
        s.art(3, 35, THRONE, MAGENTA)
        s.art(1, 35, KING, ROBOT_COL)
        for i in range(4):
            s.art(10, 2 + i * 9, ROBOT[bob(now + i)], ROBOT_COL)
            s.art(10, 45 + i * 9, ROBOT[bob(now + i + 1)], ROBOT_COL)
        s.text(15, "-" * 78, RED, False)
        x = 2 + t * 35
        s.art(16, int(x), HERO_WALK if int(now * 6) % 2 else HERO, HERO_COL)
        s.typed(22, "The hero walks into the castle...", t * 2, WHITE)

    def crowning(s, t, now):
        s.art(3, 35, THRONE, MAGENTA)
        s.art(1, 35, KING, ROBOT_COL)
        s.art(16, 37, HERO, HERO_COL)
        y = 5 + t * 8.5                                 # the crown floats down onto the hero
        s.art(int(y), 36, CROWN, YELLOW)
        if bob(now, 5):
            s.burst(40, y + 2, 4, [YELLOW, WHITE], now, "*+.")
        if t > .95:
            s.text(21, "THE GOLDEN CROWN!", YELLOW)

    def hero(s, t, now):
        s.rainbow(40, 23, 38, 14, grow=min(1, t * 2), thick=2)
        s.fireworks(now)
        s.big("HERO!", 2, now=now)
        s.art(13, 37, CROWN_SMALL, YELLOW)
        s.art(15, 37, HERO if bob(now, 4) else HERO_WALK, HERO_COL)
        for i in range(3):
            s.art(16, 8 + i * 8, ROBOT[bob(now * 2 + i)], ROBOT_COL)
            s.art(16, 52 + i * 8, ROBOT[bob(now * 2 + i + 1)], ROBOT_COL)

    def saved(s, t, now):
        s.stars(now)
        s.fireworks(now, .8)
        s.text(6, "You saved Robot Town!", YELLOW)
        s.art(9, 37, CROWN_SMALL, YELLOW)
        s.art(11, 37, HERO, HERO_COL)
        if t > .4:
            s.text(17, "But far away, across the sea...", CYAN, False)
        if t > .7:
            s.art(18, 34, GHOST[bob(now, 2)], GHOST_COL)
            s.text(22, "NEXT: SPOOKY ISLANDS", MAGENTA)

    return [(4.0, walk_in, lambda s, now: s.snd.melody("march")),
            (3.5, crowning, lambda s, now: s.snd.melody("crown")),
            (5.0, hero, lambda s, now: s.snd.melody("fanfare")),
            (5.0, saved, lambda s, now: s.snd.melody("quest"))]


def opening_ship(stage):
    """Level 2: a spooky ship sails to the islands."""
    def sail(s, t, now):
        s.stars(now)
        s.art(1, 66, MOON, YELLOW)
        x = -14 + t * 60
        s.art(13 + bob(now, 2), int(x), SHIP, {"o": CYAN, "default": WHITE})
        for row in range(3):
            off = int(now * 4 + row * 3) % 4
            s.put(18 + row, 0, (WAVES[0][off:] + WAVES[0])[:W], s.attr(BLUE, row == 0))
        if t > .8:
            s.text(5, "BOO!", WHITE)

    def islands(s, t, now):
        s.big("SPOOKY", 1, colors=lambda i: MAGENTA if bob(now + i, 3) else WHITE)
        s.big("ISLANDS", 7, colors=lambda i: CYAN if bob(now + i, 3) else WHITE)
        for i, x in enumerate((8, 36, 64)):
            s.art(13 + bob(now + i, 2), x, GHOST[bob(now + i, 1)], GHOST_COL)
        s.art(17, 34, CHEST_SHUT, {"(": YELLOW, ")": YELLOW, "default": ORANGE})
        s.typed(22, "Find the GHOST'S TREASURE!", t * 3, YELLOW)

    return [(5.0, sail, lambda s, now: s.snd.melody("spooky")),
            (4.0, islands, lambda s, now: s.snd.melody("boo"))]


def ending_ghosts(stage):
    """Level 2 won: the ghosts throw a party."""
    def boo(s, t, now):
        for i in range(3):
            if t > i * .25:
                s.art(6 + bob(now + i, 2), 14 + i * 20, GHOST[0], GHOST_COL)
        s.art(16, 37, HERO, HERO_COL)
        if t > .75:
            s.big("BOO!", 1, colors=lambda i: WHITE)

    def lights(s, t, now):
        if t < .25 and bob(now, 10):
            for y in range(H - 1):
                s.put(y, 0, " " * W, s.attr(YELLOW) | curses.A_REVERSE)
            return
        for i in range(3):
            s.art(6 + bob(now * 2 + i, 2), 14 + i * 20, GHOST[1], GHOST_COL)
        s.art(16, 37, HERO, HERO_COL)
        s.big("HOORAY!", 0, now=now)
        s.typed(21, "They're NICE ghosts! It's a party!", (t - .25) * 2, YELLOW)

    def treasure(s, t, now):
        chest = CHEST_OPEN if t > .2 else CHEST_SHUT
        s.art(12, 34, chest, {"$": YELLOW, "(": YELLOW, ")": YELLOW, "default": ORANGE})
        if t > .2:
            s.fountain(40, 12, 3, now)
        s.art(16, 18, HERO if bob(now, 3) else HERO_WALK, HERO_COL)
        for i in range(2):
            s.art(5 + bob(now + i, 2), 12 + i * 46, GHOST[1], GHOST_COL)
        s.text(2, "THE GHOST'S TREASURE!", YELLOW)

    def party(s, t, now):
        s.rainbow(40, 23, 38, 14, grow=min(1, t * 1.5), thick=2)
        s.fireworks(now, .6)
        for i in range(4):
            s.art(4 + bob(now * 3 + i, 2) * 2, 4 + i * 20, GHOST[bob(now * 2 + i, 1)], GHOST_COL)
        s.art(15, 37, HERO if bob(now, 4) else HERO_WALK, HERO_COL)
        if t > .55:
            s.art(17, 60, LEPRECHAUN[bob(now, 3)], LEP_COL)
            s.text(22, "NEXT: RAINBOW KINGDOM", GREEN)

    return [(3.5, boo, lambda s, now: s.snd.melody("boo")),
            (3.5, lights, lambda s, now: s.snd.melody("fanfare")),
            (4.0, treasure, lambda s, now: s.snd.melody("gold")),
            (5.0, party, lambda s, now: s.snd.melody("party"))]


def opening_rainbow(stage):
    """Level 3: a rainbow appears and a leprechaun hops over it."""
    def appear(s, t, now):
        s.rainbow(40, 21, 38, 15, grow=min(1, t * 1.6), thick=2)
        for i in range(6):
            s.art(16, 2 + i * 13, HOUSE, {"[": YELLOW, "]": YELLOW, "default": RED if i % 2 else MAGENTA})
        if t > .55:
            a = (t - .55) / .45 * math.pi
            s.art(int(19 - 15 * math.sin(a)) - 4, int(4 + (t - .55) / .45 * 66), LEPRECHAUN[bob(now, 4)], LEP_COL)

    def kingdom(s, t, now):
        s.big("RAINBOW", 1, now=now)
        s.big("KINGDOM", 7, now=now + 1)
        s.art(14, 34, POT, {"$": YELLOW, "default": ORANGE})
        if bob(now, 3):
            s.fountain(39, 14, 2, now)
        s.art(14, 12, FAIRY[bob(now, 3)], {"*": YELLOW, "default": MAGENTA})
        s.art(14, 58, LEPRECHAUN[bob(now, 3)], LEP_COL)
        s.typed(21, "Find the POT OF GOLD at the end of the rainbow!", t * 2.5, YELLOW)

    return [(5.0, appear, lambda s, now: s.snd.melody("rainbow")),
            (4.5, kingdom, lambda s, now: s.snd.melody("quest"))]


def ending_rainbow(stage):
    """Level 3 won: the big finale."""
    def gold(s, t, now):
        s.rainbow(40, 21, 38, 15, thick=2)
        s.art(16, 60, POT, {"$": YELLOW, "default": ORANGE})
        s.fountain(65, 16, 3, now)
        s.art(16, 44, LEPRECHAUN[bob(now, 4)], LEP_COL)
        s.art(16, 12, HERO if bob(now, 3) else HERO_WALK, HERO_COL)
        s.text(2, "THE POT OF GOLD!", YELLOW)

    def parade(s, t, now):
        s.rainbow(40, 23, 38, 16, thick=1)
        cast = [(HERO, HERO_WALK, HERO_COL), (ROBOT[0], ROBOT[1], ROBOT_COL), (GHOST[0], GHOST[1], GHOST_COL),
                (LEPRECHAUN[0], LEPRECHAUN[1], LEP_COL), (ROBOT[1], ROBOT[0], ROBOT_COL),
                (FAIRY[0] + [""], FAIRY[1] + [""], {"*": YELLOW, "default": MAGENTA}), (GHOST[1], GHOST[0], GHOST_COL)]
        for i, (a, b, col) in enumerate(cast):
            x = -10 + (t * 110) - i * 11
            s.art(15 - (bob(now * 2 + i, 2)), int(x), a if bob(now + i, 3) else b, col)
        s.text(3, "Everybody is here to say THANK YOU!", WHITE)

    def the_end(s, t, now):
        s.fireworks(now, .35)
        s.big("THE END", 3, now=now)
        s.art(11, 37, CROWN_SMALL, YELLOW)
        s.art(13, 37, HERO if bob(now, 4) else HERO_WALK, HERO_COL)
        s.text(19, "YOU ARE A SUPER HERO!", YELLOW)

    def or_is_it(s, t, now):
        s.stars(now, 60)
        s.text(10, "...or is it?", CYAN)
        if t > .4:
            s.text(13, "Keep exploring. Find every gem. Catch every leprechaun!", WHITE, False)

    return [(5.0, gold, lambda s, now: s.snd.melody("gold")),
            (6.0, parade, lambda s, now: s.snd.melody("march")),
            (5.0, the_end, lambda s, now: s.snd.melody("fanfare")),
            (3.5, or_is_it, lambda s, now: s.snd.melody("quest"))]


SCENES = {"town": opening_town, "crown": ending_crown, "ship": opening_ship, "ghosts": ending_ghosts,
          "rainbow": opening_rainbow, "rainbow_end": ending_rainbow}


# ================================================================ playing a scene
class Cutscene:
    def __init__(self, name, scr, ox, oy, fancy, sounds, now):
        self.stage = Stage(scr, ox, oy, fancy, sounds)
        self.beats = SCENES[name](self.stage)
        self.i = -1
        self.done = False
        self.last = now
        self.next_beat(now)

    def next_beat(self, now):
        self.i += 1
        if self.i >= len(self.beats):
            self.done = True
            return
        self.beat_at = now
        self.stage.parts = [p for p in self.stage.parts if p[6] != -1]
        start = self.beats[self.i][2]
        if start:
            start(self.stage, now)

    def skip(self, now):
        """ENTER or SPACE: on to the next beat (not too fast, so a mashed key doesn't skip everything)."""
        if now - self.beat_at > 0.8:
            self.next_beat(now)

    def draw(self, now, ox, oy):
        if self.done:
            return
        self.stage.ox, self.stage.oy = ox, oy
        seconds, paint, _ = self.beats[self.i]
        t = (now - self.beat_at) / seconds
        if t >= 1:
            self.next_beat(now)
            if self.done:
                return
            seconds, paint, _ = self.beats[self.i]
            t = 0.0
        paint(self.stage, t, now)
        self.stage.draw_parts(now, min(0.1, now - self.last))
        self.last = now
        self.stage.text(H - 1, "ENTER: skip", WHITE, False)
