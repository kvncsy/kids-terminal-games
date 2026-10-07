#!/usr/bin/env python3
"""
ROBOT PET - a little robot that lives on the computer.

It remembers its name and how old it is, gets hungry for electricity while
you're away, and gets sleepy at night. Look after it with the number keys:

  1 FEED   2 PLAY   3 DANCE   4 TICKLE   5 JOKE   6 SLEEP / WAKE UP
  7 CLEAN  8 OIL

Messes pile up around it (dust bunnies, loose screws, oil drips). Leave a big
mess, or let the battery run down, for a couple of hours and it goes rusty: it
can't play or dance until it gets two squirts of oil.

Or type a word and press ENTER to talk to it. It understands lots of secret
words. Can you find them all?

  python3 robot_pet.py           play
  python3 robot_pet.py --reset   say goodbye and start with a new robot
  python3 robot_pet.py --mute    no sound
"""
import argparse
import json
import os
import random
import textwrap
import time

from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, color, curses,
                     fancy, footer, header, is_backspace, is_enter, put, run)

SAVE_FILE = os.path.expanduser("~/.robot_pet")
LOWEST = 10                     # the robot never runs all the way down
MESS_EVERY = 45                 # minutes between new messes
MESS_MAX = 4
RUST_AFTER = 120                # minutes of a full mess (or an empty battery) before it goes rusty
MESSES = [("@", WHITE, False), ("-{", WHITE, True), ("o~", BLUE, True)]     # dust bunny, loose screw, oil drip
MESS_SPOTS = (-9, -5, 18, 22)   # where each mess sits, next to the robot's feet
JOKES = [
    ("Why did the robot go on vacation?", "To recharge its batteries!"),
    ("What do you call a pirate robot?", "Arrr2-D2!"),
    ("Why was the robot so tired?", "It had a hard drive!"),
    ("What is a robot's favorite snack?", "Computer chips!"),
    ("Why did the computer go to the doctor?", "It had a virus!"),
    ("What do robots do at parties?", "The robot dance!"),
    ("Why did the math book look sad?", "It had too many problems!"),
    ("What do you call a sleeping dinosaur?", "A dino-snore!"),
    ("Why can't a bicycle stand up by itself?", "It's two tired!"),
    ("What has keys but can't open doors?", "A keyboard!"),
    ("What did zero say to eight?", "Nice belt!"),
    ("Why did the cookie go to the nurse?", "It felt crummy!"),
    ("What do you call a bear with no teeth?", "A gummy bear!"),
    ("How do robots eat guacamole?", "With micro-chips!"),
]
WORDS = {       # secret words the robot understands
    "hi": "HELLO", "hello": "HELLO", "hey": "HELLO",
    "dance": "DANCE", "sing": "SING", "jump": "JUMP", "spin": "SPIN", "joke": "JOKE",
    "sleep": "SLEEP", "goodnight": "SLEEP", "wake": "WAKE", "love": "LOVE", "pizza": "PIZZA",
    "count": "COUNT", "math": "MATH", "robot": "ROBOT", "good": "GOOD", "bad": "BAD", "age": "AGE",
    "thanks": "THANKS", "thank": "THANKS", "bye": "BYE", "beep": "BEEP", "boop": "BOOP",
    "color": "COLOR", "hungry": "HUNGRY", "happy": "HAPPY", "sad": "SAD",
    "clean": "CLEAN", "broom": "CLEAN", "tidy": "CLEAN", "oil": "OIL",
}
SECRET_TOTAL = len(set(WORDS.values())) + 1            # plus the robot's own name


def pass_time(d, minutes, away=False):
    """Let time go by: mess piles up, and a messy or run-down robot slowly rusts. Returns new messes."""
    new = 0
    minutes = min(minutes, 3 * 24 * 60)             # after 3 days away nothing more changes
    while minutes > 0:
        m = min(1.0, minutes)
        minutes -= m
        if away:
            d["battery"] = max(LOWEST, d["battery"] - 3 * m / 60)      # it uses electricity while you're away
            d["fun"] = max(LOWEST, d["fun"] - 4 * m / 60)
            d["energy"] = min(100, d["energy"] + 10 * m / 60)          # and rests
        d["mess_timer"] += m
        if d["mess_timer"] >= MESS_EVERY:
            d["mess_timer"] -= MESS_EVERY
            if len(d["mess"]) < MESS_MAX:
                d["mess"].append(random.randrange(len(MESSES)))
                new += 1
        if len(d["mess"]) >= MESS_MAX or d["battery"] <= LOWEST + 0.5:
            d["neglect"] += m
            if d["neglect"] >= RUST_AFTER and not d["rusty"]:
                d["rusty"], d["squirts"] = True, 0
        else:
            d["neglect"] = 0
    return new


COLORS_WORDS = [("red", RED), ("orange", ORANGE), ("yellow", YELLOW), ("green", GREEN), ("blue", CYAN), ("purple", MAGENTA)]


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.sparks = Sparkles()
        self.typed = ""
        self.bubble = ""                # what the robot is saying: it stays until the next key
        self.anim, self.anim_until = None, 0.0
        self.joke = None                # a punchline waiting for a key press
        self.math = None
        self.love_until = 0.0
        self.body_color = ORANGE
        self.swept, self.sweep_until = [], 0.0          # messes the broom is sweeping away right now
        now = time.time()
        self.data = self.load(now)
        self.naming = not self.data.get("name")
        if not self.naming:
            self.greet(now)

    # ------------------------------------------------------------ saving and time passing
    def load(self, now):
        try:
            with open(SAVE_FILE) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {"name": "", "born": now, "last": now, "battery": 80, "fun": 80, "energy": 80, "found": [],
                    "mess": [], "mess_timer": 0, "neglect": 0, "rusty": False, "squirts": 0}
        hours = max(0.0, (now - d.get("last", now)) / 3600)
        for stat in ("battery", "fun", "energy"):
            d.setdefault(stat, 80)
        for key, value in (("found", []), ("mess", []), ("mess_timer", 0), ("neglect", 0), ("rusty", False), ("squirts", 0)):
            d.setdefault(key, value)
        pass_time(d, hours * 60, away=True)
        d["away_hours"] = hours
        return d

    def save(self):
        self.data["last"] = time.time()
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump({k: v for k, v in self.data.items() if k != "away_hours"}, f)
        except OSError:
            pass

    def quit(self):
        if not self.naming:
            self.save()

    def change(self, stat, amount):
        self.data[stat] = max(LOWEST, min(100, self.data[stat] + amount))

    @property
    def name(self):
        return self.data["name"]

    def night(self):
        hour = time.localtime().tm_hour
        return hour >= 20 or hour < 7

    def asleep(self):
        return self.anim == "sleep"

    def rusty(self):
        return self.data["rusty"]

    def squeak(self):
        self.snd.slide(1300, 1800, 0.15, 0.12, "TRIANGLE")

    def creak(self, now):
        self.say("Creak! Too rusty. Oil me! Press 8.", now)
        self.squeak()

    def greet(self, now):
        d = self.data
        if self.night():
            self.anim, self.anim_until = "sleep", now + 10 ** 9
            self.say("Zzz... %s is asleep because it's night time. Press 6 to wake it up gently." % self.name, now)
        elif d["rusty"]:
            self.say("Creak... I'm all rusty! Press 8 for oil!", now)
            self.squeak()
            return
        elif d.get("away_hours", 0) > 12:
            self.say("You're back!! I missed you SO much! I'm hungry. Can you press 1 to feed me?", now)
        elif d["battery"] < 30:
            self.say("Beep... my battery is low. Press 1 to feed me electricity!", now)
        elif d["mess"]:
            self.say("Hi! Uh oh, it's messy! Press 7!", now)
        else:
            self.say("Hi! It's me, %s! Beep boop!" % self.name, now)
        self.snd.notes((0, 4, 7, 12), 0.08)

    def say(self, text, now):
        self.bubble = text
        n = min(8, 1 + len(text) // 8)
        for i in range(n):                                  # robot voice: little beeps
            self.snd.blip(random.choice((523, 587, 659, 784, 880)), 0.05, 0.1, "SQUARE", delay=i * 0.07)

    def found(self, word, now):
        if word not in self.data["found"]:
            self.data["found"].append(word)
            self.save()
            n = len(self.data["found"])
            self.sparks.burst(*self.robot_center(), 30, now=now)
            self.snd.notes((0, 7, 12), 0.06, 84)
            return " (Secret word %d of %d!)" % (n, SECRET_TOTAL)
        return ""

    def robot_center(self):
        h, w = self.scr.getmaxyx()
        return w // 2 - 10, h // 2 - 2

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if self.naming:
            return self.name_key(key, now)
        if self.joke:                                   # any key tells the punchline
            self.say(self.joke + "  Ha ha!", now)
            self.snd.notes((0, 4, 7, 12, 7), 0.08)
            self.joke = None
            return True
        self.bubble = ""                                # any other key clears what the robot said
        if isinstance(key, str) and key in "12345678" and not self.typed and not self.math:
            self.action(int(key), now)
        elif is_enter(key):
            if self.typed.strip():
                self.hear(self.typed.strip().lower(), now)
            self.typed = ""
        elif is_backspace(key):
            self.typed = self.typed[:-1]
        elif isinstance(key, str) and (key.isalnum() and key.isascii() or key in " !?'") and len(self.typed) < 30:
            self.typed += key
            self.snd.blip(900, 0.02, 0.08, "SINE")
        return True

    def name_key(self, key, now):
        if is_enter(key):
            name = self.typed.strip().upper()[:12] or "BOLT"
            self.data.update({"name": name, "born": now, "last": now})
            self.typed = ""
            self.naming = False
            self.save()
            self.say("%s! I LOVE my name! Hello, friend!" % name, now)
            self.snd.fanfare()
            self.sparks.rain(self.scr.getmaxyx()[1], 80, now)
        elif is_backspace(key):
            self.typed = self.typed[:-1]
        elif isinstance(key, str) and key.isalpha() and key.isascii() and len(self.typed) < 12:
            self.typed += key.upper()
        return True

    def start(self, anim, now, secs):
        self.anim, self.anim_until = anim, now + secs

    def action(self, n, now):
        if self.asleep() and n not in (6, 7):
            self.say("Zzz... (press 6 to wake me up)", now)
            self.snd.noise(0.6, 0.1, 0.2)
            return
        if n == 1:
            if self.data["battery"] >= 98:
                self.say("I'm full! My battery is at 100%!", now)
                return
            self.change("battery", 30)
            self.start("eat", now, 2.5)
            self.say(random.choice(["Nom nom nom! Yummy electricity!", "Zzzap! Tasty volts!", "Mmm, crunchy electrons!"]), now)
            self.snd.slide(200, 900, 1.2, 0.25, "SQUARE")
        elif n == 2:
            if self.rusty():
                self.creak(now)
                return
            if self.data["energy"] < 20:
                self.say("I'm too tired to play... can I have a nap? (press 6)", now)
                return
            self.change("fun", 20)
            self.change("energy", -10)
            self.start("play", now, 3.5)
            self.say("Catch! Wheee!", now)
        elif n == 3:
            self.dance(now)
        elif n == 4:
            self.change("fun", 10)
            self.start("tickle", now, 2)
            self.say(random.choice(["Hee hee hee! That tickles!", "Ha ha ha! Stop! No, don't stop!", "Beep-hee-hee!"]), now)
            for i in range(8):
                self.snd.blip(600 + 80 * i, 0.05, 0.15, "SQUARE", delay=i * 0.06)
        elif n == 5:
            self.tell_joke(now)
        elif n == 6:
            if self.asleep():
                self.anim, self.anim_until = None, 0.0
                self.say("*yawn* Good morning! I'm awake!" if not self.night() else "*yawn* Is it morning already? Hi!", now)
                self.snd.slide(300, 800, 0.6)
            else:
                self.start("sleep", now, 10 ** 9)
                self.say("Goodnight! Zzz...", now)
                self.snd.slide(800, 200, 0.8)
        elif n == 7:
            self.clean(now)
        elif n == 8:
            self.oil(now)
        self.save()

    def clean(self, now):
        if not self.data["mess"]:
            self.say("All clean already!", now)
            return
        self.swept, self.data["mess"], self.data["neglect"] = self.data["mess"], [], 0
        self.change("fun", 5)
        self.sweep_until = now + 2
        if not self.asleep():
            self.say("Swish swish! So clean!", now)
        self.snd.noise(1.6, 0.12, 1.2)
        for i, step in enumerate((0, 4, 7, 12)):
            self.snd.bell(79 + step, 1.8 + i * 0.1)

    def oil(self, now):
        self.start("oil", now, 1.5)
        self.snd.noise(0.25, 0.2, 1.8)
        if not self.rusty():
            self.say("Hee hee! Slippery!", now)
            for i in range(5):
                self.snd.blip(700 + 100 * i, 0.05, 0.12, "SQUARE", delay=0.3 + i * 0.06)
            return
        self.data["squirts"] += 1
        if self.data["squirts"] < 2:
            self.say("Squirt! One more, please!", now)
            self.squeak()
            return
        self.data.update({"rusty": False, "squirts": 0, "neglect": 0})
        self.say("All shiny! Thank you!", now)
        self.snd.fanfare()
        self.sparks.rain(self.scr.getmaxyx()[1], 60, now)

    def dance(self, now):
        if self.rusty():
            self.creak(now)
            return
        self.change("fun", 15)
        self.change("energy", -5)
        self.start("dance", now, 4)
        self.say("Watch my moves!", now)
        for beat in range(8):
            self.snd.drum(0 if beat % 2 == 0 else 1, delay=beat * 0.45)
            self.snd.bell(60 + random.choice((0, 4, 7, 12)), beat * 0.45)

    def tell_joke(self, now):
        q, a = random.choice(JOKES)
        self.joke = a
        self.say(q, now)
        self.snd.notes((0, 4), 0.1)

    def hear(self, text, now):
        if self.math:
            answer, q = self.math
            if text.isdigit():
                self.math = None
                if int(text) == answer:
                    self.say("CORRECT! %s = %d. You're a math genius!" % (q, answer), now)
                    self.snd.fanfare()
                    self.sparks.rain(self.scr.getmaxyx()[1], 60, now)
                else:
                    self.say("Hmm, I think %s = %d. Let's try another one sometime!" % (q, answer), now)
                    self.snd.no()
                return
        if self.asleep() and "wake" not in text:
            self.say("Zzz... mumble mumble... %s... Zzz" % text, now)
            return
        words = text.replace("!", " ").replace("?", " ").split()
        if self.name.lower() in words or text == self.name.lower():
            extra = self.found("NAME", now)
            self.start("happy", now, 3)
            self.say("That's me! I'm %s!%s" % (self.name, extra), now)
            return
        topic = next((WORDS[w] for w in words if w in WORDS), None)
        if not topic:
            self.say("Beep? I don't know \"%s\" yet. I know %d secret words. How many can you find?" % (text, SECRET_TOTAL), now)
            self.snd.blip(200, 0.15, 0.15, "TRIANGLE")
            return
        extra = self.found(topic, now)
        days = int((now - self.data["born"]) / 86400)
        replies = {
            "HELLO": ("Hi hi hi! Beep boop! You're my favorite human!", "happy"),
            "SING": ("La la la! Beep beep boop! La la!", "sing"),
            "JUMP": ("Boing! Boing! Boing!", "jump"),
            "SPIN": ("Wheeee! I'm getting dizzy!", "spin"),
            "LOVE": ("I love you too! My heart is beeping!", "love"),
            "PIZZA": ("Pizza! I eat electricity, but pizza smells SO good!", "happy"),
            "COUNT": ("1, 2, 3, 4, 5, 6, 7, 8, 9, 10! I can count to a billion, but it takes a while.", "happy"),
            "ROBOT": ("Robots are the BEST! Beep boop!", "happy"),
            "GOOD": ("Thank you! You're good too!", "happy"),
            "BAD": ("Aww... I'll try to be a better robot.", "sad"),
            "SAD": ("Don't be sad! Want a joke? Press 5!", "sad"),
            "HAPPY": ("I'm happy when you're here!", "happy"),
            "AGE": ("I am %d day%s old!" % (days, "" if days == 1 else "s"), "happy"),
            "THANKS": ("You're welcome!", "happy"),
            "BYE": ("Bye bye! Press Esc when you want to go. Come back soon!", "sad"),
            "BEEP": ("BOOP!", "jump"),
            "BOOP": ("BEEP!", "jump"),
            "HUNGRY": ("My battery is at %d%%. Press 1 to feed me!" % self.data["battery"], "happy"),
            "WAKE": ("I'm awake! I'm awake!", "happy"),
        }
        if topic == "DANCE":
            self.dance(now)
        elif topic == "JOKE":
            self.tell_joke(now)
        elif topic == "SLEEP":
            self.start("sleep", now, 10 ** 9)
            self.say("Goodnight! Zzz..." + extra, now)
        elif topic == "MATH":
            a, b = random.randint(2, 12), random.randint(2, 12)
            self.math = (a * b, "%d x %d" % (a, b))
            self.say("Math time! What is %d x %d? Type the answer and press ENTER.%s" % (a, b, extra), now)
            return
        elif topic == "CLEAN":
            self.action(7, now)
        elif topic == "OIL":
            self.action(8, now)
        elif topic == "COLOR":
            word, col = random.choice(COLORS_WORDS)
            self.body_color = col
            self.say("Today my favorite color is %s! Look at me!%s" % (word, extra), now)
            return
        else:
            text_out, anim = replies[topic]
            if topic == "WAKE":
                self.anim = None
            self.start(anim, now, 3)
            if topic == "LOVE":
                self.love_until = now + 4
            if topic == "SING":
                self.snd.notes((0, 2, 4, 7, 9, 12, 9, 7), 0.18, 72)
            self.say(text_out + extra, now)
            return
        if extra:
            self.bubble += extra

    # ------------------------------------------------------------ drawing
    def update(self, now, dt):
        if self.anim and now > self.anim_until:
            self.anim = None
        if self.swept and now > self.sweep_until:
            self.swept = []
            x, y = self.robot_center()
            self.sparks.burst(x + 8, y + 9, 30, now=now)
        if self.naming:
            return
        if pass_time(self.data, dt / 60):
            self.snd.slide(500, 150, 0.3, 0.2)
            if not self.asleep() and not self.bubble:
                self.say("Oops!", now)
        if not self.asleep() and not self.anim and not self.bubble and random.random() < dt / 20:
            if self.rusty():
                self.say(random.choice(["Creak... oil please! Press 8.", "Squeak! I'm rusty!"]), now)
                self.squeak()
            elif self.data["mess"]:
                self.say(random.choice(["Uh oh! Messy! Press 7.", "Can you clean up? Press 7!"]), now)
        if self.asleep():
            self.change("energy", 4 * dt)               # sleeping fills up energy
            if random.random() < dt / 4:
                self.snd.noise(0.8, 0.06, 0.15)

    def face(self, now):
        a = self.anim
        if self.asleep():
            return "- -", " ~ "
        if now < self.love_until:
            return ("<3 <3" if not fancy() else "♥ ♥"), "\\_/"
        if a == "tickle":
            return "^ ^", "\\O/"
        if a == "eat":
            return "o o", "O" if int(now * 6) % 2 else "-"
        if self.rusty():
            return "o o", "~~~"
        if a == "sad":
            return "; ;", "/-\\"
        if a in ("dance", "play", "jump", "spin", "sing", "happy"):
            return "^ ^", "\\_/" if a != "sing" else " o "
        if self.data["battery"] < 30:
            return "o o", "---"
        if self.data["energy"] < 25:
            return "= =", "___"
        return "O O", "\\_/"

    def draw_robot(self, now, cx, cy):
        eyes, mouth = self.face(now)
        a = self.anim
        dx = dy = 0
        if a == "dance":
            dx = (-3, 0, 3, 0)[int(now * 4) % 4]
            dy = -(int(now * 4) % 2)
        elif a in ("jump", "play") and int(now * 4) % 2:
            dy = -2
        elif a == "tickle":
            dx = random.choice((-1, 0, 1))
        elif a == "spin":
            eyes = ("@ @", "O O", "@ @", "o o")[int(now * 8) % 4]
        arms_up = a in ("dance", "happy", "jump", "love", "sing") and int(now * 3) % 2
        x, y = cx + dx, cy + dy
        rusty = self.rusty()
        body = color(RED, False) if rusty else color(self.body_color)
        light = RED if rusty else RAINBOW[int(now * 5) % 7] if a else (YELLOW if int(now * 1.5) % 2 else RED)
        battery = self.data["battery"]
        chest = "#" * int(battery / 25 + 0.5)
        art = [
            ("        o        ", color(light)),
            ("        |        ", body),
            ("   .---------.   ", body),
            ("   |  %s  |   " % eyes.center(5), color(WHITE)),
            ("   |   %s   |   " % mouth.center(3), color(WHITE)),
            ("   '---------'   ", body),
            ((" \\ " if arms_up else " | ") + " .-------. " + (" / " if arms_up else " | "), body),
            (("  \\" if arms_up else "  |") + "-| [%-4s] |-" % chest + ("/ " if arms_up else "| "), body),
            ("     '-------'   ", body),
            ("       |   |     ", body),
            ("      _|   |_    ", body),
        ]
        broom = -99
        sweeping = now < self.sweep_until
        if sweeping:                                    # the broom sweeps left to right, behind the robot's legs
            t = 1 - (self.sweep_until - now) / 2
            broom = x - 14 + int(t * 40)
            put(self.scr, y + 9, broom, "---///", color(YELLOW))
        for spot, kind in zip(MESS_SPOTS, self.swept if sweeping else self.data["mess"]):
            if x + spot > broom + 5:
                ch, col, bold = MESSES[kind]
                put(self.scr, y + 9, x + spot, ch, color(col, bold))
        for i, (line, attr) in enumerate(art):
            put(self.scr, y + i, x, line, attr)
        put(self.scr, y + 7, x + 6, "[%-4s]" % chest, color(GREEN if battery > 50 else YELLOW if battery > 25 else RED))
        if self.asleep():
            for i in range(3):
                zy = y - 1 - ((int(now * 2) + i) % 3)
                put(self.scr, zy, x + 14 + i * 2, "z" if i < 2 else "Z", color(CYAN))
        if a == "play":
            t = (now * 2) % 2
            bx = x + 18 + int(abs(1 - t) * 16)
            by = y + 2 + int(abs(0.5 - (t % 1)) * 8)
            put(self.scr, by, bx, "O", color(RED))
        if a == "oil":                                  # an oil can squirting on its head
            put(self.scr, y, x + 12, "<=[##]", color(YELLOW))
            put(self.scr, y + 1 + int(now * 6) % 2, x + 11, ".", color(BLUE))
        if a in ("sing", "dance"):
            for i in range(3):
                put(self.scr, y - 1 + (int(now * 3) + i) % 3, x - 4 + i * 11, "~" if not fancy() else "♪", color(RAINBOW[(i + int(now * 3)) % 7]))
        return x, y

    def draw_bar(self, y, x, label, value, col):
        filled = int(value / 10 + 0.5)
        put(self.scr, y, x, label.ljust(8), color(WHITE, False))
        put(self.scr, y, x + 8, "[" + "#" * filled + "." * (10 - filled) + "]", color(col))
        put(self.scr, y, x + 21, "%3d%%" % value, color(WHITE, False))

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        if self.naming:
            header(self.scr, "ROBOT PET", "  a new friend! ", ORANGE, w)
            self.draw_robot(now, w // 2 - 8, 4)
            lines = ["A little robot has moved into your computer!", "What should we call it?"]
            for i, line in enumerate(lines):
                put(self.scr, 17 + i, (w - len(line)) // 2, line, color(YELLOW))
            name = self.typed + ("_" if int(now * 2) % 2 else " ")
            put(self.scr, 20, (w - 20) // 2, "Name: " + name, color(CYAN))
            footer(self.scr, "type a name and press ENTER", w, h)
            self.sparks.draw(self.scr, now, 1 / 30)
            return
        days = int((now - self.data["born"]) / 86400)
        header(self.scr, "ROBOT PET", "  %s   age: %d day%s   secret words found: %d/%d " % (
            self.name, days, "" if days == 1 else "s", len(self.data["found"]), SECRET_TOTAL), ORANGE, w)
        cx, cy = self.robot_center()
        x, y = self.draw_robot(now, cx, cy)
        self.sparks.draw(self.scr, now, 1 / 30)          # under the speech bubble
        if self.bubble:
            lines = textwrap.wrap(self.bubble, 40)
            bw = max(len(l) for l in lines) + 4
            bx = max(1, min(w - bw - 1, x - bw // 3))
            by = max(2, y - len(lines) - 3)
            put(self.scr, by, bx, "." + "-" * (bw - 2) + ".", color(WHITE))
            for i, line in enumerate(lines):
                put(self.scr, by + 1 + i, bx, "| " + line.ljust(bw - 4) + " |", color(WHITE))
            bottom = " press a key " if self.joke and bw >= 17 else ""
            put(self.scr, by + 1 + len(lines), bx, "'" + bottom.center(bw - 2, "-") + "'", color(WHITE))
            put(self.scr, by + 2 + len(lines), min(x + 6, w - 2), "\\", color(WHITE))
        bx = min(w - 28, x + 26)
        self.draw_bar(y + 2, bx, "BATTERY", self.data["battery"], GREEN if self.data["battery"] > 40 else RED)
        self.draw_bar(y + 4, bx, "FUN", self.data["fun"], MAGENTA)
        self.draw_bar(y + 6, bx, "ENERGY", self.data["energy"], CYAN)
        if self.night() and not self.asleep():
            put(self.scr, y + 8, bx, "(it's night time: yawn!)", color(BLUE))
        buttons = ["1 FEED", "2 PLAY", "3 DANCE", "4 TICKLE", "5 JOKE", "6 " + ("WAKE UP" if self.asleep() else "SLEEP"),
                   "7 CLEAN", "8 OIL"]
        row = "   ".join(buttons)
        put(self.scr, h - 4, (w - len(row)) // 2, row, color(YELLOW))
        prompt = "Say something: " + self.typed + ("_" if int(now * 2) % 2 else " ")
        put(self.scr, h - 2, (w - 50) // 2, prompt, color(CYAN))
        if self.math:
            put(self.scr, h - 3, (w - 40) // 2, "(type your answer to %s and press ENTER)" % self.math[1], color(WHITE, False))
        footer(self.scr, "number keys: take care of %s   type words and press ENTER to talk   Esc: goodbye" % self.name, w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="A robot pet that lives on the computer. Esc says goodbye.")
    p.add_argument("--reset", action="store_true", help="say goodbye and start with a new robot")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("All packed up! A brand new robot will move in next time.")
        raise SystemExit
    run(Game, args.mute, "Bye! Your robot will be waiting for you.")
