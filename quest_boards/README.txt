MAKING QUEST BOARDS
===================

Every place in the Quest is one text file in this folder. The game starts on
town.txt. Change a board, or copy one to make a new place, then run
"quest check" to look for mistakes.

A board file looks like this:

    title: Robot Town
    north: forest
    east: lake
    1: Bolt: Welcome to Robot Town!
    map:
    ####################  ...
    #        1         #  ...

  title:              the name shown in the sidebar
  north: / south: / east: / west:
                      which board you reach by walking off that edge
                      (leave a gap in the wall there, and a matching gap
                      on the other board)
  dark: yes           (optional) the board is dark: you only see near you
                      (more with the lamp), but ghosts can always be seen
  1: to 9:            what robot 1 to 9 on the map says ("Name: words")
  map:                everything after this line is the map:
                      60 columns wide and 21 rows tall

MAP SYMBOLS
  @        where the player starts (only needed in town.txt)
  (space)  empty ground
  #        wall
  %        weak wall (zap it to break it)
  ~        water (zaps fly over it; push a boulder in to make a bridge)
  =        bridge (walk on it over water)
  T        tree
  O        boulder (push it)
  *        gem
  a        ammo
  +        heart
  l        the lamp (see more on dark boards)
  r b y g p c   red, blue, yellow, green, purple and light blue keys
  R B Y G P C   doors of the same colors (a key opens its own color;
                each key is used up, so use each color for one door only)
  L        lion
  H        ghost (says BOO and sends you back to where you came in)
  1 to 9   a robot who talks
  !        the Golden Crown (walk onto it to win)

When you change the boards, run "quest reset" so the quest starts fresh
with your new world. Boulders go back home each time you enter a board,
so nobody gets stuck.
