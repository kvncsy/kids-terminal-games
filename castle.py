#!/usr/bin/env python3
"""
CASTLE CANNONS - aim your cannon and knock down the other castle.

  UP / DOWN      tilt the cannon
  LEFT / RIGHT   less / more power
  SPACE          FIRE!
  Esc            back to the start screen (Esc again leaves the game)

Play the computer (sleepy, silly or tricky) or another person. Cannonballs
blow holes in the ground, and if the ground under a castle is blown away the
castle falls down and gets hurt. Three hits and a castle falls apart. Every
win against the computer gives a new level: hills, a mountain, a lake, a
floating island... and from level 2 the wind starts to blow.

  python3 castle.py           play
  python3 castle.py --reset   back to level 1
  python3 castle.py --mute    no sound
"""
import argparse
import json
import math
import os
import random
import time

import kidslib
from kidslib import (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE, RAINBOW, Sparkles, best_scale, color,
                     curses, draw_big_centered, fancy, footer, header, is_enter, put, run)

SAVE_FILE = os.path.expanduser("~/.castle_cannons")
TOP = 2                         # screen row where the sky starts (row 0 is the title, row 1 the aim bars)
HEARTS = 3
STEP = 1 / 120                  # physics step in seconds
FLIGHT = 2.4                    # seconds a full-power 45 degree shot flies
EMPTY, DIRT, WATER = 0, 1, 2
CASTLE = ["# ## #", "######", "##  ##"]     # solid blocks; the cannon sits in a gap on top
CASTLE_W = 6
LANDS = ["hills", "mountain", "lake", "island"]
COMPUTERS = {       # how wrong its first shot is, how fast it learns, and how good it ever gets
    "sleepy": (0.40, 0.85, 0.12),
    "silly": (0.45, 0.95, 0.25),
    "tricky": (0.28, 0.75, 0.06),
}


class Game:
    def __init__(self, scr, snd):
        self.scr, self.snd = scr, snd
        self.sparks = Sparkles()
        self.level = self.load_level()
        self.mode = None                # "sleepy", "silly", "tricky" or "two"
        self.state = "menu"
        self.round = 0
        self.wins = [0, 0]
        self.note, self.note_until, self.note_color = "", 0.0, WHITE

    # ------------------------------------------------------------ saving
    def load_level(self):
        try:
            with open(SAVE_FILE) as f:
                return max(1, int(json.load(f).get("level", 1)))
        except (OSError, ValueError, AttributeError, TypeError):
            return 1

    def save_level(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump({"level": self.level}, f)
        except OSError:
            pass

    def say(self, text, now, secs=3.0, col=WHITE):
        self.note, self.note_until, self.note_color = text, now + secs, col

    # ------------------------------------------------------------ a new round
    def new_round(self, now):
        h, w = self.scr.getmaxyx()
        self.W, self.GH = w, h - TOP - 1                 # the ground grid fills the screen above the footer
        land = LANDS[(self.level - 1) % len(LANDS)] if self.mode != "two" else LANDS[self.round % len(LANDS)]
        if self.level > len(LANDS) and self.mode != "two":
            land = random.choice(LANDS)
        self.land = land
        self.make_land(land)
        level = self.level if self.mode != "two" else 1 + self.round
        biggest = min(3, level - 1)                     # no wind on level 1
        self.wind = random.randint(-biggest, biggest) if biggest else 0
        self.gravity = 2 * 1.15 * self.W / FLIGHT ** 2
        self.vmax = math.sqrt(1.15 * self.W * self.gravity)
        self.castles = []
        for side in (0, 1):
            lo, hi = (0.05, 0.13) if side == 0 else (0.82, 0.90)
            x = int(self.W * random.uniform(lo, hi))
            x = min(self.W - CASTLE_W - 1, x)
            bottom = self.flatten(x)
            self.castles.append({"x": x, "bottom": bottom, "hearts": HEARTS, "angle": 45, "power": 60,
                                 "color": BLUE if side == 0 else RED, "fall": 0, "side": side})
        self.loose = set()
        self.ball = None
        self.trail = []
        self.turn = self.round % 2 if self.mode == "two" else 0
        self.cpu_shots = 0
        self.dirty = set(range(self.GH))
        self.rows = [[] for _ in range(self.GH)]
        self.start_turn(now)

    def make_land(self, land):
        W, GH = self.W, self.GH
        top = int(GH * 0.55)                            # how tall the tallest hill can be
        p1, p2 = random.uniform(0, 6.3), random.uniform(0, 6.3)
        a1, a2 = random.uniform(2, 4) * math.pi / W, random.uniform(6, 10) * math.pi / W
        mid = W / 2 + random.uniform(-0.05, 0.05) * W
        heights = []
        for c in range(W):
            f = 0.30 + 0.12 * math.sin(c * a1 + p1) + 0.05 * math.sin(c * a2 + p2)
            bump = math.exp(-((c - mid) / (W * 0.12)) ** 2)
            if land == "mountain":
                f = 0.22 + 0.06 * math.sin(c * a2 + p2) + 0.62 * bump
            elif land == "lake":
                f = 0.42 + 0.05 * math.sin(c * a2 + p2) - 0.36 * math.exp(-((c - mid) / (W * 0.18)) ** 2)
            elif land == "island":
                f = 0.18 + 0.05 * math.sin(c * a2 + p2)
            heights.append(max(1, min(top, int(f * top / 0.85))))
        self.grid = [bytearray(W) for _ in range(GH)]
        for c, height in enumerate(heights):
            for r in range(GH - height, GH):
                self.grid[r][c] = DIRT
        if land == "lake":                              # fill the valley with water
            level = GH - int(0.30 * top / 0.85)
            for c in range(W):
                for r in range(level, GH):
                    if self.grid[r][c] == EMPTY:
                        self.grid[r][c] = WATER
        if land == "island":                            # a floating island in the sky, in the way
            cy, rx, ry = int(GH * 0.40), W * 0.10, max(2, int(GH * 0.08))
            for r in range(cy - ry, cy + ry + 1):
                dy = (r - cy) / ry
                half = rx * math.sqrt(1 - dy * dy) if dy <= 0 else rx * (1 - dy)     # round on top, pointy below
                for c in range(int(mid - half), int(mid + half) + 1):
                    if 0 <= r < GH and 0 <= c < W:
                        self.grid[r][c] = DIRT

    def flatten(self, x):
        """Make a flat spot for a castle at column x. Returns the row its bottom sits on."""
        surface = [self.surface(c) for c in range(x, x + CASTLE_W)]
        row = sorted(surface)[len(surface) // 2]
        for c in range(x - 1, x + CASTLE_W + 1):
            if 0 <= c < self.W:
                for r in range(max(0, row - 12), self.GH):
                    self.grid[r][c] = DIRT if r >= row else EMPTY
        return row - 1

    def surface(self, c):
        for r in range(self.GH):
            if self.grid[r][c] != EMPTY:
                return r
        return self.GH - 1

    # ------------------------------------------------------------ turns
    def human(self, side):
        return self.mode == "two" or side == 0

    def start_turn(self, now):
        self.state = "aim" if self.human(self.turn) else "cpu"
        who = self.castles[self.turn]
        if self.state == "aim":
            if self.mode == "two":
                self.say("PLAYER %d's turn! (%s castle)" % (self.turn + 1, "blue" if self.turn == 0 else "red"),
                         now, 3, who["color"])
            else:
                self.say("Your turn! UP/DOWN aims, LEFT/RIGHT is power, SPACE fires!", now, 4, CYAN)
            self.snd.notes((0, 7), 0.08)
        else:
            self.cpu_plan(now)

    def cpu_plan(self, now):
        me, them = self.castles[self.turn], self.castles[1 - self.turn]
        first, learn, best = COMPUTERS[self.mode]
        miss = max(best, first * learn ** self.cpu_shots)
        angle, power = self.aim_at(me, them)
        if self.mode == "silly" and random.random() < 0.15:          # oops
            angle, power = random.choice([(88, 60), (20, 15), (80, 100)])
            self.cpu_oops = True
        else:
            power *= 1 + random.choice((-1, 1)) * miss * random.uniform(0.6, 1.0)
            angle += random.uniform(-1, 1) * miss * 20
            self.cpu_oops = False
        self.cpu_from = (me["angle"], me["power"])
        self.cpu_to = (max(5, min(88, angle)), max(5, min(100, power)))
        self.cpu_start, self.cpu_fire = now, now + (2.2 if self.mode == "sleepy" else 1.4)
        self.say(random.choice(["Hmm... let me think...", "My turn!", "Here it comes!"]) if self.mode != "sleepy" else
                 random.choice(["*yawn* My turn...", "Zzz... oh! My turn."]), now, 2, RED)
        self.cpu_shots += 1

    def aim_at(self, me, them):
        """The angle and power that would hit them (if nothing is in the way)."""
        tx, ty = them["x"] + CASTLE_W / 2, (them["bottom"] - 1) * 2
        best = None
        for angle in (30, 40, 45, 50, 60, 70, 80):
            lo, hi = 5.0, 100.0
            for _ in range(14):
                mid = (lo + hi) / 2
                x = self.fly_to(me, angle, mid, ty, terrain=False)
                if (x > tx) == (me["side"] == 0):
                    hi = mid
                else:
                    lo = mid
            power = (lo + hi) / 2
            hit = self.fly_to(me, angle, power, ty, terrain=True)
            score = abs(hit - tx) if hit is not None else 999
            if best is None or score < best[0]:
                best = (score, angle, power)
        return best[1], best[2]

    def fly_to(self, me, angle, power, ty, terrain):
        """Where a shot comes down: at height ty in empty sky, or where it lands for real."""
        x, y, vx, vy = self.launch(me, angle, power)
        dt = 1 / 40
        for _ in range(400):
            vx += self.wind_push() * dt
            vy += self.gravity * dt
            x, y = x + vx * dt, y + vy * dt
            if not terrain:
                if vy > 0 and y >= ty:
                    return x
            else:
                c, r = int(x), int(y / 2)
                if c < 0 or c >= self.W:
                    return None
                if r >= self.GH or r >= 0 and self.grid[r][c] != EMPTY or self.castle_at(c, r, me) is not None:
                    return x
        return x

    def wind_push(self):
        return self.wind * 0.017 * self.W

    def barrel(self, castle, angle=None):
        """The cannon's pivot and the end of its barrel, in columns and rows."""
        angle = castle["angle"] if angle is None else angle
        px, py = castle["x"] + (4 if castle["side"] == 0 else 1), castle["bottom"] - 2
        d = 1 if castle["side"] == 0 else -1
        if angle < 25:
            step = (d, 0)
        elif angle < 65:
            step = (d, -1)
        else:
            step = (0, -1)
        return (px, py), step

    def launch(self, castle, angle, power):
        (px, py), (sx, sy) = self.barrel(castle, angle)
        v = self.vmax * math.sqrt(power / 100)
        d = 1 if castle["side"] == 0 else -1
        a = math.radians(angle)
        return px + 2 * sx + 0.5, (py + 2 * sy) * 2 + 1, d * v * math.cos(a), -v * math.sin(a)

    def fire(self, now):
        me = self.castles[self.turn]
        x, y, vx, vy = self.launch(me, me["angle"], me["power"])
        self.ball = {"x": x, "y": y, "vx": vx, "vy": vy, "t": 0.0, "acc": 0.0}
        self.trail = []
        self.state = "fly"
        self.snd.slide(260, 70, 0.35, 0.35, "SQUARE")
        self.snd.noise(0.3, 0.25, 0.5)
        (px, py), _ = self.barrel(me)
        self.sparks.burst(px, TOP + py, 10, [YELLOW, ORANGE, WHITE], 12, now, "*.")

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if self.state == "menu":
            choices = {"1": "sleepy", "2": "silly", "3": "tricky", "4": "two"}
            if isinstance(key, str) and key in choices:
                self.mode, self.round, self.wins = choices[key], 0, [0, 0]
                self.snd.fanfare()
                self.new_round(now)
            return True
        if self.state == "over":
            if key == " " or is_enter(key):
                self.new_round(now)
            return True
        if self.state != "aim":
            return True
        me = self.castles[self.turn]
        if key == curses.KEY_UP:
            me["angle"] = min(85, me["angle"] + 5)
            self.snd.blip(400 + me["angle"] * 6, 0.04, 0.12, "TRIANGLE")
        elif key == curses.KEY_DOWN:
            me["angle"] = max(5, me["angle"] - 5)
            self.snd.blip(400 + me["angle"] * 6, 0.04, 0.12, "TRIANGLE")
        elif key == curses.KEY_RIGHT:
            me["power"] = min(100, me["power"] + 5)
            self.snd.blip(200 + me["power"] * 8, 0.04, 0.12, "SQUARE")
        elif key == curses.KEY_LEFT:
            me["power"] = max(5, me["power"] - 5)
            self.snd.blip(200 + me["power"] * 8, 0.04, 0.12, "SQUARE")
        elif key == " " or is_enter(key):
            self.fire(now)
        return True

    def escape(self, now):
        """Esc in a game goes back to the start screen; Esc there leaves."""
        if self.state == "menu":
            return False
        self.state = "menu"
        return True

    # ------------------------------------------------------------ flying and booms
    def castle_at(self, c, r, skip=None):
        for i, k in enumerate(self.castles):
            if k is skip or k["hearts"] <= 0:
                continue
            if k["x"] <= c < k["x"] + CASTLE_W and k["bottom"] - 2 <= r <= k["bottom"]:
                return i
        return None

    def update(self, now, dt):
        if self.state == "cpu":
            if now >= self.cpu_fire:
                me = self.castles[self.turn]
                me["angle"], me["power"] = self.cpu_to
                if self.cpu_oops:
                    self.say("Oops!", now, 2, RED)
                self.fire(now)
        elif self.state == "fly":
            b = self.ball
            b["acc"] += dt
            while b["acc"] >= STEP and self.state == "fly":
                b["acc"] -= STEP
                b["t"] += STEP
                b["vx"] += self.wind_push() * STEP
                b["vy"] += self.gravity * STEP
                b["x"] += b["vx"] * STEP
                b["y"] += b["vy"] * STEP
                self.check_ball(now)
            if self.state == "fly" and (not self.trail or self.trail[-1] != (int(b["x"]), int(b["y"] / 2))):
                self.trail = (self.trail + [(int(b["x"]), int(b["y"] / 2))])[-8:]
        elif self.state == "settle" and now >= self.settle_next:
            self.settle_next = now + 1 / 30
            if not self.settle_step(now):
                self.after_shot(now)
        elif self.state == "pause" and now >= self.pause_until:
            self.turn = 1 - self.turn
            self.start_turn(now)

    def check_ball(self, now):
        b = self.ball
        c, r = int(b["x"]), int(b["y"] / 2)
        me = self.castles[self.turn]
        if c < 0 or c >= self.W:
            self.miss_msg(now, "Whoosh! Off the edge of the world!", b["x"])
            self.state, self.settle_next = "settle", now
            return
        if r >= self.GH:
            r = self.GH - 1
        if r < 0:
            return
        own = me if b["t"] < 0.25 else None                 # don't hit our own cannon on the way out
        hit = self.castle_at(c, r, own)
        cell = self.grid[r][c]
        if cell == WATER and hit is None:
            self.sparks.burst(c, TOP + r, 20, [CYAN, BLUE, WHITE], 10, now, "~o.")
            self.snd.noise(0.5, 0.2, 0.3)
            self.miss_msg(now, "SPLOOSH! Into the water!", b["x"])
            self.state, self.settle_next = "settle", now
        elif cell == DIRT or hit is not None or r == self.GH - 1:
            self.boom(c, r, now)

    def boom(self, c, r, now):
        rx, ry = max(3, self.W // 40), 2
        for y in range(r - ry, r + ry + 1):
            for x in range(c - rx, c + rx + 1):
                if 0 <= y < self.GH - 1 and 0 <= x < self.W and ((x - c) / rx) ** 2 + ((y - r) / ry) ** 2 <= 1:
                    if self.grid[y][x] == DIRT:
                        self.grid[y][x] = EMPTY
                        self.dirty.update((y, y + 1))
        for x in range(c - rx - 1, c + rx + 2):
            if 0 <= x < self.W:
                self.loose.add(x)
        self.sparks.burst(c, TOP + r, 40, [YELLOW, ORANGE, RED, WHITE], 22, now, "*#o.")
        self.snd.noise(0.6, 0.35, 0.25)
        self.snd.drum(0)
        me = self.castles[self.turn]
        hurt = []
        for k in self.castles:                          # anything close enough to the boom gets hurt
            if k["hearts"] <= 0:
                continue
            nx = min(max(c, k["x"]), k["x"] + CASTLE_W - 1)
            ny = min(max(r, k["bottom"] - 2), k["bottom"])
            if ((nx - c) / (rx + 1)) ** 2 + ((ny - r) / (ry + 1)) ** 2 <= 1:
                k["hearts"] -= 1
                hurt.append(k)
                self.sparks.burst(k["x"] + 3, TOP + k["bottom"] - 1, 30, [k["color"], WHITE], 16, now)
        if hurt:
            if me in hurt and len(hurt) == 1:
                self.say("Oops! That's your OWN castle!", now, 3, YELLOW)
                self.snd.no()
            else:
                self.say(random.choice(["BOOM! A HIT!", "KABOOM! Right on target!", "BONK! Got it!"]), now, 3, YELLOW)
                self.snd.notes((0, 4, 7, 12), 0.06, 60)
        else:
            self.miss_msg(now, "BOOM! Missed.", c)
        self.state, self.settle_next = "settle", now

    def miss_msg(self, now, text, x):
        """Tell the kid what went wrong: too short or too far."""
        me, them = self.castles[self.turn], self.castles[1 - self.turn]
        if not self.human(self.turn):
            self.say(text + " The computer missed!", now, 3, RED)
            return
        mx, tx = me["x"] + 3, them["x"] + 3
        if abs(x - mx) < abs(tx - mx):
            self.say(text + " Too short! Try more POWER.", now, 4, YELLOW)
        else:
            self.say(text + " Too far! Try less POWER.", now, 4, YELLOW)

    def settle_step(self, now):
        """Loose dirt falls down one row, castles with nothing under them fall. True if anything moved."""
        moved = False
        for c in list(self.loose):
            col_moved = False
            for r in range(self.GH - 2, -1, -1):
                if self.grid[r][c] == DIRT and self.grid[r + 1][c] != DIRT:
                    self.grid[r + 1][c], self.grid[r][c] = DIRT, EMPTY
                    self.dirty.update((r, r + 1, r + 2))
                    col_moved = True
            if col_moved:
                moved = True
            else:
                self.loose.discard(c)
        for k in self.castles:
            below = k["bottom"] + 1
            if below < self.GH and not any(self.grid[below][c] == DIRT for c in range(k["x"], k["x"] + CASTLE_W)):
                k["bottom"] += 1
                k["fall"] += 1
                moved = True
        return moved

    def after_shot(self, now):
        self.ball, self.trail = None, []
        for k in self.castles:
            if k["fall"] >= 3 and k["hearts"] > 0:
                k["hearts"] -= 1
                self.say("CRASH! The ground fell out from under the castle!", now, 3, ORANGE)
                self.snd.slide(600, 80, 0.6, 0.3, "SQUARE")
            k["fall"] = 0
        alive = [k for k in self.castles if k["hearts"] > 0]
        if len(alive) == 2:
            self.state, self.pause_until = "pause", now + 1.2
            return
        winner = alive[0]["side"] if alive else 1 - self.turn
        loser = self.castles[1 - winner]
        self.sparks.burst(loser["x"] + 3, TOP + loser["bottom"] - 1, 80, RAINBOW, 30, now)
        self.wins[winner] += 1
        self.state, self.winner = "over", winner
        self.round += 1
        if self.mode != "two" and winner == 0:
            self.level += 1
            self.save_level()
        if self.mode == "two" or winner == 0:
            self.snd.fanfare()
            self.sparks.rain(self.W, 100, now)
        else:
            self.snd.no()

    # ------------------------------------------------------------ drawing
    def terrain_rows(self):
        """Turn changed rows of the grid into a few long strings (much faster than one square at a time)."""
        block = kidslib.BLOCK
        for r in self.dirty:
            if not 0 <= r < self.GH:
                continue
            runs, row, above = [], self.grid[r], self.grid[r - 1] if r > 0 else bytearray(self.W)
            c = 0
            while c < self.W:
                look = self.look_of(r, c, row, above)
                start = c
                while c < self.W and self.look_of(r, c, row, above) == look:
                    c += 1
                if look:
                    ch = {"grass": block, "dirt": block, "rock": "#", "water": "~"}[look]
                    attr = {"grass": color(GREEN), "dirt": color(ORANGE, False), "rock": color(WHITE, False),
                            "water": color(CYAN)}[look]
                    runs.append((start, ch * (c - start), attr))
            self.rows[r] = runs
        self.dirty = set()

    def look_of(self, r, c, row, above):
        kind = row[c]
        if kind == DIRT:
            return "rock" if r == self.GH - 1 else ("grass" if above[c] != DIRT else "dirt")
        return "water" if kind == WATER else None

    def draw_blocks(self, y, x, pair, damage=0, seed=0):
        """A castle made of solid blocks, with its top row at y. Hits make it darker and crumbly."""
        # shade blocks the Linux console font has (it has no dark shade), or plain ASCII without UTF-8
        solid, worn, crumbly = (kidslib.BLOCK, "\u2592", "\u2591") if kidslib.BLOCK != "#" else ("#", "%", ":")
        for i, line in enumerate(CASTLE):
            for j, ch in enumerate(line):
                if ch != "#":
                    continue
                r = random.Random(seed * 1000 + i * 10 + j).random()   # the same pattern every time it's drawn
                if damage >= 2 and r < 0.12:
                    continue                                    # a block knocked right out
                if r < 0.33 * damage:
                    look = crumbly if damage >= 2 and r < 0.4 else worn
                    put(self.scr, y + i, x + j, look, color(pair, False))
                else:
                    put(self.scr, y + i, x + j, solid, color(pair))

    def draw_castle(self, k, now, active):
        x, y = k["x"], TOP + k["bottom"] - 2
        if k["hearts"] <= 0:
            put(self.scr, y + 2, x, "_/\\_,.", color(WHITE, False))
            return
        self.draw_blocks(y, x, k["color"], HEARTS - k["hearts"], k["side"] + 7 * self.round)
        (px, py), (sx, sy) = self.barrel(k)
        ch = "=" if sy == 0 else ("|" if sx == 0 else ("/" if sx > 0 else "\\"))
        put(self.scr, TOP + py, px, "o", color(WHITE))
        for n in (1, 2):
            put(self.scr, TOP + py + n * sy, px + n * sx, ch, color(WHITE))
        heart = "♥" if fancy() else "<3"
        hearts = heart * k["hearts"]
        put(self.scr, y - 3, x + (CASTLE_W - len(hearts)) // 2, hearts, color(RED))       # above the cannon
        if active and int(now * 3) % 2:
            put(self.scr, y - 4, x + 2, "vv", color(YELLOW))

    def draw_bars(self, k, active):
        w = self.W
        width = 10
        filled = int(k["power"] / 100 * width + 0.5)
        wide = w >= 100
        text = ("ANGLE %2d   POWER [%s%s]" if wide else "ANGLE %2d POWER [%s%s]") % (
            k["angle"], "#" * filled, "." * (width - filled))
        if self.mode == "two":
            name = ("PLAYER %d" if wide else "P%d") % (k["side"] + 1)
        else:
            name = "YOU" if k["side"] == 0 else ("COMPUTER" if wide else "CPU")
        text = name + ("  " if wide else " ") + text
        x = 2 if k["side"] == 0 else w - len(text) - 2
        put(self.scr, 1, x, text, color(k["color"]) | (curses.A_REVERSE if active else 0))

    def draw(self, now):
        h, w = self.scr.getmaxyx()
        if self.state == "menu" or (w, h - TOP - 1) != (getattr(self, "W", w), getattr(self, "GH", h - TOP - 1)):
            if self.state != "menu":
                self.state = "menu"                     # the screen changed size: start again
            return self.draw_menu(now, w, h)
        cpu = self.state == "cpu"
        if cpu:                                          # the computer slides its cannon into place
            t = min(1.0, (now - self.cpu_start) / max(0.1, self.cpu_fire - self.cpu_start - 0.3))
            me = self.castles[self.turn]
            me["angle"] = int(self.cpu_from[0] + (self.cpu_to[0] - self.cpu_from[0]) * t)
            me["power"] = int(self.cpu_from[1] + (self.cpu_to[1] - self.cpu_from[1]) * t)
        vs = "2 players  %d - %d" % tuple(self.wins) if self.mode == "two" else "level %d   vs the %s computer" % (
            self.level, self.mode.upper())
        header(self.scr, "CASTLE CANNONS", "  %s   land: %s " % (vs, self.land), ORANGE, w)
        if self.dirty:
            self.terrain_rows()
        for r, runs in enumerate(self.rows):
            for x, s, attr in runs:
                put(self.scr, TOP + r, x, s, attr)
        for i, k in enumerate(self.castles):
            active = i == self.turn and self.state in ("aim", "cpu")
            self.draw_castle(k, now, active)
            self.draw_bars(k, active)
        if self.wind:
            arrows = (">" if self.wind > 0 else "<") * abs(self.wind)
            put(self.scr, TOP, (w - 12) // 2, "wind %s" % arrows, color(CYAN))
        if self.state == "aim":                          # dots show which way the ball will start off
            me = self.castles[self.turn]
            x, y, vx, vy = self.launch(me, me["angle"], me["power"])
            for i in range(1, 4):
                t = i * 0.06
                dx = vx * t + 0.5 * self.wind_push() * t * t
                dy = vy * t + 0.5 * self.gravity * t * t
                if (y + dy) >= 0:
                    put(self.scr, TOP + int((y + dy) / 2), int(x + dx), ".", color(WHITE, False))
        for c, r in self.trail[:-1]:
            put(self.scr, TOP + r, c, ".", color(YELLOW, False))
        if self.ball:
            bx, by = int(self.ball["x"]), int(self.ball["y"] / 2)
            if by < 0:
                put(self.scr, TOP, bx, "^", color(YELLOW))      # up above the top of the screen
            else:
                put(self.scr, TOP + by, bx, "O", color(WHITE))
        self.sparks.draw(self.scr, now, 1 / 30)
        if now < self.note_until:
            put(self.scr, TOP + 2, max(0, (w - len(self.note)) // 2), self.note, color(self.note_color))
        if self.state == "over":
            self.draw_over(now, w, h)
        footer(self.scr, "UP/DOWN aim   LEFT/RIGHT power   SPACE fire   Esc start screen", w, h)

    def draw_over(self, now, w, h):
        if self.mode == "two":
            text, col = ("BLUE WINS!", BLUE) if self.winner == 0 else ("RED WINS!", RED)
            more = "SPACE: play again"
        elif self.winner == 0:
            text, col, more = "YOU WIN!", YELLOW, "SPACE: go to level %d" % self.level
        else:
            text, col, more = "TRY AGAIN", RED, "SPACE: try again"
        sx, sy = best_scale(text, w - 4, h // 2)
        y = max(TOP + 3, h // 4)
        draw_big_centered(self.scr, text, y, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 5)) % 7])
                          if self.winner == 0 or self.mode == "two" else color(col))
        put(self.scr, y + 5 * sy + 1, (w - len(more)) // 2, more, color(WHITE))

    def draw_menu(self, now, w, h):
        header(self.scr, "CASTLE CANNONS", "  level %d " % self.level, ORANGE, w)
        sx, sy = best_scale("CASTLE", w - 4, h // 2 - 4)
        draw_big_centered(self.scr, "CASTLE", 3, w, sx, sy, colors=lambda i: color(RAINBOW[(i + int(now * 3)) % 7]))
        y = 3 + 5 * sy + 6
        self.draw_blocks(y, w // 2 - 20, BLUE)            # two little castles facing each other
        self.draw_blocks(y, w // 2 + 14, RED)
        put(self.scr, y, w // 2 - 16, "o", color(WHITE))
        put(self.scr, y, w // 2 + 15, "o", color(WHITE))
        arc = int(now * 12) % 30
        put(self.scr, y - 1 - int(3.5 * math.sin(arc / 30 * math.pi)), w // 2 - 12 + arc, "O", color(WHITE))
        y += 6
        choices = [("1", "play the SLEEPY computer", GREEN), ("2", "play the SILLY computer", YELLOW),
                   ("3", "play the TRICKY computer", RED), ("4", "TWO PLAYERS (take turns)", CYAN)]
        for i, (key, what, col) in enumerate(choices):
            put(self.scr, y + i * 2, w // 2 - 16, key, color(WHITE) | curses.A_REVERSE)
            put(self.scr, y + i * 2, w // 2 - 13, what, color(col))
        footer(self.scr, "press 1, 2, 3 or 4   Esc: leave", w, h)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Aim your cannon and knock down the other castle. Esc quits.")
    p.add_argument("--reset", action="store_true", help="back to level 1")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.reset:
        try:
            os.remove(SAVE_FILE)
        except OSError:
            pass
        print("Back to level 1!")
        raise SystemExit
    run(Game, args.mute, "Bye! The castles will be waiting.")
