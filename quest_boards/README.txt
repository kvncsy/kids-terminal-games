MAKING QUEST BOARDS
===================

Every place in the Quest is one text file in this folder. Boards are grouped
into levels (level 1 is Robot Town, 2 is Spooky Islands, 3 is Rainbow
Kingdom). Each level starts on the board with the @ in it. Change a board,
or copy one to make a new place, then run "quest check" to look for
mistakes.

A board file looks like this:

    title: Robot Town
    north: forest
    east: lake
    1: Bolt: Welcome to Robot Town!
    map:
    ####################  ...
    #        1         #  ...

  title:              the name shown in the sidebar
  level: 2            which level the board belongs to (leave it out for
                      level 1). Exits only lead to boards of the same level.
  north: / south: / east: / west:
                      which board you reach by walking off that edge
                      (leave a gap in the wall there, and a matching gap
                      on the other board)
  dark: yes           (optional) the board is dark: you only see near you
                      (more with the lamp), but ghosts can always be seen
  These go on a level's start board (the one with the @):
  adventure:          the level's name ("Spooky Islands")
  goal:               what the ! is ("the Ghost's Treasure")
  intro:              the words in the box when the level starts
  opening: / ending:  the movie played at the start and at the end
                      (town, crown, ship, ghosts, rainbow, rainbow_end;
                      they live in quest_scenes.py)

  1: to 9:            what robot 1 to 9 on the map says ("Name: words")
  map:                everything after this line is the map:
                      60 columns wide and 21 rows tall

MAP SYMBOLS
  @        where the player starts (one per level, on its start board)
  (space)  empty ground
  #        wall
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
  1 to 9   a robot who talks
  !        the level's goal (walk onto it to win the level)

A level you are in the middle of remembers its walls and doors. After you
change its boards, finish it or run "quest reset" to see your changes. Boulders go back home each time you enter a board,
so nobody gets stuck.
