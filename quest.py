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
(see quest_boards/README.txt). The file name says the level, the board's name
and where it is (2-house-nee.txt); the board with the @ is where a level starts.

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
import math
import os
import random
import re
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
RAINBOW_SHOES = 20.0
CROW_STEP = 0.12           # how often crows look around (and fly)
CROW_FRIGHT = 4            # crows fly away when you come this close
KING_PRICE = 15            # gold the Leprechaun King wants for the crown
WITCH_FRIGHT = 3           # witches vanish (and leave ammo) when you come this close
RAT_STEP = 0.18            # rats are fast!
RAT_NIBBLE = 1.2           # seconds between nibbles       # seconds the rainbow shoes from a surprise box last
DARK_SIGHT, LAMP_SIGHT = 4.0, 6.5   # how far you can see on a dark board, without and with the lamp
DEFAULT_INTRO = ("Walk with the ARROW keys. Walk into robots to talk to them. "
                 "Find the three keys and bring home the Golden Crown!")
ZAP_STEP = 0.035           # seconds for a zap to move one square
RUN_STEP = 0.12            # hold an arrow to run: one step this often (about 8 a second)
SHOT_GAP = 0.25            # and holding SPACE zaps this often
HELD = 0.1                 # a key back this fast is being held down, not pressed again
LEGEND = set(" #%&~=:TO*$a+l?rbygpcRBYGPCLHEFVKQA,<>!@123456789")
KEYS = {"r": "red", "b": "blue", "y": "yellow", "g": "green", "p": "purple", "c": "light blue"}
DOORS = {k.upper(): k for k in KEYS}
DIRS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
STAIRS = {">": "down", "<": "up"}       # step on them to go down (or up) to another board

RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
KEY_COLORS = {"r": RED, "b": BLUE, "y": YELLOW, "g": GREEN, "p": MAGENTA, "c": CYAN}
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]

# how each thing looks: classic ZZT symbols, and plain ones for a small console font
FANCY = {"#": "█", "%": "▒", "~": "≈", "=": "═", ":": "░", "T": "♣", "O": "■", "*": "♦", "$": "$", "a": "ä",
         "+": "♥", "L": "Ω", "H": "Ö", "E": "¥", "F": "ƒ", "?": "?", "l": "☼", "!": "♛",
         "&": "▓", "V": "v", "K": "K", "Q": "Q", "A": "A", ",": ",", ">": "▼", "<": "▲",
         "key": "♀", "door": "◘", "friend": "☻", "player": "☺", "heart": "♥", "star": "★"}
PLAIN = {"#": "█", "%": "%", "~": "~", "=": "=", ":": ":", "T": "T", "O": "O", "*": "*", "$": "$", "a": "a",
         "+": "+", "L": "L", "H": "G", "E": "E", "F": "F", "?": "?", "l": "i", "!": "W",
         "&": "#", "V": "v", "K": "K", "Q": "Q", "A": "A", ",": ",", ">": ">", "<": "<",
         "key": "k", "door": "▒", "friend": "&", "player": "@", "heart": "+", "star": "*"}
# the Linux console with the kids' font (KIDS_FANCY=1, see kids.bashrc): the old PC symbols, but no star or crown
CONSOLE = dict(FANCY, **{"!": "W", "star": "*"})
COLORS = {"#": WHITE, "%": YELLOW, "~": BLUE, "=": ORANGE, "T": GREEN, "O": MAGENTA, "*": CYAN, "$": YELLOW,
          "a": CYAN, "+": RED, "L": RED, "H": WHITE, "E": GREEN, "F": MAGENTA, "?": MAGENTA, "l": YELLOW, "!": YELLOW,
          "&": GREEN, "V": WHITE, "K": GREEN, "Q": MAGENTA, "A": MAGENTA, ",": ORANGE, ">": CYAN, "<": CYAN}
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
        self.crow_homes = set()
        for y, row in enumerate(self.grid):
            for x, c in enumerate(row):
                if c == "@":
                    self.start = (x, y)
                    row[x] = " "
                elif c == "O":
                    self.boulder_homes.add((x, y))
                elif c == "V":
                    self.crow_homes.add((x, y))

    def at(self, x, y):
        return self.grid[y][x]

    def set(self, x, y, c):
        self.grid[y][x] = c


FILE_NAME = re.compile(r"^(\d+)-([a-z0-9_]+)(?:-([nsewud]+|start))?$")


def parse_board(path):
    """Read a board file. Returns (Board, list of problems).
    A file called 2-house-nee.txt is the board "house" in level 2, north and two east of the start.
    (Plain names like house.txt work too; then the level comes from a 'level:' line.)"""
    stem = os.path.splitext(os.path.basename(path))[0]
    named = FILE_NAME.match(stem.lower())
    name = named.group(2) if named else stem
    title, exits, messages, rows, problems = name.title(), {}, {}, [], []
    dark = False
    info = {"level": int(named.group(1)), "where": named.group(3) or ""} if named else {}
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
                if named and value != named.group(1):
                    problems.append("line %d: the file name says level %s" % (n, named.group(1)))
                elif value.isdigit() and int(value) >= 1:
                    info["level"] = int(value)
                else:
                    problems.append("line %d: the level should be a number, like 'level: 2'" % n)
            elif key in ("adventure", "goal", "intro", "opening", "ending"):
                info[key] = value
            elif key == "box":
                if value in KEYS:
                    info["box"] = value
                else:
                    problems.append("line %d: the box should hold a key, like 'box: y'" % n)
            elif key in DIRS or key in STAIRS.values():
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
            elif c in STAIRS and STAIRS[c] not in exits:
                problems.append("map row %d: a way %s, but no '%s:' line says where it goes" % (y + 1, STAIRS[c], STAIRS[c]))
            elif c in "123456789" and c not in messages:
                problems.append("map row %d: robot %s has nothing to say (add a line '%s: ...')" % (y + 1, c, c))
    rows = [r[:BOARD_W].ljust(BOARD_W) for r in (rows + [""] * BOARD_H)[:BOARD_H]]
    rows = ["".join(c if c in LEGEND else " " for c in r) for r in rows]
    return Board(name, title, exits, messages, rows, dark, info), problems


def load_world(level=None):
    """The boards of one level, by name. With no level: every board, by (level, name), for checking."""
    boards, problems = {}, []
    for path in sorted(glob.glob(os.path.join(BOARD_DIR, "*.txt"))):
        if os.path.basename(path).lower() == "readme.txt":
            continue
        board, probs = parse_board(path)
        if level is not None and board.level != level:
            continue
        key = board.name if level is not None else (board.level, board.name)
        if key in boards:
            problems.append("%s: level %d already has a board called %s" % (os.path.basename(path), board.level, board.name))
        board.file = os.path.basename(path)
        boards[key] = board
        problems += ["%s: %s" % (board.file, p) for p in probs]
    for lv in sorted({b.level for b in boards.values()}):
        here = {b.name: b for b in boards.values() if b.level == lv}
        starts = [b for b in here.values() if b.start]
        if len(starts) != 1:
            problems.append("level %d needs exactly one @ (where the player starts); it has %d" % (lv, len(starts)))
        for b in here.values():
            for d, target in b.exits.items():
                if target not in here:
                    problems.append("%s: the %s exit goes to %r, but level %d has no board called that"
                                    % (b.file, d, target, lv))
        if len(starts) == 1:
            problems += where_problems(here, starts[0])
    return boards, problems


def where_problems(here, start):
    """Check the n/s/e/w in file names (like 1-throne-nnn.txt) against where the exits really lead."""
    spot, todo = {start.name: (0, 0, 0)}, [start.name]
    while todo:
        b = here[todo.pop(0)]
        for d, target in b.exits.items():
            if target in here and target not in spot:
                dx, dy, dz = DIRS[d] + (0,) if d in DIRS else (0, 0, 1 if d == "down" else -1)
                spot[target] = (spot[b.name][0] + dx, spot[b.name][1] + dy, spot[b.name][2] + dz)
                todo.append(target)
    out = []
    for b in here.values():
        where = b.info.get("where", "")
        if not where or b.name not in spot:
            continue
        x, y, z = spot[b.name]
        real = "d" * z + "u" * -z + "n" * -y + "s" * y + "e" * x + "w" * -x or "start"
        said = (where.count("e") - where.count("w"), where.count("s") - where.count("n"),
                where.count("d") - where.count("u")) if where != "start" else (0, 0, 0)
        if said != (x, y, z):
            out.append("%s: the name says %s, but this board is %s from the start" % (b.file, where, real))
    return out


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
    def cackle(self): self.notes((19, 16, 19, 16, 19, 16, 12), 0.06)
    def squeak(self): self.play(lambda: bb.Voice([bb.tone(bb.SINE, 1700, .35)], .08, .002, .05, sweep_from=.7, sweep_time=.06))
    def caw(self): self.play(lambda: bb.Voice([bb.tone(bb.SAW, 700, .4)], .18, .005, .12, sweep_from=1.4, sweep_time=.12)); self.play(lambda: bb.Voice([bb.hiss(bb.NOISE, .25, .4)], .4, .05, .5))
    def boom(self): self.play(lambda: bb.drum(random.choice((0, 4, 9))))

    MELODIES = {               # (notes above middle C, seconds between notes)
        "morning": ((0, 4, 7, 12, 7, 4, 7, 12, 16), .22), "quest": ((0, 7, 12, 7, 16, 12, 19), .18),
        "march": ((0, 0, 7, 7, 9, 9, 7, 5, 5, 4, 4, 2, 2, 0), .24), "crown": ((12, 16, 19, 24, 28, 31, 36), .3),
        "fanfare": ((0, 4, 7, 12, 7, 12, 16, 19, 24, 19, 24, 28), .14), "spooky": ((0, 3, 7, 6, 3, 0, -1, 0), .4),
        "boo": ((12, 11, 10, 9, 8, 7), .12), "gold": ((24, 28, 31, 36, 31, 36, 40, 43), .1),
        "party": ((0, 4, 7, 4, 9, 7, 4, 0, 12, 16, 19, 24), .15), "rainbow": ((0, 2, 4, 5, 7, 9, 11, 12, 16, 19, 24), .2),
        "night": ((12, 7, 4, 0, 4, 7, 4, 0), .35), "sneak": ((0, 2, 0, 2, 3, 5, 3, 7), .16),
        "forest": ((0, 4, 7, 9, 7, 4, 2, 0), .26), "home": ((7, 5, 4, 2, 4, 0, 4, 7, 12), .3),
        "journal": ((12, 11, 9, 7, 9, 11, 12, 16), .32),
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
        if not utf:
            self.look = PLAIN
        elif os.environ.get("TERM") != "linux":
            self.look = FANCY
        else:
            self.look = CONSOLE if os.environ.get("KIDS_FANCY") == "1" else PLAIN
        self.last_key, self.last_key_at, self.last_step, self.last_shot = None, 0.0, 0.0, 0.0
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
            data = self.old_save(data)
        data.setdefault("unlocked", min(self.levels))
        data.setdefault("done", [])
        data.setdefault("slots", {})
        for lv in data["done"]:                               # a level added after you won the one before it
            later = [n for n in self.levels if n > lv]
            if later:
                data["unlocked"] = max(data["unlocked"], later[0])
        return data

    def old_save(self, data):
        """An old one-quest save. If it was already in a board that is now part of a later
        level (the haunted house), that level opens, the ones before it count as won, and it
        starts fresh at its first room: the old walls and doors don't match it."""
        boards, _ = load_world()
        lv = min([lv for lv, name in boards if name == data.get("board")] or [min(self.levels)])
        slots = {str(lv): data} if lv == min(self.levels) else {}
        return {"unlocked": lv, "done": [v for v in self.levels if v < lv], "slots": slots}

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
                                         self.look is not PLAIN, self.snd, time.time())
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
        if key in (curses.KEY_LEFT, curses.KEY_UP, curses.KEY_RIGHT, curses.KEY_DOWN):
            if now - self.last_step < RUN_STEP * 2:
                return True
            self.last_step = now
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
        self.crown = False        # Level 4: the crown from the Leprechaun King, for Queen Maeve
        self.birds = []           # crows flying away
        self.nibbled_at = 0.0     # when a rat last nibbled you
        self.parts = []           # sparkles on the board
        self.shoes_until = 0.0    # rainbow shoes from a surprise box
        self.zaps = []
        self.won = False
        self.dialog = None
        self.msg, self.msg_until, self.msg_color = "", 0.0, WHITE
        self.hurt_until = 0.0
        self.next_lion = self.next_zap = self.next_ghost = self.next_lep = self.next_fairy = self.next_crow = self.next_rat = 0.0
        self.hint_until = 0.0

    def save(self):
        if self.screen != "play" or self.won:          # (nothing to save on the level screen)
            return
        data = {"board": self.board.name, "x": self.px, "y": self.py, "entry": list(self.entry),
                "health": self.health, "ammo": self.ammo, "gems": self.gems, "score": self.score,
                "keys": sorted(self.keys), "lamp": self.lamp, "gold": self.gold, "crown": self.crown, "grids": {n: ["".join(r) for r in b.grid] for n, b in self.boards.items()}}
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
                            edge = x in (0, BOARD_W - 1) or y in (0, BOARD_H - 1)
                            if (grid[y][x] == "#" and fresh[y][x] in WALKABLE) or edge or fresh[y][x] == "!":
                                grid[y][x] = fresh[y][x]  # and the edges and the goal are always the real ones
                    self.boards[name].grid = grid
            self.board = self.boards[data["board"]]
            self.px, self.py = data["x"], data["y"]
            self.entry = tuple(data["entry"])
            self.health, self.ammo = data["health"], data["ammo"]
            self.gems, self.score = data["gems"], data["score"]
            self.keys = set(data["keys"])
            self.lamp = data.get("lamp", False)
            self.gold = data.get("gold", 0)
            self.crown = data.get("crown", False)
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
        held = key == self.last_key and now - self.last_key_at < HELD
        self.last_key, self.last_key_at = key, now
        if held and key in ("\n", "\r", " ", curses.KEY_ENTER) and self.screen != "play":
            return True                          # holding ENTER doesn't skip the movies one after another
        if self.screen == "levels":
            return self.level_key(key, now)
        if self.screen == "cut":
            if key in ("\n", "\r", " ", curses.KEY_ENTER):
                self.cut.skip(now)
            return True
        if self.dialog:
            if now - self.dialog[2] > 0.35 and not held:   # not mashed or held down: let go, then press
                self.dialog = None
            return True
        if self.won:
            if key in ("\n", "\r", curses.KEY_ENTER) and time.time() - self.won_at > 1.0 and not held:
                if self.next_level:
                    self.progress["slots"].pop(str(self.next_level), None)
                    self.write_progress()
                    self.start_level(self.next_level)        # straight on to the start of the next level
                else:
                    self.open_level_screen()
            return True
        moves = {curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0)}
        if key in moves:
            if now - self.last_step < RUN_STEP:  # held down: run, at a steady pace
                return True
            self.last_step = now
            self.facing = moves[key]
            self.move(*moves[key])
        elif key == " ":
            if now - self.last_shot < SHOT_GAP:
                return True
            self.last_shot = now
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
        elif t in STAIRS:
            self.take_stairs(STAIRS[t])
            return
        elif t == ",":
            self.squash_rat(nx, ny)
        elif t == "?" and b.info.get("box") and not b.info.get("box_open"):
            b.info["box_open"] = True                   # this box was hiding a key!
            k = b.info["box"]
            b.set(nx, ny, k)
            self.snd.surprise()
            self.burst(nx, ny, 40, [KEY_COLORS[k], WHITE])
            self.say("SURPRISE! A %s KEY was inside the box!" % KEYS[k].upper(), KEY_COLORS[k], 4)
            return
        elif t == "?":
            b.set(nx, ny, " ")
            self.surprise(nx, ny)
        elif t == "E":
            self.catch_leprechaun(nx, ny)
            return
        elif t == "K":
            self.meet_king(nx, ny)
            return
        elif t == "Q":
            self.meet_queen(nx, ny)
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

    def meet_king(self, x, y):
        """The Leprechaun King swaps the Golden Crown for gold."""
        self.snd.talk()
        if self.crown:
            self.say_box("Leprechaun King", "Off you go! Queen Maeve is in the Fairy Glade, west of the forest.")
        elif self.gold >= KING_PRICE:
            self.gold -= KING_PRICE
            self.crown = True
            self.score += 200
            self.snd.leprechaun()
            self.burst(x, y, 50, [YELLOW, GREEN, WHITE], "$*+")
            self.say_box("Leprechaun King", "%d gold coins! A fair trade. Here is the GOLDEN CROWN! "
                         "Take it to Queen Maeve in the Fairy Glade." % KING_PRICE)
        else:
            self.say_box("Leprechaun King", "Hee hee! I have the Golden Crown. I want %d GOLD for it. "
                         "You have %d. Catch leprechauns! Find gold!" % (KING_PRICE, self.gold))

    def meet_queen(self, x, y):
        """Queen Maeve sends the crown home, and that wins Level 4."""
        self.snd.talk()
        if not self.crown:
            self.say_box("Queen Maeve", "Hello, brave one! The Leprechaun King has the Golden Crown. "
                         "Bring it to me, and my magic will send it home.")
            return
        self.crown = False
        self.score += 500
        self.burst(x, y, 60, [MAGENTA, YELLOW, WHITE, CYAN], "*+.")
        self.snd.fairy()
        self.finish_level()
        self.snd.win()

    def open_door(self, x, y, t):
        """A door can be several squares wide; open all of it."""
        todo = [(x, y)]
        while todo:
            cx, cy = todo.pop()
            if 0 <= cx < BOARD_W and 0 <= cy < BOARD_H and self.board.at(cx, cy) == t:
                self.board.set(cx, cy, " ")
                todo += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]

    def take_stairs(self, way):
        """Down the stairs (or the well), or back up: you come out at the other board's way back."""
        name = self.board.exits.get(way)
        if name not in self.boards:
            return
        nb = self.boards[name]
        back = "<" if way == "down" else ">"
        spots = [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if nb.at(x, y) == back]
        if spots:
            sx, sy = spots[0]
        else:
            sx, sy = nb.start or (BOARD_W // 2, BOARD_H // 2)
        free = [(sx + dx, sy + dy) for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1))
                if 0 <= sx + dx < BOARD_W and 0 <= sy + dy < BOARD_H and nb.at(sx + dx, sy + dy) in WALKABLE]
        self.board = nb
        self.px, self.py = free[0] if free else (sx, sy)
        self.entry = (self.px, self.py)
        self.zaps = []
        self.boulders_home()
        self.snd.whoosh()
        self.say("~ %s ~%s" % (nb.title, "  (it's dark down here!)" if nb.dark and not self.lamp else ""), YELLOW, 2.5)

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
        self.birds = []
        for x, y in b.crow_homes:                   # and the crows come back to their trees
            if b.at(x, y) == " " and (x, y) != (self.px, self.py):
                b.set(x, y, "V")

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

    def scatter(self, x, y):
        """WHOOSH! A crow takes fright, and the whole flock near it flies away."""
        b = self.board
        flock, todo = set(), [(x, y)]
        while todo:
            cx, cy = todo.pop()
            if (cx, cy) in flock:
                continue
            flock.add((cx, cy))
            todo += [(fx, fy) for fy in range(max(0, cy - 3), min(BOARD_H, cy + 4))
                     for fx in range(max(0, cx - 6), min(BOARD_W, cx + 7)) if b.at(fx, fy) == "V"]
        for fx, fy in flock:
            b.set(fx, fy, " ")
            away_x = fx - self.px or random.choice((-1, 1))
            dist = max(1.0, math.hypot(away_x, fy - self.py))
            self.birds.append([float(fx), float(fy), away_x / dist * random.uniform(14, 22) + random.uniform(-4, 4),
                               -random.uniform(5, 9), random.random()])
        self.snd.caw()
        self.say("CAW! CAW! WHOOSH!" if len(flock) > 1 else "CAW!", WHITE, 1.5)

    def vanish(self, x, y):
        """A witch cackles and vanishes in a puff of smoke... leaving ammo behind."""
        self.board.set(x, y, "a")
        self.score += 20
        self.snd.cackle()
        self.burst(x, y, 25, [MAGENTA, GREEN, WHITE], "*+.o")
        self.say("Hee hee hee! POOF! The witch left you some zaps!", MAGENTA, 2.5)

    def squash_rat(self, x, y):
        self.board.set(x, y, " ")
        self.score += 10
        self.snd.squeak()
        self.burst(x, y, 8, [ORANGE, WHITE], ".,")
        self.say("SQUEAK! Squished a rat!", ORANGE, 1.5)

    def nibble(self):
        """A rat nibbles you and runs off with a gold coin, or a gem."""
        now = time.time()
        if now - self.nibbled_at < RAT_NIBBLE:
            return
        self.nibbled_at = now
        self.snd.squeak()
        if self.gold:
            self.gold -= 1
            self.say("Nibble nibble! A rat took a GOLD coin! Step on it!", ORANGE, 2.5)
        elif self.gems:
            self.gems -= 1
            self.say("Nibble nibble! A rat took a GEM! Step on it!", ORANGE, 2.5)
        else:
            self.say("Nibble nibble! (Nothing to steal. Silly rat!)", ORANGE, 2)

    def zap_hit(self, x, y):
        """A zap hits whatever is here. Returns True if it should stop flying."""
        b = self.board
        t = b.at(x, y)
        if t == "A":
            self.vanish(x, y)
            return True
        if t == ",":
            self.squash_rat(x, y)
            return True
        if t == "V":
            self.scatter(x, y)
            return True
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
        if now >= self.next_crow:
            self.next_crow = now + CROW_STEP
            for x, y in [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "V"]:
                if b.at(x, y) == "V" and abs(x - self.px) * 0.5 + abs(y - self.py) <= CROW_FRIGHT:
                    self.scatter(x, y)
        for x, y in [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == "A"]:
            if abs(x - self.px) * 0.5 + abs(y - self.py) <= WITCH_FRIGHT:
                self.vanish(x, y)
        if now >= self.next_rat:
            self.next_rat = now + RAT_STEP
            for x, y in [(x, y) for y in range(BOARD_H) for x in range(BOARD_W) if b.at(x, y) == ","]:
                if b.at(x, y) != ",":
                    continue
                ddx, ddy = self.px - x, self.py - y
                if abs(ddx) + abs(ddy) <= 7 and random.random() < 0.5:          # sniff sniff... gold!
                    step = ((ddx > 0) - (ddx < 0), 0) if abs(ddx) > abs(ddy) else (0, (ddy > 0) - (ddy < 0))
                elif random.random() < 0.6:
                    step = random.choice(list(DIRS.values()))
                else:
                    continue
                tx, ty = x + step[0], y + step[1]
                if (tx, ty) == (self.px, self.py):
                    self.nibble()
                    away = [(x - step[0], y - step[1])]               # and scurry off
                    for ax, ay in away:
                        if 0 <= ax < BOARD_W and 0 <= ay < BOARD_H and b.at(ax, ay) == " ":
                            b.set(x, y, " ")
                            b.set(ax, ay, ",")
                elif 0 <= tx < BOARD_W and 0 <= ty < BOARD_H and b.at(tx, ty) == " ":
                    b.set(x, y, " ")
                    b.set(tx, ty, ",")
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
                    if 0 <= sx < BOARD_W and 0 <= sy < BOARD_H and b.at(sx, sy) in "LHE,A":
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
        if t == "K":
            return "K", color(GREEN if int(now * 2) % 3 else YELLOW)
        if t == "Q":
            return "Q", color(MAGENTA if int(now * 3) % 3 else WHITE)
        if t == "&":
            return L["&"], color(GREEN, False)
        if t == "A":
            return "A", color(MAGENTA if int(now * 3) % 4 else GREEN)
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
            put(scr, oy + y, ox + x, "•" if self.look is not PLAIN else ("-" if dx else "|"), color(WHITE))
        dt = min(0.1, now - getattr(self, "last_draw", now))
        self.last_draw = now
        for p in self.parts:                             # sparkles
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 8 * dt
            if 0 <= p[0] < BOARD_W and 0 <= p[1] < BOARD_H:
                put(scr, oy + int(p[1]), ox + int(p[0]), p[5], color(p[6]))
        self.parts = [p for p in self.parts if p[4] > now][-300:]
        for bird in self.birds:                          # crows flying away, flapping
            bird[0] += bird[2] * dt
            bird[1] += bird[3] * dt
            bird[4] += dt * 6
            if 0 <= bird[0] < BOARD_W and 0 <= bird[1] < BOARD_H:
                put(scr, oy + int(bird[1]), ox + int(bird[0]), "v" if int(bird[4]) % 2 else "^", color(WHITE))
        self.birds = [bd for bd in self.birds if 0 <= bd[0] < BOARD_W and 0 <= bd[1] < BOARD_H]
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
        if self.crown:
            put(self.scr, y + 11, x, "  Crown", on_blue(WHITE))
            put(self.scr, y + 11, x + 9, self.look["!"], on_blue(RAINBOW[int(now * 6) % len(RAINBOW)]))
        for i, line in enumerate(textwrap.wrap(self.board.title, 17)[:2]):
            put(self.scr, y + 12 + i, x + 2, line, on_blue(CYAN))
        put(self.scr, y + 15, x, "  LEVEL %d" % self.level, on_blue(YELLOW))
        for r, text in ((17, "  Arrows  walk"), (18, "  (hold to run!)"), (19, "  Space   zap"), (20, "  Esc     quit")):
            put(self.scr, y + r, x, text, on_blue(WHITE, False))

    def draw_levels(self, ox, oy, now):
        """The save screen: one big card per open level, a star on each finished one."""
        title = "PICK A LEVEL"
        put(self.scr, oy + 1, ox + (SCREEN_W - len(title)) // 2, title, color(RAINBOW[int(now * 3) % len(RAINBOW)]))
        opened = self.open_levels()
        cards = opened + [lv for lv in self.levels if lv > max(opened)][:1]   # and the next locked one
        if len(cards) > 5:                                    # only five fit: slide along with the pick
            first = min(max(0, self.level_pick - 2), len(cards) - 5)
            cards = cards[first:first + 5]
        cw, gap = 14, 2
        x0 = ox + (SCREEN_W - (len(cards) * (cw + gap) - gap)) // 2
        star = self.look["star"]
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
                put(self.scr, y + 2 + r, x + (cw - 10) // 2, row.replace("#", "██" if self.look is not PLAIN else "##").replace(" ", "  "),
                    color(WHITE if locked else RAINBOW[(lv * 2) % len(RAINBOW)], not locked))
            if lv in self.progress["done"]:
                put(self.scr, y + 8, x + (cw - 5) // 2, (star + " ") * 3, color(YELLOW))
            elif str(lv) in self.progress["slots"]:
                put(self.scr, y + 8, x + 2, "playing...".center(cw - 4), color(GREEN))
            name = "?" if locked else self.levels[lv][0]
            for r, line in enumerate(textwrap.wrap(name, cw)[:2]):        # long names get two lines
                put(self.scr, y + 11 + r, x + (cw - len(line)) // 2, line, color(WHITE if locked else col))
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
            if os.environ.get("TERM") == "linux" and sys.stdout.isatty():
                sys.stdout.write("\033[?8h")             # key repeat on (the kids' console has it off), so holding runs
                sys.stdout.flush()
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue
    if os.environ.get("TERM") == "linux" and sys.stdout.isatty():
        sys.stdout.write("\033[?8l")                     # and back off, like the rest of the kids' console
    print("Your quest is saved. See you next time, explorer!")
