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

# On the laptop's own screen, load a console font that has the old PC symbols
# (♣ ♥ ☺ Ω, like ZZT), in the size console-setup uses, so the games can use
# them. Your own console's font needs no sudo. Elsewhere nothing changes.
kids_font() {
    [ "$TERM" = linux ] && [[ "$(tty)" == /dev/tty[0-9]* ]] || return
    setfont "$(kids_font_file)" 2>/dev/null && export KIDS_FANCY=1
}
kids_font_file() {
    local size w h f dir=/usr/share/consolefonts
    size=$(sed -n 's/^FONTSIZE="\{0,1\}\([0-9]*x[0-9]*\).*/\1/p' "${1:-/etc/default/console-setup}" 2>/dev/null)
    w=${size%x*} h=${size#*x}
    f=$dir/FullGreek-TerminusBold${h}x${w}.psf.gz              # like 24x12
    [ -f "$f" ] || f=$dir/FullGreek-TerminusBold${h}.psf.gz   # like 16
    [ -f "$f" ] || f=$dir/FullGreek-TerminusBold16.psf.gz
    echo "$f"
}

# show the menu when the kids log in
case $- in
    *i*) kids_font; kids_repeat off; menu ;;
esac
