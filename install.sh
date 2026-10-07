#!/bin/sh
# Sets up the Kids Computer menu for the user who runs it.
#   1. Copy this whole folder to the kids' laptop, e.g. to ~/kids-computer
#   2. Log in as the kids' user and run:  sh ~/kids-computer/install.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if grep -qF "$DIR/kids.bashrc" "$HOME/.bashrc" 2>/dev/null; then
    echo "The Kids Computer menu is already in ~/.bashrc"
else
    printf '\n# Kids Computer menu\n. "%s/kids.bashrc"\n' "$DIR" >> "$HOME/.bashrc"
    echo "Added the Kids Computer menu to ~/.bashrc"
fi

command -v python3 >/dev/null || echo "Missing python3. Install it with:  sudo apt install python3"
command -v pacat >/dev/null || command -v aplay >/dev/null || \
    echo "No sound player found. For sound:  sudo apt install alsa-utils"
echo "Log out and back in (or run:  . ~/.bashrc) to see the menu."
