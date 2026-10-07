#!/usr/bin/env python3
"""
BIG CALCULATOR - giant numbers, a musical note on every key, and fun facts
about every answer.

  0-9 .        numbers
  + - * x /    plus, minus, times, divide ( ) work too
  ENTER or =   work it out
  BACKSPACE    fix a mistake
  C            clear
  Esc          quit

Try: 12*12, 1/3, 111111111*111111111, 2*2*2*2*2*2*2*2, and dividing by zero...

  python3 big_calc.py          play
  python3 big_calc.py --mute   no sound
"""
import argparse
import math
import random
from fractions import Fraction

from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, best_scale,
                     big_width, color, curses, draw_big, footer, header, is_backspace, is_enter, put, run)

MAX_TYPED = 40
SPECIAL = {
    7: "Lots of people say 7 is a lucky number.",
    12: "12 is a dozen, like a box of eggs!",
    13: "13 is a baker's dozen.",
    24: "There are 24 hours in a day.",
    42: "42 is the answer to everything, says a famous story.",
    60: "There are 60 seconds in a minute and 60 minutes in an hour.",
    100: "100 is a century! 100 years, or 100 runs in cricket.",
    144: "144 is a gross: a dozen dozens!",
    256: "256 is how many numbers fit in one byte of computer memory.",
    365: "There are 365 days in a year!",
    366: "There are 366 days in a leap year.",
    1000: "One thousand!",
    1024: "1024 bytes make a kilobyte.",
    3600: "There are 3600 seconds in an hour.",
    86400: "There are 86,400 seconds in a day!",
    1000000: "ONE MILLION!",
}
BIG_NAMES = ["thousand", "million", "billion", "trillion", "quadrillion", "quintillion", "sextillion",
             "septillion", "octillion", "nonillion", "decillion"]
ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


# ---------------------------------------------------------------- math
class MathError(Exception):
    pass


class DivideByZero(Exception):
    pass


def tokenize(text):
    tokens, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch.isdigit() or ch == ".":
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            num = text[i:j]
            if num.count(".") > 1 or num == ".":
                raise MathError("that number has too many dots")
            tokens.append(Fraction(num))
            i = j
        elif ch in "+-*/()":
            tokens.append(ch)
            i += 1
        else:
            i += 1
    return tokens


def evaluate(text):
    """Exact math with fractions: expr = term (+|- term)*, term = factor (*|/ factor)*."""
    tokens = tokenize(text)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def factor():
        t = peek()
        if t == "-":
            take()
            return -factor()
        if t == "(":
            take()
            v = expr()
            if peek() != ")":
                raise MathError("a ( is missing its )")
            take()
            return v
        if isinstance(t, Fraction):
            return take()
        raise MathError("that problem isn't finished yet")

    def term():
        v = factor()
        while peek() in ("*", "/"):
            op = take()
            rhs = factor()
            if op == "*":
                v *= rhs
            elif rhs == 0:
                raise DivideByZero()
            else:
                v /= rhs
            if abs(v) > 10 ** 120:
                raise MathError("that number is too big even for me!")
        return v

    def expr():
        v = term()
        while peek() in ("+", "-"):
            op = take()
            v = v + term() if op == "+" else v - term()
        return v

    if not tokens:
        raise MathError("type a problem first")
    v = expr()
    if pos != len(tokens):
        raise MathError("something is missing between those numbers")
    return v


def group(n):
    return "{:,}".format(n)


def show(value):
    """How the answer is written: whole numbers with commas, others as decimals."""
    if value.denominator == 1:
        return group(value.numerator)
    d = value.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    text = "%.6f" % float(value)
    text = text.rstrip("0").rstrip(".")
    return text + ("..." if d != 1 else "")


def words(n):
    if n < 0:
        return "minus " + words(-n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" and " + words(n % 100) if n % 100 else "")
    for i, name in reversed(list(enumerate(BIG_NAMES))):
        unit = 1000 ** (i + 1)
        if n >= unit:
            rest = n % unit
            return words(n // unit) + " " + name + ((" " + words(rest)) if rest else "")
    return str(n)


def is_prime(n):
    if n < 2:
        return False
    for p in range(2, int(n ** 0.5) + 1):
        if n % p == 0:
            return False
    return True


def facts(value, text):
    """Fun things to say about an answer."""
    out = []
    if value.denominator != 1:
        whole = value.numerator // value.denominator
        tokens = tokenize(text)
        if len(tokens) == 3 and tokens[1] == "/" and all(isinstance(t, Fraction) and t.denominator == 1 for t in (tokens[0], tokens[2])) and tokens[0] > 0:
            a, b = int(tokens[0]), int(tokens[2])
            out.append("%d / %d = %d remainder %d" % (a, b, a // b, a % b))
        if show(value).endswith("..."):
            out.append("The digits go on forever!")
        out.append("As a fraction: %d/%d" % (value.numerator, value.denominator))
        return out
    n = value.numerator
    if n == 10 ** 100:
        return ["That's a GOOGOL! A 1 with 100 zeros!"]
    if n in SPECIAL:
        out.append(SPECIAL[n])
    if n < 0:
        out.append("Less than zero, like a temperature below freezing!")
    if n == 0:
        out.append("Zero: nothing at all!")
    a = abs(n)
    if a >= 1000:
        if a < 10 ** 36:
            name = words(n)
            out.append(("Say it: " + name) if len(name) < 90 else "That number has %d digits!" % len(str(a)))
        else:
            out.append("That number has %d digits! Bigger than a decillion!" % len(str(a)))
    elif 0 < a < 1000:
        out.append("Say it: " + words(n))
    s = str(a)
    if len(s) >= 3 and len(set(s)) == 1:
        out.append("Every digit is the same!")
    elif len(s) >= 3 and s == s[::-1]:
        out.append("It reads the same backwards and forwards!")
    if n > 1 and a & (a - 1) == 0 and a < 2 ** 64:
        out.append("That's %s: 2 times itself %d times. Computers love it!" % (group(a), a.bit_length() - 1))
    elif 3 < n < 10 ** 12 and math.isqrt(a) ** 2 == a:
        r = math.isqrt(a)
        out.append("A square number: %s x %s!" % (group(r), group(r)))
    if 1 < n < 100000 and is_prime(n):
        out.append("A prime number: only 1 and itself divide into it!")
    if a < 10 ** 15:
        out.append("It's %s." % ("even" if a % 2 == 0 else "odd"))
    if 0 < n < 1024:
        out.append("In binary (computer numbers): %s" % bin(a)[2:])
    return out[:4]


# ---------------------------------------------------------------- the calculator
class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.typed = ""
        self.result = None           # (text shown, Fraction) or None
        self.error = ""
        self.melt_until = 0.0
        self.tape = []
        self.sparks = Sparkles()

    def handle_key(self, key, now):
        if not isinstance(key, str):
            if is_backspace(key):
                self.backspace()
            elif is_enter(key):
                self.equals(now)
            return True
        if is_enter(key) or key == "=":
            self.equals(now)
        elif is_backspace(key):
            self.backspace()
        elif key in "cC":
            self.typed, self.result, self.error = "", None, ""
            self.snd.slide(900, 200, 0.3)
        elif key.isdigit() or key == ".":
            if self.result is not None:       # a new problem starts
                self.typed, self.result = "", None
            self.error = ""
            if len(self.typed) < MAX_TYPED:
                self.typed += key
                self.snd.key_note(int(key) if key.isdigit() else 10)
        elif key in "+-*/xX()":
            op = "*" if key in "xX" else key
            if self.result is not None:       # keep going from the answer
                value = self.result[1]
                self.typed = (str(value.numerator) if value.denominator == 1 else "(%d/%d)" % (value.numerator, value.denominator))
                self.result = None
            self.error = ""
            if len(self.typed) < MAX_TYPED:
                self.typed += op
                self.snd.blip({"+": 523, "-": 440, "*": 659, "/": 392, "(": 587, ")": 587}[op], 0.08, 0.2)
        return True

    def backspace(self):
        if self.result is not None:
            self.result = None
        else:
            self.typed = self.typed[:-1]
        self.error = ""
        self.snd.blip(220, 0.06, 0.15, "TRIANGLE")

    def equals(self, now):
        if not self.typed or self.result is not None:
            return
        try:
            value = evaluate(self.typed)
        except DivideByZero:
            self.melt(now)
            return
        except MathError as e:
            self.error = "Hmm, " + str(e) + "."
            self.snd.no()
            return
        self.result = (show(value), value)
        self.tape = (self.tape + ["%s = %s" % (self.typed.replace("*", " x ").replace("/", " / ")
                                                .replace("+", " + ").replace("-", " - "), show(value))])[-12:]
        h, w = self.scr.getmaxyx()
        digits = len(str(abs(value.numerator)))
        if digits > 12:
            self.snd.fanfare()
            self.sparks.rain(w, 120, now)
        else:
            self.snd.notes((0, 4, 7, 12)[: 2 + min(2, digits // 3)], 0.08)
            self.sparks.burst(w / 2, h / 2, 15 + 3 * digits, now=now)

    def melt(self, now):
        self.melt_until = now + 3.0
        self.error = "OH NO! Nobody can divide by zero. Not even a computer!"
        self.snd.noise(1.2, 0.35, 0.3)
        self.snd.slide(800, 60, 1.5, 0.35, "SAW")
        h, w = self.scr.getmaxyx()
        for _ in range(150):
            self.sparks.parts.append([random.uniform(0, w), random.uniform(1, h / 2), 0, random.uniform(2, 8),
                                      now + random.uniform(1.5, 3), random.choice("~:;|!"), random.choice([RED, ORANGE, YELLOW])])

    def update(self, now, dt):
        pass

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        header(self.scr, "BIG CALCULATOR", "  0-9 + - x /   ENTER: answer   C: clear ", GREEN, w)
        tape_w = 34 if w >= 110 else 0
        width = w - tape_w - 4
        melting = now < self.melt_until
        shake = random.randint(-2, 2) if melting else 0

        text = self.typed or ("0" if not self.error else "")
        cursor = "_" if self.result is None and int(now * 2) % 2 else " "
        sx, sy = best_scale(text + " ", width, (h - 10) // 2)
        if big_width(text, sx) > width:
            text = text[-(width // (6 * sx)):]              # show the end of a long problem
        y = 2
        draw_big(self.scr, text + cursor, y, 2 + shake, sx, sy,
                 colors=lambda i: color(CYAN if i < len(text) and text[i] in "+-*/()" else (RED if melting else YELLOW)))
        y += 5 * sy + 1

        if self.result:
            shown = "=" + self.result[0]
            rx, ry = best_scale(shown, width, (h - 10) // 2)
            if big_width(shown, rx) <= width:
                draw_big(self.scr, shown, y, 2, rx, ry,
                         colors=lambda i: color(GREEN if len(shown) < 14 else RAINBOW[(i + int(now * 4)) % 7]))
                y += 5 * ry + 1
            else:                                           # too long even when small
                put(self.scr, y, 2, "= " + self.result[0][: width * 3], color(GREEN))
                y += 2 + len(self.result[0]) // max(1, width)
            for line in facts(self.result[1], self.typed):
                put(self.scr, y, 3, "* " + line, color(MAGENTA))
                y += 1
            y += 1
            self.draw_picture(y, width, h)
        error_y = y
        if tape_w:
            x = w - tape_w
            put(self.scr, 2, x, "PAPER TAPE", color(WHITE, False) | curses.A_UNDERLINE)
            for i, line in enumerate(self.tape[-(h - 6):]):
                put(self.scr, 4 + i, x, line[: tape_w - 1], color(WHITE, False))
        self.sparks.draw(self.scr, now, 1 / 30)
        if self.error:                                      # on top of the melting drips
            put(self.scr, error_y, 3, self.error, color(RED) | (curses.A_REVERSE if melting and int(now * 6) % 2 else 0))
        footer(self.scr, "Try: 12x12   1/3   2x2x2x2x2x2x2x2   111111111x111111111   and 7/0 ...   Esc: quit", w, h)

    def draw_picture(self, y, width, h):
        """Blocks that show what small sums and times mean."""
        tokens = tokenize(self.typed)
        if len(tokens) != 3 or not all(isinstance(t, Fraction) and t.denominator == 1 for t in (tokens[0], tokens[2])):
            return
        a, op, b = int(tokens[0]), tokens[1], int(tokens[2])
        if op == "*" and 1 <= a <= 12 and 1 <= b <= 12 and y + a < h - 1:
            put(self.scr, y, 3, "%d rows of %d:" % (a, b), color(WHITE, False))
            for r in range(a):
                put(self.scr, y + 1 + r, 3, "[]" * b, color(RAINBOW[r % 7]))
        elif op == "+" and 1 <= a <= 30 and 1 <= b <= 30 and y + 2 < h - 1:
            put(self.scr, y, 3, "[]" * a, color(CYAN))
            put(self.scr, y, 3 + 2 * a, "[]" * b, color(ORANGE))
        elif op == "-" and 1 <= b <= a <= 30 and y + 2 < h - 1:
            put(self.scr, y, 3, "[]" * (a - b), color(CYAN))
            put(self.scr, y, 3 + 2 * (a - b), "><" * b, color(RED, False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="A big calculator with fun facts. Esc quits.")
    p.add_argument("--mute", action="store_true", help="run without sound")
    p.add_argument("--reset", action="store_true", help="(nothing is saved, so there is nothing to reset)")
    args = p.parse_args()
    if args.reset:
        print("The Big Calculator doesn't save anything, so there is nothing to reset!")
        raise SystemExit
    run(Game, args.mute, "Bye! Keep counting!")
