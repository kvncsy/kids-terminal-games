# Kids Computer: a typed-command menu for a laptop that boots to a text console.
# Loaded from ~/.bashrc (install.sh adds that line). To add a program, add a
# function to kids_commands.sh, a line to PROGRAMS in kids_menu.py, and a
# help file in help/.

. "$(dirname "${BASH_SOURCE[0]}")/kids_commands.sh"

menu() { clear; python3 "$KIDS_DIR/kids_menu.py"; }
adult() { python3 "$KIDS_DIR/kids_menu.py" --adult; menu; }

# "help" shows the big help file; "help band" shows the help for one game
help() { python3 "$KIDS_DIR/kids_menu.py" --help-topic "${1:-help}"; }

# CAPS LOCK still works (KEYS, Band Help, ...) and typos get a friendly answer
command_not_found_handle() {
    if [[ " $KIDS_COMMANDS menu help adult " == *" ${1,,} "* ]]; then
        "${1,,}" "${@:2}"
    else
        python3 "$KIDS_DIR/kids_menu.py" --unknown "$1"
        return 127
    fi
}

PS1='\[\e[1;33m\]type here >\[\e[0m\] '

# show the menu when the kids log in
case $- in
    *i*) kids_repeat off; menu ;;
esac
