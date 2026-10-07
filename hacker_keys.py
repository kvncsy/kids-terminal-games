#!/usr/bin/env python3
"""
HACKER KEYS - a keyboard-mashing toy for kids.

Every letter shows a big ASCII word (C -> CAT), a picture, and hacker effects.
Little robot buddies walk around, cheer, and (rarely) pop open umbrellas.

  Letters  -> word + picture
  Letters never repeat until every word for that letter has been seen.
  Numbers  -> shows the number big, and adds that many POINTS to the corner counter
  000      -> reset points to zero (points are saved in ~/.hacker_keys_points)
  SPACE    -> ACCESS GRANTED (or DENIED!)
  ENTER    -> hack the mainframe progress bar
  Anything else -> sparks

EXIT: press Esc.
Ctrl+C / Ctrl+Z are captured so little hands can't quit by accident.

Usage:  python3 hacker_keys.py
Tip: run your terminal full-screen (F11), e.g.
     gnome-terminal --full-screen -- python3 ~/hacker_keys.py
"""
import argparse
import curses
import json
import locale
import os
import random
import time
from collections import deque

# ---------------------------------------------------------------- font (5x5)
FONT_RAW = {
    "A": " ### |#   #|#####|#   #|#   #",
    "B": "#### |#   #|#### |#   #|#### ",
    "C": " ####|#    |#    |#    | ####",
    "D": "#### |#   #|#   #|#   #|#### ",
    "E": "#####|#    |#### |#    |#####",
    "F": "#####|#    |#### |#    |#    ",
    "G": " ####|#    |#  ##|#   #| ####",
    "H": "#   #|#   #|#####|#   #|#   #",
    "I": "#####|  #  |  #  |  #  |#####",
    "J": "#####|   # |   # |#  # | ##  ",
    "K": "#   #|#  # |###  |#  # |#   #",
    "L": "#    |#    |#    |#    |#####",
    "M": "#   #|## ##|# # #|#   #|#   #",
    "N": "#   #|##  #|# # #|#  ##|#   #",
    "O": " ### |#   #|#   #|#   #| ### ",
    "P": "#### |#   #|#### |#    |#    ",
    "Q": " ### |#   #|# # #|#  # | ## #",
    "R": "#### |#   #|#### |#  # |#   #",
    "S": " ####|#    | ### |    #|#### ",
    "T": "#####|  #  |  #  |  #  |  #  ",
    "U": "#   #|#   #|#   #|#   #| ### ",
    "V": "#   #|#   #|#   #| # # |  #  ",
    "W": "#   #|#   #|# # #|## ##|#   #",
    "X": "#   #| # # |  #  | # # |#   #",
    "Y": "#   #| # # |  #  |  #  |  #  ",
    "Z": "#####|   # |  #  | #   |#####",
    "0": " ### |#  ##|# # #|##  #| ### ",
    "1": "  #  | ##  |  #  |  #  | ### ",
    "2": " ### |#   #|  ## | #   |#####",
    "3": "#### |    #| ### |    #|#### ",
    "4": "#   #|#   #|#####|    #|    #",
    "5": "#####|#    |#### |    #|#### ",
    "6": " ### |#    |#### |#   #| ### ",
    "7": "#####|    #|   # |  #  |  #  ",
    "8": " ### |#   #| ### |#   #| ### ",
    "9": " ### |#   #| ####|    #| ### ",
    "-": "     |     |#####|     |     ",
    "!": "  #  |  #  |  #  |     |  #  ",
    " ": "     |     |     |     |     ",
}
FONT = {k: v.split("|") for k, v in FONT_RAW.items()}

# ---------------------------------------------------------------- words + art
# Short-vowel phonics words. Base list: keepkidsreading.net CVC word lists,
# filtered for kid-friendly words and topped up for letters it lacks.
WORDS = {
    "A": "ant ax add ask and am at an act",
    "B": "bag bat bed beg bib big bin bug bun bus box bell belt bump bud",
    "C": "cab can cap cat clam cot cub cup cut crab clap camp",
    "D": "dad dam den dig dip dog dot drip drop dug duck drum doll desk dust",
    "E": "egg elf elk end exit",
    "F": "fan fed fig fin fit fox fog fun fish flag flap flat flip flop frog fast",
    "G": "gap get glad grab grin grip grub gum gift gulp gust",
    "H": "ham hat hen hid hip hit hog hop hot hug hum hut hub hand hill",
    "I": "in it if ink inch imp",
    "J": "jam jet jig job jog jug jump",
    "K": "kid kit kick kiss kelp",
    "L": "lab lap leg lid lip log lamp lift lock",
    "M": "man map mat men mix mop mud mug milk mask mint",
    "N": "nap net nut nod nest neck",
    "O": "ox on off odd",
    "P": "pad pan pat peg pen pet pig pin pit pop pot pup plan plug plum pond pink",
    "Q": "quiz quit quack quilt",
    "R": "rag ram ran rat red rib rip rug rub run rock raft rest ring",
    "S": "sad sat sip sit sub sun sock sand six skip sled slip slug snip spin swim skin stop step",
    "T": "tag tap ten tin tip top tub tug tent trap trip tusk",
    "U": "up us ugh um",
    "V": "van vet vest vat",
    "W": "wag web wet wig win wax well wish wink",
    "X": "box fox six mix fix wax",
    "Y": "yes yak yam yell yum yuck",
    "Z": "zip zap zigzag",
}
WORDS = {k: v.upper().split() for k, v in WORDS.items()}
IN_WORD_LETTERS = {"X"}  # no kid words start with X, so use words with X inside
SOUND_CHUNKS = ("QU", "CK", "SH", "CH", "TH", "LL", "SS", "FF", "ZZ", "NG")


def sound_chunks(word):
    """Split a word into sounds: DUCK -> D U CK."""
    out, i = [], 0
    while i < len(word):
        if word[i:i + 2] in SOUND_CHUNKS:
            out.append(word[i:i + 2])
            i += 2
        else:
            out.append(word[i])
            i += 1
    return out


def art(s):
    lines = s.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


ART = {
    "ANT": r"""
   \  /
    \/     ___    ____
   (oo)---(   )--(    )
   /||\   /| |\   /||\
""",
    "BUG": r"""
     \   /
      (oo)
   /--(  )--\
   \--(  )--/
   /--(__)--\
""",
    "BAT": r"""
  /\                 /\
 /  \'._  (\_/)  _.'/  \
|.''._'--(o.o)--'_.''.|
 \_ / `;=/ " \=;` \ _/
   `\__| \___/ |__/`
""",
    "BUS": r"""
  _________________
 |  _   _   _   _  |\
 | |_| |_| |_| |_| | |
 |_________________|_|
   (O)          (O)
""",
    "BED": r"""
 _                 _
| |_______________| |
| | (__)          | |
| |_______________| |
|_|               |_|
""",
    "BOX": r"""
    ________
   /       /|
  /_______/ |
  |       | |
  |  BOX  | /
  |_______|/
""",
    "BAG": r"""
     ____
    /    \
  _|______|_
 |          |
 |   BAG    |
 |__________|
""",
    "BELL": r"""
      _
     (_)
    /   \
   /     \
  /_______\
      O
""",
    "CAT": r"""
   /\_/\
  ( o.o )
   > ^ <
  /     \
 (_|   |_)
""",
    "CUP": r"""
     ( (
      ) )
   ........
   |      |]
   \      /
    `----'
""",
    "CAP": r"""
       _____
     /       \
    |    o    |
  __|_________|
  \___________|
""",
    "CRAB": r"""
  (\/)     (\/)
   \/  .-.  \/
    \_(o o)_/
    /_(___)_\
     /  |  \
""",
    "DOG": r"""
    / \__
   (    @\___
   /         O
  /   (_____/
 /_____/   U
""",
    "DUCK": r"""
     __
   <(o )___
    ( ._> /
     `---'
  ~~~~~~~~~~~
""",
    "DRUM": r"""
  \\       //
   \\_____//
   (_______)
   |\/\/\/\|
   |/\/\/\/|
   (_______)
""",
    "EGG": r"""
    .-""-.
   /      \
  |        |
  |        |
   \      /
    '-..-'
""",
    "ELF": r"""
      *
     / \
    /   \
   (o . o)
    \ ~ /
    /| |\
""",
    "FOX": r"""
  /\   /\
 //\\_//\\
 \_     _/
  / * * \
  \_\O/_/
""",
    "FISH": r"""
       ,-.
    ,-'   '-.  /|
   (  o      )< |
    '-.   ,-'  \|
       '-'
""",
    "FROG": r"""
     @..@
    (----)
   ( >__< )
   ^^ ~~ ^^
""",
    "FAN": r"""
     .-.
   .'   '.
  ( ( + ) )
   '.   .'
     '|'
     _|_
""",
    "GUM": r"""
     .----.
    /  o   \
   |  GUM   |
    \      /
     '----'
""",
    "HAT": r"""
       _____
      |     |
      |     |
   ___|_____|___
  (_____________)
""",
    "HUT": r"""
       /\
      /  \
     /    \
    /______\
    |  __  |
    | |  | |
    |_|__|_|
""",
    "HEN": r"""
     ^^
   >(o)___
    ( ._> /
     `---'
      ^ ^
""",
    "INK": r"""
     ___
    |___|
    /   \
   | INK |
   |_____|
""",
    "JAM": r"""
    _______
   [_______]
   |       |
   |  JAM  |
   |_______|
""",
    "JET": r"""
           |
           |
  ------ _/ \_ ------
   ---o--(_o_)--o---
          / \
""",
    "JUG": r"""
     ___
    |   |
   /     \_
  |       \\
  |  JUG  |/
   \_____/
""",
    "KID": r"""
     (^_^)
     --|--
       |
      / \
     /   \
""",
    "LOG": r"""
    ______________
   /             /\
  (  o          (  )
   \_____________\/
""",
    "LAMP": r"""
     ______
    /      \
   /________\
       ||
       ||
     __||__
    |______|
""",
    "MOP": r"""
       ||
       ||
       ||
       ||
      /||\
     //||\\
    ///||\\\
""",
    "MUG": r"""
    _____
   |     |__
   |     |  |
   |     |__|
   |_____|
""",
    "MILK": r"""
     ____
    /____\
   |      |
   | MILK |
   |      |
   |______|
""",
    "MAP": r"""
   ___________
  |  ~~   X   |
  | ~  ---'   |
  |   /    ~~ |
  |__/________|
""",
    "NET": r"""
   |\/\/\/\/\/|
   |/\/\/\/\/\|
   |\/\/\/\/\/|
   |/\/\/\/\/\|
""",
    "NUT": r"""
    .---.
   /     \
  |  (O)  |
   \     /
    '---'
""",
    "NEST": r"""
    (o) (o) (o)
   \~~~~~~~~~~~/
    \~~~~~~~~~/
     '-------'
""",
    "OX": r"""
  \\_____//
    (o o)
     \ /
     (_)
""",
    "PIG": r"""
    ^...^
   / o o \
  |  (oo) |
   \ ~~~ /
    \___/
""",
    "POT": r"""
    ________
   (________)
   |        |
   |        |
    \______/
""",
    "PEN": r"""
   _____________________
  |_|___________________|>
""",
    "PAN": r"""
    ______
   /      \
  |        |==========
   \______/
""",
    "PUP": r"""
    __
  o-''|\_____/)
   \_/|_)     )
      \  __  /
      (_/ (_/
""",
    "QUIZ": r"""
    ___
   / _ \
  |_| | |
     / /
    |_|
     _
    (_)
""",
    "RAT": r"""
     (\_/)
     (o.o)
     (> <)~~~~
""",
    "RUG": r"""
  ~~~~~~~~~~~~~~~
  |:::::::::::::|
  |:::|RUG|:::::|
  |:::::::::::::|
  ~~~~~~~~~~~~~~~
""",
    "SUN": r"""
      \   |   /
    '.  \ | /  .'
  ---  ( o o )  ---
    .'  \___/  '.
      /   |   \
""",
    "SUB": r"""
          __|__
    _____/  o  \_____
   (  o    o    o    )>
    \_______________/
""",
    "SOCK": r"""
    ____
   |    |
   |    |
   |    |__
   |       \
    \______/
""",
    "SLED": r"""
   ___________
  |___________|
   ||       ||
 __||_______||__
 \_____________/
""",
    "SIX": r"""
   _______
  | o   o |
  | o   o |
  | o   o |
   -------
""",
    "TOP": r"""
      |
    __|__
   /     \
  <=======>
   \     /
    \   /
     \ /
      V
""",
    "TENT": r"""
       /\
      /  \
     / /\ \
    / /  \ \
   /_/____\_\
""",
    "TUB": r"""
          ____
   o O   |
  _o_O___|___
 |           |
  \_________/
   ||     ||
""",
    "UP": r"""
      /\
     /  \
    /    \
   /_    _\
     |  |
     |  |
     |__|
""",
    "VAN": r"""
   ______________
  |  |   |   |   \
  |__|___|___|____\
  |          _    |
  '-(O)-----(O)---'
""",
    "WEB": r"""
   \ \   |   / /
    \ \--+--/ /
   --+--(*)--+--
    / /--+--\ \
   / /   |   \ \
""",
    "WIG": r"""
    .-~~~-.
   (~~~~~~~)
   (~  .  ~)
   (~~   ~~)
""",
    "YAK": r"""
   \__/
   (oo)\_______
   (__)\       )\/\
       ||----w |
       ||     ||
""",
    "ZAP": r"""
      _
     / /
    / /_
   /_  /
    / /
   //
   /
""",
    "ZIP": r"""
   |  |
   |[]|
   |><|
   |><|
   |><|
   |><|
""",
}
ART = {k: art(v) for k, v in ART.items()}

NUM_NAMES = ["ZERO", "ONE", "TWO", "THREE", "FOUR",
             "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]

# ---------------------------------------------------------------- robot buddies
ROBOT_WALK = [
    ["  _|_  ", " [o_o] ", " /|_|\\ ", "  / \\  "],
    ["  _|_  ", " [o_o] ", " \\|_|/ ", "  | |  "],
]
ROBOT_HAPPY = ["  _|_  ", " [^_^] ", " \\|_|/ ", "  / \\  "]
ROBOT_WOW = ["  _*_  ", " [O_O] ", " \\|_|/ ", "  | |  "]
ROBOT_UMBRELLA = [
    ["   |   ", " [o_o] ", " /|_|  ", "  / \\  "],
    ["   |   ", " [o_o] ", " /|_|  ", "  | |  "],
]
UMBRELLA = [" .-^-. ", "/_/_\\_\\"]
ROBOT_H = 4
ROBOT_W = 7
ROBOT_NAMES = ["CLAUDE", "BEEP", "BOOP", "ZIGGY", "BOLT"]
ROBOT_CHEERS = ["WOW!", "BEEP!", "YAY!", "COOL!", "HACK!", "NICE!", "WHOA!"]
UMBRELLA_CHANCE = 1 / 300   # per robot, per second -> about once a minute total

# ---------------------------------------------------------------- silly log lines
AMBIENT = [
    "scanning the cookie jar ... 3 cookies found",
    "bypassing dinosaur firewall ... ROAR",
    "downloading more RAM ... done",
    "uploading pizza.exe ... 100%",
    "robots reporting for duty ... beep boop",
    "pinging the moon ... 1.3 sec",
    "encrypting socks ... smelly",
    "counting stars ... too many",
    "charging laser ... pew pew",
    "decoding secret banana code ... OK",
    "calibrating rocket boots ... ready",
    "teaching robots to dance ... success",
    "hacking the mainframe ... almost",
    "searching for lost LEGO ... ouch",
    "checking the weather ... umbrellas ready",
]
HACK_TARGETS = [
    "THE MAINFRAME", "THE MOON", "THE COOKIE JAR", "A SPACE STATION",
    "THE DINOSAUR MUSEUM", "THE ICE CREAM TRUCK", "ROBOT HEADQUARTERS",
]

RAIN_CHARS_ASCII = "0123456789ABCDEF$#%&*+<>"
RAIN_CHARS_UTF = RAIN_CHARS_ASCII + "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎ"
SPARK_CHARS = "*+x.o#@%&~^"
VOWELS = set("AEIOU")

POINTS_FILE = os.path.expanduser("~/.hacker_keys_points")
POINTS_MILESTONE = 50
MAX_TERMS = 1000        # how many pressed numbers to remember

# calculator-style digits for the always-on counter
SEG = {
    "0": [" _ ", "| |", "|_|"], "1": ["   ", "  |", "  |"], "2": [" _ ", " _|", "|_ "],
    "3": [" _ ", " _|", " _|"], "4": ["   ", "|_|", "  |"], "5": [" _ ", "|_ ", " _|"],
    "6": [" _ ", "|_ ", "|_|"], "7": [" _ ", "  |", "  |"], "8": [" _ ", "|_|", "|_|"],
    "9": [" _ ", "|_|", " _|"],
}

# color pair ids
RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]


def put(win, y, x, s, attr=0):
    """addstr that never crashes on edges."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w or not s:
        return
    if x < 0:
        s = s[-x:]
        x = 0
    s = s[: w - x]
    if y == h - 1 and x + len(s) >= w:
        s = s[: w - x - 1]
    if s:
        try:
            win.addstr(y, x, s, attr)
        except curses.error:
            pass


def load_score():
    """Returns (points, terms). terms = the numbers pressed, for the big sum."""
    try:
        with open(POINTS_FILE) as f:
            data = json.loads(f.read())
    except (OSError, ValueError):
        return 0, []
    if isinstance(data, int):          # old format: just the total
        return max(0, data), [data] if data > 0 else []
    try:
        return max(0, int(data["points"])), [int(t) for t in data["terms"]]
    except (KeyError, TypeError, ValueError):
        return 0, []


def save_score(points, terms):
    try:
        with open(POINTS_FILE, "w") as f:
            json.dump({"points": points, "terms": terms[-MAX_TERMS:]}, f)
    except OSError:
        pass


class Robot:
    def __init__(self, x, name):
        self.x = float(x)
        self.dir = random.choice([-1, 1])
        self.speed = random.uniform(4, 9)
        self.name = name
        self.jump_t = -10.0
        self.bubble = ""
        self.bubble_until = 0.0
        self.color = random.choice([ORANGE, ORANGE, CYAN, MAGENTA, YELLOW])
        self.umbrella_until = 0.0
        self.umbrella_color = RED

    def cheer(self, now, text=None):
        self.jump_t = now + random.uniform(0, 0.15)
        if text or random.random() < 0.5:
            self.bubble = text or random.choice(ROBOT_CHEERS)
            self.bubble_until = now + 1.5


class App:
    def __init__(self, scr, args):
        self.scr = scr
        self.typed = ""
        self.utf = locale.getpreferredencoding().lower().replace("-", "") == "utf8"
        self.block = "█" if self.utf else "#"
        # the plain Linux text console font has no Japanese characters
        fancy = self.utf and os.environ.get("TERM") != "linux"
        self.rain_chars = RAIN_CHARS_UTF if fancy else RAIN_CHARS_ASCII
        self.drops = []
        self.rain_w = 0
        self.sparks = []
        self.robots = []
        self.log = deque(maxlen=50)
        self.next_ambient = 0.0
        self.scene = None
        self.mode = None  # None | "hack" | "granted" | "denied"
        self.mode_t = 0.0
        self.hack_target = ""
        self.decks = {}       # letter -> words not yet shown this session
        self.last_word = {}
        self.points, self.terms = load_score()
        self.shown_points = self.points   # counts up toward points, like an odometer
        self.points_flash_until = 0.0
        self.add_log("KID-HACK OS booted. Press any key, agent!")
        self.set_scene("HI!", ["  Press a letter!  "], "WELCOME, AGENT", time.time())

    # ------------------------------------------------------------ helpers
    def add_log(self, text):
        self.log.append(time.strftime("%H:%M:%S ") + text)

    def attr(self, pair, bold=True):
        return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)

    def set_scene(self, word, picture, caption, now, sounds=None):
        pixels = []
        for i, ch in enumerate(word):
            glyph = FONT.get(ch, FONT[" "])
            for r, row in enumerate(glyph):
                for c, px in enumerate(row):
                    if px == "#":
                        settle = now + random.uniform(0.05, 0.45) + i * 0.08
                        pixels.append((i, r, c, settle))
        self.scene = {
            "word": word, "art": picture, "caption": caption, "t0": now,
            "pixels": pixels, "sounds": sounds,
            "art_color": random.choice([YELLOW, CYAN, MAGENTA, WHITE]),
        }

    # ------------------------------------------------------------ input
    def handle_key(self, key, now):
        if isinstance(key, str):
            if key == "\x1b":     # Esc quits
                return False
            self.typed = (self.typed + key)[-20:]
            ch = key.upper()
            if ch in WORDS:
                self.mode = None
                self.show_letter(ch, now)
            elif ch.isdigit() and len(ch) == 1:
                self.mode = None
                if self.typed.endswith("000"):
                    self.typed = ""
                    self.reset_points(now)
                else:
                    self.show_number(int(ch), now)
            elif key == " ":
                self.mode = "granted" if random.random() < 0.75 else "denied"
                self.mode_t = now
                self.add_log("> authenticating ... " +
                             ("ACCESS GRANTED" if self.mode == "granted" else "ACCESS DENIED (try again!)"))
                for r in self.robots:
                    r.cheer(now, "YES!" if self.mode == "granted" else "UH OH!")
            elif key in "\n\r":
                self.mode = "hack"
                self.mode_t = now
                self.hack_target = random.choice(HACK_TARGETS)
                self.add_log("> initiating hack of " + self.hack_target + " ...")
                for r in self.robots:
                    r.cheer(now, "HACK!")
            else:
                self.add_log("> unknown signal [%r] ... sparks!" % key)
                self.burst(now, 40)
        elif key != curses.KEY_RESIZE:
            self.add_log("> special key intercepted ... sparks!")
            self.burst(now, 40)
        return True

    def next_word(self, ch):
        """Deal words like cards: no repeats until every word for the letter is used."""
        deck = self.decks.get(ch)
        if not deck:
            if ch in self.decks:
                self.add_log("> ALL %s WORDS FOUND! shuffling them again ..." % ch)
            deck = WORDS[ch][:]
            random.shuffle(deck)
            if len(deck) > 1 and deck[-1] == self.last_word.get(ch):
                deck.insert(0, deck.pop())
            self.decks[ch] = deck
        word = deck.pop()
        self.last_word[ch] = word
        return word

    def show_letter(self, ch, now):
        word = self.next_word(ch)
        picture = ART.get(word, [])
        link = "is in" if ch in IN_WORD_LETTERS else "is for"
        self.set_scene(word, picture, "%s %s %s" % (ch, link, word), now,
                       sounds=None if picture else sound_chunks(word))
        self.add_log("> key [%s] intercepted ... decrypting '%s' ... OK" % (ch, word))
        self.burst(now, 25)
        if self.robots:
            random.choice(self.robots).cheer(now, word + "!")
            for r in self.robots:
                if random.random() < 0.6:
                    r.cheer(now)

    def show_number(self, n, now):
        old = self.points
        self.points += n
        self.terms = (self.terms + [n])[-MAX_TERMS:]
        save_score(self.points, self.terms)
        if n:
            self.points_flash_until = now + 1.0
        if n == 0:
            picture = ["  ( nothing! )  "]
        else:
            row = "[%s] " % self.block
            picture = [(row * min(5, n - i)).rstrip() for i in range(0, n, 5)]
        self.set_scene(str(n), picture, "%d = %s    +%d POINTS!" % (n, NUM_NAMES[n], n), now)
        self.add_log("> number [%d] ... +%d points ... total %d" % (n, n, self.points))
        self.burst(now, 25)
        if self.points // POINTS_MILESTONE > old // POINTS_MILESTONE:
            self.add_log("> *** %d POINTS! LEVEL UP! ***" % self.points)
            for r in self.robots:
                r.cheer(now, "%d POINTS!" % self.points)
            for _ in range(4):
                self.burst(now, 30)
        else:
            for r in self.robots:
                r.cheer(now, NUM_NAMES[n] + "!" if random.random() < 0.3 else None)

    def reset_points(self, now):
        self.points = self.shown_points = 0
        self.terms = []
        save_score(0, [])
        self.points_flash_until = now + 1.5
        self.set_scene("0", [], "POINTS RESET!", now)
        self.add_log("> points wiped ... starting over at 0")

    def burst(self, now, n):
        h, w = self.scr.getmaxyx()
        cx = random.uniform(w * 0.15, w * 0.85)
        cy = random.uniform(h * 0.2, h * 0.7)
        for _ in range(n):
            self.sparks.append([cx, cy, random.uniform(-30, 30), random.uniform(-12, 8),
                                now + random.uniform(0.4, 1.1),
                                random.choice(SPARK_CHARS), random.choice(RAINBOW)])

    # ------------------------------------------------------------ update
    def update(self, dt, now, h, w, floor_y):
        # matrix rain
        if w != self.rain_w:
            self.rain_w = w
            self.drops = [self.new_drop(h, True) for _ in range(max(1, w // 3))]
        for d in self.drops:
            d[1] += d[2] * dt
            if d[1] - d[3] > h:
                d[:] = self.new_drop(h, False)
        # sparks
        for s in self.sparks:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[3] += 25 * dt  # gravity
        self.sparks = [s for s in self.sparks if s[4] > now]
        # odometer: count up toward the real total
        if self.shown_points < self.points:
            step = max(1, int((self.points - self.shown_points) * 6 * dt))
            self.shown_points = min(self.points, self.shown_points + step)
        else:
            self.shown_points = self.points
        # robots
        want = max(1, min(5, w // 25))
        while len(self.robots) < want:
            name = ROBOT_NAMES[len(self.robots) % len(ROBOT_NAMES)]
            self.robots.append(Robot(random.uniform(0, max(1, w - ROBOT_W)), name))
        del self.robots[want:]
        for r in self.robots:
            umbrella = now < r.umbrella_until
            if not umbrella and random.random() < UMBRELLA_CHANCE * dt:
                r.umbrella_until = now + random.uniform(8, 15)
                r.umbrella_color = random.choice(RAINBOW)
                r.bubble, r.bubble_until = "RAIN!", now + 2
                self.add_log("> %s detected rain ... deploying umbrella" % r.name)
            r.x += r.dir * r.speed * (0.5 if umbrella else 1) * dt
            if r.x < 0:
                r.x, r.dir = 0, 1
            elif r.x > w - ROBOT_W:
                r.x, r.dir = w - ROBOT_W, -1
            elif random.random() < 0.2 * dt:
                r.dir = -r.dir
        # ambient log chatter
        if now > self.next_ambient:
            self.next_ambient = now + random.uniform(2.5, 5)
            self.add_log(random.choice(AMBIENT))

    def new_drop(self, h, anywhere):
        return [random.randrange(self.rain_w), random.uniform(-h, h) if anywhere else random.uniform(-10, 0),
                random.uniform(6, 22), random.randint(4, 14)]

    # ------------------------------------------------------------ drawing
    def draw(self, now):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        log_n = 4 if h > 24 else 2
        floor_y = h - log_n - 1          # line under the robots
        big_counter = h >= 30 and w >= 60
        top = 5 if big_counter else 1              # room for the points counter
        bottom = floor_y - ROBOT_H - 3             # room for umbrellas/bubbles

        self.update(1 / 30, now, h, w, floor_y)
        self.draw_rain(h, w, bottom)

        if self.mode == "hack":
            self.draw_hack(now, top, bottom, w)
        elif self.mode in ("granted", "denied"):
            self.draw_granted(now, top, bottom, w)
        else:
            self.draw_scene(now, top, bottom, w)

        for s in self.sparks:
            put(scr, int(s[1]), int(s[0]), s[5], self.attr(s[6]))
        self.draw_robots(now, floor_y, w)
        if big_counter:
            self.draw_counter(now, w)
        self.draw_header(now, w, show_points=not big_counter)
        self.draw_log(now, h, w, log_n)
        scr.refresh()

    def draw_header(self, now, w, show_points):
        title = " >> KID-HACK TERMINAL v4.2 << "
        right = " SECURITY: MAXIMUM  %s " % time.strftime("%H:%M:%S")
        bar = title + " " * max(0, w - len(title) - len(right)) + right
        put(self.scr, 0, 0, bar[:w], curses.color_pair(GREEN) | curses.A_REVERSE | curses.A_BOLD)
        if show_points:
            pts = " * POINTS: %d * " % self.shown_points
            flash = now < self.points_flash_until and int(now * 8) % 2
            put(self.scr, 0, max(len(title) + 1, (w - len(pts)) // 2), pts,
                self.attr(WHITE if flash else YELLOW) | curses.A_REVERSE)

    def draw_counter(self, now, w):
        """Always-on calculator-style points display, top right."""
        digits = str(self.shown_points)
        rows = [" ".join(SEG[d][r] for d in digits) for r in range(3)]
        width = max(len(rows[0]), 8) + 4
        x = w - width - 2
        flash = now < self.points_flash_until and int(now * 8) % 2
        a = self.attr(WHITE if flash else YELLOW)
        self.clear_box(1, 5, x - 1, x + width + 1)
        put(self.scr, 1, x, " POINTS ".center(width), a | curses.A_REVERSE)
        for r, row in enumerate(rows):
            put(self.scr, 2 + r, x + (width - len(row)) // 2, row, a)

    def draw_log(self, now, h, w, n):
        sep = ("─" if self.utf else "-") * w
        put(self.scr, h - n - 1, 0, sep, self.attr(GREEN, False))
        lines = list(self.log)[-n:]
        for i, line in enumerate(lines):
            last = i == len(lines) - 1
            cursor = "_" if last and int(now * 2) % 2 else ""
            put(self.scr, h - n + i, 1, line + cursor, self.attr(GREEN, last))

    def draw_rain(self, h, w, bottom):
        dim = curses.color_pair(GREEN) | curses.A_DIM
        for x, y, _, length in self.drops:
            head = int(y)
            for i in range(length):
                yy = head - i
                if 1 <= yy <= bottom:
                    if i == 0:
                        a = self.attr(WHITE)
                    elif i < length // 3:
                        a = self.attr(GREEN)
                    else:
                        a = dim
                    put(self.scr, yy, x, random.choice(self.rain_chars), a)

    def pick_scale(self, text_len, avail_w, avail_h, extra_h):
        text_w = text_len * 6 - 1
        for sx, sy in ((4, 2), (3, 2), (2, 1), (1, 1)):
            if text_w * sx <= avail_w - 4 and 5 * sy + extra_h <= avail_h:
                return sx, sy
        return None

    def draw_big(self, text, y, w, sx, sy, now, pixels=None, colors=None):
        text_w = (len(text) * 6 - 1) * sx
        x0 = (w - text_w) // 2
        if pixels is None:
            pixels = [(i, r, c, 0) for i, ch in enumerate(text)
                      for r, row in enumerate(FONT.get(ch, FONT[" "]))
                      for c, px in enumerate(row) if px == "#"]
        shift = int(now * 3)
        for i, r, c, settle in pixels:
            if now < settle:
                ch, a = random.choice(self.rain_chars), self.attr(GREEN)
            else:
                pair = colors[i] if colors else RAINBOW[(i + shift) % len(RAINBOW)]
                ch, a = self.block, self.attr(pair)
            for dy in range(sy):
                put(self.scr, y + r * sy + dy, x0 + (i * 6 + c) * sx, ch * sx, a)
        return text_w

    def clear_box(self, y0, y1, x0, x1):
        blank = " " * max(0, x1 - x0)
        for y in range(y0, y1):
            put(self.scr, y, x0, blank)

    def draw_sounds(self, now, y, w, sounds, t0):
        """Sound-it-out boxes that light up one at a time, then all together."""
        widths = [len(s) + 4 for s in sounds]
        total = sum(widths) + len(sounds) - 1
        x = (w - total) // 2
        step = int(max(0, now - t0 - 0.6) * 1.5) % (len(sounds) + 2)
        hz, vt, tl, tr, bl, br = ("─", "│", "┌", "┐", "└", "┘") if self.utf else ("-", "|", "+", "+", "+", "+")
        for i, (s, bw) in enumerate(zip(sounds, widths)):
            lit = step == i or step == len(sounds)
            color = ORANGE if any(c in VOWELS for c in s) else CYAN
            a = self.attr(color) | (curses.A_REVERSE if lit else 0)
            put(self.scr, y, x, tl + hz * (bw - 2) + tr, self.attr(color))
            put(self.scr, y + 1, x, vt, self.attr(color))
            put(self.scr, y + 1, x + 1, " " + s + " ", a)
            put(self.scr, y + 1, x + bw - 1, vt, self.attr(color))
            put(self.scr, y + 2, x, bl + hz * (bw - 2) + br, self.attr(color))
            x += bw + 1

    def draw_scene(self, now, top, bottom, w):
        sc = self.scene
        avail_h = bottom - top + 1
        pic, sounds = sc["art"], sc["sounds"]
        body_h = len(pic) if pic else (3 if sounds else 0)
        extra = body_h + 3
        scale = self.pick_scale(len(sc["word"]), w, avail_h, extra)
        if scale is None:
            pic, sounds, extra = [], None, 2
            scale = self.pick_scale(len(sc["word"]), w, avail_h, extra) or (1, 1)
        sx, sy = scale
        total_h = 5 * sy + extra
        y = top + max(0, (avail_h - total_h) // 2)
        text_w = (len(sc["word"]) * 6 - 1) * sx
        body_w = max(len(l) for l in pic) if pic else (sum(len(s) + 5 for s in sounds) if sounds else 0)
        box_w = max(text_w, body_w, len(sc["caption"]) + 4) + 6
        bx = (w - box_w) // 2
        self.clear_box(y - 1, y + total_h + 1, bx, bx + box_w)

        self.draw_big(sc["word"], y, w, sx, sy, now, sc["pixels"])
        y += 5 * sy + 1

        if pic:
            # picture "types" itself in
            typed = int(max(0, now - sc["t0"] - 0.25) * 90)
            px = (w - max(len(l) for l in pic)) // 2
            for line in pic:
                shown = line[:typed]
                put(self.scr, y, px, shown, self.attr(sc["art_color"]))
                if 0 < typed < len(line):
                    put(self.scr, y, px + len(shown), self.block, self.attr(GREEN))
                typed -= len(line)
                y += 1
            y += 1
        elif sounds:
            self.draw_sounds(now, y, w, sounds, sc["t0"])
            y += 4

        # rainbow caption
        cap = sc["caption"]
        cx = (w - len(cap)) // 2
        for i, ch in enumerate(cap):
            put(self.scr, y, cx + i, ch, self.attr(RAINBOW[(i + int(now * 8)) % len(RAINBOW)]))

    def draw_hack(self, now, top, bottom, w):
        el = now - self.mode_t
        dur = 3.0
        if el > dur:
            self.mode, self.mode_t = "granted", now
            self.add_log("> " + self.hack_target + " HACKED! ACCESS GRANTED")
            for r in self.robots:
                r.cheer(now, "WE DID IT!")
            return self.draw_granted(now, top, bottom, w)
        pct = min(100, int(el / dur * 100))
        bw = min(50, w - 10)
        filled = int(bw * pct / 100)
        empty_ch = "░" if self.utf else "."
        lines = [
            ("HACKING " + self.hack_target + " ...", GREEN),
            ("", GREEN),
            ("[" + self.block * filled + empty_ch * (bw - filled) + "] %3d%%" % pct, CYAN),
            ("", GREEN),
            (" ".join("%02X" % random.randrange(256) for _ in range(min(16, (w - 10) // 3))), GREEN),
            (random.choice(["cracking password ...", "bypassing lasers ...", "asking robots nicely ...",
                            "rerouting power ...", "feeding the hamster ..."]) if int(el * 4) % 2 else "", YELLOW),
        ]
        y = top + max(0, (bottom - top - len(lines)) // 2)
        box_w = bw + 12
        bx = (w - box_w) // 2
        self.clear_box(y - 2, y + len(lines) + 2, bx, bx + box_w)
        self.draw_border(y - 2, y + len(lines) + 1, bx, bx + box_w - 1, GREEN)
        for i, (text, c) in enumerate(lines):
            put(self.scr, y + i, (w - len(text)) // 2, text, self.attr(c))

    def draw_granted(self, now, top, bottom, w):
        if now - self.mode_t > 2.2:
            self.mode = None
            return self.draw_scene(now, top, bottom, w)
        good = self.mode == "granted"
        words = ["ACCESS", "GRANTED" if good else "DENIED!"]
        flash = int(now * 6) % 2
        color = (GREEN if flash else WHITE) if good else (RED if flash else YELLOW)
        avail_h = bottom - top + 1
        scale = None
        for sx, sy in ((2, 1), (1, 1)):
            if 7 * 6 * sx <= w - 6 and 11 * sy + 1 <= avail_h:
                scale = (sx, sy)
                break
        if scale:
            sx, sy = scale
            total = 10 * sy + 1
            y = top + (avail_h - total) // 2
            box_w = 7 * 6 * sx + 6
            bx = (w - box_w) // 2
            self.clear_box(y - 1, y + total + 1, bx, bx + box_w)
            self.draw_border(y - 1, y + total, bx, bx + box_w - 1, color)
            for k, word in enumerate(words):
                self.draw_big(word, y + k * (5 * sy + 1), w, sx, sy, now,
                              colors=[color] * len(word))
        else:
            text = " ".join(words)
            put(self.scr, (top + bottom) // 2, (w - len(text)) // 2, text,
                self.attr(color) | curses.A_REVERSE)

    def draw_border(self, y0, y1, x0, x1, color):
        a = self.attr(color)
        hz, vt, cs = ("═", "║", "╔╗╚╝") if self.utf else ("=", "|", "++++")
        put(self.scr, y0, x0, cs[0] + hz * (x1 - x0 - 1) + cs[1], a)
        put(self.scr, y1, x0, cs[2] + hz * (x1 - x0 - 1) + cs[3], a)
        for y in range(y0 + 1, y1):
            put(self.scr, y, x0, vt, a)
            put(self.scr, y, x1, vt, a)

    def draw_robots(self, now, floor_y, w):
        for r in self.robots:
            jt = now - r.jump_t
            jumping = 0 <= jt < 0.6
            umbrella = now < r.umbrella_until
            lift = int(round(3 * 4 * (jt / 0.6) * (1 - jt / 0.6))) if jumping else 0
            if umbrella:
                sprite = ROBOT_UMBRELLA[int(now * 2 + r.x) % 2]
            elif jumping:
                sprite = ROBOT_HAPPY if int(jt * 10) % 2 else ROBOT_WOW
            else:
                sprite = ROBOT_WALK[int(now * 4 + r.x) % 2]
            x = int(r.x)
            y0 = floor_y - ROBOT_H - lift
            for i, line in enumerate(sprite):
                pair = WHITE if i == 1 else r.color
                put(self.scr, y0 + i, x, line, self.attr(pair))
            if umbrella:
                for i, line in enumerate(UMBRELLA):
                    put(self.scr, y0 - 2 + i, x, line, self.attr(r.umbrella_color))
                for k in range(3):   # little raindrops bouncing off the umbrella
                    dy = int((now * 5 + k * 1.3) % 3)
                    put(self.scr, y0 - 5 + dy, x + 1 + k * 2, "'", self.attr(BLUE))
                bubble_y = y0 - 6
            else:
                # blinking antenna light
                put(self.scr, y0, x + 3, "*" if int(now * 3 + r.x) % 2 else "|",
                    self.attr(RED if int(now * 3) % 2 else YELLOW))
                bubble_y = y0 - 1
            if r.bubble and now < r.bubble_until:
                b = " " + r.bubble + " "
                bx = max(0, min(w - len(b), x + ROBOT_W // 2 - len(b) // 2))
                put(self.scr, bubble_y, bx, b, self.attr(r.color) | curses.A_REVERSE)
            elif not jumping and not umbrella:
                put(self.scr, y0 - 1, x, r.name[:ROBOT_W].center(ROBOT_W),
                    curses.color_pair(r.color) | curses.A_DIM)
        put(self.scr, floor_y, 0, ("▀" if self.utf else "=") * w, self.attr(BLUE))


def drain(scr):
    """Read any keys already waiting; returns True if there were some."""
    got = False
    while True:
        try:
            if scr.get_wch() != "\x1b":     # more Escs (held key, quick taps) still mean Esc
                got = True
        except curses.error:
            return got


def main(scr, args):
    curses.curs_set(0)
    curses.raw()          # capture Ctrl+C / Ctrl+Z as normal keys
    curses.noecho()
    scr.nodelay(True)
    scr.keypad(True)
    try:
        curses.set_escdelay(25)
    except AttributeError:
        pass
    curses.start_color()
    orange = 208 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    pairs = {RED: curses.COLOR_RED, YELLOW: curses.COLOR_YELLOW, GREEN: curses.COLOR_GREEN,
             CYAN: curses.COLOR_CYAN, BLUE: curses.COLOR_BLUE, MAGENTA: curses.COLOR_MAGENTA,
             WHITE: curses.COLOR_WHITE, ORANGE: orange}
    for pid, fg in pairs.items():
        curses.init_pair(pid, fg, curses.COLOR_BLACK)
    scr.bkgd(" ", curses.color_pair(GREEN))

    app = App(scr, args)
    frame = 1 / 30
    while True:
        start = time.time()
        while True:
            try:
                key = scr.get_wch()
            except curses.error:
                break
            if key == "\x1b" and drain(scr):
                key = -1     # Alt+key or odd key sequence, not a lone Esc
            if not app.handle_key(key, time.time()):
                return
        app.draw(time.time())
        time.sleep(max(0, frame - (time.time() - start)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Hacker keyboard toy for kids. Esc quits.")
    p.add_argument("--reset", action="store_true", help="set the points back to zero")
    args = p.parse_args()
    if args.reset:
        save_score(0, [])
        print("Hacker Keys points are back to zero.")
        raise SystemExit
    locale.setlocale(locale.LC_ALL, "")
    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue  # nice try, kiddo
    print("Bye, agent!")
