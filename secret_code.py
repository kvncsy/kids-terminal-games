#!/usr/bin/env python3
"""
SECRET CODE MACHINE - turn messages into secret codes, and crack them.

MAKE A CODE: type a message and see it as numbers, computer numbers,
binary, Morse code, a code-wheel secret and backwards. ENTER beeps it out
in Morse code with a flashing lamp. UP and DOWN turn the code wheel.

CRACK A CODE (press TAB): a secret message is scrambled with the code wheel.
Turn the wheel with UP and DOWN until it makes sense!

  python3 secret_code.py          play
  python3 secret_code.py --mute   no sound
"""
import argparse
import random
import time

from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, bb, best_scale,
                     box, color, curses, draw_big_centered, footer, header, is_backspace, is_enter, put, run)

ABC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....", "I": "..",
    "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
    "7": "--...", "8": "---..", "9": "----.",
}
SECRETS = [
    "ROBOTS LOVE PIZZA", "YOU ARE A CODE CRACKER", "MEET ME ON THE MOON", "OCTOPUSES HAVE THREE HEARTS",
    "BANANAS ARE BERRIES", "THE CAT IS A SECRET AGENT", "DO A SILLY DANCE", "GIVE SOMEONE A HIGH FIVE",
    "THE ROBOT SAYS BEEP BOOP", "OWLS CAN TURN THEIR HEADS", "HONEY NEVER GOES BAD", "THE SUN IS A STAR",
    "SHARKS ARE OLDER THAN TREES", "A GROUP OF FLAMINGOS IS A FLAMBOYANCE", "COWS HAVE BEST FRIENDS",
    "SNAILS CAN SLEEP FOR THREE YEARS", "THE PASSWORD IS PANCAKES", "SPIES LOVE CARROTS", "SAY BANANA FIVE TIMES FAST",
    "YOUR SOCKS ARE GLOWING", "THE PENGUIN HAS THE MAP", "HIPPOS CANNOT SWIM",
]
DOT, DASH, GAP = 0.09, 0.27, 0.09          # Morse timing in seconds


def shift(text, n):
    return "".join(ABC[(ABC.index(c) + n) % 26] if c in ABC else c for c in text)


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.mode = "make"
        self.msg = ""
        self.wheel = 3
        self.beeps = []            # (start, end, letter index) while Morse is playing
        self.sparks = Sparkles()
        self.cracked = 0
        self.note, self.note_until = "", 0.0
        self.new_secret(time.time())

    def say(self, text, now, secs=4.0):
        self.note, self.note_until = text, now + secs

    def new_secret(self, now):
        self.secret = random.choice([s for s in SECRETS if s != getattr(self, "secret", "")])
        self.secret_shift = random.randint(3, 23)
        self.scrambled = shift(self.secret, self.secret_shift)
        self.guess = 0
        self.solved = False
        self.secret_at = now

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if key == "\t":
            self.mode = "crack" if self.mode == "make" else "make"
            self.snd.slide(300, 900 if self.mode == "crack" else 300, 0.25)
            return True
        if key in (curses.KEY_UP, curses.KEY_RIGHT, curses.KEY_DOWN, curses.KEY_LEFT):
            step = 1 if key in (curses.KEY_UP, curses.KEY_RIGHT) else -1
            if self.mode == "make":
                self.wheel = (self.wheel + step) % 26
                if self.wheel == 13:
                    self.say("Wheel 13 is special: the same wheel makes AND breaks the code!", now)
            elif not self.solved:
                self.guess = (self.guess + step) % 26
                self.check_crack(now)
            self.snd.blip(300 + 20 * ((self.wheel if self.mode == "make" else self.guess) % 26), 0.05, 0.15)
            return True
        if self.mode == "crack":
            if is_enter(key) and self.solved:
                self.new_secret(now)
                self.snd.notes((0, 4), 0.08)
            return True
        if is_enter(key):
            self.play_morse(now)
        elif is_backspace(key):
            self.msg = self.msg[:-1]
        elif isinstance(key, str) and (key.isalnum() and key.isascii() or key == " ") and len(self.msg) < 20:
            self.msg += key.upper()
            self.snd.blip(700, 0.04, 0.12, "SINE")
            if self.msg.endswith("SOS"):
                self.say("S O S means HELP! in Morse code. Press ENTER to hear it!", now)
        return True

    def play_morse(self, now):
        t = 0.15
        self.beeps = []
        for i, ch in enumerate(self.msg):
            if ch == " ":
                t += DASH * 2
                continue
            for sym in MORSE.get(ch, ""):
                length = DOT if sym == "." else DASH
                self.beeps.append((now + t, now + t + length, i))
                if self.snd.eng:
                    self.snd.play(lambda t=t, length=length: bb.Voice([bb.tone(bb.SINE, 700, .8)], .3, .004, .05,
                                                                     sustain=1.0, release=.02, hold=t + length, delay=t))
                t += length + GAP
            t += DASH
        if not self.beeps:
            self.say("Type a message first!", now, 2)

    def check_crack(self, now):
        if shift(self.scrambled, -self.guess) == self.secret:
            self.solved = True
            self.cracked += 1
            self.snd.fanfare()
            h, w = self.scr.getmaxyx()
            self.sparks.rain(w, 100, now)

    def update(self, now, dt):
        if self.beeps and now > self.beeps[-1][1] + 0.3:
            self.beeps = []
        if self.mode == "crack" and not self.solved and now - self.secret_at > 40 and now > self.note_until:
            self.say("Hint: look at the short words. A word with one letter is usually A or I!", now, 8)

    # ------------------------------------------------------------ drawing
    def draw(self, now):
        h, w = self.scr.getmaxyx()
        header(self.scr, "SECRET CODE MACHINE",
               "  %s   TAB: %s   codes cracked: %d " % ("MAKE A CODE" if self.mode == "make" else "CRACK A CODE",
                                                         "crack a code" if self.mode == "make" else "make a code",
                                                         self.cracked), GREEN, w)
        if self.mode == "make":
            self.draw_make(now, h, w)
        else:
            self.draw_crack(now, h, w)
        if now < self.note_until:
            put(self.scr, h - 3, max(0, (w - len(self.note)) // 2), self.note, color(YELLOW))
        self.sparks.draw(self.scr, now, 1 / 30)

    def draw_wheel(self, y, w, n, label):
        x = max(0, (w - 60) // 2)
        put(self.scr, y, x, label, color(WHITE, False))
        put(self.scr, y + 1, x, " ".join(ABC), color(WHITE))
        put(self.scr, y + 2, x, " ".join(shift(ABC, n)), color(CYAN))
        put(self.scr, y + 3, x, " ".join("|" for _ in ABC), color(BLUE, False))

    def draw_make(self, now, h, w):
        playing = [b for b in self.beeps if b[0] <= now < b[1]]
        started = [i for s, e, i in self.beeps if s <= now]
        active = started[-1] if started else None          # the letter being beeped
        text = self.msg or "TYPE"
        sx, sy = best_scale(text, w - 14, 12, 0, ((2, 1), (1, 1)))
        cursor = "_" if int(now * 2) % 2 else " "
        draw_big_centered(self.scr, text + (cursor if self.msg else ""), 2, w, sx, sy,
                          colors=lambda i: color(ORANGE if i == active else (YELLOW if self.msg else WHITE), bool(self.msg)))
        lamp_on = bool(playing)
        put(self.scr, 3, w - 9, " .--. ", color(WHITE, False))
        put(self.scr, 4, w - 9, "( %s )" % ("##" if lamp_on else "  "), color(YELLOW if lamp_on else WHITE))
        put(self.scr, 5, w - 9, " '--' ", color(WHITE, False))
        put(self.scr, 6, w - 9, " lamp ", color(WHITE, False) | curses.A_DIM)

        msg = self.msg.strip()
        rows = [
            ("A=1 NUMBERS", " ".join(str(ABC.index(c) + 1) if c in ABC else ("/" if c == " " else c) for c in self.msg), CYAN),
            ("COMPUTER NUMBERS", " ".join(str(ord(c)) for c in self.msg), GREEN),
            ("BINARY", " ".join(format(ord(c), "08b") for c in self.msg), GREEN),
            ("MORSE CODE", "  ".join(MORSE.get(c, "/") for c in self.msg), ORANGE),
            ("CODE WHEEL %d" % self.wheel, shift(self.msg, self.wheel), MAGENTA),
            ("BACKWARDS", self.msg[::-1], RED),
        ]
        y = 3 + 5 * sy + 1
        for label, value, col in rows:
            put(self.scr, y, 2, label.rjust(17) + ":", color(WHITE, False))
            put(self.scr, y, 21, (value if len(value) < w - 23 else value[: w - 26] + "...") if msg else "", color(col))
            y += 2
        self.draw_wheel(y, w, self.wheel, "The code wheel: each letter (top) becomes a secret letter (bottom)")
        footer(self.scr, "type a message   ENTER: beep it in Morse code   UP/DOWN: turn the wheel   TAB: crack a code   Esc: quit", w, h)

    def draw_crack(self, now, h, w):
        put(self.scr, 2, (w - 34) // 2, "A secret message has been found!", color(WHITE))
        decoded = shift(self.scrambled, -self.guess)
        box(self.scr, 4, 2, 4, w - 4, color(RED if not self.solved else GREEN))
        put(self.scr, 5, 4, "SECRET:  ", color(WHITE, False))
        put(self.scr, 5, 13, self.scrambled, color(RED))
        put(self.scr, 6, 4, "WHEEL %2d:" % self.guess, color(WHITE, False))
        put(self.scr, 6, 14, decoded, color(GREEN if self.solved else YELLOW))
        if self.solved:
            sx, sy = best_scale("CRACKED!", w - 4, 12)
            draw_big_centered(self.scr, "CRACKED!", 10, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 5)) % 7]))
            m = "You cracked it! Press ENTER for the next secret."
            put(self.scr, 11 + 5 * sy, (w - len(m)) // 2, m, color(WHITE))
        else:
            put(self.scr, 10, (w - 48) // 2, "Turn the wheel with UP and DOWN until the", color(WHITE, False))
            put(self.scr, 11, (w - 48) // 2, "yellow line turns into a real message!", color(WHITE, False))
            self.draw_wheel(13, w, -self.guess, "The code wheel: each secret letter (top) becomes a real letter (bottom)")
        footer(self.scr, "UP/DOWN: turn the wheel   ENTER: next secret   TAB: make a code   Esc: quit", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Make and crack secret codes. Esc quits.")
    p.add_argument("--mute", action="store_true", help="run without sound")
    p.add_argument("--reset", action="store_true", help="(nothing is saved, so there is nothing to reset)")
    args = p.parse_args()
    if args.reset:
        print("The Secret Code Machine doesn't save anything, so there is nothing to reset!")
        raise SystemExit
    run(Game, args.mute, "Your secrets are safe with me. Bye!")
