#!/usr/bin/env python3
"""
SKI HILL - ski down a snowy mountain. Watch out for trees... and the snow monster!

  LEFT / RIGHT   turn (each press turns a bit more)
  DOWN           point straight down the hill: fastest!
  UP             stop
  SPACE          jump
  Esc            leave

Collect stars, ski between the flags for bonus stars, and fly off the ramps.
After 400 meters the snow monster wakes up and chases you. If it catches you,
you get a big snowy HUG and the run is over. How far can you ski?

  python3 ski.py           ski
  python3 ski.py --reset   forget the best run
  python3 ski.py --mute    no sound
"""
import argparse
import json
import os
import random
import time

from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, best_scale, color,
                     curses, draw_big_centered, footer, header, is_enter, put, run)

SAVE_FILE = os.path.expanduser("~/.ski_hill")
MONSTER_AT = 400                # meters before the snow monster wakes up
ACROSS = [-1.4, -0.9, 0, 0.9, 1.4]      # sideways speed for each way the skis can point, left to right
DOWN = [0.35, 0.8, 1.0, 0.8, 0.35]      # downhill speed for each way
SKIER = {           # three lines each; the bottom line is the skis
    -2: [" o ", "/|\\", "== "], -1: [" o ", "/|\\", "/ /"], 0: [" o ", "/|\\", "| |"],
    1: [" o ", "/|\\", "\\ \\"], 2: [" o ", "/|\\", " =="],
    "stop": [" o ", "/|\\", "\\ /"], "jump": ["\\o/", " | ", "/ \\"], "crash": [" * ", "\\o/", "---"],
}
THINGS = {          # picture, color of each line, what happens if you touch it
    "tree": ([" ^ ", "/^\\", " | "], [GREEN, GREEN, ORANGE], "crash"),
    "bigtree": (["  ^  ", " /^\\ ", "/^^^\\", "  |  "], [GREEN, GREEN, GREEN, ORANGE], "crash"),
    "rock": (["(@)"], [WHITE], "crash"),
    "star": (["*"], [YELLOW], "star"),
    "ramp": (["/==\\"], [CYAN], "ramp"),
    "bump": (["~"], [WHITE], None),
}
MONSTER = [[" .---. ", "( O O )", "/|===|\\", " |   | "],
           ["\\.---./", " (O O) ", " |===| ", " /   \\ "]]


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.sparks = Sparkles()
        self.best = self.load()
        self.state = "title"
        self.note, self.note_until, self.note_color = "", 0.0, WHITE

    # ------------------------------------------------------------ saving
    def load(self):
        try:
            with open(SAVE_FILE) as f:
                d = json.load(f)
            return {"meters": int(d.get("meters", 0)), "stars": int(d.get("stars", 0))}
        except (OSError, ValueError, AttributeError, TypeError):
            return {"meters": 0, "stars": 0}

    def save(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(self.best, f)
        except OSError:
            pass

    def say(self, text, now, secs=2.5, col=WHITE):
        self.note, self.note_until, self.note_color = text, now + secs, col

    # ------------------------------------------------------------ a new run
    def start(self, now):
        h, w = self.scr.getmaxyx()
        self.w, self.h = w, h
        self.row = max(4, h // 4)                   # the screen row the skier stays on; the hill moves up
        self.x = w / 2 - 1.5
        self.y = 0.0                                # how far down the hill, in rows
        self.heading, self.stopped = 0, True
        self.speed = 0.0
        self.air_until = self.crash_until = self.safe_until = 0.0
        self.stars = 0
        self.things = []
        self.made_to = 10                           # a clear space to start in
        self.tracks = []
        self.track_at = 0.0
        self.monster = None
        self.warned = False
        self.state = "ski"
        self.make_hill()
        self.say("Press DOWN to go! LEFT and RIGHT turn. SPACE jumps.", now, 5, CYAN)
        self.snd.notes((0, 4, 7), 0.08)

    def top_speed(self):
        """Straight down the hill, in rows a second. It slowly gets faster the farther you go."""
        return self.h * (0.25 + min(0.15, self.meters() / 2000 * 0.15))

    def meters(self):
        return int(self.y / 2)

    def make_hill(self):
        """Put trees, rocks, stars and things on the hill below the bottom of the screen."""
        bottom = self.y + (self.h - self.row) + 2
        while self.made_to < bottom:
            r = self.made_to
            busy = (0.15 + min(0.25, r / 5000)) * self.w / 80      # more things the farther down you go
            for _ in range(int(busy) + (random.random() < busy % 1)):
                self.add_thing(r)
            self.made_to += 1

    def add_thing(self, r):
        kind = random.choices(["tree", "bigtree", "rock", "star", "ramp", "bump", "gate"],
                              [30, 12, 12, 24, 5, 10, 7])[0]
        if kind == "gate":
            gap = 9
            x = random.randint(2, self.w - gap - 4)
            if not self.crowded(x - 2, r - 3, gap + 6, 6):
                self.things.append({"kind": "gate", "x": x, "y": r, "gap": gap, "done": False})
            return
        pic = THINGS[kind][0]
        x = random.randint(1, self.w - len(pic[0]) - 1)
        if not self.crowded(x - 1, r - 1, len(pic[0]) + 2, len(pic) + 2):
            self.things.append({"kind": kind, "x": x, "y": r, "got": False})

    def crowded(self, x, y, w, h):
        for t in self.things:
            if t["y"] > y + h or t["y"] < y - 6:
                continue
            tw = t["gap"] + 2 if t["kind"] == "gate" else len(THINGS[t["kind"]][0][0])
            th = 1 if t["kind"] == "gate" else len(THINGS[t["kind"]][0])
            if t["x"] < x + w and x < t["x"] + tw and t["y"] < y + h and y < t["y"] + th:
                return True
        return False

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if self.state in ("title", "hug"):
            if (key == " " or is_enter(key)) and now > getattr(self, "hug_at", 0) + 1.0:
                self.start(now)
            return True
        if now < self.crash_until:
            return True
        if key == curses.KEY_LEFT:
            self.heading = -1 if self.stopped else max(-2, self.heading - 1)
            self.stopped = False
            self.snd.noise(0.08, 0.1, 1.5)
        elif key == curses.KEY_RIGHT:
            self.heading = 1 if self.stopped else min(2, self.heading + 1)
            self.stopped = False
            self.snd.noise(0.08, 0.1, 1.5)
        elif key == curses.KEY_DOWN:
            self.heading, self.stopped = 0, False
            self.snd.noise(0.1, 0.1, 1.2)
        elif key == curses.KEY_UP:
            self.stopped = True
            self.snd.noise(0.3, 0.15, 0.8)
        elif key == " " and now > self.air_until and self.speed > 1:
            self.air_until = now + 0.7
            self.snd.slide(300, 700, 0.2, 0.2)
        return True

    # ------------------------------------------------------------ moving
    def update(self, now, dt):
        if self.state != "ski":
            return
        crashed = now < self.crash_until
        target = 0 if (self.stopped or crashed) else self.top_speed()
        if self.speed < target:
            self.speed = min(target, self.speed + self.top_speed() * 0.8 * dt)
        else:
            self.speed = max(target, self.speed - self.top_speed() * 2.5 * dt)
        h = 0 if self.stopped else self.heading
        self.x = max(0, min(self.w - 3, self.x + self.speed * ACROSS[h + 2] * dt))
        self.y += self.speed * DOWN[h + 2] * dt
        self.make_hill()
        self.things = [t for t in self.things if t["y"] > self.y - self.row - 6]
        if now > self.air_until and self.speed > 0.5 and now > self.track_at:
            self.track_at = now + 0.04
            self.tracks = (self.tracks + [(int(self.x) + 1, self.y + 2)])[-150:]
        if not crashed:
            self.touch(now)
        self.chase(now, dt)

    def touch(self, now):
        """What the skier bumps into."""
        flying = now < self.air_until
        feet = self.y + 2
        for t in self.things:
            if t["kind"] == "gate":
                if not t["done"] and t["y"] <= feet:
                    t["done"] = True
                    if t["x"] + 2 <= self.x + 1 <= t["x"] + t["gap"]:
                        self.stars += 3
                        self.say("Through the flags! +3 stars!", now, 2, YELLOW)
                        self.snd.notes((0, 4, 7, 12), 0.06)
                continue
            pic, _, what = THINGS[t["kind"]]
            if what is None or t["got"] or t["y"] > feet + 1 or t["y"] + len(pic) < self.y:
                continue
            if self.touching(t, pic, what == "star"):
                self.bump(t, what, now, flying)

    def touching(self, t, pic, whole_body):
        """Does any part of this thing touch the skier's skis (or, for stars, any part of the skier)?"""
        for i, line in enumerate(pic):
            for j, ch in enumerate(line):
                cx, cy = t["x"] + j, t["y"] + i
                if ch == " ":
                    continue
                if whole_body and self.x - 0.5 <= cx <= self.x + 2.5 and self.y - 0.5 <= cy <= self.y + 2.5:
                    return True
                if not whole_body and self.x <= cx <= self.x + 2 and int(self.y + 2) == int(cy):
                    return True
        return False

    def bump(self, t, what, now, flying):
        if what == "star":
            t["got"] = True
            self.stars += 1
            self.snd.bell(84 + random.choice((0, 4, 7, 12)))
            self.sparks.burst(t["x"], self.row + (t["y"] - self.y), 8, [YELLOW, WHITE], 10, now, "*+.")
        elif what == "ramp" and not flying:
            self.air_until = now + 1.4
            t["got"] = True
            self.say(random.choice(["WHEEEE!", "Big air!", "You're flying!"]), now, 2, CYAN)
            self.snd.slide(300, 1200, 0.5, 0.25)
        elif what == "crash" and not flying and now > self.safe_until:
            self.crash_until = now + 1.5
            self.safe_until = now + 2.7                 # time to get up and ski past it
            self.speed = 0
            self.say(random.choice(["BONK!", "OOF!", "Oopsie!", "Timber!"]), now, 1.5, ORANGE)
            self.snd.no()
            self.sparks.burst(self.x + 1, self.row + 1, 15, [WHITE, CYAN], 12, now, "*.")

    def chase(self, now, dt):
        m = self.meters()
        if m >= MONSTER_AT - 60 and not self.warned:
            self.warned = True
            self.say("Uh oh... something is waking up on the mountain...", now, 4, MAGENTA)
            self.snd.slide(200, 60, 1.2, 0.3, "SAW")
        if m >= MONSTER_AT and not self.monster:
            self.monster = {"x": self.x - 2, "y": self.y - self.row - 8, "start": m}
            self.say("THE SNOW MONSTER! Ski fast!", now, 3, RED)
            self.snd.slide(120, 60, 1.0, 0.35, "SAW")
        if not self.monster:
            return
        mo = self.monster
        hurry = 0.92 + min(0.2, (m - mo["start"]) / 3000)    # it slowly gets faster
        if self.y - mo["y"] > self.row + 25:
            hurry = 1.4                                   # never too far behind
        mo["y"] += self.top_speed() * hurry * dt
        mx = self.x - 2
        step = self.top_speed() * 1.3 * dt
        mo["x"] += max(-step, min(step, mx - mo["x"]))
        if mo["y"] + 3 >= self.y and abs(mo["x"] + 2 - self.x) <= 3:
            self.caught(now)

    def caught(self, now):
        self.state, self.hug_at = "hug", now
        m = self.meters()
        self.new_best = m > self.best["meters"]
        if self.new_best:
            self.best["meters"] = m
        self.best["stars"] = max(self.best["stars"], self.stars)
        self.save()
        self.snd.slide(400, 100, 0.8, 0.3, "SAW")
        if self.new_best:
            self.snd.fanfare()
        self.sparks.burst(self.x + 1, self.row + 1, 60, [WHITE, CYAN, MAGENTA], 25, now, "*o.")

    # ------------------------------------------------------------ drawing
    def draw(self, now):
        h, w = self.scr.getmaxyx()
        if self.state == "title":
            return self.draw_title(now, w, h)
        if (w, h) != (self.w, self.h):
            self.state = "title"                        # the screen changed size
            return
        header(self.scr, "SKI HILL", "  %d meters   stars: %d   best: %d meters " % (
            self.meters(), self.stars, self.best["meters"]), CYAN, w)
        if self.state == "hug":                         # just the monster and the message
            self.draw_monster(now, w)
            self.sparks.draw(self.scr, now, 1 / 30)
            return self.draw_hug(now, w, h)
        for tx, ty in self.tracks:
            ty = self.row + ty - self.y
            if 1 <= ty < self.row or abs(tx - self.x - 1) > 2 and ty >= 1:   # not over the title or the skier
                put(self.scr, ty, tx, "'", color(WHITE, False) | curses.A_DIM)
        for t in self.things:
            sy = self.row + t["y"] - self.y
            if sy < 1 or sy >= h - 1:
                continue
            if t["kind"] == "gate":
                put(self.scr, int(sy), t["x"], "|>", color(RED))
                put(self.scr, int(sy), t["x"] + t["gap"], "<|", color(BLUE))
                continue
            if t.get("got") and t["kind"] == "star":
                continue
            pic, cols, _ = THINGS[t["kind"]]
            for i, line in enumerate(pic):
                if not 1 <= int(sy) + i < h - 1:                # between the title and the help line
                    continue
                for j, ch in enumerate(line):
                    if ch != " ":
                        dim = cols[i] == ORANGE or t["kind"] == "bump"             # tree trunks and snow bumps
                        put(self.scr, int(sy) + i, t["x"] + j, ch, color(cols[i], not dim))
        self.draw_skier(now)
        if self.monster:
            self.draw_monster(now, w)
        self.sparks.draw(self.scr, now, 1 / 30)
        if now < self.note_until:
            put(self.scr, 2, max(0, (w - len(self.note)) // 2), self.note, color(self.note_color))
        footer(self.scr, "LEFT/RIGHT turn   DOWN go fast   UP stop   SPACE jump   Esc leave", w, h)

    def draw_skier(self, now):
        if self.state == "hug":
            return
        flying = now < self.air_until
        if now < self.crash_until:
            pic = SKIER["crash"]
        elif flying:
            pic = SKIER["jump"]
        elif self.stopped:
            pic = SKIER["stop"]
        else:
            pic = SKIER[self.heading]
        if now < self.safe_until and now > self.crash_until and int(now * 8) % 2:
            return                                      # blinks while getting going again
        lift = -1 if flying else 0
        cols = [color(YELLOW), color(RED), color(MAGENTA)]
        for i, line in enumerate(pic):
            for j, ch in enumerate(line):
                if ch != " ":
                    put(self.scr, self.row + i + lift, int(self.x) + j, ch, cols[i])
        if flying:
            put(self.scr, self.row + 3, int(self.x), " . ", color(WHITE, False) | curses.A_DIM)    # shadow

    def draw_monster(self, now, w):
        mo = self.monster
        sy = self.row + mo["y"] - self.y
        if sy + 4 < 1:                                   # still above the screen: show where it is
            if int(now * 4) % 2:
                put(self.scr, 1, int(mo["x"]) + 2, "!!!", color(RED) | curses.A_REVERSE)
            return
        pic = MONSTER[int(now * 4) % 2]
        for i, line in enumerate(pic):
            for j, ch in enumerate(line):
                if ch != " ":
                    put(self.scr, int(sy) + i, int(mo["x"]) + j, ch, color(WHITE))

    def draw_hug(self, now, w, h):
        sx, sy = best_scale("HUG!", w - 4, h // 3)
        top = max(4, h // 3)
        draw_big_centered(self.scr, "HUG!", top, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 5)) % 7]))
        lines = [("The snow monster caught you and gave you a big snowy hug!", WHITE),
                 ("You skied %d meters and found %d stars." % (self.meters(), self.stars), YELLOW)]
        if self.new_best:
            lines.append(("NEW BEST! Your farthest run ever!", GREEN))
        else:
            lines.append(("Your best is %d meters." % self.best["meters"], CYAN))
        if now > self.hug_at + 1.0:
            lines.append(("SPACE: ski again", WHITE))
        for i, (text, col) in enumerate(lines):
            put(self.scr, top + 5 * sy + 2 + i * 2, (w - len(text)) // 2, text, color(col))
        footer(self.scr, "SPACE ski again   Esc leave", w, h)

    def draw_title(self, now, w, h):
        header(self.scr, "SKI HILL", "  best: %d meters   most stars: %d " % (self.best["meters"], self.best["stars"]),
               CYAN, w)
        for i in range(w // 6):                         # falling snow
            x = (i * 37 + int(now * (3 + i % 4))) % w
            y = (i * 11 + int(now * (4 + i % 3))) % (h - 2) + 1
            put(self.scr, y, x, "*" if i % 3 else ".", color(WHITE, False))
        sx, sy = best_scale("SKI HILL", w - 4, h // 2 - 4)
        draw_big_centered(self.scr, "SKI HILL", 3, w, sx, sy, colors=lambda i: color(CYAN if i < 3 else WHITE))
        y = 3 + 5 * sy + 2
        hill = [("  ^  ", GREEN), (" /^\\ ", GREEN), ("/^^^\\", GREEN)]
        for i, (line, col) in enumerate(hill):
            put(self.scr, y + i, w // 2 - 14, line, color(col))
        pic = SKIER[1 if int(now) % 2 else -1]
        for i, line in enumerate(pic):
            put(self.scr, y + i, w // 2 - 1, line, [color(YELLOW), color(RED), color(MAGENTA)][i])
        for i, line in enumerate(MONSTER[int(now * 2) % 2]):
            put(self.scr, y + i, w // 2 + 10, line, color(WHITE))
        y += 6
        lines = [("LEFT / RIGHT   turn", WHITE), ("DOWN           go fast", WHITE), ("UP             stop", WHITE),
                 ("SPACE          jump", WHITE), ("", WHITE), ("Get the stars.  Dodge the trees.", YELLOW),
                 ("Don't let the snow monster catch you!", MAGENTA), ("", WHITE), ("Press SPACE to start!", GREEN)]
        for i, (text, col) in enumerate(lines):
            put(self.scr, y + i, (w - 37) // 2, text, color(col))
        footer(self.scr, "SPACE start   Esc leave", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ski down the hill and get away from the snow monster. Esc quits.")
    p.add_argument("--reset", action="store_true", help="forget the best run")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("The best run is forgotten. Fresh snow!")
        raise SystemExit
    run(Game, args.mute, "Bye! See you on the slopes.")
