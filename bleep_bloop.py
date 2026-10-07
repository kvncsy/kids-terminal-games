#!/usr/bin/env python3
"""
BLEEP BLOOP BAND - a button-mashing synthesizer for kids.

Every key makes music, and nothing sounds wrong: all notes come from
pentatonic scales. Each keyboard row is a different instrument:

  1 2 3 ... 0   drums        (hold one down for a drum roll)
  Q W E ... P   bells
  A S D ... L   bloops       (left/right arrows change the wave shape)
  Z X C ... M   bass
  left = low, right = high

Kids discover the rest. There are 13 secrets; run with --hints to see them.
The screen shows the real sound wave and the numbers sent to the speaker.

Sound is made with wavetable synthesis (one-cycle waveform tables read at
different speeds, with linear interpolation), after Jan Wilczek's article:
https://thewolfsound.com/sound-synthesis/wavetable-synthesis-algorithm/

Plain Python, no installs. Audio plays through pacat (PulseAudio) or aplay.

  python3 bleep_bloop.py              play
  python3 bleep_bloop.py --hints      list the secrets (grown-ups only!)
  python3 bleep_bloop.py --reset      hide all found secrets again
  python3 bleep_bloop.py --mute       no sound (for testing)

EXIT: press Esc. Ctrl+C / Ctrl+Z are captured so small hands can't quit.
"""
import argparse
import array
import curses
import fcntl
import json
import locale
import math
import os
import queue
import random
import re
import shutil
import subprocess
import threading
import time

# ================================================================ wavetables
SR = 22050          # samples per second
BLOCK = 256         # samples per audio block (~12 ms)
TABLE_N = 2048      # samples in one wave cycle
LEAD = 0.06         # how far ahead of the speaker we render (seconds)
MAX_VOICES = 12
MELLOW = 2800       # warmth: the output is softened above this many Hz (higher = brighter, 0 = off)
MASTER = 2.5        # overall volume, before the soft limiter (mashing never gets harsh, it just squashes)
DRUMS = 1.6         # drum level in the mix, relative to the other instruments (1.0 = as designed)


def make_table(f, n=TABLE_N):
    """One cycle of f(phase), normalized to -1..1, plus a guard sample for interpolation."""
    t = [f(2 * math.pi * i / n) for i in range(n)]
    mean = sum(t) / n
    t = [v - mean for v in t]
    peak = max(abs(v) for v in t) or 1.0
    t = [v / peak for v in t]
    return t + [t[0]]


def additive(harmonics):
    """Band-limited wave from (harmonic number, strength) pairs."""
    return lambda x: sum(g * math.sin(k * x) for k, g in harmonics)


def gaussian_blob(x):
    """The 'sum of 5 Gaussians' wave from the wavetable article."""
    return (math.exp(-3 * (x - 1) ** 2) - 0.4 * math.exp(-3 * (x - 2.3) ** 2)
            + 0.8 * math.exp(-10 * (x - 3.3) ** 2) - math.exp(-7 * (x - 4.5) ** 2)
            + 0.3 * math.exp(-2 * (x - 5) ** 2))


SINE = make_table(math.sin)
TRIANGLE = make_table(additive([(k, (-1) ** (k // 2) / k ** 2) for k in range(1, 16, 2)]))
SQUARE = make_table(additive([(k, 1 / k) for k in range(1, 22, 2)]))
SAW = make_table(additive([(k, 1 / k) for k in range(1, 25)]))
ORGAN = make_table(additive([(1, 1), (2, .6), (3, .45), (4, .3), (6, .2), (8, .15)]))
BLOB = make_table(gaussian_blob)
BELL = make_table(additive([(1, 1), (2, .37), (4, .12)]))        # several tones baked into one table
BASS = make_table(additive([(1, 1.9)] + [(k, 1 / k ** 2) for k in range(2, 9)]))   # round, not buzzy

_rng = random.Random(7)
NOISE_N = 8192
NOISE = [_rng.uniform(-1, 1) for _ in range(NOISE_N)]
HISS = [NOISE[i] - NOISE[i - 1] for i in range(NOISE_N)]   # brighter noise, for hi-hats
NOISE.append(NOISE[0])
HISS.append(HISS[0])

SHAPES = [("SQUARE", SQUARE), ("TRIANGLE", TRIANGLE), ("SAW", SAW),
          ("SINE", SINE), ("ORGAN", ORGAN), ("BLOB", BLOB)]


# ================================================================ voices
def tone(table, freq, gain):
    return [table, TABLE_N, 0.0, TABLE_N * freq / SR, gain]


def hiss(table, speed, gain):
    return [table, NOISE_N, random.uniform(0, NOISE_N - 1), speed, gain]


class Voice:
    """One sound: wavetable partials shaped by an attack/decay/sustain/release envelope."""

    def __init__(self, partials, amp, attack=0.004, decay=0.3, sustain=0.0, release=0.2,
                 hold=0.0, sweep_from=1.0, sweep_time=0.0, delay=0.0):
        self.parts = []
        for p in partials:
            target = p[3]
            mult = 1.0
            if sweep_from != 1.0 and sweep_time > 0:
                p[3] = target * sweep_from
                mult = (1 / sweep_from) ** (1 / (sweep_time * SR))
            self.parts.append(p + [target, mult])
        self.amp = amp
        self.env = 0.0
        self.stage = 0                      # 0 attack, 1 decay/sustain, 2 release
        self.att = amp / max(1, attack * SR)
        self.dcoef = math.exp(-6.9 / (decay * SR))
        self.sus = sustain * amp
        self.rcoef = math.exp(-6.9 / (release * SR))
        self.hold_until = time.time() + hold   # the keyboard side extends this while a key is held
        self.delay = int(delay * SR)
        self.done = False

    def render(self, out, n, now):
        if self.delay >= n:
            self.delay -= n
            return
        start, self.delay = self.delay, 0
        if self.stage < 2 and self.sus > 0 and now > self.hold_until:
            self.stage = 2
        env, stage = self.env, self.stage
        amp, att, sus, dc, rc = self.amp, self.att, self.sus, self.dcoef, self.rcoef
        e = [0.0] * n
        for i in range(start, n):
            if stage == 0:
                env += att
                if env >= amp:
                    env, stage = amp, 1
            elif stage == 1:
                env = sus + (env - sus) * dc
            else:
                env *= rc
            e[i] = env
        self.env, self.stage = env, stage
        if env < 1e-4 and (stage == 2 or (stage == 1 and sus == 0)):
            self.done = True

        for p in self.parts:
            tbl, size, ph, inc, g, target, mult = p
            if mult == 1.0:
                for i in range(start, n):
                    j = int(ph)
                    a = tbl[j]
                    out[i] += e[i] * g * (a + (tbl[j + 1] - a) * (ph - j))
                    ph += inc
                    if ph >= size:
                        ph -= size
            else:
                falling = mult < 1.0
                for i in range(start, n):
                    j = int(ph)
                    a = tbl[j]
                    out[i] += e[i] * g * (a + (tbl[j + 1] - a) * (ph - j))
                    ph += inc
                    if ph >= size:
                        ph -= size
                    inc *= mult
                    if (inc <= target) if falling else (inc >= target):
                        inc, mult = target, 1.0
                        p[6] = 1.0
            p[2], p[3] = ph, inc


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---- instruments
def drum(idx, delay=0.0):
    d = dict(delay=delay)
    v = [
        lambda: Voice([tone(SINE, 48, 1.0)], .95, .001, .45, sweep_from=3.3, sweep_time=.1, **d),      # 1 kick
        lambda: Voice([hiss(NOISE, 1.0, .55), tone(TRIANGLE, 190, .45)], .6, .001, .2, **d),         # 2 snare
        lambda: Voice([hiss(HISS, 1.0, .5)], .35, .001, .06, **d),                                   # 3 hi-hat
        lambda: Voice([hiss(HISS, 1.0, .5)], .3, .001, .45, **d),                                    # 4 open hat
        lambda: Voice([hiss(NOISE, .55, .7)], .55, .002, .25, **d),                                  # 5 clap
        lambda: Voice([tone(SINE, 90, 1.0)], .7, .001, .45, sweep_from=1.7, sweep_time=.15, **d),    # 6 low tom
        lambda: Voice([tone(SINE, 150, 1.0)], .6, .001, .4, sweep_from=1.7, sweep_time=.15, **d),    # 7 high tom
        lambda: Voice([tone(SQUARE, 540, .5), tone(SQUARE, 800, .5)], .25, .001, .3, **d),          # 8 cowbell
        lambda: Voice([tone(SQUARE, 110, .5)], .22, .002, .4, sweep_from=13, sweep_time=.3, **d),    # 9 laser
        lambda: Voice([tone(SINE, 420, 1.0)], .5, .005, .6, sweep_from=.33, sweep_time=.45, **d),    # 0 boing
    ][idx]()
    for p in v.parts:
        p[4] *= DRUMS
    return v


def bell(freq, delay=0.0):
    return Voice([tone(BELL, freq, .75)], .6, .01, 1.6, delay=delay)


def bloop(freq, shape, hold):
    return Voice([tone(shape, freq, .5)], .85, .008, .35, sustain=.55, release=.25, hold=hold,
                 sweep_from=.7, sweep_time=.04)


def bass(freq, hold):
    return Voice([tone(BASS, freq, .75)], 1.0, .006, .3, sustain=.7,
                 release=.15, hold=hold)


def silly():
    return random.choice([
        lambda: Voice([tone(SAW, 220, .5)], .35, .005, .2, sweep_from=1.45, sweep_time=.15),    # quack
        lambda: Voice([tone(SINE, 1100, .7)], .4, .02, .5, sweep_from=.27, sweep_time=.4),      # slide up
        lambda: Voice([tone(SINE, 200, .7)], .4, .02, .5, sweep_from=4.5, sweep_time=.4),       # slide down
        lambda: drum(9), lambda: drum(8),
    ])()


# ================================================================ worlds
WORLDS = [
    dict(name="SUNNY DAY", root=0, scale=[0, 2, 4, 7, 9], wet=.15, fb=.25, delay=.25,
         kick=[0, 8, 10], snare=[4, 12], hat=[0, 2, 4, 6, 8, 10, 12, 14], extra={}),
    dict(name="SPOOKY NIGHT", root=-3, scale=[0, 3, 5, 7, 10], wet=.3, fb=.4, delay=.33,
         kick=[0, 6, 8], snare=[4, 12], hat=[2, 6, 10, 14], extra={14: 6, 15: 5}),
    dict(name="OUTER SPACE", root=2, scale=[0, 2, 5, 7, 10], wet=.4, fb=.55, delay=.42,
         kick=[0, 10], snare=[8], hat=[0, 3, 6, 9, 12, 14], extra={15: 8}),
]
BPM = 104

# Enter plays the world's own beat, then each of these grooves, then stops.
# 16 steps per bar (the 4 beats are steps 0 4 8 12). ghost = quiet snare taps,
# swing = how late the in-between steps land (0 straight, .33 very bouncy),
# extra = {step: drum number or a tuple of them} (drums: 0 kick ... 4 clap, 7 cowbell, 9 boing).
GROOVES = [
    dict(name="FUNK MACHINE", bpm=98, swing=.12,
         kick=[0, 3, 10, 13], snare=[4, 12], ghost=[7, 9, 15], hat=[0, 2, 4, 8, 10, 12, 14], extra={6: 3}),
    dict(name="BOOM BAP", bpm=88, swing=.22,
         kick=[0, 7, 10, 11], snare=[4, 12], ghost=[15], hat=[0, 2, 4, 6, 8, 10, 12, 14], extra={}),
    dict(name="DISCO PARTY", bpm=120, swing=0,
         kick=[0, 4, 8, 12], snare=[], ghost=[], hat=[0, 4, 8, 12], extra={2: 3, 4: 4, 6: 3, 10: 3, 12: 4, 14: 3}),
    dict(name="COWBELL FEVER", bpm=108, swing=.08,
         kick=[0, 3, 8, 11], snare=[], ghost=[6, 13], hat=[2, 6, 10, 14],
         extra={0: 7, 3: 7, 6: 7, 10: 7, 12: 7, 14: 6, 15: 5}),
    dict(name="BOUNCY CASTLE", bpm=104, swing=.28,
         kick=[0, 6, 8], snare=[4, 12], ghost=[10], hat=[0, 2, 4, 6, 8, 10, 12, 14], extra={11: 9, 15: 4}),
]


# ================================================================ audio engine
def start_player():
    """Start a program that plays our raw audio: pacat (desktop sound server) or aplay (plain ALSA,
    for a text-only console with no sound server)."""
    players = [
        ["pacat", "--raw", "--format=s16le", "--rate=%d" % SR, "--channels=1",
         "--latency-msec=30", "--client-name=Bleep Bloop Band"],
        ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(SR), "-c", "1", "--buffer-time=60000"],
    ]
    for cmd in players:
        if not shutil.which(cmd[0]):
            continue
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        if proc.poll() is not None:      # couldn't reach a sound server; try the next player
            continue
        try:   # a tiny pipe keeps the delay between key and sound short
            fcntl.fcntl(proc.stdin.fileno(), fcntl.F_SETPIPE_SZ, 4096)
        except (AttributeError, OSError):
            pass
        return proc
    return None


class Engine(threading.Thread):
    def __init__(self, sound=True):
        super().__init__(daemon=True)
        self.inbox = queue.SimpleQueue()
        self.voices = []
        self.world = WORLDS[0]
        self.beat = None           # the playing beat: a world or a groove
        self.beat_acc = 0.0
        self.beat_step = 0
        self.last_kick = 0.0
        self.scope = [0.0] * 1024
        self.echo = [0.0] * int(SR * 0.5)
        self.echo_pos = 0
        self.warm = [0.0, 0.0]     # the two low-pass filter stages
        self.running = True
        self.proc = start_player() if sound else None

    def play(self, voice):
        self.inbox.put(voice)
        return voice

    @property
    def beat_on(self):
        return self.beat is not None

    def set_beat(self, beat):
        """Play this beat from the top (None stops)."""
        if beat is not self.beat:
            self.beat_acc = SR * 60 / beat.get("bpm", BPM) / 4 if beat else 0.0   # first step plays right away
            self.beat_step = 0
        self.beat = beat

    def beat_tick(self):
        w = self.beat
        if w is None:
            return
        step_len = SR * 60 / w.get("bpm", BPM) / 4
        self.beat_acc += BLOCK
        while self.beat_acc >= step_len:
            self.beat_acc -= step_len
            s = self.beat_step
            late = w.get("swing", 0) * step_len / SR if s % 2 else 0.0   # swing: in-between steps land late
            if s in w["kick"]:
                self.voices.append(drum(0, late))
                self.last_kick = time.time()
            if s in w["snare"]:
                self.voices.append(drum(1, late))
            if s in w.get("ghost", ()):
                v = drum(1, late)
                v.amp *= .3
                self.voices.append(v)
            if s in w["hat"]:
                v = drum(2, late)
                v.amp *= .6
                self.voices.append(v)
            extra = w["extra"].get(s, ())
            for idx in extra if isinstance(extra, tuple) else (extra,):
                self.voices.append(drum(idx, late))
            self.beat_step = (s + 1) % 16

    def run(self):
        start = time.perf_counter()
        written = 0
        while self.running:
            now = time.time()
            while True:
                try:
                    self.voices.append(self.inbox.get_nowait())
                except queue.Empty:
                    break
            self.beat_tick()
            if len(self.voices) > MAX_VOICES:
                self.voices = self.voices[-MAX_VOICES:]
            out = [0.0] * BLOCK
            for v in self.voices:
                v.render(out, BLOCK, now)
            self.voices = [v for v in self.voices if not v.done]

            # echo, a soft limiter so mashing never gets harsh, then two gentle low-pass stages for warmth
            w = self.world
            buf, pos, size = self.echo, self.echo_pos, int(SR * w["delay"])
            wet, fb = w["wet"], w["fb"]
            a = 1 - math.exp(-2 * math.pi * MELLOW / SR) if MELLOW else 1.0
            y1, y2 = self.warm
            for i in range(BLOCK):
                x = out[i]
                d = buf[pos]
                buf[pos] = x + d * fb
                pos += 1
                if pos >= size:
                    pos = 0
                y1 += a * (math.tanh((x + d * wet) * MASTER) - y1)
                y2 += a * (y1 - y2)
                out[i] = y2
            self.warm = [y1, y2]
            self.echo_pos = pos
            self.scope = self.scope[BLOCK:] + out

            if self.proc:
                data = array.array("h", [int(v * 32000) for v in out]).tobytes()
                try:
                    self.proc.stdin.write(data)
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    self.proc = None
            written += BLOCK
            ahead = written / SR - (time.perf_counter() - start)
            if ahead > LEAD:
                time.sleep(ahead - LEAD)
            elif ahead < -0.2:           # fell behind (computer was busy): catch up quietly
                start = time.perf_counter() - written / SR

    def stop(self):
        """Stop at once. Closing the pipe first could wait forever if the player stops
        reading while the audio thread is mid-write, freezing the game as it quits."""
        self.running = False
        proc, self.proc = self.proc, None
        if proc:
            try:
                proc.kill()                  # a stuck write in the audio thread now fails right away
                proc.wait(timeout=1)
            except Exception:
                pass
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=0.5)


# ================================================================ secrets
SECRETS = [
    ("up",    "STAIRS UP",     "Play four keys in one row, going left to right."),
    ("down",  "STAIRS DOWN",   "Walk down a row, right to left."),
    ("peck",  "WOODPECKER",    "Tap one key five times, fast."),
    ("band",  "WHOLE BAND",    "Play all four rows within two seconds."),
    ("solo",  "DRUM SOLO",     "Ten drum hits in four seconds."),
    ("roll",  "DRUM ROLL",     "Hold down a number key."),
    ("long",  "LOOONG NOTE",   "Hold a letter key down for three seconds."),
    ("world", "NEW WORLD",     "Press the space bar."),
    ("beat",  "BEAT MACHINE",  "Press Enter. Again to stop, and again for the next groove."),
    ("giant", "GIANT VOICE",   "Press the down arrow."),
    ("mouse", "MOUSE VOICE",   "Press the up arrow."),
    ("shape", "SHAPE SHIFTER", "Press the left or right arrow, then play the A row."),
    ("wake",  "WAKE UP!",      "Stay quiet until the band falls asleep, then play."),
]
SECRETS_FILE = os.path.expanduser("~/.bleep_bloop_secrets")


def load_found():
    try:
        with open(SECRETS_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def save_found(found):
    try:
        with open(SECRETS_FILE, "w") as f:
            json.dump(sorted(found), f)
    except OSError:
        pass


def repeat_timing():
    """The keyboard's auto-repeat delay and interval, so held keys can be detected.
    Without a desktop (no xset) the delay is unknown; fast repeats are still spotted."""
    try:
        out = subprocess.run(["xset", "q"], capture_output=True, text=True, timeout=2).stdout
        m = re.search(r"repeat delay:\s*(\d+)\s+repeat rate:\s*(\d+)", out)
        if m:
            return int(m.group(1)) / 1000, 1 / max(1, int(m.group(2)))
    except (OSError, subprocess.SubprocessError):
        pass
    return None, 0.033


# ================================================================ screen
RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA, WHITE, ORANGE = range(1, 9)
RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, MAGENTA]
ROWS = [
    ("drums", "1234567890", ORANGE, 0.0, None),
    ("bells", "QWERTYUIOP", YELLOW, 0.5, 72),
    ("bloops", "ASDFGHJKL", CYAN, 0.75, 60),
    ("bass", "ZXCVBNM", MAGENTA, 1.25, 36),
]
KEYPOS = {k: (r, i) for r, (_, keys, _, _, _) in enumerate(ROWS) for i, k in enumerate(keys)}
WORLD_COLORS = [YELLOW, MAGENTA, CYAN]
FACES = {"idle": "(o.o)", "sing": "(^O^)", "sleep": "(-.-)"}


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


class App:
    def __init__(self, scr, engine):
        self.scr = scr
        self.eng = engine
        self.utf = locale.getpreferredencoding().lower().replace("-", "") == "utf8"
        # the plain Linux text console has a small font: no music notes, arrows or round corners
        self.fancy = self.utf and os.environ.get("TERM") != "linux"
        self.rep_delay, self.rep_interval = repeat_timing()
        self.world = 0
        self.beat = -1             # the last beat chosen: -1 none yet, 0 the world's own beat, then GROOVES
        self.size = 0              # -1 giant, 0 normal, +1 mouse
        self.shape = 1             # TRIANGLE: the mellow one
        self.shape_shown_until = 0.0
        self.shape_changed = False
        self.sleeping = False
        self.last_input = time.time()
        self.keys = {}             # key -> press state, for spotting held keys
        self.lit = {}              # key -> time its pad stops glowing
        self.sing = {}             # row -> time its face stops singing
        self.parts = []
        self.toasts = []
        self.toast_until = 0.0
        self.found = load_found()
        self.hist = []
        self.drum_times = []
        self.row_times = {}
        self.peck = (None, [])
        self.numbers = []
        self.numbers_at = 0.0
        self.layout = {}

    def attr(self, pair, bold=True):
        return curses.color_pair(pair) | (curses.A_BOLD if bold else 0)

    # ------------------------------------------------------------ keys
    def handle_key(self, key, now):
        if key == "\x1b":
            return False
        name = self.key_name(key)
        if name is None:
            return True
        self.wake(now)
        st = self.keys.get(name)
        repeat = False
        if st:
            gap = now - st["last"]
            if gap < max(0.1, 3 * self.rep_interval):     # faster than any finger: auto-repeat
                repeat = True
                st["rep"] = True
            elif (self.rep_delay and not st["rep"] and st["last"] == st["press"]
                  and abs(gap - self.rep_delay) < 0.12):     # the first repeat, after the delay
                repeat = True
                st["rep"] = True
        if repeat:
            st["last"] = now
            st["count"] += 1
            self.held(name, st, now)
        else:
            st = self.keys[name] = {"press": now, "last": now, "rep": False, "count": 0, "voice": None}
            self.pressed(name, st, now)
        return True

    def key_name(self, key):
        if isinstance(key, str):
            if key == " ":
                return "SPACE"
            if key in "\n\r":
                return "ENTER"
            k = key.upper()
            return k if k in KEYPOS else "OTHER"
        names = {curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN", curses.KEY_LEFT: "LEFT",
                 curses.KEY_RIGHT: "RIGHT", curses.KEY_ENTER: "ENTER"}
        if key == curses.KEY_RESIZE:
            return None
        return names.get(key, "OTHER")

    def note(self, row, idx):
        w = WORLDS[self.world]
        base = ROWS[row][4]
        shift = -12 * self.size if row != 3 else (12 if self.size == 1 else 0)
        return mtof(base + w["root"] + w["scale"][idx % 5] + 12 * (idx // 5) + shift)

    def pressed(self, name, st, now):
        self.lit[name] = now + 0.18
        if name in KEYPOS:
            row, idx = KEYPOS[name]
            hold = (self.rep_delay or 0.5) + 0.12   # sound until auto-repeat can tell us the key is held
            if row == 0:
                self.eng.play(drum(idx))
            elif row == 1:
                self.eng.play(bell(self.note(row, idx)))
            elif row == 2:
                st["voice"] = self.eng.play(bloop(self.note(row, idx), SHAPES[self.shape][1], hold))
            else:
                st["voice"] = self.eng.play(bass(self.note(row, idx), hold))
            self.sing[row] = now + 0.25
            self.spawn(name, row, now)
            self.check_secrets(name, row, idx, now)
        elif name == "SPACE":
            self.world = (self.world + 1) % len(WORLDS)
            self.eng.world = WORLDS[self.world]
            if self.beat == 0 and self.eng.beat_on:
                self.eng.set_beat(WORLDS[self.world])
            self.eng.play(Voice([hiss(NOISE, .25, .6)], .4, .25, .9))
            self.toast("WELCOME TO", WORLDS[self.world]["name"], WORLD_COLORS[self.world], 1.6)
            self.unlock("world")
        elif name == "ENTER":                  # on, off, then the next beat: the world's, each groove, round again
            if self.eng.beat_on:
                self.eng.set_beat(None)
                self.toast("BEAT", "OFF", WHITE, 0.8)
            else:
                self.beat = (self.beat + 1) % (len(GROOVES) + 1)
                beat = WORLDS[self.world] if self.beat == 0 else GROOVES[self.beat - 1]
                self.eng.set_beat(beat)
                self.toast("NOW PLAYING", beat["name"], WORLD_COLORS[self.world], 1.2)
                self.unlock("beat")
        elif name in ("UP", "DOWN"):
            up = name == "UP"
            before = self.size
            self.size = max(-1, min(1, self.size + (1 if up else -1)))
            self.eng.play(Voice([tone(SINE, 1100 if up else 200, .7)], .4, .02, .5,
                                sweep_from=.27 if up else 4.5, sweep_time=.4))
            if self.size != before and self.size == 1:
                self.unlock("mouse")
            if self.size != before and self.size == -1:
                self.unlock("giant")
        elif name in ("LEFT", "RIGHT"):
            self.shape = (self.shape + (1 if name == "RIGHT" else -1)) % len(SHAPES)
            self.shape_shown_until = now + 1.8
            self.shape_changed = True
            self.eng.play(bloop(self.note(2, 2), SHAPES[self.shape][1], 0.25))
        else:
            self.eng.play(silly())
            self.spawn(None, random.randrange(4), now)

    def held(self, name, st, now):
        self.lit[name] = now + 0.12
        if name not in KEYPOS:
            return
        row, _ = KEYPOS[name]
        if row == 0:
            if st["count"] % 2 == 0:          # drum roll!
                self.eng.play(drum(KEYPOS[name][1]))
                self.sing[0] = now + 0.1
            if st["count"] >= 8:
                self.unlock("roll")
            return
        if st["voice"]:
            st["voice"].hold_until = time.time() + 0.15
        self.sing[row] = now + 0.15
        if now - st["press"] >= 3.0:
            self.unlock("long")
        if st["count"] % 4 == 0:
            self.spawn(name, row, now)

    def check_secrets(self, name, row, idx, now):
        who, times = self.peck
        times = [t for t in times if now - t < 2.5] + [now] if who == name else [now]
        self.peck = (name, times)
        if len(times) >= 5:
            self.unlock("peck")
        self.row_times[row] = now
        if len(self.row_times) == 4 and now - min(self.row_times.values()) < 2.0:
            self.unlock("band")
        if row == 0:
            self.drum_times = [t for t in self.drum_times if now - t < 4] + [now]
            if len(self.drum_times) >= 10:
                self.unlock("solo")
            return
        if row == 2 and self.shape_changed:
            self.unlock("shape")
        self.hist = (self.hist + [(row, idx, now)])[-4:]
        if len(self.hist) == 4 and all(h[0] == row for h in self.hist):
            steps = [(b[1] - a[1], b[2] - a[2]) for a, b in zip(self.hist, self.hist[1:])]
            if all(d == 1 and dt < 1.5 for d, dt in steps):
                self.unlock("up")
            if all(d == -1 and dt < 1.5 for d, dt in steps):
                self.unlock("down")

    def wake(self, now):
        self.last_input = now
        if self.sleeping:
            self.sleeping = False
            self.unlock("wake")

    def unlock(self, sid):
        if sid in self.found:
            return
        self.found.add(sid)
        save_found(self.found)
        name = next(n for s, n, _ in SECRETS if s == sid)
        self.toast("SECRET FOUND!", name, YELLOW, 2.4)
        w = WORLDS[self.world]
        for i, d in enumerate([0, 1, 2, 3, 5, 7]):
            self.eng.play(bell(mtof(72 + w["root"] + w["scale"][d % 5] + 12 * (d // 5)), delay=0.12 + i * 0.08))
        h, wd = self.scr.getmaxyx()
        for _ in range(90):
            self.parts.append([random.uniform(0, wd), random.uniform(-6, 0), random.uniform(-3, 3),
                               random.uniform(4, 12), time.time() + random.uniform(1.5, 3),
                               random.choice("*+o~^%#@"), random.choice(RAINBOW), 4])

    def toast(self, kicker, name, color, secs):
        self.toasts.append((kicker, name, color, secs))

    def spawn(self, name, row, now):
        pos = self.layout.get(name)
        if pos is None:
            h, w = self.scr.getmaxyx()
            pos = (h // 2, random.uniform(w * .2, w * .8))
        y, x = pos
        color = ROWS[row][2]
        if row == 0:
            for _ in range(10):
                a = random.uniform(0, 6.28)
                self.parts.append([x, y, math.cos(a) * 22, math.sin(a) * 9 - 4, now + random.uniform(.3, .6),
                                   random.choice("*+x"), color, 12])
        elif row == 3:
            for _ in range(4):
                self.parts.append([x, y, random.uniform(-10, 10), random.uniform(-16, -10), now + 1.2,
                                   "▀" if self.utf else "#", color, 30])
        else:
            chars = "♪♫*" if self.fancy else "*+o"
            for _ in range(3 if row == 1 else 2):
                self.parts.append([x, y, random.uniform(-4, 4), random.uniform(-9, -5),
                                   now + random.uniform(1.2, 2.0), random.choice(chars), color, 0])

    # ------------------------------------------------------------ drawing
    def draw(self, now, dt):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        if not self.sleeping and not self.eng.beat_on and now - self.last_input > 20:
            self.sleeping = True
        if self.eng.beat_on and now - self.eng.last_kick < 0.15:
            self.sing[0] = max(self.sing.get(0, 0), now + 0.1)

        big = h >= 34 and w >= 80
        pw, ph = (5, 3) if big else (3, 1)
        step = pw + 1
        strip_h = 2
        board_h = 5 * ph + (4 if not big else 0)
        board_bottom = h - strip_h - 2
        board_top = board_bottom - board_h + 1
        total_w = 9 + int(1.25 * step) + 10 * step
        x0 = max(0, (w - total_w) // 2)

        self.draw_header(now, w)
        scope_top, scope_bottom = 2, board_top - 2
        self.draw_scope(now, scope_top, scope_bottom, w)
        self.draw_board(now, board_top, x0, pw, ph, step, big)
        self.draw_parts(now, dt, h, w)
        self.draw_toast(now, scope_top, scope_bottom, w)
        self.draw_strip(h, w, strip_h)
        scr.refresh()

    def draw_header(self, now, w):
        world = WORLDS[self.world]
        size = ["GIANT", "NORMAL", "MOUSE"][self.size + 1]
        title = " BLEEP BLOOP BAND "
        info = "  %s   voice: %s   bloop wave: %s   beat: %s " % (
            world["name"], size, SHAPES[self.shape][0],
            ("ON" if self.beat == 0 else GROOVES[self.beat - 1]["name"]) if self.eng.beat_on else "off")
        if self.sleeping:
            info += "  zzz "
        put(self.scr, 0, 0, " " * w, self.attr(WORLD_COLORS[self.world]) | curses.A_REVERSE)
        put(self.scr, 0, 0, title, self.attr(WHITE) | curses.A_REVERSE)
        put(self.scr, 0, len(title), info, self.attr(WORLD_COLORS[self.world]) | curses.A_REVERSE)
        if not self.eng.proc:
            put(self.scr, 0, max(0, w - 12), " NO SOUND ", self.attr(RED) | curses.A_REVERSE)

    def draw_scope(self, now, top, bottom, w):
        """The actual sound wave coming out of the speaker, like an oscilloscope."""
        hgt = min(11, bottom - top + 1)
        if hgt < 3:
            return
        mid = top + hgt // 2
        color = WORLD_COLORS[self.world]
        showing_shape = now < self.shape_shown_until
        if showing_shape:
            table = SHAPES[self.shape][1]
            samples = [table[int(i * TABLE_N / 600) % TABLE_N] * 0.9 for i in range(600)] * 2
            start, span = 0, 1200
            label = "NEW WAVE SHAPE: %s" % SHAPES[self.shape][0]
        else:
            samples = self.eng.scope
            start = 0
            for i in range(1, 500):     # start at a rising zero crossing, so the wave holds still
                if samples[i - 1] < 0 <= samples[i]:
                    start = i
                    break
            span = min(len(samples) - start, 520)
            label = "SOUND WAVE"
        cols = max(10, w - 4)
        amp = (hgt - 1) / 2
        prev = None
        dot = "•" if self.fancy else "*"
        for c in range(cols):
            v = samples[start + int(c * span / cols)]
            y = mid - int(round(max(-1, min(1, v)) * amp))
            if prev is not None and abs(y - prev) > 1:
                for yy in range(min(y, prev) + 1, max(y, prev)):
                    put(self.scr, yy, 2 + c, "|", self.attr(color, False))
            put(self.scr, y, 2 + c, dot, self.attr(color))
            prev = y
        put(self.scr, top - 1, 2, label, self.attr(WHITE))
        if now > self.numbers_at:
            self.numbers_at = now + 0.12
            s = self.eng.scope
            self.numbers = ["%+.2f" % s[-1 - i * 37] for i in range(6)]
        nums = "numbers going to the speaker: " + " ".join(self.numbers)
        put(self.scr, top - 1, max(len(label) + 4, w - len(nums) - 2), nums, self.attr(GREEN, False))

    def draw_board(self, now, top, x0, pw, ph, step, big):
        self.layout = {}
        gap = 0 if big else 1
        for r, (rid, keys, color, offset, _) in enumerate(ROWS):
            y = top + r * (ph + gap)
            mood = "sleep" if self.sleeping else ("sing" if now < self.sing.get(r, 0) else "idle")
            face = FACES[mood]
            fy = y + ph // 2 - (1 if mood == "sing" and big else 0)
            put(self.scr, fy, x0 + 1, face, self.attr(color))
            if mood == "sleep":
                put(self.scr, fy - 1, x0 + 6, "z" if int(now * 2 + r) % 2 else "Z", self.attr(WHITE))
            px = x0 + 9 + int(offset * step)
            for i, k in enumerate(keys):
                self.draw_pad(y, px + i * step, pw, ph, k, color, now < self.lit.get(k, 0))
                self.layout[k] = (y, px + i * step + pw // 2)
        y = top + 4 * (ph + gap)
        px = x0 + 9 + int(1.5 * step)
        arrows = ("←", "↓", "↑", "→") if self.fancy else ("<", "v", "^", ">")
        for name, label, wide in (("LEFT", arrows[0], 1), ("DOWN", arrows[1], 1), ("SPACE", "space", 4),
                                  ("UP", arrows[2], 1), ("RIGHT", arrows[3], 1), ("ENTER", "enter", 2)):
            pwide = pw * wide + (wide - 1) * (step - pw)
            self.draw_pad(y, px, pwide, ph, label, WHITE, now < self.lit.get(name, 0))
            self.layout[name] = (y, px + pwide // 2)
            px += pwide + (step - pw)

    def draw_pad(self, y, x, pw, ph, label, color, lit):
        a = self.attr(color)
        if ph == 1:
            s = ("[%s]" % label.center(pw - 2))[:max(pw, len(label) + 2)]
            put(self.scr, y, x, s, a | (curses.A_REVERSE if lit else 0))
            return
        if self.fancy:
            tl, tr, bl, br, hz, vt = "╭", "╮", "╰", "╯", "─", "│"
        elif self.utf:
            tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
        else:
            tl, tr, bl, br, hz, vt = "+", "+", "+", "+", "-", "|"
        put(self.scr, y, x, tl + hz * (pw - 2) + tr, a)
        put(self.scr, y + 1, x, vt, a)
        put(self.scr, y + 1, x + 1, label.center(pw - 2), a | (curses.A_REVERSE if lit else 0))
        put(self.scr, y + 1, x + pw - 1, vt, a)
        put(self.scr, y + 2, x, bl + hz * (pw - 2) + br, a)

    def draw_parts(self, now, dt, h, w):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += p[7] * dt
            put(self.scr, int(p[1]), int(p[0]), p[5], self.attr(p[6]))
        self.parts = [p for p in self.parts if p[4] > now and -8 < p[1] < h][-400:]

    def draw_toast(self, now, top, bottom, w):
        if now > self.toast_until and self.toasts:
            self.current = self.toasts.pop(0)
            self.toast_until = now + self.current[3]
        if now > self.toast_until:
            return
        kicker, name, color, _ = self.current
        big = "  ".join(" ".join(word) for word in name.split())
        bw = max(len(big), len(kicker)) + 8
        bx = (w - bw) // 2
        y = top + max(0, (bottom - top - 5) // 2)
        flash = color if int(now * 6) % 2 else WHITE
        for i in range(5):
            put(self.scr, y + i, bx, " " * bw, self.attr(flash) | curses.A_REVERSE)
        put(self.scr, y + 1, (w - len(kicker)) // 2, kicker, self.attr(flash) | curses.A_REVERSE)
        put(self.scr, y + 3, (w - len(big)) // 2, big, self.attr(flash) | curses.A_REVERSE)

    def draw_strip(self, h, w, n):
        label = " SECRETS %d/%d " % (len(self.found), len(SECRETS))
        put(self.scr, h - n - 1, 0, ("─" if self.utf else "-") * w, self.attr(BLUE, False))
        y, x = h - n, 1
        put(self.scr, y, x, label, self.attr(YELLOW) | curses.A_REVERSE)
        x += len(label) + 1
        for sid, name, _ in SECRETS:
            got = sid in self.found
            tag = "[%s]" % (name if got else "?" * min(4, len(name)))
            if x + len(tag) >= w - 1:
                y, x = y + 1, 1 + len(label) + 1
            put(self.scr, y, x, tag, self.attr(GREEN) if got else self.attr(WHITE, False) | curses.A_DIM)
            x += len(tag) + 1


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
    for pid, fg in {RED: curses.COLOR_RED, YELLOW: curses.COLOR_YELLOW, GREEN: curses.COLOR_GREEN,
                    CYAN: curses.COLOR_CYAN, BLUE: curses.COLOR_BLUE, MAGENTA: curses.COLOR_MAGENTA,
                    WHITE: curses.COLOR_WHITE, ORANGE: orange}.items():
        curses.init_pair(pid, fg, curses.COLOR_BLACK)
    scr.bkgd(" ", curses.color_pair(WHITE))

    engine = Engine(sound=not args.mute)
    engine.start()
    app = App(scr, engine)
    last = time.time()
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
                if not app.handle_key(key, time.time()):
                    return
            now = time.time()
            app.draw(now, min(0.1, now - last))
            last = now
            time.sleep(max(0, 1 / 30 - (time.time() - t0)))
    finally:
        engine.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="A button-mashing synthesizer for kids. Esc quits.")
    p.add_argument("--hints", action="store_true", help="list the secrets and how to find them")
    p.add_argument("--reset", action="store_true", help="hide all found secrets again")
    p.add_argument("--mute", action="store_true", help="run without sound")
    args = p.parse_args()
    if args.hints:
        found = load_found()
        for sid, name, hint in SECRETS:
            print("%s %-14s %s" % ("*" if sid in found else " ", name, hint))
        raise SystemExit
    if args.reset:
        save_found(set())
        print("All secrets hidden again.")
        raise SystemExit
    locale.setlocale(locale.LC_ALL, "")
    while True:
        try:
            os.environ.setdefault("ESCDELAY", "25")   # Python 3.8 has no curses.set_escdelay
            curses.wrapper(main, args)
            break
        except KeyboardInterrupt:
            continue
    print("Thanks for playing in the Bleep Bloop Band!")
