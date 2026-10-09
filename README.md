# Kids Terminal Games

Thirteen keyboard games for kids, made to turn an old laptop into a **kids' computer** that boots straight into a text console. The kids log in to a friendly menu, type a game's name and press Enter. Esc always brings them back.

Everything is plain Python 3, with nothing to install. Sound is optional.

```
   █   █  █████    █
   █   █    █      █          _|_
   █████    █      █         [o_o]     Good morning!
   █   █    █                /|_|\     It's Saturday, 9:30 AM
   █   █  █████    █          / \

   Type a word, then press ENTER:

      keys     Hacker Keys        letters, words, points and robots
      band     Bleep Bloop Band   make music with the keyboard
      robot    Robot Commander    tell the robot where to go
      ...
type here > _
```

## The games

| Type | Game | What it is |
|---|---|---|
| `keys` | Hacker Keys | Mash the keyboard: every letter "decrypts" a short-vowel phonics word with ASCII art, numbers add points, robots cheer |
| `band` | Bleep Bloop Band | A wavetable synthesizer where no note sounds wrong; each keyboard row is an instrument, with beats and 13 secrets to discover |
| `robot` | Robot Commander | Program a robot with arrow keys; numbers make repeats (a first taste of loops) |
| `rain` | Alphabet Rain | Type the falling letters to pop them; nobody loses |
| `quest` | The Quest for the Golden Crown | A [ZZT](https://en.wikipedia.org/wiki/ZZT)-style adventure in five levels (Robot Town, Spooky Islands, Rainbow Kingdom, the Witches' Crown, the Whispering Forest) with ASCII movies between them: keys, doors, boulders, bridges, ghosts, leprechauns, witches, rats, crows, a hedge maze and surprise boxes. Every board is a text file, and `quest edit` opens a ZZT-style editor for them |
| `times` | Times Tables | Big flash cards for 1–20, a lightning round, hints that break hard facts apart, and a chart that fills in as they learn |
| `calc` | Big Calculator | Giant numbers and a fun fact about every answer |
| `lights` | Binary Lights | Eight light bulbs that count in binary |
| `secret` | Secret Codes | Messages as numbers, binary and Morse beeps, plus a code wheel to crack |
| `paint` | Pixel Painter | Paint square by square; pictures save as text files |
| `pet` | Robot Pet | A robot that remembers its name, gets hungry between visits and sleeps at night |
| `castle` | Castle Cannons | Aim the cannon, knock down the castle |
| `ski` | Ski Hill | Ski down the mountain, away from the snow monster |

Every game also understands `help` and `reset` after its name (`band help`, `quest reset`), and typing `help` shows the master help file.

## Try it

Any game runs on its own in a terminal (80 × 24 or bigger):

```bash
python3 quest.py
```

## Set up a kids' computer

1. Copy this folder to the kids' account as `~/kids-computer`.
2. As the kids' user, run `sh ~/kids-computer/install.sh`. The menu now shows at login.
3. Optionally boot to the text console with automatic login, and stop Ctrl+Alt+Delete from rebooting. [`README.txt`](README.txt) has the exact steps.

## For grown-ups

- Type the hidden word `adult` at the menu to turn games on and off and set the volume from 0 to 11.
- `band hints` lists the synthesizer's secrets. `quest edit` opens the Quest Editor to change the boards or make new ones, and `quest check` finds mistakes ([how boards work](quest_boards/README.txt)).
- Ctrl+C and Ctrl+Z are ignored inside the games, so little hands can't quit by accident.
- On the Linux console, the login loads a console font with the old PC symbols (♣ ♥ ☺ Ω), so Quest looks like ZZT. Elsewhere the games pick characters the font can draw.
- Saved progress lives in hidden files in the home folder. [`README.txt`](README.txt) lists them.

## Requirements

- Linux with Python 3.8 or newer (only the standard library).
- For sound: `pacat` (PulseAudio/PipeWire) or `aplay` (`sudo apt install alsa-utils`).

## Credits

- Band's sound engine uses wavetable synthesis, after Jan Wilczek's [wavetable synthesis article](https://thewolfsound.com/sound-synthesis/wavetable-synthesis-algorithm/).
- The phonics words in Hacker Keys start from the [Keep Kids Reading CVC word lists](https://www.keepkidsreading.net/docs/cvcwordlist.pdf).
- Quest is inspired by ZZT (Tim Sweeney, Epic MegaGames, 1991).
- Made with [Claude Code](https://claude.com/claude-code).

## License

[MIT](LICENSE): use it, change it, share it, just keep the credit.
