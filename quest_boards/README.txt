MAKING QUEST BOARDS
===================

The easy way: type  quest edit  (or run python3 quest_edit.py). Move the
cursor with the arrows and type a symbol to put it on the map; Ctrl+E has a
board's settings and Ctrl+T tries it out. The editor names the files and
keeps a copy of every board it changes in the old/ folder.

Every place in the Quest is one text file in this folder. Boards are grouped
into levels (1 is Robot Town, 2 is Spooky Islands, 3 is Rainbow Kingdom,
4 is the Witches' Crown, 5 is the Whispering Forest). Each level starts on the board with the @ in it.
Change a board, or copy one to make a new place, then run "quest check" to
look for mistakes.

FILE NAMES
  1-town-start.txt   level - name - where
  1-forest-n.txt     the forest in level 1, one board north of the start
  2-house-nee.txt    the house in level 2: north, then two east
  4-well-ddd.txt     the well in level 4: down, down, down from the start
  The name is what exits use ("north: forest"). Two levels can both have a
  "forest". The "where" is just a reminder for you; "quest check" tells you
  if it doesn't match the exits.

A board file looks like this:

    title: Robot Town
    north: forest
    east: lake
    1: Bolt: Welcome to Robot Town!
    map:
    ####################  ...
    #        1         #  ...

  title:              the name shown in the sidebar
  down: / up:         which board the > (or <) on this board leads to
  box: y              (optional) the ? box on this board hides this key
  north: / south: / east: / west:
                      which board you reach by walking off that edge
                      (leave a gap in the wall there, and a matching gap
                      on the other board; only boards in the same level)
  dark: yes           (optional) the board is dark: you only see near you
                      (more with the lamp), but ghosts can always be seen
  These go on a level's start board (the one with the @):
  adventure:          the level's name ("Spooky Islands")
  goal:               what the ! is ("the Ghost's Treasure")
  intro:              the words in the box when the level starts
  opening: / ending:  the movie played at the start and at the end
                      (town, crown, ship, ghosts, rainbow, rainbow_end,
                      thief, home, witches, moon;
                      they live in quest_scenes.py)

  1: to 9:            what robot 1 to 9 on the map says ("Name: words")
  map:                everything after this line is the map:
                      60 columns wide and 21 rows tall

MAP SYMBOLS
  @        where the player starts (one per level, on its start board)
  (space)  empty ground
  #        wall
  &        hedge (a green wall)
  %        weak wall (zap it to break it)
  ~        water (zaps fly over it; push a boulder in to make a bridge)
  =        bridge (walk on it over water)
  :        rainbow road (walk on it)
  T        tree
  O        boulder (push it)
  *        gem
  $        gold
  ?        a surprise box (gold, hearts, zaps, rainbow shoes or a party)
  a        ammo
  +        heart
  l        the lamp (see more on dark boards)
  r b y g p c   red, blue, yellow, green, purple and light blue keys
  R B Y G P C   doors of the same colors (a key opens its own color;
                each key is used up, so use each color for one door only)
  L        lion
  H        ghost (says BOO and sends you back to where you came in)
  E        leprechaun (runs away; catch or zap it for gold)
  F        fairy (bump it to fill your hearts)
  V        crow (the flock flies away when you come close)
  K        the Leprechaun King (trades the Golden Crown for 15 gold)
  Q        Queen Maeve (bring her the crown to win the level)
  A        a witch (vanishes when you come close, and leaves ammo)
  ,        a rat (fast! nibbles your gold or gems; step on it)
  >        a way down (stairs, a hole, a well)
  <        the way back up
  1 to 9   a robot who talks
  !        the level's goal (walk onto it to win the level)

A level you are in the middle of remembers its walls and doors. After you
change its boards, finish it or run "quest reset" to see your changes. Boulders go back home each time you enter a board,
so nobody gets stuck.
