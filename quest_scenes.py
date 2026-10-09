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
KING_SLEEP = ["   \\|/   ", "  [-_-]  ", " /|___|\\ ", "  _| |_  "]
KING_BARE = ["         ", "  [O_O]  ", " /|___|\\ ", "  _| |_  "]
KING_HAPPY = ["   \\|/   ", "  [^o^]  ", " \\|___|/ ", "  _| |_  "]
LEP_KING = [["   *.*.*  ", "  _=====_ ", "   (^o^)  ", "  /|[]|\\  ", "   d  b   "],
            ["   *.*.*  ", "  _=====_ ", "   (^o^)  ", "  \\|[]|/  ", "    db    "]]
QUEEN = [["     *.*.*     ", "    ( ^_^ )    ", " <\\  /|~|\\  /> ", "  <\\/ ~~~ \\/>  ", "     /~~~~\\    ", "    /______\\   "],
         ["     *.*.*     ", "    ( ^_^ )    ", "  </ /|~|\\ \\>  ", " </  / ~~~ \\  \\>", "     /~~~~\\    ", "    /______\\   "]]
TREE = ["  .@@@.  ", " @@@@@@@ ", "@@@@@@@@@", " '@@@@@' ", "   | |   ", "   |_|   "]
CROW = ["\\v/", "-v-"]
JEN = ["  ,~~~~~,  ", " ( (^_^) ) ", " ) /|_|\\ ( ", "   / | \\   "]
JEN_WRITE = ["  ,~~~~~,  ", " ( (^_^) ) ", " ) /|_|\\_( ", "   / |  ~\\ "]
DESK = ["=" * 42, " ||" + " " * 36 + "|| ", " ||" + " " * 36 + "|| "]
BOOK = [" ________ ________ ", "|~~~~~~~ |~~~~~   |", "|~~~~~ ~ |~~~~~~~ |", "|~~~~~~  |~~~     |", "|________|________|"]
WITCH = [["    /\\    ", "   /  \\   ", " _/____\\_ ", "  (o.o)   ", "  /|##|\\  ", "   /__\\   "],
         ["    /\\    ", "   /  \\   ", " _/____\\_ ", "  (^o^)   ", "  \\|##|/  ", "   /__\\   "]]
WITCH_BROOM = [["    /\\       ", "  _/__\\_     ", "   (^.^)     ", "---/##\\---}}}"],
               ["    /\\       ", "  _/__\\_     ", "   (^o^)     ", "---/##\\---{{{"]]
CAULDRON = ["  o  O   o  ", " .~~~~~~~~. ", "(__________)", "  ||    ||  "]
WITCH_HOUSE = ["      /\\      ", "     /  \\     ", "    / /\\ \\    ", "   /______\\   ", "   | [] []|   ",
               "   |  __  |   ", "   |_|__|_|   "]
RAT = ["<:3)~", "<:3)-"]
WINDOW = ["+-------+", "|   |   |", "|---+---|", "|   |   |", "+-------+"]

HERO_COL = {"^": WHITE, "_": WHITE, "(": WHITE, ")": WHITE, "default": YELLOW}
ROBOT_COL = {"o": WHITE, "^": WHITE, "[": WHITE, "]": WHITE, "_": WHITE, "default": ORANGE}
GHOST_COL = {"o": CYAN, "O": CYAN, "^": CYAN, "v": CYAN, "default": WHITE}
QUEEN_COL = {"*": YELLOW, ".": YELLOW, "<": CYAN, ">": CYAN, "^": WHITE, "_": WHITE, "(": WHITE, ")": WHITE,
             "default": MAGENTA}
TREE_COL = {"|": ORANGE, "_": ORANGE, "default": GREEN}
JEN_COL = {"~": ORANGE, ",": ORANGE, "(": ORANGE, ")": ORANGE, "^": WHITE, "_": WHITE, "default": MAGENTA}
BOOK_COL = {"~": BLUE, "default": WHITE}
WITCH_COL = {"/": MAGENTA, "\\": MAGENTA, "_": MAGENTA, "o": GREEN, ".": GREEN, "^": GREEN, "(": GREEN, ")": GREEN,
             "#": MAGENTA, "-": ORANGE, "}": YELLOW, "{": YELLOW, "default": MAGENTA}
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
            s.text(13, "Far away, the witches are very upset...", WHITE, False)
        if t > .7:
            s.art(15, 35, WITCH[bob(now, 3)], WITCH_COL)
            s.text(22, "NEXT: THE WITCHES' CROWN", MAGENTA)

    return [(5.0, gold, lambda s, now: s.snd.melody("gold")),
            (6.0, parade, lambda s, now: s.snd.melody("march")),
            (5.0, the_end, lambda s, now: s.snd.melody("fanfare")),
            (3.5, or_is_it, lambda s, now: s.snd.melody("quest"))]


def crows(s, now, n=7, y0=2, seed=3, speed=9):
    """A flock of crows flapping across the sky."""
    rng = random.Random(seed)
    for i in range(n):
        x = (rng.uniform(0, 80) + now * speed * rng.uniform(.8, 1.2)) % 90 - 5
        y = y0 + rng.randrange(5) + bob(now + i, 3)
        s.put(y, x, CROW[bob(now * 2 + i, 3)], s.attr(WHITE, False))


def opening_thief(stage):
    """Level 4: a leprechaun sneaks off with the Robot King's crown, into the Whispering Forest."""
    def night(s, t, now):
        s.stars(now, 50)
        s.art(1, 68, MOON, YELLOW)
        s.art(9, 35, THRONE, MAGENTA)
        s.art(7, 35, KING_SLEEP, ROBOT_COL)
        for i in range(3):                              # z z Z float up
            zt = (now * .6 + i / 3.0) % 1
            s.put(6 - zt * 5, 44 + i * 2 + zt * 4, "zZ"[i % 2], s.attr(CYAN))
        s.text(15, "-" * 78, BLUE, False)
        s.typed(18, "Night in Robot Town. The Robot King is fast asleep...", t * 2, CYAN)

    def sneak(s, t, now):
        s.stars(now, 50)
        s.art(9, 35, THRONE, MAGENTA)
        grabbed = t > .45
        s.art(7, 35, KING_BARE if grabbed else KING_SLEEP, ROBOT_COL)
        if t < .45:
            x = -8 + t / .45 * 37                        # tiptoe in...
        else:
            x = 29 + (t - .45) / .55 * 60                # ...and RUN!
            s.art(7 + bob(now, 6), int(x) + 2, CROWN_SMALL, YELLOW)
        s.art(9 + bob(now, 6 if grabbed else 2), int(x), LEPRECHAUN[bob(now, 8 if grabbed else 2)], LEP_COL)
        s.text(15, "-" * 78, BLUE, False)
        if grabbed:
            s.text(18, "Hee hee hee!", GREEN)
        else:
            s.text(18, "Tip... toe... tip... toe...", GREEN, False)

    def wake(s, t, now):
        s.art(9, 35, THRONE, MAGENTA)
        s.art(7 - bob(now, 8), 35, KING_BARE, ROBOT_COL)
        s.big("MY CROWN!", 0, colors=lambda i: RED if bob(now + i, 6) else YELLOW)
        for i in range(4):
            s.art(16, 4 + i * 20, ROBOT[0], ROBOT_COL)
        s.typed(21, "A leprechaun took the Golden Crown! Who can help?", t * 2, YELLOW)

    def forest(s, t, now):
        for i in range(8):
            s.art(10, -2 + i * 11, TREE, TREE_COL)
        s.big("FOREST", 0, colors=lambda i: GREEN if bob(now + i, 2) else CYAN)
        x = -4 + t * 42
        s.art(17, int(x), HERO_WALK if int(now * 6) % 2 else HERO, HERO_COL)
        if t > .4:                                      # the crows see the hero and WHOOSH
            crows(s, now, 9, 6 - int((t - .4) * 10), speed=20)
        else:
            for i in range(6):
                s.put(9, 8 + i * 11, CROW[0], s.attr(WHITE, False))
        s.typed(22, "Into the Whispering Forest! Bring GOLD for the Leprechaun King.", (t - .3) * 2, YELLOW)

    return [(4.5, night, lambda s, now: s.snd.melody("night")),
            (4.5, sneak, lambda s, now: s.snd.melody("sneak")),
            (3.5, wake, lambda s, now: s.snd.melody("boo")),
            (5.0, forest, lambda s, now: s.snd.melody("forest"))]


def ending_home(stage):
    """Level 4 won: Queen Maeve sends the crown home, and the hero goes home too... it's Jennifer!"""
    def queen(s, t, now):
        s.art(3, 32, QUEEN[bob(now, 3)], QUEEN_COL)
        s.art(16, 20, HERO, HERO_COL)
        for i, fx in enumerate((6, 58, 70)):
            s.art(4 + bob(now + i, 3), fx, FAIRY[bob(now + i, 4)], {"*": YELLOW, "default": MAGENTA})
        y = 15 - t * 6                                   # the crown floats up to the Queen
        s.art(int(y), int(20 + t * 17), CROWN_SMALL, YELLOW)
        if bob(now, 5):
            s.burst(39, y, 3, [MAGENTA, YELLOW, WHITE], now, "*+.")
        if t > .5:
            s.typed(20, "Thank you! Fairy magic... take this crown HOME!", (t - .5) * 3, MAGENTA)

    def fly(s, t, now):
        s.stars(now, 40)
        for i in range(8):
            s.art(16, -2 + i * 11, TREE, TREE_COL)
        x, y = -6 + t * 90, 9 - math.sin(t * math.pi) * 6
        s.art(int(y), int(x), CROWN_SMALL, YELLOW)
        s.burst(x, y + 1, 2, RAINBOW, now, "*+.", 6)
        crows(s, now, 6, 3, seed=9, speed=14)
        s.text(1, "WHOOSH! Over the forest, over the hills...", CYAN, False)

    def crowned(s, t, now):
        s.art(4, 35, THRONE, MAGENTA)
        on = t > .45
        s.art(2, 35, KING_HAPPY if on else KING_BARE, ROBOT_COL)
        if not on:
            s.art(int(-2 + t / .45 * 2.5), 37, CROWN_SMALL, YELLOW)
        else:
            s.fireworks(now, .5)
        for i in range(4):
            s.art(10, 2 + i * 9, ROBOT[bob(now * 2 + i) if on else 0], ROBOT_COL)
            s.art(10, 45 + i * 9, ROBOT[bob(now * 2 + i + 1) if on else 0], ROBOT_COL)
        if on:
            s.big("HOORAY!", 15, now=now)

    def walk_home(s, t, now):
        s.art(int(9 + t * 3), 64, SUN, ORANGE)           # the sun sets
        s.art(11, 60, HOUSE, {"[": YELLOW, "]": YELLOW, "default": RED})
        s.text(16, "~" * 78, GREEN, False)
        x = 4 + t * 52
        s.art(12, int(x), HERO_WALK if int(now * 5) % 2 else HERO, HERO_COL)
        s.typed(19, "The sun goes down. Time to go home...", t * 2, ORANGE)

    def jennifer(s, t, now):
        s.art(2, 60, WINDOW, BLUE)
        s.put(3, 62, "*", s.attr(WHITE))
        s.put(4, 66, "C", s.attr(YELLOW))
        s.art(9, 16, JEN_WRITE if bob(now, 3) else JEN, JEN_COL)
        s.art(12, 6, DESK, ORANGE)
        s.art(7, 29, BOOK, BOOK_COL)
        if t > .25:
            s.big("JENNIFER", 0, x=4, now=now)
            s.typed(17, "Hi! I'm JENNIFER. I'm 14 years old.", (t - .25) * 3, YELLOW)
        if t > .55:
            s.typed(19, "I was the hero all along!", (t - .55) * 4, MAGENTA)
        if t > .75:
            s.typed(21, "And I LOVE writing in my journal.", (t - .75) * 5, CYAN)

    def journal(s, t, now):
        page = ["Dear Journal,",
                "Today I chased a sneaky leprechaun",
                "through the Whispering Forest.",
                "Crows went WHOOSH! I found a lamp,",
                "a hedge maze, and a dark dark cave.",
                "I gave GOLD to the Leprechaun King,",
                "and the crown to Queen Maeve.",
                "Now the Robot King has his crown!",
                "What an adventure!   -- Jennifer"]
        for y in range(1, 22):
            s.put(y, 16, "|" + " " * 46 + "|", s.attr(WHITE))
        s.put(0, 16, "+" + "-" * 46 + "+", s.attr(WHITE))
        s.put(22, 16, "+" + "-" * 46 + "+", s.attr(WHITE))
        for y in range(3, 21, 2):
            s.put(y, 18, "-" * 44, s.attr(BLUE, False))
        shown = t * 1.25 * sum(len(l) + 4 for l in page)
        for i, line in enumerate(page):
            n = int(max(0, min(len(line), shown)))
            shown -= len(line) + 4
            last = i in (0, len(page) - 1)
            s.put(2 + i * 2, 20, line[:n], s.attr(MAGENTA if last else WHITE, last))   # writing sits on the lines
        if t > .9:
            s.put(20, 56, "<3", s.attr(RED))

    def the_end(s, t, now):
        s.fireworks(now, .35)
        s.big("THE END", 1, now=now)
        cast = [(JEN, JEN_COL, 4), (QUEEN[bob(now, 3)][:4], QUEEN_COL, 4), (KING_HAPPY, ROBOT_COL, 4),
                (LEP_KING[bob(now, 3)][1:], LEP_COL, 4), (FAIRY[bob(now, 4)], {"*": YELLOW, "default": MAGENTA}, 5)]
        x = 2
        for i, (a, col, _) in enumerate(cast):
            s.art(10 + bob(now * 2 + i, 2), x, a, col)
            if a is KING_HAPPY:
                s.art(8 + bob(now * 2 + i, 2), x + 2, CROWN_SMALL, YELLOW)     # the King wears his crown
            x += max(len(r) for r in a) + 4
        crows(s, now, 5, 16, seed=12, speed=12)
        s.text(21, "Thank you for playing, hero!", YELLOW)

    return [(5.0, queen, lambda s, now: s.snd.melody("crown")),
            (4.0, fly, lambda s, now: s.snd.melody("rainbow")),
            (5.0, crowned, lambda s, now: s.snd.melody("fanfare")),
            (5.0, walk_home, lambda s, now: s.snd.melody("home")),
            (7.0, jennifer, lambda s, now: s.snd.melody("journal")),
            (12.0, journal, lambda s, now: s.snd.melody("journal")),
            (6.0, the_end, lambda s, now: s.snd.melody("party"))]


def big_moon(s, cx, cy, r, col=YELLOW):
    """A great big full moon."""
    block = "#" if not s.fancy else "█"
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r * 2), int(cx + r * 2) + 1):
            if ((x - cx) / 2.0) ** 2 + (y - cy) ** 2 <= r * r:
                s.put(y, x, block, s.attr(col, False))


def opening_witches(stage):
    """Level 4: the witches have lost their crown! (Psst... it was the rats.)"""
    def cauldron(s, t, now):
        s.stars(now, 40)
        s.art(1, 66, MOON, YELLOW)
        s.art(10, 4, WITCH_HOUSE, {"[": YELLOW, "]": YELLOW, "default": MAGENTA})
        s.art(14, 34, CAULDRON, {"o": GREEN, "O": GREEN, "~": GREEN, "default": WHITE})
        if bob(now, 3):
            s.burst(40, 13, 2, [GREEN, MAGENTA], now, "o.", 6)
        for i, x in enumerate((22, 48)):
            s.art(12 + bob(now + i, 2), x, WITCH[bob(now * 2 + i, 2)], WITCH_COL)
        crows(s, now, 4, 2, seed=21, speed=6)
        s.typed(21, "Bubble bubble... the witches are making soup.", t * 2, GREEN)

    def stolen(s, t, now):
        s.big("OH NO!", 0, colors=lambda i: MAGENTA if bob(now + i, 6) else GREEN)
        for i, x in enumerate((14, 34, 54)):
            s.art(7 - bob(now * 3 + i, 6), x, WITCH[0], WITCH_COL)
        s.typed(15, "Our CROWN is gone! Somebody STOLE it!", t * 3, YELLOW)
        if t > .45:                                     # down at the bottom... who's that?
            x = 84 - (t - .45) / .55 * 100
            for i in range(3):
                s.put(19, x + i * 7, RAT[bob(now * 3 + i, 4)], s.attr(ORANGE))
            s.art(18, int(x + 21), CROWN_SMALL, YELLOW)
            s.text(22, "(psst... who are THOSE little guys?)", WHITE, False)

    def quest(s, t, now):
        s.big("WITCHES", 0, colors=lambda i: MAGENTA if (i + int(now * 3)) % 2 else GREEN)
        s.art(8, 37, HERO if bob(now, 2) else HERO_WALK, HERO_COL)
        s.art(7, 14, WITCH[1], WITCH_COL)
        s.art(7, 56, WITCH[1], WITCH_COL)
        s.typed(14, "Find the WITCHES' CROWN!", t * 3, YELLOW)
        s.typed(17, "Get the lamp. Go down, down, down...", (t - .3) * 3, CYAN)
        s.typed(19, "Step on the rats before they nibble your gold!", (t - .5) * 3, ORANGE)

    return [(5.0, cauldron, lambda s, now: s.snd.melody("spooky")),
            (5.0, stolen, lambda s, now: s.snd.melody("boo")),
            (5.0, quest, lambda s, now: s.snd.melody("quest"))]


def ending_moon(stage):
    """Level 4 won: the rats run off, and the witches say thank you under a great big moon."""
    def found(s, t, now):
        s.text(1, "At the bottom of the well...", CYAN, False)
        s.art(9, 37, CROWN, YELLOW)
        if bob(now, 4):
            s.burst(40, 10, 3, [YELLOW, WHITE], now, "*+.")
        s.art(15, 20, HERO if bob(now, 3) else HERO_WALK, HERO_COL)
        for i in range(4):                              # the rats run for it!
            x = 46 + t * 50 + i * 7
            s.put(17 + i % 2, x, RAT[bob(now * 4 + i, 4)], s.attr(ORANGE))
        if t > .3:
            s.text(21, "SQUEAK! It was the RATS all along!", ORANGE)

    def moon(s, t, now):
        s.stars(now, 50)
        big_moon(s, 40, 10, 8)
        for i in range(3):                              # witches on broomsticks fly across the moon
            x = -16 + ((t * 1.2 + i * .33) % 1.2) * 90
            s.art(4 + i * 5 + bob(now + i, 2), int(x), WITCH_BROOM[bob(now * 2 + i, 3)], WITCH_COL)
        s.text(21, "Whoooosh! The witches have their crown back!", MAGENTA)

    def thanks(s, t, now):
        """Like the sketch: THANK YOU! in a cloud, a moon, pointy hats everywhere, and the crowned witch."""
        s.stars(now, 40)
        s.art(9, 2, MOON, YELLOW)
        s.big("THANK YOU!", 1, colors=lambda i: MAGENTA if (i + int(now * 4)) % 2 else GREEN)
        wave = "~-~~-~^~-~~^-~~-~^~~-~-~~^~-~~-~^~~-~~-~^~-~~-~~^~-~~-~^~-~~"
        off = int(now * 3) % 6
        s.put(7, 10, wave[off:off + 60], s.attr(WHITE, False))           # the cloud the words sit in
        s.put(0, 10, wave[off:off + 60], s.attr(WHITE, False))
        if bob(now, 2):
            s.fireworks(now, .7)
        for i, x in enumerate((14, 25, 49, 62)):                          # witches all around
            s.art(11 + (i % 2) * 2 + bob(now * 2 + i, 2), x, WITCH[bob(now * 3 + i, 3)], WITCH_COL)
        s.art(9 + bob(now, 2), 37, CROWN_SMALL, YELLOW)                    # the witch with her crown back
        s.art(11 + bob(now, 2), 35, WITCH[1][1:], WITCH_COL)
        s.typed(21, "Thank you for finding our crown! You are our friend forever!", t * 2, YELLOW)

    def next_up(s, t, now):
        s.stars(now, 60)
        s.text(8, "Meanwhile, back in Robot Town...", CYAN)
        if t > .3:
            s.art(12, int(-8 + t * 60), LEPRECHAUN[bob(now, 6)], LEP_COL)
        if t > .6:
            s.text(19, "NEXT: THE WHISPERING FOREST", GREEN)

    return [(4.5, found, lambda s, now: s.snd.melody("gold")),
            (5.0, moon, lambda s, now: s.snd.melody("night")),
            (5.0, thanks, lambda s, now: s.snd.melody("fanfare")),
            (4.0, next_up, lambda s, now: s.snd.melody("sneak"))]


SCENES = {"town": opening_town, "crown": ending_crown, "ship": opening_ship, "ghosts": ending_ghosts,
          "rainbow": opening_rainbow, "rainbow_end": ending_rainbow,
          "thief": opening_thief, "home": ending_home, "witches": opening_witches, "moon": ending_moon}


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
