# Kids Computer game commands: "band" starts a game, "band help" shows its help,
# "band reset" starts it over. Loaded by kids.bashrc on the kids' laptop.
#
# To open games in their own full-screen window on a desktop instead, load it
# like this in ~/.bashrc:
#     KIDS_LAUNCH="gnome-terminal --full-screen --"
#     . ~/kids-computer/kids_commands.sh

KIDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Held keys don't repeat on the text console (no "mmmmmmmm"), except in Band,
# whose drum rolls and long notes need them. \e[?8l / \e[?8h is the console's own switch.
kids_repeat() {
    if [ "$TERM" = linux ] && [ -t 1 ]; then
        if [ "$1" = on ]; then printf '\033[?8h'; else printf '\033[?8l'; fi
    fi
}

# start a game; on the console, come back to the menu afterwards
kids_start() {
    if [ -n "$KIDS_LAUNCH" ]; then
        $KIDS_LAUNCH python3 "$KIDS_DIR/$1"
    else
        clear
        [ "$1" = bleep_bloop.py ] && kids_repeat on
        python3 "$KIDS_DIR/$1"
        kids_repeat off
        clear
        python3 "$KIDS_DIR/kids_menu.py"
    fi
}

# kids_program FILE NAME "EXTRA WORDS" [word]
kids_program() {
    local file=$1 name=$2 extra=$3
    shift 3
    local word="${1,,}"
    python3 "$KIDS_DIR/kids_menu.py" --check-on "$name" || return 0   # a grown-up turned it off
    case "$word" in
        "")    kids_start "$file" ;;
        help)  python3 "$KIDS_DIR/kids_menu.py" --help-topic "$name" ;;
        reset) python3 "$KIDS_DIR/$file" --reset ;;
        *)
            if [[ " $extra " == *" $word "* ]]; then
                python3 "$KIDS_DIR/$file" "--$word"
            else
                python3 "$KIDS_DIR/kids_menu.py" --bad-word "$name" "$1"
            fi ;;
    esac
}

keys()   { kids_program hacker_keys.py     keys   ""      "$@"; }
band()   { kids_program bleep_bloop.py     band   "hints" "$@"; }
robot()  { kids_program robot_commander.py robot  ""      "$@"; }
rain()   { kids_program letter_rain.py     rain   ""      "$@"; }
quest()  { kids_program quest.py           quest  "check edit" "$@"; }
times()  { kids_program times_tables.py    times  ""      "$@"; }
calc()   { kids_program big_calc.py        calc   ""      "$@"; }
lights() { kids_program binary_lights.py   lights ""      "$@"; }
secret() { kids_program secret_code.py     secret ""      "$@"; }
paint()  { kids_program pixel_paint.py     paint  ""      "$@"; }
pet()    { kids_program robot_pet.py       pet    ""      "$@"; }
castle() { kids_program castle.py          castle ""      "$@"; }
ski()    { kids_program ski.py             ski    ""      "$@"; }

# every command above, for the Caps Lock and typo helper in kids.bashrc
KIDS_COMMANDS="keys band robot rain quest times calc lights secret paint pet castle ski"

# grown-up settings (not shown anywhere): turn games on and off
adult() { python3 "$KIDS_DIR/kids_menu.py" --adult; }
