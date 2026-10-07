#!/usr/bin/env python3
"""
The Kids Computer menu: a colorful message printed at login and after each
program ends. The kids type a program's name and press ENTER.

To add a program: add a line to PROGRAMS below, a matching function in
kids_commands.sh, and a help file in help/.

Grown-ups: type "adult" (it is not listed anywhere) to turn games on and off
and set the volume from 0 to 11.

  python3 kids_menu.py                      print the menu
  python3 kids_menu.py --help-topic band    print help/band.txt
  python3 kids_menu.py --unknown WORD       friendly answer for a word the computer doesn't know
  python3 kids_menu.py --bad-word band WORD friendly answer for "band WORD"
  python3 kids_menu.py --check-on band      exit 1 (with a kind message) if band is turned off
  python3 kids_menu.py --adult              the grown-up settings (games on/off, volume 0-11)
"""
import argparse
import array
import difflib
import json
import math
import os
import random
import re
import subprocess
import time

HELP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "help")
SETTINGS_FILE = os.path.expanduser("~/.kids_computer.json")

# (what to type, name, what it does, color)
PROGRAMS = [
    ("keys", "Hacker Keys", "letters, words, points and robots", "32"),
    ("band", "Bleep Bloop Band", "make music with the keyboard", "36"),
    ("robot", "Robot Commander", "tell the robot where to go", "33"),
    ("rain", "Alphabet Rain", "pop the falling letters by typing them", "35"),
    ("quest", "Quest", "find the Golden Crown in a big adventure", "31"),
    ("times", "Times Tables", "big multiplication flash cards", "35"),
    ("calc", "Big Calculator", "giant numbers and fun facts", "32"),
    ("lights", "Binary Lights", "count like a computer with light bulbs", "33"),
    ("secret", "Secret Codes", "make and crack secret messages", "36"),
    ("paint", "Pixel Painter", "paint pictures square by square", "35"),
    ("pet", "Robot Pet", "a robot friend who lives in the computer", "33"),
    ("castle", "Castle Cannons", "aim the cannon, knock down the castle", "31"),
    ("ski", "Ski Hill", "ski down the mountain, away from the snow monster", "36"),
]
EXTRA = []
HIDDEN = ["menu", "adult", "help"]    # these work, but the menu doesn't show them

FACTS = [
    "Every letter you type is a number inside the computer. A is 65!",
    "Computers count with only 0 and 1. That is called binary.",
    "Sound is numbers too! Bleep Bloop Band sends 22,050 numbers to the speaker every second.",
    "A program is a list of steps. When you play Robot Commander, you are programming!",
    "A computer 'bug' is named after a real moth that got stuck inside a computer in 1947.",
    "Your screen is made of tiny dots of light called pixels.",
    "The space bar is the biggest key on the keyboard.",
    "The first computer mouse was made of wood.",
    "Press Esc to leave any program and come back here.",
    "Quest is like ZZT, a game from 1991 where kids built their own worlds out of letters.",
    "Type a game's name and then help, like: robot help",
    "Light bulbs can count! Binary Lights shows how: 8 bulbs can make any number up to 255.",
    "Morse code sends letters as short and long beeps. Try it in Secret Codes!",
    "Your robot pet gets hungry while you're away. Don't forget to feed it!",
    "11 x 11 = 121, and 111 x 111 = 12321. Try 1111 x 1111 in the Big Calculator!",
]

# 5x5 block letters for the title
FONT = {
    "H": ["#   #", "#   #", "#####", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "#####"],
    "!": ["  #  ", "  #  ", "  #  ", "     ", "  #  "],
}
RAINBOW = ["31", "33", "32", "36", "34", "35"]
ROBOT = ["   _|_   ", "  [o_o]  ", "  /|_|\\  ", "   / \\   "]


def c(text, code):
    return "\033[1;%sm%s\033[0m" % (code, text)


# ---------------------------------------------------------------- settings
def turned_off():
    """The games a grown-up has turned off."""
    try:
        with open(SETTINGS_FILE) as f:
            return set(json.load(f).get("off", []))
    except (OSError, ValueError, AttributeError):
        return set()


def save_off(off):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"off": sorted(off)}, f)


def games_on():
    off = turned_off()
    return [p for p in PROGRAMS if p[0] not in off]


# ---------------------------------------------------------------- volume
MAX_VOLUME = 11     # this one goes to eleven


def get_volume():
    """The speaker volume from 0 to 11, or None if there's no sound card."""
    try:
        out = subprocess.run(["amixer", "-M", "sget", "Master"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\[(\d+)%\].*?\[(on|off)\]", out)
    if not m:
        return None
    return 0 if m.group(2) == "off" else round(int(m.group(1)) * MAX_VOLUME / 100)


def set_volume(level):
    """Set the volume (0 is silent). -M spaces the steps the way ears hear them. True if it worked."""
    pct = "%d%%" % round(level * 100 / MAX_VOLUME)
    try:
        return subprocess.run(["amixer", "-q", "-M", "sset", "Master", pct, "mute" if level == 0 else "unmute"],
                              capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def beep():
    """A short friendly beep, so a grown-up can hear the new volume."""
    rate = 22050
    n = rate // 4
    data = array.array("h", [int(12000 * math.sin(2 * math.pi * 660 * i / rate) * min(1, (n - i) / 800))
                             for i in range(n)]).tobytes()
    try:
        subprocess.run(["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", "1"],
                       input=data, capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass


def volume_bar(level):
    return c("█" * level, "32") + c("░" * (MAX_VOLUME - level), "37") + "  %d of %d" % (level, MAX_VOLUME)


# ---------------------------------------------------------------- the kids' side
def greeting():
    hour = time.localtime().tm_hour
    part = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    return part + "!", time.strftime("It's %A, %-I:%M %p")


def menu():
    title = "HI!"
    hello, today = greeting()
    right = ["", c(hello, "33"), c(today, "37"), ""]
    print()
    for r in range(5):
        row = "  ".join(c(FONT[ch][r].replace("#", "█"), RAINBOW[i % len(RAINBOW)]) for i, ch in enumerate(title))
        robot = c(ROBOT[r - 1], "33") if 1 <= r <= 4 else " " * 9
        side = right[r - 1] if 1 <= r <= 4 else ""
        print("   " + row + "     " + robot + "   " + side)
    print()
    print("   " + c("Type a word, then press ENTER:", "37"))
    print()
    games = games_on()
    for cmd, name, what, color in games:
        print("      %s   %s  %s" % (c(cmd.ljust(6), color), c(name.ljust(17), "37"), what))
    if not games:
        print("      " + c("The games are taking a nap right now.", "36"))
    for cmd, what in EXTRA:
        print("      %s   %s" % (c(cmd.ljust(6), "37"), what))
    print()
    print("   " + c("Did you know?", "35") + " " + random.choice(FACTS))
    print()


def unknown(word):
    words = [p[0] for p in games_on()] + [e[0] for e in EXTRA]
    close = difflib.get_close_matches(word.lower(), words, n=1, cutoff=0.5)
    print()
    print("   Hmm, the computer doesn't know %s." % c('"%s"' % word, "31"))
    if close:
        print("   Did you mean %s?" % c(close[0], "32"))
    else:
        print("   Try one of these: " + ", ".join(c(w, "32") for w in words))
    print()


def check_on(name):
    """True if the game may run; otherwise explain kindly."""
    if name not in turned_off():
        return True
    title = next((p[1] for p in PROGRAMS if p[0] == name), name)
    print()
    print("   %s is taking a nap right now. Ask a grown-up!" % c(title, "36"))
    print()
    return False


def show_help(topic):
    """Print a help file: '# ' lines are headings, and the first word of an indented line is a command.
    Games that are turned off are left out of the GAMES list, and "GAME" becomes a game that is on."""
    path = os.path.join(HELP_DIR, os.path.basename(topic.lower()) + ".txt")
    if not os.path.exists(path):
        print()
        print("   There is no help for %s yet. Try: %s" % (c(topic, "31"), c("help", "32")))
        print()
        return
    off = turned_off()
    example = next((p[0] for p in PROGRAMS if p[0] not in off), "keys")
    heading = ""
    print()
    with open(path, encoding="utf-8") as f:
        for line in f.read().replace("GAME ", example + " ").splitlines():
            cmd = re.match(r"^  (\S+(?: \S+){0,3})( {2,})(.*)$", line)
            if line.startswith("# "):
                heading = line[2:].strip().upper()
                print("   " + c(line[2:], "33"))
            elif cmd:
                if heading == "GAMES" and cmd.group(1) in off:
                    continue
                print("     " + c(cmd.group(1), "32") + cmd.group(2) + cmd.group(3))
            else:
                print("   " + line)
    print()


def bad_word(program, word):
    print()
    print("   %s doesn't know %s." % (c(program, "32"), c('"%s"' % word, "31")))
    print("   Try: %s   %s   %s" % (c(program, "32"), c(program + " help", "32"), c(program + " reset", "32")))
    print()


# ---------------------------------------------------------------- the grown-up side
def adult():
    """Turn games on and off and set the volume. Reached by typing "adult", which is not listed anywhere."""
    note = ""
    while True:
        off = turned_off()
        volume = get_volume()
        print("\033[2J\033[H")
        print("   " + c("GROWN-UP SETTINGS", "33") + "   (hidden: type " + c("adult", "32") + " to come back here)")
        print()
        print("   Type a game's number to turn it on or off, then press ENTER.")
        print("   Type %s and a number from 0 to %d to set the volume, like %s." % (c("v", "33"), MAX_VOLUME, c("v 7", "32")))
        print("   Press ENTER on its own when you're done.")
        print()
        for i, (cmd, name, _, _) in enumerate(PROGRAMS, 1):
            state = c("OFF", "31") if cmd in off else c("ON ", "32")
            print("     %s   %s  %s  %s" % (c(str(i).rjust(2), "33"), cmd.ljust(6), name.ljust(18), state))
        print()
        print("     %s   %s  %s" % (c(" v", "33"), "volume".ljust(26),
                                    volume_bar(volume) if volume is not None else c("no sound card found", "31")))
        print()
        if note:
            print("   " + note)
            print()
        try:
            choice = input("   " + c("number >", "33") + " ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not choice:
            return
        vol = re.fullmatch(r"v(?:ol(?:ume)?)?\s*(\d*)", choice)
        if vol:
            if not vol.group(1) or int(vol.group(1)) > MAX_VOLUME:
                note = c("Type v and a number from 0 to %d, like v 7." % MAX_VOLUME, "31")
            elif set_volume(int(vol.group(1))):
                note = "Volume is now %s." % c(vol.group(1), "32")
                beep()
            else:
                note = c("Couldn't change the volume (is there a sound card?).", "31")
            continue
        names = [p[0] for p in PROGRAMS]
        if choice.isdigit() and 1 <= int(choice) <= len(PROGRAMS):
            cmd = names[int(choice) - 1]
        elif choice in names:
            cmd = choice
        else:
            note = c("Type a number from 1 to %d." % len(PROGRAMS), "31")
            continue
        off ^= {cmd}
        try:
            save_off(off)
            note = "%s is now %s." % (cmd, c("off", "31") if cmd in off else c("on", "32"))
        except OSError as e:
            note = c("Couldn't save the setting: %s" % e, "31")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Kids Computer menu")
    p.add_argument("--unknown", metavar="WORD", help="answer for a word the computer doesn't know")
    p.add_argument("--help-topic", metavar="NAME", help="print the help file help/NAME.txt")
    p.add_argument("--bad-word", nargs=2, metavar=("PROGRAM", "WORD"), help='answer for "PROGRAM WORD"')
    p.add_argument("--check-on", metavar="NAME", help="exit with status 1 if this game is turned off")
    p.add_argument("--adult", action="store_true", help="the grown-up settings")
    args = p.parse_args()
    if args.unknown is not None:
        unknown(args.unknown)
    elif args.help_topic:
        show_help(args.help_topic)
    elif args.bad_word:
        bad_word(*args.bad_word)
    elif args.check_on:
        raise SystemExit(0 if check_on(args.check_on) else 1)
    elif args.adult:
        adult()
    else:
        menu()
