#!/usr/bin/env python3
"""
BINARY LIGHTS - eight light bulbs that count the way a computer does.

Each bulb is worth a number: 128 64 32 16 8 4 2 1. Add up the lit bulbs and
you get the number. That's binary: computers count with only on and off.

  1 to 8          switch a bulb on or off (the key is written under it)
  SPACE or arrows count up and down (hold SPACE to count fast!)
  0               all the lights off
  ENTER           a challenge: "Make 42!"
  A to Z          see a letter's computer number
  Esc             quit

  python3 binary_lights.py          play
  python3 binary_lights.py --mute   no sound
"""
import argparse
import random

import kidslib
from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, best_scale,
                     color, curses, draw_big_centered, footer, header, is_enter, put, run)

VALUES = [128, 64, 32, 16, 8, 4, 2, 1]          # left to right
BULB_OFF = ["  .-.  ", " (   ) ", "  )-(  ", "  [_]  "]
BULB_ON = ["  .-.  ", " (###) ", "  )-(  ", "  [_]  "]
GLOW = " \\ | / "
SPECIAL = {
    42: "42: the answer to everything!",
    100: "One hundred! In binary it's 1100100.",
    128: "Only the biggest light is on!",
    255: "ALL THE LIGHTS! 255 is the biggest number 8 lights can make.",
    0: "All dark. That's zero.",
}


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.value = 0
        self.sparks = Sparkles()
        self.target = None
        self.target_at = 0.0
        self.solved = 0
        self.message, self.message_until, self.message_color = "", 0.0, WHITE
        self.letter = None
        self.flash = {}          # bulb -> time it was switched

    def say(self, text, now, col=YELLOW, secs=3.0):
        self.message, self.message_until, self.message_color = text, now + secs, col

    def set_value(self, v, now, sound=True):
        v %= 256
        changed = self.value ^ v
        for i, val in enumerate(VALUES):
            if changed & val:
                self.flash[i] = now
        self.value = v
        self.letter = None
        if sound:
            self.snd.key_note(v % 10, 60 + (12 if v >= 128 else 0))
        self.notice(now)

    def notice(self, now):
        v = self.value
        self.message_until = 0.0                      # an old message no longer fits the new number
        if self.target is not None and v == self.target:
            self.solved += 1
            self.say("YOU MADE %d!  Press ENTER for another challenge." % v, now, GREEN, 30)
            self.snd.fanfare()
            h, w = self.scr.getmaxyx()
            self.sparks.rain(w, 90, now)
            self.target = None
            return
        if v in SPECIAL:
            self.say(SPECIAL[v], now, YELLOW if v else WHITE)
        elif v & (v - 1) == 0:
            self.say("Only ONE light is on! That's a power of 2.", now, CYAN)

    def handle_key(self, key, now):
        if key == " " or key in (curses.KEY_UP, curses.KEY_RIGHT):
            if self.value == 255:
                self.set_value(0, now, sound=False)
                self.say("ROLLOVER! Out of lights, so it starts again at 0!", now, ORANGE)
                self.snd.slide(900, 120, 0.6, 0.35, "SQUARE")
            else:
                self.set_value(self.value + 1, now)
        elif key in (curses.KEY_DOWN, curses.KEY_LEFT):
            self.set_value(self.value - 1, now)
        elif isinstance(key, str) and key in "12345678":
            bulb = 8 - int(key)                       # key 1 is the right-hand bulb
            self.set_value(self.value ^ VALUES[bulb], now, sound=False)
            on = self.value & VALUES[bulb]
            self.snd.bell(60 + 3 * (8 - bulb) + (12 if on else 0))
        elif key == "0":
            self.set_value(0, now, sound=False)
            self.snd.slide(600, 150, 0.3)
        elif is_enter(key):
            self.new_challenge(now)
        elif isinstance(key, str) and key.isalpha() and key.isascii():
            self.set_value(ord(key.upper()), now, sound=False)
            self.letter = key.upper()
            self.snd.notes((0, 7), 0.08)
            self.say("The computer stores the letter %s as the number %d!" % (key.upper(), ord(key.upper())), now, MAGENTA, 5)
        return True

    def new_challenge(self, now):
        top = 15 if self.solved < 4 else 63 if self.solved < 10 else 255
        choices = [n for n in range(1, top + 1) if n != self.value]
        self.target = random.choice(choices)
        self.target_at = now
        self.say("Can you make %d? Switch lights on with keys 1 to 8." % self.target, now, CYAN, 6)
        self.snd.notes((0, 4, 7), 0.09)

    def update(self, now, dt):
        if self.target is not None and now - self.target_at > 25 and now > self.message_until:
            self.say("Hint: start with the biggest light that fits, then add smaller ones.", now, CYAN, 6)

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        info = "  challenges done: %d " % self.solved
        header(self.scr, "BINARY LIGHTS", info, YELLOW, w)
        x0 = max(0, (w - 72) // 2)
        y0 = 3
        if self.target is not None:
            t = "MAKE %d!" % self.target
            put(self.scr, 1, max(0, w - len(t) - 3), t, color(CYAN) | curses.A_REVERSE)
        for i, val in enumerate(VALUES):
            on = bool(self.value & val)
            x = x0 + i * 9
            recent = now - self.flash.get(i, -9) < 0.25
            if on:
                put(self.scr, y0, x, GLOW, color(YELLOW, not recent))
            art = BULB_ON if on else BULB_OFF
            for r, line in enumerate(art):
                a = color(YELLOW if on else WHITE, on) if r < 2 else color(WHITE, False)
                if not on and r < 2:
                    a |= curses.A_DIM
                put(self.scr, y0 + 1 + r, x, line.replace("#", kidslib.BLOCK), a)
            put(self.scr, y0 + 5, x, str(val).center(7), color(CYAN))
            put(self.scr, y0 + 6, x, ("1" if on else "0").center(7), color(GREEN if on else WHITE, on))
            put(self.scr, y0 + 7, x, ("key %d" % (8 - i)).center(7), color(WHITE, False) | curses.A_DIM)

        y = y0 + 9
        lit = [str(v) for v in VALUES if self.value & v]
        sum_line = (" + ".join(lit) + " = %d" % self.value) if lit else "no lights on = 0"
        put(self.scr, y, (w - len(sum_line)) // 2, sum_line, color(WHITE))
        binary = "in binary: " + format(self.value, "08b")
        put(self.scr, y + 1, (w - len(binary)) // 2, binary, color(GREEN, False))
        text = self.letter or str(self.value)
        sx, sy = best_scale(text, w - 4, h - y - 7)
        draw_big_centered(self.scr, text, y + 3, w, sx, sy,
                          colors=lambda i: color(MAGENTA if self.letter else RAINBOW[(self.value // 8 + i) % 7]))
        if now < self.message_until:
            m = self.message
            put(self.scr, h - 3, max(0, (w - len(m)) // 2), m, color(self.message_color))
        self.sparks.draw(self.scr, now, 1 / 30)
        footer(self.scr, "keys 1-8: lights   SPACE: count   0: all off   ENTER: challenge   letters: secret codes   Esc: quit", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Eight light bulbs that count in binary. Esc quits.")
    p.add_argument("--mute", action="store_true", help="run without sound")
    p.add_argument("--reset", action="store_true", help="(nothing is saved, so there is nothing to reset)")
    args = p.parse_args()
    if args.reset:
        print("Binary Lights doesn't save anything, so there is nothing to reset!")
        raise SystemExit
    run(Game, args.mute, "Lights out! Bye!")
