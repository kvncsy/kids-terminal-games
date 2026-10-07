#!/usr/bin/env python3
"""
QUEST - The Quest for the Golden Crown. A ZZT-style text adventure for kids.

The quest has levels. Level 1 is Robot Town: walk with the arrow keys, talk to
robots by walking into them, collect gems, find the red, blue and yellow keys
and open the castle doors to reach the Golden Crown. Finding it opens Level 2,
Spooky Islands: push rocks into water to make bridges, zap weak walls, and
find the ghost's treasure in the dark haunted house (ghosts say BOO and send
you back; a lamp helps you see). Lions are grumpy: a bump costs a heart.
Press SPACE to zap (you need ammo). Running out of hearts just sends you back
to where you came into the board. Progress is saved when you quit.

Like ZZT, the world is made of boards. Each board is a plain text file in
quest_boards/ that you can change, or copy to make your own
(see quest_boards/README.txt). A board says which level it belongs to
("level: 2"); the board with the @ is where that level starts.

  arrows  walk      SPACE  zap      Esc  save and quit

Once more than one level is open, Quest starts with a level screen: big
numbers, stars on finished levels. Each level keeps its own saved game.

  python3 quest.py           play (continues a saved game)
  python3 quest.py --reset   start a new quest
  python3 quest.py --check   look for mistakes in the board files
  python3 quest.py --mute    no sound

Set KIDS_FANCY=1 to use the classic ZZT symbols on a text console whose font has them.
"""
import argparse
import curses
import glob
import json
import locale
import os
import random
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from hacker_keys import FONT as _FONT
    BIG_DIGITS = {k: v for k, v in _FONT.items() if k.isdigit()}
except Exception:
    BIG_DIGITS = {}
BIG_DIGITS["?"] = [" ### ", "#   #", "  ## ", "     ", "  #  "]
try:
    import bleep_bloop as bb
except Exception:          # the game works fine without sound
    bb = None
try:
    import quest_scenes    # the cutscenes (the game works without them too)
except Exception:
    quest_scenes = None

BOARD_W, BOARD_H = 60, 21
SCREEN_W, SCREEN_H = 80, 24
BOARD_DIR = os.path.join(HERE, "quest_boards")
SAVE_FILE = os.path.expanduser("~/.quest_save")
MAX_HEALTH = 5
LION_STEP = 0.55           # seconds between lion moves (slow, so they're easy to zap)
LION_CHASE = 0.35          # how often a lion that sees you walks toward you
GHOST_STEP = 0.6           # seconds between ghost moves
LEPRECHAUN_STEP = 0.32     # leprechauns are quick... but not too quick
FAIRY_STEP = 0.5
RAINBOW_SHOES = 20.0       # seconds the rainbow shoes from a surprise box last
DARK_SIGHT, LAMP_SIGHT = 4.0, 6.5   # how far you can see on a dark board, without and with the lamp
DEFAULT_INTRO = ("Walk with the ARROW keys. Walk into robots to talk to them. "
                 "Find the three keys and bring home the Golden Crown!")
ZAP_STEP = 0.035           # seconds for a zap to move one square
LEGEND = set(" #%~=:TO*$a+l?rbygpcRBYGPCLHEF!@123456789")
KEYS = {"r": "red", "b": "blue", "y": "yellow", "g": "green", "p": "purple", "c": "light blue"}
DOORS = {k.upper(): k for k in KEYS}
DIRS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}

RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
KEY_COLORS = {"r": RED, "b": BLUE, "y": YELLOW, "g": GREEN, "p": MAGENTA, "c": CYAN}
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]

# how each thing looks: classic ZZT symbols, and plain ones for a small console font
FANCY = {"#": "█", "%": "▒", "~": "≈", "=": "═", ":": "░", "T": "♣", "O": "■", "*": "♦", "$": "$", "a": "ä",
         "+": "♥", "L": "Ω", "H": "Ö", "E": "¥", "F": "ƒ", "?": "?", "l": "☼", "!": "♛",
         "key": "♀", "door": "◘", "friend": "☻", "player": "☺", "heart": "♥"}
PLAIN = {"#": "█", "%": "%", "~": "~", "=": "=", ":": ":", "T": "T", "O": "O", "*": "*", "$": "$", "a": "a",
         "+": "+", "L": "L", "H": "G", "E": "E", "F": "F", "?": "?", "l": "i", "!": "W",
         "key": "k", "door": "▒", "friend": "&", "player": "@", "heart": "+"}
COLORS = {"#": WHITE, "%": YELLOW, "~": BLUE, "=": ORANGE, "T": GREEN, "O": MAGENTA, "*": CYAN, "$": YELLOW,
          "a": CYAN, "+": RED, "L": RED, "H": WHITE, "E": GREEN, "F": MAGENTA, "?": MAGENTA, "l": YELLOW, "!": YELLOW}
WALKABLE = " =:"           # ground you can stand on (bridges and rainbows stay put when you walk over them)


# ================================================================ boards
class Board:
    def __init__(self, name, title, exits, messages, rows, dark=False, info=None):
        self.name, self.title, self.exits, self.messages = name, title, exits, messages
        self.dark = dark
        info = info or {}
        self.info = info
        self.level = info.get("level", 1)
        self.adventure = info.get("adventure", "")      # the level's name (on its start board)
        self.goal = info.get("goal", "")                # what you find to finish the level
        self.intro = info.get("intro", "")              # what the box says when the level starts
        self.grid = [list(r) for r in rows]
        self.start = None
        self.boulder_homes = set()
        for y, row in enumerate(self.grid):
            for x, c in enumerate(row):
                if c == "@":
                    self.start = (x, y)
                    row[x] = " "
                elif c == "O":
                    self.boulder_homes.add((x, y))

    def at(self, x, y):
        return self.grid[y][x]

    def set(self, x, y, c):
        self.grid[y][x] = c


def parse_board(path):
    """Read a board file. Returns (Board, list of problems)."""
    name = os.path.splitext(os.path.basename(path))[0]
    title, exits, messages, rows, problems = name.title(), {}, {}, [], []
    dark = False
    info = {}
    in_map = False
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if in_map:
                rows.append(line)
                continue
            if not line.strip() or line.lstrip().startswith("//"):
                continue
            if line.strip().lower() == "map:":
                in_map = True
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "title":
                title = value
            elif key == "dark":
                dark = value.lower() in ("yes", "true", "1", "on")
            elif key == "level":
                if value.isdigit() and int(value) >= 1:
                    info["level"] = int(value)
                else:
                    problems.append("line %d: the level should be a number, like 'level: 2'" % n)
            elif key in ("adventure", "goal", "intro", "opening", "ending"):
                info[key] = value
            elif key in DIRS:
                exits[key] = value
            elif len(key) == 1 and key in "123456789":
                messages[key] = value
            else:
                problems.append("line %d: I don't understand %r" % (n, line))
    if len(rows) > BOARD_H:
        problems.append("the map has %d rows; only the first %d are used" % (len(rows), BOARD_H))
    for y, r in enumerate(rows[:BOARD_H]):
        if len(r) > BOARD_W:
            problems.append("map row %d is %d wide; only %d fit" % (y + 1, len(r), BOARD_W))
        for x, c in enumerate(r[:BOARD_W]):
            if c not in LEGEND:
                problems.append("map row %d, column %d: unknown symbol %r" % (y + 1, x + 1, c))
            elif c in "123456789" and c not in messages:
                problems.append("map row %d: robot %s has nothing to say (add a line '%s: ...')" % (y + 1, c, c))
    rows = [r[:BOARD_W].ljust(BOARD_W) for r in (rows + [""] * BOARD_H)[:BOARD_H]]
    rows = ["".join(c if c in LEGEND else " " for c in r) for r in rows]
    return Board(name, title, exits, messages, rows, dark, info), problems


def load_world(level=None):
    """The boards of one level (or of every level, for checking)."""
    boards, problems = {}, []
    for path in sorted(glob.glob(os.path.join(BOARD_DIR, "*.txt"))):
        if os.path.basename(path).lower() == "readme.txt":
            continue
        board, probs = parse_board(path)
        if level is not None and board.level != level:
            continue
        boards[board.name] = board
        problems += ["%s: %s" % (os.path.basename(path), p) for p in probs]
    for b in boards.values():
        for d, target in b.exits.items():
            if target not in boards:
                problems.append("%s.txt: the %s exit goes to %r, but there is no %s.txt" % (b.name, d, target, target))
            elif boards[target].level != b.level:
                problems.append("%s.txt: the %s exit goes to %s.txt, which is in another level" % (b.name, d, target))
    for lv in sorted({b.level for b in boards.values()}):
        starts = [b.name for b in boards.values() if b.level == lv and b.start]
        if len(starts) != 1:
            problems.append("level %d needs exactly one @ (where the player starts); it has %d" % (lv, len(starts)))
    return boards, problems


def level_list():
    """{level number: (name, goal)} for every level that has a start board."""
    boards, _ = load_world()
    out = {}
    for b in boards.values():
        if b.start:
            out[b.level] = (b.adventure or b.title, b.goal or "the Golden Crown")
    return dict(sorted(out.items()))


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

    def notes(self, steps, gap=0.07, base=72):
        for i, n in enumerate(steps):
            self.play(lambda n=n, i=i: bb.bell(bb.mtof(base + n), delay=i * gap))

    def gem(self): self.notes((12, 19))
    def ammo(self): self.play(lambda: bb.Voice([bb.tone(bb.SQUARE, 520, .5)], .2, .002, .1))
    def heart(self): self.notes((0, 7, 12), 0.08)
    def key(self): self.notes((0, 4, 7, 12, 16), 0.06)
    def door(self): self.play(lambda: bb.drum(5)); self.notes((0, 7), 0.12, 60)
    def push(self): self.play(lambda: bb.drum(5))
    def bump(self): self.play(lambda: bb.Voice([bb.tone(bb.TRIANGLE, 110, .6)], .15, .002, .06))
    def splash(self): self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .3, .6)], .2, .01, .3))
    def zap(self): self.play(lambda: bb.drum(8))
    def hurt(self): self.play(lambda: bb.drum(1)); self.play(lambda: bb.Voice([bb.tone(bb.SAW, 300, .5)], .3, .005, .3, sweep_from=1.8, sweep_time=.25))
    def lion_gone(self): self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .8, .6)], .3, .002, .25))
    def talk(self): self.notes((7, 4), 0.09)
    def whoosh(self): self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .25, .6)], .3, .15, .6))
    def win(self): self.notes((0, 4, 7, 12, 7, 12, 16, 19, 24), 0.12)
    def bridge(self): self.splash(); self.play(lambda: bb.drum(0)); self.notes((0, 7, 12), 0.1, 60)
    def lamp(self): self.notes((0, 4, 7, 11, 14), 0.08)
    def boo(self): self.play(lambda: bb.Voice([bb.tone(bb.SAW, 150, .5)], .3, .05, .9, sweep_from=4, sweep_time=.8)); self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .3, .5)], .2, .1, .8))
    def poof(self): self.play(lambda: bb.Voice([bb.tone(bb.SINE, 1200, .5)], .25, .01, .4, sweep_from=.3, sweep_time=.35))
    def coin(self): self.notes((24, 31), 0.05)
    def fairy(self): self.notes((12, 16, 19, 24, 28, 31), 0.05)
    def surprise(self): self.notes((0, 7, 12, 16, 19, 24), 0.06); self.play(lambda: bb.drum(0))
    def leprechaun(self): self.notes((7, 9, 12, 9, 7, 12, 16, 19), 0.07)
    def boom(self): self.play(lambda: bb.drum(random.choice((0, 4, 9))))

    MELODIES = {               # (notes above middle C, seconds between notes)
        "morning": ((0, 4, 7, 12, 7, 4, 7, 12, 16), .22), "quest": ((0, 7, 12, 7, 16, 12, 19), .18),
        "march": ((0, 0, 7, 7, 9, 9, 7, 5, 5, 4, 4, 2, 2, 0), .24), "crown": ((12, 16, 19, 24, 28, 31, 36), .3),
        "fanfare": ((0, 4, 7, 12, 7, 12, 16, 19, 24, 19, 24, 28), .14), "spooky": ((0, 3, 7, 6, 3, 0, -1, 0), .4),
        "boo": ((12, 11, 10, 9, 8, 7), .12), "gold": ((24, 28, 31, 36, 31, 36, 40, 43), .1),
        "party": ((0, 4, 7, 4, 9, 7, 4, 0, 12, 16, 19, 24), .15), "rainbow": ((0, 2, 4, 5, 7, 9, 11, 12, 16, 19, 24), .2),
    }

    def melody(self, name):
        steps, gap = self.MELODIES.get(name, ((0, 4, 7), .1))
        self.notes(steps, gap, 60)

    def stop(self):
        if self.eng:
            self.eng.stop()


# ================================================================ screen helpers
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


def color(fg, bold=True):
    return curses.color_pair(fg) | (curses.A_BOLD if bold else 0)


def on_blue(fg, bold=True):
    return curses.color_pair(8 + fg) | (curses.A_BOLD if bold else 0)


# ================================================================ the game
class Game:
    def __init__(self, scr, sounds):
        self.scr = scr
        self.snd = sounds
        utf = locale.getpreferredencoding().lower().replace("-", "") == "utf8"
        fancy = utf and (os.environ.get("TERM") != "linux" or os.environ.get("KIDS_FANCY") == "1")
        self.look = FANCY if fancy else PLAIN
        self.levels = level_list()
        self.progress = self.read_progress()
        if len(self.open_levels()) > 1:
            self.open_level_screen()
        else:
            self.start_level(min(self.levels))

    # ------------------------------------------------------------ levels and saving
    def read_progress(self):
        """{"unlocked": 2, "done": [1], "slots": {"1": a saved game, ...}}. An old one-quest save becomes level 1."""
        try:
            with open(SAVE_FILE) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if "grids" in data:                                   # a save from before there were levels
            data = {"unlocked": 1, "done": [], "slots": {"1": data}}
        data.setdefault("unlocked", min(self.levels))
        data.setdefault("done", [])
        data.setdefault("slots", {})
        return data

    def write_progress(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.progress, f)
        except OSError:
            pass

    def open_levels(self):
        return [lv for lv in self.levels if lv <= self.progress["unlocked"]]

    def start_level(self, level):
        self.level = level
        self.new_game()
        self.screen = "play"
        name, _ = self.levels[level]
        if self.load_save():
            self.say_box("Welcome back!", "Level %d: %s. Your quest continues!" % (level, name))
            return
        start = next(b for b in self.boards.values() if b.start)
        self.after_cut = lambda: self.say_box("LEVEL %d: %s" % (level, name.upper()), start.intro or DEFAULT_INTRO)
        if not self.play_cut(start.info.get("opening")):
            self.after_cut()

    def play_cut(self, name):
        """Start a cutscene; False if there isn't one."""
        if not (quest_scenes and name in getattr(quest_scenes, "SCENES", {})):
            return False
        h, w = self.scr.getmaxyx() if self.scr else (SCREEN_H, SCREEN_W)
        self.cut = quest_scenes.Cutscene(name, self.scr, (w - SCREEN_W) // 2, max(0, (h - SCREEN_H) // 2),
                                         self.look is FANCY, self.snd, time.time())
        self.screen = "cut"
        return True

    def end_cut(self):
        self.screen = "play"
        self.cut = None
        self.after_cut()

    def open_level_screen(self):
        self.screen = "levels"
        opened = self.open_levels()
        pick = max(opened)
        for lv in opened:                                     # the level being played, if there is one
            if str(lv) in self.progress["slots"] and lv not in self.progress["done"]:
                pick = lv
        self.level_pick = opened.index(pick)

    def level_key(self, key, now):
        opened = self.open_levels()
        if key in (curses.KEY_LEFT, curses.KEY_UP):
            self.level_pick = (self.level_pick - 1) % len(opened)
            self.snd.ammo()
        elif key in (curses.KEY_RIGHT, curses.KEY_DOWN):
            self.level_pick = (self.level_pick + 1) % len(opened)
            self.snd.ammo()
        elif key in ("\n", "\r", " ", curses.KEY_ENTER):
            self.snd.whoosh()
            self.start_level(opened[self.level_pick])
        elif isinstance(key, str) and key.isdigit() and int(key) in opened:
            self.snd.whoosh()
            self.start_level(int(key))
        return True

    def finish_level(self):
        """The crown (or treasure) is found: this level is done and the next one opens."""
        self.won = True
        if self.level not in self.progress["done"]:
            self.progress["done"].append(self.level)
        later = [lv for lv in self.levels if lv > self.level]
        self.next_level = later[0] if later else None
        if self.next_level:
            self.progress["unlocked"] = max(self.progress["unlocked"], self.next_level)
        self.progress["slots"].pop(str(self.level), None)    # a finished level starts fresh next time
        self.write_progress()
        start = next(b for b in self.boards.values() if b.start)
        self.won = False                                      # the ending plays first, then the "you did it" box
        self.after_cut = self.show_win
        if not self.play_cut(start.info.get("ending")):
            self.show_win()

    def show_win(self):
        self.won = True
        self.won_at = time.time()

    # ------------------------------------------------------------ state
    def new_game(self):
        self.boards, _ = load_world(self.level)
        self.board = next(b for b in self.boards.values() if b.start)
        self.px, self.py = self.board.start
        self.entry = (self.px, self.py)
        self.facing = (1, 0)
        self.health, self.ammo, self.gems, self.score = MAX_HEALTH, 0, 0, 0
        self.keys = set()
        self.lamp = False
        self.gold = 0
        self.parts = []           # sparkles on the board
        self.shoes_until = 0.0    # rainbow shoes from a surprise box
        self.zaps = []
        self.won = False
        self.dialog = None
        self.msg, self.msg_until, self.msg_color = "", 0.0, WHITE
        self.hurt_until = 0.0
        self.next_lion = self.next_zap = self.next_ghost = self.next_lep = self.next_fairy = 0.0
        self.hint_until = 0.0

    def save(self):
        if self.won or self.screen != "play":
            return
        data = {"board": self.board.name, "x": self.px, "y": self.py, "entry": list(self.entry),
                "health": self.health, "ammo": self.ammo, "gems": self.gems, "score": self.score,
                "keys": sorted(self.keys), "lamp": self.lamp, "gold": self.gold, "grids": {n: ["".join(r) for r in b.grid] for n, b in self.boards.items()}}
        self.progress["slots"][str(self.level)] = data
        self.write_progress()

    def load_save(self):
        """Continue this level's saved game, if there is one."""
        data = self.progress["slots"].get(str(self.level))
        if not data:
            return False
        try:
            for name, rows in data["grids"].items():
                if name in self.boards and len(rows) == BOARD_H and all(len(r) == BOARD_W for r in rows):
                    fresh = self.boards[name].grid
                    grid = [list(r) for r in rows]
                    for y in range(BOARD_H):            # new ways through (like the lake's road south)
                        for x in range(BOARD_W):        # open up in old saved games too
                            if grid[y][x] == "#" and fresh[y][x] in WALKABLE:
                                grid[y][x] = fresh[y][x]
                    self.boards[name].grid = grid
            self.board = self.boards[data["board"]]
            self.px, self.py = data["x"], data["y"]
            self.entry = tuple(data["entry"])
            self.health, self.ammo = data["health"], data["ammo"]
            self.gems, self.score = data["gems"], data["score"]
            self.keys = set(data["keys"])
            self.lamp = data.get("lamp", False)
            self.gold = data.get("gold", 0)
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    # ------------------------------------------------------------ messages
    def say(self, text, col=WHITE, secs=3.0):
        self.msg, self.msg_until, self.msg_color = text, time.time() + secs, col

    def say_box(self, title, text):
        self.dialog = (title, textwrap.wrap(text, 40), time.time())

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if key == "\x1b":
            self.save()
            return False
        if self.screen == "levels":
            return self.level_key(key, now)
        if self.screen == "cut":
            if key in ("\n", "\r", " ", curses.KEY_ENTER):
                self.cut.skip(now)
            return True
        if self.dialog:
            if now - self.dialog[2] > 0.35:      # so a mashed key doesn't skip it unread
                self.dialog = None
            return True
        if self.won:
            if key in ("\n", "\r", curses.KEY_ENTER) and time.time() - self.won_at > 1.0:
                if self.next_level:
                    self.start_level(self.next_level)        # straight on to the next level
                else:
                    self.open_level_screen()
            return True
        moves = {curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0)}
        if key in moves:
            self.facing = moves[key]
            self.move(*moves[key])
        elif key == " ":
            self.shoot()
        elif isinstance(key, str) and now > self.hint_until:
            self.say("Walk with the ARROW keys. SPACE zaps.", CYAN, 2)
            self.hint_until = now + 3
        return True

    # ------------------------------------------------------------ moving
    def move(self, dx, dy):
        b = self.board
        nx, ny = self.px + dx, self.py + dy
        if not (0 <= nx < BOARD_W and 0 <= ny < BOARD_H):
            self.leave(dx, dy)
            return
        t = b.at(nx, ny)
        if t in WALKABLE:
            pass
        elif t == "*":
            self.gems += 1
            self.score += 10
            self.snd.gem()
            self.burst(nx, ny, 8, [CYAN, WHITE])
            self.say("You found a gem!", CYAN, 1.5)
        elif t == "$":
            self.gold += 1
            self.score += 5
            self.snd.coin()
            self.burst(nx, ny, 6, [YELLOW, ORANGE])
            if self.gold % 10 == 0:
                self.say("%d GOLD COINS!" % self.gold, YELLOW, 2)
        elif t == "?":
            b.set(nx, ny, " ")
            self.surprise(nx, ny)
        elif t == "E":
            self.catch_leprechaun(nx, ny)
            return
        elif t == "F":
            self.health = MAX_HEALTH
            self.snd.fairy()
            self.burst(nx, ny, 25, [MAGENTA, YELLOW, WHITE], "*+.")
            self.say("A fairy! Sparkle sparkle... your hearts are full!", MAGENTA, 3)
            return
        elif t == "a":
            self.ammo += 5
            self.snd.ammo()
            self.say("Ammo! Press SPACE to zap.", CYAN)
        elif t == "+":
            if self.health >= MAX_HEALTH:
                self.say("Your hearts are already full!", RED)
                return
            self.health += 1
            self.snd.heart()
            self.say("A heart! You feel better.", RED)
        elif t in KEYS:
            if t in self.keys:
                self.say("You already have a %s key." % KEYS[t], KEY_COLORS[t])
                return
            self.keys.add(t)
            self.score += 50
            self.snd.key()
            self.burst(nx, ny, 20, [KEY_COLORS[t], WHITE])
            self.say("You got the %s key!" % KEYS[t].upper(), KEY_COLORS[t], 4)
        elif t == "l":
            self.lamp = True
            self.score += 50
            self.snd.lamp()
            self.say("A LAMP! Now you can see more in the dark.", YELLOW, 4)
        elif t in DOORS:
            k = DOORS[t]
            if k in self.keys:
                self.keys.discard(k)
                self.open_door(nx, ny, t)
                self.snd.door()
                self.say("The %s door opens!" % KEYS[k], KEY_COLORS[k], 3)
            else:
                self.snd.bump()
                self.say("This %s door is locked. Find the %s key!" % (KEYS[k], KEYS[k]), KEY_COLORS[k])
            return
        elif t == "O":
            bx, by = nx + dx, ny + dy
            beyond = b.at(bx, by) if 0 <= bx < BOARD_W and 0 <= by < BOARD_H else "#"
            if beyond == " ":
                b.set(bx, by, "O")
                b.set(nx, ny, " ")
                self.snd.push()
            elif beyond == "~":                     # the rock sinks and makes a bridge
                b.set(bx, by, "=")
                b.set(nx, ny, " ")
                self.snd.bridge()
                self.say("SPLASH! The rock made a bridge!", ORANGE, 3)
            else:
                self.snd.bump()
                self.say("The boulder won't budge that way.", MAGENTA, 2)
                return
        elif t == "L":
            self.hurt()
            b.set(nx, ny, " ")
            return
        elif t == "H":
            b.set(nx, ny, " ")
            self.boo()
            return
        elif t in "123456789":
            self.snd.talk()
            text = b.messages.get(t, "...")
            who, sep, words = text.partition(":")
            if sep and len(who) <= 20:
                self.say_box(who.strip(), words.strip())
            else:
                self.say_box("A robot says:", text)
            return
        elif t == "!":
            b.set(nx, ny, " ")
            self.px, self.py = nx, ny
            self.score += 500
            self.burst(nx, ny, 40)
            self.finish_level()
            self.snd.win()
            return
        elif t == "~":
            self.snd.splash()
            self.say("Splash! You can't swim here.", BLUE, 1.5)
            return
        elif t == "%":
            self.snd.bump()
            self.say("This wall looks weak. Zap it with SPACE!", YELLOW)
            return
        else:
            return                                  # walls and trees
        if t not in WALKABLE:
            b.set(nx, ny, " ")
        if time.time() < self.shoes_until and b.at(self.px, self.py) == " ":
            b.set(self.px, self.py, ":")                # rainbow shoes leave a rainbow behind you
        self.px, self.py = nx, ny

    def open_door(self, x, y, t):
        """A door can be several squares wide; open all of it."""
        todo = [(x, y)]
        while todo:
            cx, cy = todo.pop()
            if 0 <= cx < BOARD_W and 0 <= cy < BOARD_H and self.board.at(cx, cy) == t:
                self.board.set(cx, cy, " ")
                todo += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]

    def leave(self, dx, dy):
        direction = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east"}[(dx, dy)]
        name = self.board.exits.get(direction)
        if not name or name not in self.boards:
            return
        nb = self.boards[name]
        x = self.px if dx == 0 else (BOARD_W - 1 if dx < 0 else 0)
        y = self.py if dy == 0 else (BOARD_H - 1 if dy < 0 else 0)
        if nb.at(x, y) != " ":                      # find the nearest open square on that edge
            spots = [(abs(i - (x if dx == 0 else y)), i) for i in range(BOARD_W if dx == 0 else BOARD_H)
                     if nb.at(*((i, y) if dx == 0 else (x, i))) == " "]
            if not spots:
                return
            i = min(spots)[1]
            x, y = (i, y) if dx == 0 else (x, i)
        self.board = nb
        self.px, self.py = x, y
        self.entry = (x, y)
        self.zaps = []
        self.boulders_home()
        self.snd.whoosh()
        self.say("~ %s ~%s" % (nb.title, "  (it's dark in here!)" if nb.dark and not self.lamp else ""), YELLOW, 2.5)

    def boulders_home(self):
        """Boulders go back where they started whenever you come into a board, so nobody gets stuck."""
        b = self.board
        for y in range(BOARD_H):
            for x in range(BOARD_W):
                if b.at(x, y) == "O":
                    b.set(x, y, " ")
        for x, y in b.boulder_homes:
            if b.at(x, y) == " " and (x, y) != (self.px, self.py):
                b.set(x, y, "O")

    # ------------------------------------------------------------ zaps, lions, hearts
    def shoot(self):
        if self.ammo <= 0:
            self.snd.bump()
            self.say("No ammo! Find some ammo packs.", CYAN)
            return
        self.ammo -= 1
        self.snd.zap()
        self.zaps.append([self.px, self.py, self.facing[0], self.facing[1]])

    def hurt(self):
        now = time.time()
        if now < self.hurt_until:
            return
        self.hurt_until = now + 0.8
        self.health -= 1
        self.snd.hurt()
        if self.health <= 0:
            self.health = MAX_HEALTH
            self.px, self.py = self.entry
            self.say_box("Oof!", "The robots carried you back to safety. Your hearts are full again!")
        else:
            self.say("OUCH! A lion bumped you.", RED)

    def boo(self):
        """A ghost touched you: no hearts lost, but you're scared back to where you came in."""
        now = time.time()
        if now < self.hurt_until:
            return
        self.hurt_until = now + 1.2
        self.snd.boo()
        self.px, self.py = self.entry
        self.say("BOO! A ghost scared you back to the start!", WHITE, 3)

    def burst(self, x, y, n=12, colors=None, chars="*+o."):
        """Sparkles on the board."""
        now = time.time()
        for _ in range(n):
            self.parts.append([x, y, random.uniform(-9, 9), random.uniform(-5, 2), now + random.uniform(.4, 1.0),
                               random.choice(chars), random.choice(colors or RAINBOW)])

    def surprise(self, x, y):
        """A surprise box: something fun every time."""
        what = random.choice(["gold", "gold", "hearts", "zaps", "shoes", "party"])
        self.snd.surprise()
        self.burst(x, y, 30)
        if what == "gold":
            self.spill_gold(x, y, 8)
            self.say("SURPRISE! A shower of GOLD!", YELLOW, 3)
        elif what == "hearts":
            self.health = MAX_HEALTH
            self.say("SURPRISE! Full hearts!", RED, 3)
        elif what == "zaps":
            self.ammo += 10
            self.say("SURPRISE! 10 more zaps!", CYAN, 3)
        elif what == "shoes":
            self.shoes_until = time.time() + RAINBOW_SHOES
            self.say("SURPRISE! RAINBOW SHOES! Look behind you!", MAGENTA, 4)
        else:
            self.score += 100
            self.burst(x, y, 60, chars="*+o.x%&")
            self.say("SURPRISE PARTY! +100 points!", GREEN, 3)

    def spill_gold(self, x, y, n):
        spots = [(x + dx, y + dy) for dx in range(-3, 4) for dy in range(-2, 3)
                 if (dx or dy) and 0 <= x + dx < BOARD_W and 0 <= y + dy < BOARD_H]
        random.shuffle(spots)
        for sx, sy in spots:
            if n and self.board.at(sx, sy) == " " and (sx, sy) != (self.px, self.py):
                self.board.set(sx, sy, "$")
                n -= 1

    def catch_leprechaun(self, x, y):
        self.board.set(x, y, " ")
        self.score += 50
        self.snd.leprechaun()
        self.burst(x, y, 35, [GREEN, YELLOW, WHITE])
        self.spill_gold(x, y, 8)
        self.say("You caught a leprechaun! He gives you his GOLD!", GREEN, 3)

    def zap_hit(self, x, y):
        """A zap hits whatever is here. Returns True if it should stop flying."""
        b = self.board
        t = b.at(x, y)
        if t == "E":
            self.catch_leprechaun(x, y)
            return True
        if t == "L":
            b.set(x, y, " ")
            self.score += 20
            self.snd.lion_gone()
            self.say("Zapped! The lion runs away.", GREEN, 1.5)
            return True
        if t == "H":
            b.set(x, y, " ")
            self.score += 20
            self.snd.poof()
            self.say("POOF! The ghost is gone.", GREEN, 1.5)
            return True
        if t == "%":
            b.set(x, y, " ")
            self.snd.push()
            return True
        return t not in " =~:"                       # zaps fly over ground, bridges, rainbows and water

    def update(self, now):
        if self.screen in ("levels", "cut") or self.dialog or self.won:
            return
        b = self.board
        if now >= self.next_lep:
            self.next_lep = now + LEPRECHAUN_STEP
            for x, y in [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "E"]:
                spots = [(x + dx, y + dy) for dx, dy in DIRS.values()
                         if 0 <= x + dx < BOARD_W and 0 <= y + dy < BOARD_H and b.at(x + dx, y + dy) == " "]
                if not spots:
                    continue
                near = abs(self.px - x) + abs(self.py - y) <= 9
                if near and random.random() < 0.7:          # run away from you!
                    tx, ty = max(spots, key=lambda c: abs(c[0] - self.px) + abs(c[1] - self.py))
                elif random.random() < 0.4:
                    tx, ty = random.choice(spots)
                else:
                    continue
                b.set(x, y, " ")
                b.set(tx, ty, "E")
        if now >= self.next_fairy:
            self.next_fairy = now + FAIRY_STEP
            for x, y in [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "F"]:
                tx, ty = x + random.choice((-1, 0, 1)), y + random.choice((-1, 0, 1))
                if random.random() < 0.5 and 0 <= tx < BOARD_W and 0 <= ty < BOARD_H and b.at(tx, ty) == " " \
                        and (tx, ty) != (self.px, self.py):
                    b.set(x, y, " ")
                    b.set(tx, ty, "F")
        if now >= self.next_zap:
            self.next_zap = now + ZAP_STEP
            for z in list(self.zaps):
                z[0] += z[2]
                z[1] += z[3]
                x, y = z[0], z[1]
                if not (0 <= x < BOARD_W and 0 <= y < BOARD_H):
                    self.zaps.remove(z)
                    continue
                # a near miss counts: lions and ghosts right beside the zap's path get hit too
                for sx, sy in ((x + z[3], y + z[2]), (x - z[3], y - z[2])):
                    if 0 <= sx < BOARD_W and 0 <= sy < BOARD_H and b.at(sx, sy) in "LHE":
                        self.zap_hit(sx, sy)
                if self.zap_hit(x, y):
                    self.zaps.remove(z)
        if now >= self.next_lion:
            self.next_lion = now + LION_STEP
            lions = [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "L"]
            for x, y in lions:
                ddx, ddy = self.px - x, self.py - y
                if abs(ddx) + abs(ddy) <= 8 and random.random() < LION_CHASE:      # it has seen you!
                    if abs(ddx) > abs(ddy):
                        step = ((ddx > 0) - (ddx < 0), 0)
                    else:
                        step = (0, (ddy > 0) - (ddy < 0))
                else:
                    step = random.choice(list(DIRS.values()))
                tx, ty = x + step[0], y + step[1]
                if (tx, ty) == (self.px, self.py):
                    b.set(x, y, " ")
                    self.hurt()
                elif 0 <= tx < BOARD_W and 0 <= ty < BOARD_H and b.at(tx, ty) == " ":
                    b.set(x, y, " ")
                    b.set(tx, ty, "L")
        if now >= self.next_ghost:
            self.next_ghost = now + GHOST_STEP
            ghosts = [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "H"]
            for x, y in ghosts:
                ddx, ddy = self.px - x, self.py - y
                if abs(ddx) + abs(ddy) <= 12 and random.random() < 0.35:     # drifting closer...
                    step = ((ddx > 0) - (ddx < 0), 0) if abs(ddx) > abs(ddy) else (0, (ddy > 0) - (ddy < 0))
                else:
                    step = random.choice(list(DIRS.values()))
                tx, ty = x + step[0], y + step[1]
                if (tx, ty) == (self.px, self.py):
                    b.set(x, y, " ")
                    self.boo()
                elif 0 <= tx < BOARD_W and 0 <= ty < BOARD_H and b.at(tx, ty) == " ":
                    b.set(x, y, " ")
                    b.set(tx, ty, "H")

    # ------------------------------------------------------------ drawing
    def glyph(self, t, now):
        L = self.look
        if t in KEYS:
            return L["key"], color(KEY_COLORS[t])
        if t in DOORS:
            return L["door"], color(KEY_COLORS[DOORS[t]])
        if t == "H":
            return L["H"], color(WHITE, int(now * 3) % 2 == 0)
        if t in "123456789":
            return L["friend"], color(MAGENTA)
        if t == "!":
            return L["!"], color(RAINBOW[int(now * 6) % len(RAINBOW)])
        if t == "*":
            return L["*"], color(CYAN if int(now * 2) % 4 else WHITE)
        if t == ":":                                     # the rainbow shimmers
            return L[":"], color(RAINBOW[int(now * 3) % len(RAINBOW)])
        if t == "$":
            return L["$"], color(YELLOW if int(now * 3) % 5 else WHITE)
        if t == "?":
            return L["?"], color(RAINBOW[int(now * 4) % len(RAINBOW)]) | curses.A_REVERSE
        if t == "F":
            return L["F"], color(MAGENTA if int(now * 4) % 2 else YELLOW)
        return L.get(t, t), color(COLORS.get(t, WHITE), t not in "#")

    def draw(self, now):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        if w < SCREEN_W or h < SCREEN_H - 1:
            put(scr, 0, 0, "Please make the window bigger (80 x 24).", color(YELLOW))
            scr.refresh()
            return
        ox, oy = (w - SCREEN_W) // 2, max(0, (h - SCREEN_H) // 2)
        if self.screen == "levels":
            self.draw_levels(ox, oy, now)
            scr.refresh()
            return
        if self.screen == "cut":
            self.cut.draw(now, ox, oy)
            if self.cut.done:
                self.end_cut()
            scr.refresh()
            return
        b = self.board
        sight = (LAMP_SIGHT if self.lamp else DARK_SIGHT) ** 2
        for y in range(BOARD_H):
            for x in range(BOARD_W):
                t = b.at(x, y)
                if t == " ":
                    continue
                # in the dark you only see near you (squares are tall, so count across as half) - and the ghosts
                if b.dark and t != "H" and ((x - self.px) * 0.5) ** 2 + (y - self.py) ** 2 > sight:
                    continue
                ch, a = self.glyph(t, now)
                put(scr, oy + y, ox + x, ch, a)
        for x, y, dx, dy in self.zaps:
            put(scr, oy + y, ox + x, "•" if self.look is FANCY else ("-" if dx else "|"), color(WHITE))
        dt = min(0.1, now - getattr(self, "last_draw", now))
        self.last_draw = now
        for p in self.parts:                             # sparkles
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 8 * dt
            if 0 <= p[0] < BOARD_W and 0 <= p[1] < BOARD_H:
                put(scr, oy + int(p[1]), ox + int(p[0]), p[5], color(p[6]))
        self.parts = [p for p in self.parts if p[4] > now][-300:]
        hurt = now < self.hurt_until and int(now * 10) % 2
        put(scr, oy + self.py, ox + self.px, self.look["player"], on_blue(RED if hurt else WHITE))
        self.draw_sidebar(ox + BOARD_W, oy, now)
        if now < self.msg_until:
            m = self.msg.center(BOARD_W)
            put(scr, oy + BOARD_H, ox, m, color(self.msg_color) | (curses.A_REVERSE if int(now * 3) % 2 else 0))
        if self.dialog:
            self.draw_box(ox, oy, self.dialog[0], self.dialog[1], "press any key")
        elif self.won:
            name, goal = self.levels[self.level]
            then = ("Press ENTER for LEVEL %d!" % self.next_level) if self.next_level else "Press ENTER to pick a level."
            self.draw_box(ox, oy, "YOU FOUND %s!" % goal.upper(),
                          textwrap.wrap("LEVEL %d DONE! You collected %d gems and scored %d points. %s"
                                        % (self.level, self.gems, self.score, then), 40),
                          "", RAINBOW[int(now * 6) % len(RAINBOW)])
        scr.refresh()

    def draw_sidebar(self, x, y, now):
        blank = " " * (SCREEN_W - BOARD_W)
        for r in range(SCREEN_H - 1):
            put(self.scr, y + r, x, blank, on_blue(WHITE))
        rows = [
            (1, "    - QUEST -", on_blue(YELLOW)),
            (2, "  for the Golden", on_blue(WHITE, False)),
            (3, "      Crown", on_blue(WHITE, False)),
        ]
        for r, text, a in rows:
            put(self.scr, y + r, x, text, a)
        heart = self.look["heart"]
        put(self.scr, y + 5, x, "  Health ", on_blue(WHITE))
        put(self.scr, y + 5, x + 9, heart * self.health, on_blue(RED))
        put(self.scr, y + 5, x + 9 + self.health, "." * (MAX_HEALTH - self.health), on_blue(WHITE, False))
        for r, label, value in ((6, "Ammo", self.ammo), (7, "Gems", self.gems), (8, "Score", self.score)):
            if label == "Gems" and self.gold:
                label, value = "Gold", "%d  gems %d" % (self.gold, self.gems)
            put(self.scr, y + r, x, "  %-6s %s" % (label, value), on_blue(WHITE))
        put(self.scr, y + 9, x, "  Keys", on_blue(WHITE))
        for i, k in enumerate(k for k in KEYS if k in self.keys):
            put(self.scr, y + 9, x + 9 + i * 2, self.look["key"], on_blue(KEY_COLORS[k]))
        if self.lamp:
            put(self.scr, y + 10, x, "  Lamp", on_blue(WHITE))
            put(self.scr, y + 10, x + 9, self.look["l"], on_blue(YELLOW))
        for i, line in enumerate(textwrap.wrap(self.board.title, 17)[:2]):
            put(self.scr, y + 12 + i, x + 2, line, on_blue(CYAN))
        put(self.scr, y + 15, x, "  LEVEL %d" % self.level, on_blue(YELLOW))
        for r, text in ((17, "  Arrows  walk"), (18, "  Space   zap"), (19, "  Esc     quit")):
            put(self.scr, y + r, x, text, on_blue(WHITE, False))

    def draw_levels(self, ox, oy, now):
        """The save screen: one big card per open level, a star on each finished one."""
        title = "PICK A LEVEL"
        put(self.scr, oy + 1, ox + (SCREEN_W - len(title)) // 2, title, color(RAINBOW[int(now * 3) % len(RAINBOW)]))
        opened = self.open_levels()
        cards = opened + [lv for lv in self.levels if lv > max(opened)][:1]   # and the next locked one
        cw, gap = 16, 2
        x0 = ox + (SCREEN_W - (len(cards) * (cw + gap) - gap)) // 2
        star = "*" if self.look is PLAIN else "★"
        for i, lv in enumerate(cards):
            x, y = x0 + i * (cw + gap), oy + 4
            locked = lv not in opened
            picked = not locked and opened.index(lv) == self.level_pick
            col = WHITE if locked else (YELLOW if picked else CYAN)
            a = color(col, not locked) | (curses.A_REVERSE if picked and int(now * 2) % 2 else 0)
            put(self.scr, y, x, "+" + "-" * (cw - 2) + "+", a)
            for r in range(1, 10):
                put(self.scr, y + r, x, "|" + " " * (cw - 2) + "|", a)
            put(self.scr, y + 10, x, "+" + "-" * (cw - 2) + "+", a)
            glyph = BIG_DIGITS.get("?" if locked else str(lv % 10), BIG_DIGITS["?"])
            for r, row in enumerate(glyph):                   # a big number
                put(self.scr, y + 2 + r, x + 3, row.replace("#", "██" if self.look is FANCY else "##").replace(" ", "  "),
                    color(WHITE if locked else RAINBOW[(lv * 2) % len(RAINBOW)], not locked))
            if lv in self.progress["done"]:
                put(self.scr, y + 8, x + (cw - 5) // 2, (star + " ") * 3, color(YELLOW))
            elif str(lv) in self.progress["slots"]:
                put(self.scr, y + 8, x + 2, "playing...".center(cw - 4), color(GREEN))
            name = "?" if locked else self.levels[lv][0]
            put(self.scr, y + 11, x + (cw - len(name[:cw])) // 2, name[:cw], color(WHITE if locked else col))
            if picked:
                put(self.scr, y + 13, x + cw // 2 - 1, self.look["player"], on_blue(WHITE))
        tip = "ARROWS pick a level, ENTER plays it"
        put(self.scr, oy + SCREEN_H - 4, ox + (SCREEN_W - len(tip)) // 2, tip, color(WHITE, False))
        put(self.scr, oy + SCREEN_H - 2, ox + (SCREEN_W - 9) // 2, "Esc: quit", color(WHITE, False))

    def draw_box(self, ox, oy, title, lines, footer, title_color=YELLOW):
        bw = 46
        bh = len(lines) + 5
        bx, by = ox + (BOARD_W - bw) // 2, oy + max(1, (BOARD_H - bh) // 2)
        a = color(WHITE)
        put(self.scr, by, bx, "╔" + "═" * (bw - 2) + "╗", a)
        for r in range(1, bh - 1):
            put(self.scr, by + r, bx, "║" + " " * (bw - 2) + "║", a)
        put(self.scr, by + bh - 1, bx, "╚" + "═" * (bw - 2) + "╝", a)
        put(self.scr, by + 1, bx + (bw - len(title)) // 2, title, color(title_color))
        for i, line in enumerate(lines):
            put(self.scr, by + 3 + i, bx + 3, line, color(WHITE, False))
        if footer:
            put(self.scr, by + bh - 1, bx + (bw - len(footer) - 2) // 2, " %s " % footer, color(CYAN))


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
    fgs = {RED: curses.COLOR_RED, YELLOW: curses.COLOR_YELLOW, GREEN: curses.COLOR_GREEN,
           CYAN: curses.COLOR_CYAN, BLUE: curses.COLOR_BLUE, MAGENTA: curses.COLOR_MAGENTA,
           WHITE: curses.COLOR_WHITE, ORANGE: orange}
    for pid, fg in fgs.items():
        curses.init_pair(pid, fg, curses.COLOR_BLACK)
        curses.init_pair(8 + pid, fg if fg != curses.COLOR_BLUE else curses.COLOR_CYAN, curses.COLOR_BLUE)
    scr.bkgd(" ", curses.color_pair(WHITE))

    sounds = Sounds(not args.mute)
    game = Game(scr, sounds)
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
                if not game.handle_key(key, time.time()):
                    return
            now = time.time()
            game.update(now)
            game.draw(now)
            time.sleep(max(0, 1 / 30 - (time.time() - t0)))
    finally:
        sounds.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="The Quest for the Golden Crown. Esc saves and quits.")
    p.add_argument("--reset", action="store_true", help="start a new quest")
    p.add_argument("--check", action="store_true", help="look for mistakes in the board files")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("The quest will start fresh next time.")
        raise SystemExit
    if args.check:
        boards, problems = load_world()
        for lv, (name, goal) in level_list().items():
            names = sorted(b.name for b in boards.values() if b.level == lv)
            print("Level %d, %s (find %s): %s" % (lv, name, goal, ", ".join(names)))
        print("\n".join(problems) if problems else "No problems found. Have fun!")
        raise SystemExit
    locale.setlocale(locale.LC_ALL, "")
    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue
    print("Your quest is saved. See you next time, explorer!")
