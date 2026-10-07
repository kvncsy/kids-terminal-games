KIDS COMPUTER
=============

Programs (plain Python 3, nothing to install):
  keys    hacker_keys.py       Hacker Keys: letters, words, points and robots
  band    bleep_bloop.py       Bleep Bloop Band: a button-mashing synthesizer
  robot   robot_commander.py   Robot Commander: program a robot with arrow keys
  rain    letter_rain.py       Alphabet Rain: type the falling letters to pop them
  quest   quest.py             The Quest for the Golden Crown: a ZZT-style adventure
                               (its world is the text files in quest_boards/)
  times   times_tables.py      Times Tables: flash cards for 1-20, a lightning round
                               and a chart of every fact they know
  calc    big_calc.py          Big Calculator: giant numbers and fun facts
  lights  binary_lights.py     Binary Lights: eight bulbs that count in binary
  secret  secret_code.py       Secret Codes: Morse code, a code wheel, code cracking
  paint   pixel_paint.py       Pixel Painter: saves pictures in ~/My Pictures
  pet     robot_pet.py         Robot Pet: a robot that remembers them between visits
  castle  castle.py            Castle Cannons: artillery vs. the computer or a friend
  ski     ski.py               Ski Hill: SkiFree-style downhill, with a snow monster
  menu    kids_menu.py         the menu shown at login (edit it to add programs)

Esc quits every program back to the menu. Ctrl+C and Ctrl+Z are ignored inside them.

Every game also understands:
  band help      that game's help (the files in help/)
  band reset     start that game over (band: hide the stickers; robot: level 1;
                 keys: points to zero; quest: a brand new quest; times: a fresh
                 chart; paint: hide the secret tools; pet: a new robot;
                 castle: level 1; ski: forget the best run)
  help           the big help file
Grown-up extras:  adult       (hidden) turn games on and off, volume 0-11
                  band hints  (how to find the synth secrets)
                  quest check (look for mistakes after editing quest boards)

Other files: kids_commands.sh (the game commands), kids.bashrc (the login
menu), kidslib.py (screen, sound and big-number code shared by the newer
games), install.sh (setup), help/ (help files), quest_boards/ (quest world).


SETTING UP THE KIDS' LAPTOP
---------------------------
1. Copy this folder to the kids' user's home folder:  ~/kids-computer

2. Log in as the kids' user and run:
       sh ~/kids-computer/install.sh

3. Boot to the text console instead of the desktop (run as an admin user):
       sudo systemctl set-default multi-user.target
   To get the desktop back later:
       sudo systemctl set-default graphical.target

4. Log the kids' user in automatically on the first console:
       sudo systemctl edit getty@tty1
   and paste these three lines into the editor (use the kids' user name):
       [Service]
       ExecStart=
       ExecStart=-/sbin/agetty --autologin KIDS_USER_NAME --noclear %I $TERM

5. Stop Ctrl+Alt+Delete from rebooting the laptop:
       sudo systemctl mask ctrl-alt-del.target

6. Optional: bigger letters on the console:
       sudo dpkg-reconfigure console-setup
   (pick "Terminus" and a size like 12x24; 16x32 is very big and the
   programs switch to their smaller layouts)


GOOD TO KNOW
------------
- No sound on the console? Install aplay:  sudo apt install alsa-utils
- Alt+F1 ... Alt+F6 switch between consoles. If the kids end up at a login
  prompt, Alt+F1 brings them back.
- Saved progress lives in hidden files in the home folder:
    ~/.hacker_keys_points     points in Hacker Keys ("000" or "keys reset")
    ~/.bleep_bloop_secrets    secrets found  ("band reset")
    ~/.robot_commander        level reached  ("robot reset")
    ~/.quest_save             the quest, saved when they press Esc ("quest reset")
    ~/.kids_computer.json     which games are turned off ("adult")
    ~/.times_tables           the times tables chart and lightning record
    ~/.pixel_paint            secret paint tools found; pictures are in ~/My Pictures
    ~/.robot_pet              the robot pet (its name, age, battery and words)
    ~/.castle_cannons         level reached in Castle Cannons ("castle reset")
    ~/.ski_hill               best ski run ("ski reset")
- On a console font that has the classic symbols (a smiley, hearts,
  diamonds), add  export KIDS_FANCY=1  to ~/.bashrc for the full ZZT look in Quest.
