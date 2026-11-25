#!/usr/bin/env python3
"""
App Installer - a terminal UI for installing popular Linux programs.

Pick programs from a list (native packages + Flatpak); the script detects
your package manager (pacman/AUR, apt, dnf, zypper) and installs them.

Usage:
    python3 installer.py                 # normal run
    python3 installer.py --dry-run       # only print the commands, install nothing
    python3 installer.py --flatpak-user  # install Flatpaks per-user (no sudo)
    python3 installer.py --list          # print the program list and exit
"""

import argparse
import curses
import locale
import os
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
#  PROGRAM DATABASE
#
#  Line format:  Name|Description|default_package|overrides
#  - default_package: package name shared by most distros ("-" = not available)
#  - overrides: key=value pairs separated by ";"   keys: arch, aur, apt, dnf, zypper
#      * a value may hold several packages separated by spaces
#      * "a/b" means "use a, or b if a does not exist" (e.g. Debian vs Ubuntu)
#      * "-" means not available for that package manager
#  - "aur=" is used on Arch when there is no "arch=" (needs paru/yay)
#  A line starting with "#" starts a new category.
#
#  apt names were checked against Debian 13 and Ubuntu 24.04, dnf names
#  against Fedora 43 (+ RPM Fusion), zypper names against openSUSE Tumbleweed.
# ---------------------------------------------------------------------------

NATIVE = r"""
# Web browsers
Firefox|Mozilla's web browser|firefox|apt=firefox/firefox-esr
Chromium|Open-source base of Chrome|chromium|apt=chromium/chromium-browser
Google Chrome|Google's web browser|-|aur=google-chrome
Brave|Browser with built-in ad blocking|-|aur=brave-bin
Vivaldi|Feature-rich browser|vivaldi|apt=-;dnf=-;zypper=-
LibreWolf|Privacy-focused Firefox fork|-|arch=librewolf
Zen Browser|Modern Firefox fork|-|aur=zen-browser-bin
Microsoft Edge|Microsoft's web browser|-|aur=microsoft-edge-stable-bin
Tor Browser|Anonymous browsing (launcher)|torbrowser-launcher
Falkon|Lightweight KDE browser|falkon
GNOME Web|Epiphany browser|epiphany|apt=epiphany-browser
qutebrowser|Keyboard-driven browser|qutebrowser
Lynx|Text-mode browser|lynx
w3m|Text-mode browser with images|w3m
# Chat and e-mail
Discord|Voice and text chat|discord|apt=-;dnf=-;zypper=-
Vesktop|Discord with Vencord|-|aur=vesktop-bin
Telegram|Telegram messenger|telegram-desktop|apt=-;zypper=telegram-desktop
Signal|Encrypted messenger|signal-desktop|apt=-;dnf=-;zypper=-
Element|Matrix client|element-desktop|apt=-;dnf=-;zypper=-
Slack|Team chat|-|aur=slack-desktop
Zoom|Video meetings|-|aur=zoom
Teams for Linux|Unofficial MS Teams client|-|aur=teams-for-linux-bin
Thunderbird|Mozilla's e-mail client|thunderbird
Evolution|GNOME mail and calendar|evolution
Geary|Simple e-mail client|geary
HexChat|IRC client|hexchat|aur=hexchat
Pidgin|Multi-protocol messenger|pidgin|aur=pidgin
WeeChat|Terminal IRC client|weechat
Irssi|Terminal IRC client|irssi
Mumble|Voice chat for gamers|mumble
Dino|XMPP client|dino|apt=dino-im
# Audio and video
VLC|Media player|vlc
mpv|Minimalist media player|mpv
Celluloid|GTK front-end for mpv|celluloid
Kodi|Media center|kodi|zypper=-
Spotify|Music streaming|-|aur=spotify
OBS Studio|Recording and streaming|obs-studio
Audacity|Audio editor|audacity
Kdenlive|KDE video editor|kdenlive
Shotcut|Video editor|shotcut
OpenShot|Simple video editor|openshot|aur=openshot;apt=openshot-qt;dnf=-;zypper=openshot-qt
HandBrake|Video converter|handbrake|dnf=HandBrake-gui;zypper=-
FFmpeg|Audio/video toolkit|ffmpeg|dnf=ffmpeg-free
yt-dlp|Download videos from YouTube etc.|yt-dlp
Rhythmbox|GNOME music player|rhythmbox
Strawberry|Music player|strawberry
Elisa|KDE music player|elisa|dnf=elisa-player
Lollypop|Modern music player|lollypop
Audacious|Lightweight music player|audacious
cmus|Terminal music player|cmus
MPD|Music Player Daemon|mpd
ncmpcpp|Terminal MPD client|ncmpcpp
EasyEffects|PipeWire audio effects|easyeffects
PulseAudio Volume Control|Audio mixer|pavucontrol
qpwgraph|PipeWire patchbay|qpwgraph
Ardour|Digital audio workstation|ardour|dnf=ardour8
LMMS|Music production|lmms
MuseScore|Music notation|musescore
Hydrogen|Drum machine|hydrogen
SimpleScreenRecorder|Screen recorder|simplescreenrecorder|aur=simplescreenrecorder
Kooha|Simple screen recorder|kooha|apt=-;dnf=-;zypper=-
Cheese|Webcam app|cheese|aur=cheese
MKVToolNix|MKV file tools|mkvtoolnix-gui|dnf=mkvtoolnix
MusicBrainz Picard|Music tagger|picard
# Graphics and design
GIMP|Raster image editor|gimp
Krita|Digital painting|krita
Inkscape|Vector graphics|inkscape
Blender|3D graphics and animation|blender
Darktable|RAW photo developer|darktable
RawTherapee|RAW photo processing|rawtherapee
digiKam|Photo management|digikam
Shotwell|Photo manager|shotwell
Gwenview|KDE image viewer|gwenview
Eye of GNOME|Image viewer|eog
Loupe|GNOME image viewer|loupe
feh|Lightweight image viewer|feh
ImageMagick|Command-line image processing|imagemagick|dnf=ImageMagick;zypper=ImageMagick
Flameshot|Screenshots with annotations|flameshot
Spectacle|KDE screenshot tool|spectacle|apt=kde-spectacle
Ksnip|Screenshot tool|ksnip
Pinta|Simple image editor|pinta|apt=-
KolourPaint|Paint for KDE|kolourpaint
MyPaint|Painting app|mypaint
FreeCAD|3D CAD modeler|freecad|dnf=-;zypper=FreeCAD
LibreCAD|2D CAD|librecad
OpenSCAD|Programmable CAD|openscad
Scribus|Desktop publishing|scribus
# Office and education
LibreOffice|Office suite|libreoffice|arch=libreoffice-fresh
OnlyOffice|MS Office-compatible suite|-|aur=onlyoffice-bin
Okular|KDE PDF viewer|okular
Evince|GNOME PDF viewer|evince
Zathura|Minimalist PDF viewer|zathura zathura-pdf-mupdf|apt=zathura zathura-pdf-poppler;zypper=zathura zathura-plugin-pdf-mupdf
Xournal++|Handwritten notes and PDF annotation|xournalpp
PDF Arranger|Merge and split PDFs|pdfarranger
Calibre|E-book library|calibre
Foliate|E-book reader|foliate
Obsidian|Markdown notes|obsidian|apt=-;dnf=-;zypper=-
Joplin|Notes with sync|-|aur=joplin-appimage
Logseq|Graph-based notes|-|aur=logseq-desktop-bin
Zotero|Reference manager|-|arch=zotero
Anki|Flashcards|-|arch=anki
CherryTree|Hierarchical notes|cherrytree|dnf=-
Ghostwriter|Markdown editor|ghostwriter
GnuCash|Personal finance|gnucash
Simple Scan|Document scanner|simple-scan
Pandoc|Document converter|pandoc|arch=pandoc-cli
TeX Live|LaTeX typesetting|texlive|dnf=texlive-scheme-medium;zypper=texlive-scheme-medium
GeoGebra|Interactive math|-|arch=geogebra
Stellarium|Planetarium|stellarium
# Development
Visual Studio Code|Microsoft's code editor|-|aur=visual-studio-code-bin
Code - OSS|Open-source build of VS Code|code|apt=-;dnf=-;zypper=-
VSCodium|VS Code without telemetry|-|aur=vscodium-bin
Zed|Fast code editor|zed|apt=-;dnf=-;zypper=-
Sublime Text|Text editor|-|aur=sublime-text-4
Neovim|Modern Vim|neovim
Vim|Classic editor|vim|dnf=vim-enhanced
Emacs|Extensible editor|emacs
Helix|Modal editor written in Rust|helix|apt=-
Micro|Simple terminal editor|micro|zypper=micro-editor
Nano|Simple terminal editor|nano
Kate|Advanced KDE editor|kate
Geany|Lightweight IDE|geany
GNOME Text Editor|GNOME text editor|gnome-text-editor
IntelliJ IDEA (OSS)|IDE for Java/Kotlin|-|arch=intellij-idea-oss
PyCharm CE|Python IDE|pycharm-community-edition|apt=-;dnf=-;zypper=-
JetBrains Toolbox|JetBrains IDE manager|-|aur=jetbrains-toolbox
Android Studio|Android IDE|-|aur=android-studio
Qt Creator|Qt/C++ IDE|qtcreator|dnf=qt-creator;zypper=qt6-creator
GNOME Builder|GNOME IDE|gnome-builder
Arduino IDE|Arduino programming|-|aur=arduino-ide-bin
Godot|Game engine|godot|apt=godot3;dnf=godot
Git|Version control|git
Git LFS|Large files in Git|git-lfs
GitHub CLI|The gh tool|github-cli|apt=gh;dnf=gh;zypper=gh
lazygit|Git TUI|lazygit|apt=-;dnf=-
Meld|Diff and merge tool|meld
gitg|Graphical Git client|gitg
Build tools|GCC, make, etc.|base-devel|apt=build-essential;dnf=gcc gcc-c++ make;zypper=gcc gcc-c++ make
Clang|LLVM C/C++ compiler|clang
CMake|Build system|cmake
Meson|Build system|meson
Ninja|Fast build system|ninja|apt=ninja-build;dnf=ninja-build
GDB|Debugger|gdb
Valgrind|Memory analysis|valgrind
strace|System call tracer|strace
Python|Python language|python|apt=python3;dnf=python3;zypper=python3
pip|Python package manager|python-pip|apt=python3-pip;dnf=python3-pip;zypper=python3-pip
pipx|Isolated Python apps|python-pipx|apt=pipx;dnf=pipx;zypper=python3-pipx/python313-pipx
uv|Fast Python package manager|uv|apt=-;zypper=-
Node.js + npm|JavaScript runtime|nodejs npm
Rustup|Rust toolchain installer|rustup
Go|Go language|go|apt=golang;dnf=golang
Java (OpenJDK)|Java runtime and compiler|jdk-openjdk|apt=default-jdk;dnf=java-latest-openjdk-devel;zypper=java-21-openjdk-devel
.NET SDK|.NET platform|dotnet-sdk|apt=dotnet-sdk-8.0;dnf=dotnet-sdk-8.0;zypper=-
Lua|Lua language|lua|apt=lua5.4
Ruby|Ruby language|ruby
PHP|PHP language|php
Zig|Zig language|zig|apt=-
Kotlin|Kotlin language|kotlin|apt=-;dnf=-;zypper=-
Docker|Containers|docker docker-compose|apt=docker.io docker-compose;dnf=moby-engine docker-compose;zypper=docker docker-compose
Podman|Daemonless containers|podman
Distrobox|Other distros in a container|distrobox
Ansible|Configuration automation|ansible
kubectl|Kubernetes client|kubectl|apt=-;dnf=kubernetes-client;zypper=kubernetes-client
SQLite|Lightweight database|sqlite|apt=sqlite3;dnf=sqlite;zypper=sqlite3
PostgreSQL|Database server|postgresql|dnf=postgresql-server
MariaDB|Database server (MySQL)|mariadb|apt=mariadb-server;dnf=mariadb-server
Redis / Valkey|Key-value store|valkey|apt=redis-server;dnf=valkey;zypper=redis
DBeaver|Database client|dbeaver|apt=-;dnf=-;zypper=-
Postman|API testing|-|aur=postman-bin
ShellCheck|Shell script linter|shellcheck|dnf=ShellCheck;zypper=ShellCheck
jq|JSON processor|jq
Hugo|Static site generator|hugo
# Terminal and CLI tools
Alacritty|GPU-accelerated terminal|alacritty
Kitty|GPU-accelerated terminal|kitty
WezTerm|Terminal written in Rust|wezterm|apt=-;dnf=-;zypper=-
Ghostty|Fast terminal|ghostty|apt=-;dnf=-;zypper=-
Foot|Lightweight Wayland terminal|foot
Konsole|KDE terminal|konsole
GNOME Terminal|GNOME terminal|gnome-terminal
Tilix|Tiling terminal|tilix|aur=tilix
Terminator|Terminal with split panes|terminator
tmux|Terminal multiplexer|tmux
Zellij|Modern multiplexer|zellij|apt=-;dnf=-
Screen|Terminal multiplexer|screen
Zsh|Z shell|zsh
Fish|Friendly interactive shell|fish
Starship|Pretty shell prompt|starship|apt=-;dnf=-
htop|Process viewer|htop
btop|Pretty resource monitor|btop
Bottom|Resource monitor in Rust|bottom|apt=-;dnf=-
Glances|System monitor|glances|zypper=python3-Glances/python313-Glances
nvtop|GPU monitor|nvtop
Fastfetch|System info|fastfetch
inxi|Detailed hardware info|inxi
ncdu|Disk usage analyzer|ncdu
duf|Better df|duf
Ranger|Terminal file manager|ranger
nnn|Minimal file manager|nnn
Yazi|Fast TUI file manager|yazi|apt=-;dnf=-
Midnight Commander|Classic file manager|mc
fzf|Fuzzy finder|fzf
ripgrep|Fast grep|ripgrep
fd|Fast find|fd|apt=fd-find;dnf=fd-find
bat|cat with syntax highlighting|bat
eza|Modern ls|eza|dnf=-
zoxide|Smarter cd|zoxide
tldr|Short help pages|tealdeer|apt=tealdeer/tldr
curl|Transfer data from URLs|curl
wget|File downloader|wget
aria2|Fast downloader|aria2
rsync|File synchronization|rsync
tree|Directory tree|tree
unzip / zip|ZIP archives|unzip zip
7-Zip|7z archives|7zip|apt=7zip;dnf=p7zip p7zip-plugins;zypper=7zip
unrar|Extract RAR|unrar|dnf=-
Nmap|Network scanner|nmap|zypper=-
mtr|Network diagnostics|mtr
iperf3|Bandwidth test|iperf3|zypper=iperf
speedtest-cli|Internet speed test|speedtest-cli
lm_sensors|Temperature sensors|lm_sensors|apt=lm-sensors;zypper=sensors
PowerTOP|Power usage analysis|powertop
hyperfine|Command benchmarking|hyperfine
cowsay|Talking cow|cowsay
cmatrix|Matrix effect|cmatrix
fortune|Random quotes|fortune-mod|zypper=fortune
# System tools
GParted|Partition editor|gparted
GNOME Disks|Disk management|gnome-disk-utility
KDE Partition Manager|KDE partition editor|partitionmanager|dnf=kde-partitionmanager
Timeshift|System backups|timeshift|zypper=-
Deja Dup|File backups|deja-dup
BleachBit|System cleaner|bleachbit
Baobab|Disk usage analyzer|baobab
Filelight|Disk usage chart|filelight
GNOME Tweaks|GNOME settings|gnome-tweaks
dconf Editor|dconf settings editor|dconf-editor
GNOME System Monitor|System monitor|gnome-system-monitor
Synaptic|Graphical package manager|-|apt=synaptic
Pamac|Graphical package manager|-|aur=pamac-aur
Octopi|Graphical package manager (Qt)|-|aur=octopi
CPU-X|CPU information|cpu-x
UFW|Simple firewall|ufw
GUFW|Graphical UFW|gufw|dnf=-;zypper=-
firewalld|Firewall|firewalld
OpenSSH|SSH server and client|openssh|apt=openssh-server;dnf=openssh-server;zypper=openssh
Samba|Windows file sharing|samba
CUPS|Printing system|cups
Printer settings|Printer configuration|system-config-printer
Blueman|Bluetooth manager|blueman
NetworkManager applet|Network tray icon|network-manager-applet|apt=network-manager-gnome;zypper=NetworkManager-applet
Cockpit|Web admin panel|cockpit
Ventoy|Multi-ISO bootable USB|-|aur=ventoy-bin
VirtualBox|Virtual machines|virtualbox|dnf=VirtualBox
virt-manager|KVM virtual machines|virt-manager
QEMU|Emulator / virtualization|qemu-full|apt=qemu-system;dnf=qemu;zypper=qemu
GNOME Boxes|Simple virtual machines|gnome-boxes
Wine|Run Windows programs|wine|apt=wine64
Winetricks|Wine helper|winetricks
Solaar|Logitech devices|solaar
Piper|Gaming mouse configuration|piper
OpenRGB|RGB lighting control|openrgb|apt=-;zypper=OpenRGB
CopyQ|Clipboard manager|copyq|zypper=-
Conky|Desktop system monitor|conky|apt=conky-all
Variety|Wallpaper changer|variety
Rofi|Application launcher|rofi
Ark|KDE archiver|ark
File Roller|GNOME archiver|file-roller
SpeedCrunch|Calculator|speedcrunch
GNOME Calculator|GNOME calculator|gnome-calculator
# File managers
Dolphin|KDE file manager|dolphin
Nautilus|GNOME file manager|nautilus
Thunar|XFCE file manager|thunar|dnf=Thunar
Nemo|Cinnamon file manager|nemo
PCManFM|Lightweight file manager|pcmanfm
Krusader|Twin-panel file manager|krusader
# Network and downloads
qBittorrent|Torrent client|qbittorrent
Transmission|Torrent client|transmission-gtk
Deluge|Torrent client|deluge-gtk|apt=deluge;zypper=deluge
FileZilla|FTP client|filezilla
Nextcloud|Nextcloud sync client|nextcloud-client|apt=nextcloud-desktop;zypper=nextcloud-desktop
Syncthing|P2P file sync|syncthing
Remmina|Remote desktop|remmina
AnyDesk|Remote desktop|-|aur=anydesk-bin
RustDesk|Open-source remote desktop|-|aur=rustdesk-bin
TeamViewer|Remote desktop|-|aur=teamviewer
KDE Connect|Phone integration|kdeconnect|dnf=kde-connect;zypper=kdeconnect-kde
LocalSend|Share files over LAN|-|aur=localsend-bin
Wireshark|Network traffic analyzer|wireshark-qt|apt=wireshark;dnf=wireshark;zypper=wireshark
Tailscale|Private VPN network|tailscale|apt=-
WireGuard|WireGuard VPN tools|wireguard-tools
OpenVPN|VPN client|openvpn
# Security
KeePassXC|Password manager|keepassxc
Bitwarden|Cloud password manager|bitwarden|apt=-;dnf=-;zypper=-
1Password|Password manager|-|aur=1password
ClamAV|Antivirus|clamav
VeraCrypt|Disk encryption|veracrypt|apt=-;dnf=-;zypper=-
GnuPG|Encryption and signing|gnupg|dnf=gnupg2;zypper=gpg2
Seahorse|GNOME key manager|seahorse
pass|Command-line password manager|pass|zypper=password-store
Firejail|Application sandbox|firejail
# Games
Steam|Game platform|steam|apt=steam-installer
Lutris|Game manager|lutris
Heroic Games Launcher|Epic, GOG, Amazon|-|aur=heroic-games-launcher-bin
ProtonUp-Qt|Proton-GE installer|-|aur=protonup-qt-bin
GameMode|Gaming optimizations|gamemode
MangoHud|FPS overlay|mangohud
Gamescope|Gaming micro-compositor|gamescope|apt=-
Prism Launcher|Minecraft launcher|prismlauncher|apt=-;dnf=-
RetroArch|Multi-system emulator|retroarch
Dolphin Emulator|GameCube / Wii emulator|dolphin-emu
PPSSPP|PSP emulator|ppsspp|apt=-;dnf=-
DOSBox|DOS emulator|dosbox|dnf=dosbox-staging
ScummVM|Classic adventure games|scummvm
SuperTuxKart|Kart racing|supertuxkart
0 A.D.|Historical strategy game|0ad
Luanti (Minetest)|Sandbox voxel game|luanti|apt=minetest/luanti;dnf=minetest
OpenTTD|Transport simulation|openttd
Battle for Wesnoth|Turn-based fantasy strategy|wesnoth
# Fonts
Noto Fonts|Google Noto fonts|noto-fonts|apt=fonts-noto;dnf=google-noto-sans-fonts google-noto-serif-fonts;zypper=google-noto-sans-fonts
Noto Emoji|Color emoji|noto-fonts-emoji|apt=fonts-noto-color-emoji;dnf=google-noto-emoji-fonts;zypper=noto-coloremoji-fonts
JetBrains Mono|Font for programmers|ttf-jetbrains-mono|apt=fonts-jetbrains-mono;dnf=jetbrains-mono-fonts;zypper=jetbrains-mono-fonts
Fira Code|Font with ligatures|ttf-fira-code|apt=fonts-firacode;dnf=fira-code-fonts;zypper=fira-code-fonts
JetBrains Mono Nerd|Nerd Font with icons|ttf-jetbrains-mono-nerd|apt=-;dnf=-;zypper=-
Microsoft Fonts|Arial, Times New Roman, etc.|-|aur=ttf-ms-fonts;apt=ttf-mscorefonts-installer
"""

# Fedora packages that live in RPM Fusion (the script offers to enable it).
RPMFUSION = {"kodi", "HandBrake-gui", "telegram-desktop", "simplescreenrecorder",
             "VirtualBox", "steam", "cmus", "mpd"}

# Line format:  Name|Description|flatpak.app.ID   (all IDs checked on Flathub)
FLATPAK = r"""
# Web browsers
Firefox|Mozilla's web browser|org.mozilla.firefox
Google Chrome|Google's web browser|com.google.Chrome
Chromium|Open-source base of Chrome|org.chromium.Chromium
Brave|Browser with built-in ad blocking|com.brave.Browser
Vivaldi|Feature-rich browser|com.vivaldi.Vivaldi
LibreWolf|Privacy-focused Firefox fork|io.gitlab.librewolf-community
Zen Browser|Modern Firefox fork|app.zen_browser.zen
Microsoft Edge|Microsoft's web browser|com.microsoft.Edge
Tor Browser|Anonymous browsing|org.torproject.torbrowser-launcher
# Chat
Discord|Voice and text chat|com.discordapp.Discord
Vesktop|Discord with Vencord|dev.vencord.Vesktop
Telegram|Telegram messenger|org.telegram.desktop
Signal|Encrypted messenger|org.signal.Signal
Element|Matrix client|im.riot.Riot
Slack|Team chat|com.slack.Slack
Zoom|Video meetings|us.zoom.Zoom
Teams for Linux|Unofficial MS Teams client|com.github.IsmaelMartinez.teams_for_linux
ZapZap|WhatsApp for Linux|com.rtosta.zapzap
Thunderbird|E-mail client|org.mozilla.Thunderbird
Mumble|Voice chat|info.mumble.Mumble
Fractal|GNOME Matrix client|org.gnome.Fractal
# Audio and video
Spotify|Music streaming|com.spotify.Client
VLC|Media player|org.videolan.VLC
mpv|Minimalist media player|io.mpv.Mpv
Celluloid|GTK front-end for mpv|io.github.celluloid_player.Celluloid
Kodi|Media center|tv.kodi.Kodi
Stremio|Movies and TV shows|com.stremio.Stremio
Jellyfin Media Player|Jellyfin client|com.github.iwalton3.jellyfin-media-player
FreeTube|Ad-free YouTube|io.freetubeapp.FreeTube
Parabolic|Video downloader|org.nickvision.tubeconverter
OBS Studio|Recording and streaming|com.obsproject.Studio
Kooha|Screen recorder|io.github.seadve.Kooha
Audacity|Audio editor|org.audacityteam.Audacity
Tenacity|Audacity fork|org.tenacityaudio.Tenacity
Kdenlive|KDE video editor|org.kde.kdenlive
Shotcut|Video editor|org.shotcut.Shotcut
OpenShot|Simple video editor|org.openshot.OpenShot
Flowblade|Video editor|io.github.jliljebl.Flowblade
HandBrake|Video converter|fr.handbrake.ghb
EasyEffects|Audio effects|com.github.wwmm.easyeffects
Rhythmbox|Music player|org.gnome.Rhythmbox3
Strawberry|Music player|org.strawberrymusicplayer.strawberry
Elisa|KDE music player|org.kde.elisa
MuseScore|Music notation|org.musescore.MuseScore
LMMS|Music production|io.lmms.LMMS
SongRec|Song recognition|com.github.marinm.songrec
Snapshot|GNOME camera|org.gnome.Snapshot
Blanket|Ambient sounds|com.rafaelmardojai.Blanket
# Graphics
GIMP|Image editor|org.gimp.GIMP
Krita|Digital painting|org.kde.krita
Inkscape|Vector graphics|org.inkscape.Inkscape
Blender|3D graphics|org.blender.Blender
Darktable|RAW photos|org.darktable.Darktable
RawTherapee|RAW photos|com.rawtherapee.RawTherapee
digiKam|Photo management|org.kde.digikam
Shotwell|Photo manager|org.gnome.Shotwell
Gwenview|Image viewer|org.kde.gwenview
Loupe|Image viewer|org.gnome.Loupe
Flameshot|Screenshots|org.flameshot.Flameshot
Pinta|Simple image editor|com.github.PintaProject.Pinta
Drawing|Simple drawing app|com.github.maoschanz.drawing
KolourPaint|Paint for KDE|org.kde.kolourpaint
MyPaint|Painting app|org.mypaint.MyPaint
Upscayl|AI image upscaler|org.upscayl.Upscayl
Curtail|Image compressor|com.github.huluti.Curtail
Switcheroo|Image converter|io.gitlab.adhami3310.Converter
FreeCAD|3D CAD|org.freecad.FreeCAD
Scribus|Desktop publishing|net.scribus.Scribus
Synfig Studio|2D animation|org.synfig.SynfigStudio
# Office
LibreOffice|Office suite|org.libreoffice.LibreOffice
OnlyOffice|Office suite|org.onlyoffice.desktopeditors
WPS Office|Office suite|com.wps.Office
Obsidian|Markdown notes|md.obsidian.Obsidian
Joplin|Notes with sync|net.cozic.joplin_desktop
Logseq|Graph-based notes|com.logseq.Logseq
AppFlowy|Notion alternative|io.appflowy.AppFlowy
Standard Notes|Encrypted notes|org.standardnotes.standardnotes
Rnote|Handwritten notes|com.github.flxzt.rnote
Xournal++|Handwritten notes and PDF|com.github.xournalpp.xournalpp
Iotas|Simple notes|org.gnome.World.Iotas
Planify|To-do list|io.github.alainm23.planify
Super Productivity|Tasks and time tracking|com.super_productivity.SuperProductivity
Zotero|Reference manager|org.zotero.Zotero
Calibre|E-books|com.calibre_ebook.calibre
Foliate|E-book reader|com.github.johnfactotum.Foliate
Okular|PDF viewer|org.kde.okular
Evince|PDF viewer|org.gnome.Evince
PDF Arranger|Merge PDFs|com.github.jeromerobert.pdfarranger
Anki|Flashcards|net.ankiweb.Anki
GnuCash|Finance|org.gnucash.GnuCash
# Development
Visual Studio Code|Code editor|com.visualstudio.code
VSCodium|VS Code without telemetry|com.vscodium.codium
Zed|Fast code editor|dev.zed.Zed
Sublime Text|Text editor|com.sublimetext.three
IntelliJ IDEA CE|Java IDE|com.jetbrains.IntelliJ-IDEA-Community
PyCharm CE|Python IDE|com.jetbrains.PyCharm-Community
Android Studio|Android IDE|com.google.AndroidStudio
GNOME Builder|GNOME IDE|org.gnome.Builder
Kate|KDE editor|org.kde.kate
Geany|Lightweight IDE|org.geany.Geany
GitHub Desktop|GitHub client|io.github.shiftey.Desktop
Meld|Diff tool|org.gnome.meld
Postman|API testing|com.getpostman.Postman
Insomnia|API testing|rest.insomnia.Insomnia
Bruno|API testing|com.usebruno.Bruno
DBeaver|Database client|io.dbeaver.DBeaverCommunity
Godot|Game engine|org.godotengine.Godot
Arduino IDE 2|Arduino programming|cc.arduino.IDE2
Podman Desktop|Containers|io.podman_desktop.PodmanDesktop
Pods|Podman containers|com.github.marhkb.Pods
Dev Toolbox|Developer utilities|me.iepure.devtoolbox
Workbench|Learn GTK|re.sonny.Workbench
# Games
Steam|Game platform|com.valvesoftware.Steam
Heroic Games Launcher|Epic, GOG, Amazon|com.heroicgameslauncher.hgl
Lutris|Game manager|net.lutris.Lutris
Bottles|Windows apps via Wine|com.usebottles.bottles
ProtonUp-Qt|Proton-GE installer|net.davidotek.pupgui2
ProtonPlus|Proton version manager|com.vysp3r.ProtonPlus
Protontricks|Winetricks for Proton|com.github.Matoking.protontricks
Cartridges|Game library|page.kramo.Cartridges
Prism Launcher|Minecraft launcher|org.prismlauncher.PrismLauncher
Sober|Roblox on Linux|org.vinegarhq.Sober
Vinegar|Roblox Studio on Linux|org.vinegarhq.Vinegar
itch.io|Indie games|io.itch.itch
Moonlight|Game streaming|com.moonlight_stream.Moonlight
Parsec|Remote gaming|com.parsecgaming.parsec
RetroArch|Multi-system emulator|org.libretro.RetroArch
Dolphin Emulator|GameCube / Wii|org.DolphinEmu.dolphin-emu
PCSX2|PS2 emulator|net.pcsx2.PCSX2
RPCS3|PS3 emulator|net.rpcs3.RPCS3
PPSSPP|PSP emulator|org.ppsspp.PPSSPP
Cemu|Wii U emulator|info.cemu.Cemu
ScummVM|Classic adventure games|org.scummvm.ScummVM
SuperTuxKart|Kart racing|net.supertuxkart.SuperTuxKart
0 A.D.|Historical strategy|com.play0ad.zeroad
Luanti (Minetest)|Sandbox voxel game|org.luanti.luanti
OpenTTD|Transport simulation|org.openttd.OpenTTD
Battle for Wesnoth|Turn-based strategy|org.wesnoth.Wesnoth
OpenRA|Classic RTS games|net.openra.OpenRA
# Network
qBittorrent|Torrent client|org.qbittorrent.qBittorrent
Transmission|Torrent client|com.transmissionbt.Transmission
Fragments|GNOME torrent client|de.haeckerfelix.Fragments
FileZilla|FTP client|org.filezillaproject.Filezilla
Nextcloud|Nextcloud sync|com.nextcloud.desktopclient.nextcloud
SyncThingy|Syncthing in the tray|com.github.zocker_160.SyncThingy
Remmina|Remote desktop|org.remmina.Remmina
AnyDesk|Remote desktop|com.anydesk.Anydesk
RustDesk|Open-source remote desktop|com.rustdesk.RustDesk
LocalSend|Share files over LAN|org.localsend.localsend_app
JDownloader|Download manager|org.jdownloader.JDownloader
Wireshark|Network traffic analyzer|org.wireshark.Wireshark
Proton VPN|VPN|com.protonvpn.www
# System tools
Flatseal|Flatpak permissions|com.github.tchx84.Flatseal
Warehouse|Manage Flatpaks|io.github.flattool.Warehouse
Gear Lever|Manage AppImages|it.mijorus.gearlever
Extension Manager|GNOME extensions|com.mattjakeman.ExtensionManager
Mission Center|System monitor|io.missioncenter.MissionCenter
Resources|Resource monitor|net.nokyan.Resources
Czkawka|Duplicate finder|com.github.qarmin.czkawka
BleachBit|System cleaner|org.bleachbit.BleachBit
Baobab|Disk usage|org.gnome.baobab
Filelight|Disk usage chart|org.kde.filelight
GNOME Boxes|Virtual machines|org.gnome.Boxes
BoxBuddy|Graphical Distrobox|io.github.dvlv.boxbuddyrs
Raspberry Pi Imager|Write SD card images|org.raspberrypi.rpi-imager
Refine|Hidden GNOME settings|page.tesk.Refine
KeePassXC|Password manager|org.keepassxc.KeePassXC
Bitwarden|Password manager|com.bitwarden.desktop
Secrets|GNOME password manager|org.gnome.World.Secrets
Authenticator|2FA codes|com.belmoussaoui.Authenticator
CopyQ|Clipboard manager|com.github.hluk.copyq
PeaZip|Archiver|io.github.peazip.PeaZip
Ark|KDE archiver|org.kde.ark
File Roller|GNOME archiver|org.gnome.FileRoller
GNOME Calculator|Calculator|org.gnome.Calculator
GNOME Text Editor|Simple editor|org.gnome.TextEditor
GNOME Weather|Weather forecast|org.gnome.Weather
GNOME Clocks|Clock, alarm, stopwatch|org.gnome.clocks
GNOME Calendar|Calendar|org.gnome.Calendar
Sound Recorder|Record audio|org.gnome.SoundRecorder
Characters|Emoji and special characters|org.gnome.Characters
"""


def parse_native(pm):
    """Return the program list with packages resolved for package manager pm."""
    key = {"pacman": "arch", "apt": "apt", "dnf": "dnf", "zypper": "zypper"}.get(pm)
    items, cat = [], "Other"
    for line in NATIVE.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            cat = line[1:].strip()
            continue
        parts = line.split("|")
        name, desc, default = parts[0], parts[1], parts[2]
        ov = {}
        if len(parts) > 3 and parts[3]:
            for kv in parts[3].split(";"):
                k, v = kv.split("=", 1)
                ov[k.strip()] = v.strip()
        source = "repo"
        if key is None:
            spec = "-"
        elif key in ov:
            spec = ov[key]
        elif pm == "pacman" and "aur" in ov:
            spec, source = ov["aur"], "aur"
        else:
            spec = default
        pkgs = [] if spec == "-" else spec.split()
        if pm == "dnf" and any(p in RPMFUSION for p in pkgs):
            source = "rpmfusion"
        items.append(dict(name=name, desc=desc, cat=cat, pkgs=pkgs, source=source,
                          avail=bool(pkgs), sel=False, installed=False))
    return items


def parse_flatpak(flatpak_possible):
    items, cat = [], "Other"
    for line in FLATPAK.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            cat = line[1:].strip()
            continue
        name, desc, appid = line.split("|")
        items.append(dict(name=name, desc=desc, cat=cat, pkgs=[appid], source="flatpak",
                          avail=flatpak_possible, sel=False, installed=False))
    return items


# ---------------------------------------------------------------------------
#  System detection
# ---------------------------------------------------------------------------

def os_name():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def detect_pm():
    for pm, binary in (("pacman", "pacman"), ("apt", "apt-get"), ("dnf", "dnf"), ("zypper", "zypper")):
        if shutil.which(binary):
            return pm
    return None


def detect_aur_helper():
    for h in ("paru", "yay"):
        if shutil.which(h):
            return h
    return None


def _lines(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
        return out.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def installed_native(pm):
    if pm == "pacman":
        return set(_lines(["pacman", "-Qq"]))
    if pm == "apt":
        s = set()
        for l in _lines(["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\n"]):
            p = l.split()
            if len(p) >= 2 and p[1].startswith("ii"):
                s.add(p[0].split(":")[0])
        return s
    if pm in ("dnf", "zypper"):
        return set(_lines(["rpm", "-qa", "--qf", "%{NAME}\n"]))
    return set()


def installed_flatpak():
    if not shutil.which("flatpak"):
        return set()
    return {l.strip() for l in _lines(["flatpak", "list", "--app", "--columns=application"]) if l.strip()}


def token_installed(token, installed):
    """A token may be 'a/b' (alternatives): installed if any of them is."""
    return any(alt in installed for alt in token.split("/"))


def refresh_installed(native, flat, pm):
    n, f = installed_native(pm), installed_flatpak()
    for it in native:
        if it["source"] == "flatpak":
            it["installed"] = it["pkgs"][0] in f
        else:
            it["installed"] = bool(it["pkgs"]) and all(token_installed(p, n) for p in it["pkgs"])
    for it in flat:
        it["installed"] = it["pkgs"][0] in f


def prepare_native(native, flat, pm, flatpak_possible):
    """Resolve 'a/b' alternatives to the real name for this distro, and let apps
    that have no native package fall back to their Flatpak version."""
    if pm and shutil.which({"pacman": "pacman", "apt": "apt-cache", "dnf": "dnf", "zypper": "zypper"}[pm]):
        for it in native:
            it["pkgs"] = [resolve_token(pm, p) for p in it["pkgs"]]
    by_name = {it["name"].lower(): it["pkgs"][0] for it in flat}
    for it in native:
        appid = by_name.get(it["name"].lower())
        if not it["avail"] and appid and flatpak_possible:
            it.update(pkgs=[appid], source="flatpak", avail=True)


def pkg_available(pm, name):
    """Ask the package manager whether a package exists in the enabled repos."""
    cmd = {"pacman": ["pacman", "-Si", name],
           "apt": ["apt-cache", "show", name],
           "dnf": ["dnf", "-q", "info", name],
           "zypper": ["zypper", "-q", "info", name]}.get(pm)
    if not cmd or not shutil.which(cmd[0]):
        return False
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and "not found" not in r.stdout.lower() and r.stdout.strip() != ""


def resolve_token(pm, token):
    """Pick the first existing name from 'a/b/c'; fall back to the first one."""
    alts = token.split("/")
    if len(alts) == 1:
        return token
    for alt in alts:
        if pkg_available(pm, alt):
            return alt
    return alts[0]


# ---------------------------------------------------------------------------
#  Terminal UI (curses)
# ---------------------------------------------------------------------------

C_TITLE, C_HEAD, C_SEL, C_INST, C_AUR, C_TAB, C_TABON, C_KEY, C_FLAT = range(1, 10)


class App:
    def __init__(self, native, flat, info):
        self.tabs = [native, flat]
        self.tab_names = ["System packages", "Flatpak (Flathub)"]
        self.tab = 0
        self.cursor = [0, 0]
        self.top = [0, 0]
        self.query = ""
        self.searching = False
        self.info = info
        self.msg = ""

    # -- data --------------------------------------------------------------
    def rows(self):
        q = self.query.lower()
        rows, last = [], None
        for it in self.tabs[self.tab]:
            if q and q not in (it["name"] + " " + it["desc"] + " " + " ".join(it["pkgs"])).lower():
                continue
            if it["cat"] != last:
                rows.append(("h", it["cat"]))
                last = it["cat"]
            rows.append(("i", it))
        return rows

    def selected(self, tab):
        return [it for it in self.tabs[tab] if it["sel"]]

    # -- drawing -----------------------------------------------------------
    def put(self, scr, y, x, text, attr=0):
        h, w = scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        text = text[: max(0, w - x - (1 if y == h - 1 else 0))]
        try:
            scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        if h < 12 or w < 60:
            self.put(scr, 0, 0, "Please enlarge the terminal (min. 60x12)")
            scr.refresh()
            return

        title = (f" ▣ App Installer   {self.info['os']}   package manager: {self.info['pm_label']}"
                 f"   flatpak: {self.info['flatpak_label']} ")
        self.put(scr, 0, 0, title.ljust(w), curses.color_pair(C_TITLE) | curses.A_BOLD)

        x = 1
        for i, nm in enumerate(self.tab_names):
            nsel = len(self.selected(i))
            label = f" {i + 1}. {nm} ({len(self.tabs[i])})" + (f" [{nsel} selected]" if nsel else "") + " "
            attr = curses.color_pair(C_TABON) | curses.A_BOLD if i == self.tab else curses.color_pair(C_TAB)
            self.put(scr, 1, x, label, attr)
            x += len(label) + 1

        if self.searching:
            self.put(scr, 2, 1, f"Search: {self.query}█", curses.A_BOLD)
        elif self.query:
            self.put(scr, 2, 1, f"Filter: \"{self.query}\"   (Esc to clear)", curses.color_pair(C_AUR))
        elif self.msg:
            self.put(scr, 2, 1, self.msg, curses.color_pair(C_AUR))
        else:
            self.put(scr, 2, 1, "Tip: press Space on a category header to select the whole category.", curses.A_DIM)

        rows = self.rows()
        t = self.tab
        self.cursor[t] = max(0, min(self.cursor[t], len(rows) - 1)) if rows else 0
        listh = h - 6
        if self.cursor[t] < self.top[t]:
            self.top[t] = self.cursor[t]
        if self.cursor[t] >= self.top[t] + listh:
            self.top[t] = self.cursor[t] - listh + 1
        self.top[t] = max(0, min(self.top[t], max(0, len(rows) - listh)))

        namew = min(26, max(14, w // 4))
        for i in range(listh):
            idx = self.top[t] + i
            if idx >= len(rows):
                break
            y = 3 + i
            kind, val = rows[idx]
            rev = curses.A_REVERSE if idx == self.cursor[t] else 0
            if kind == "h":
                items = [it for it in self.tabs[t] if it["cat"] == val]
                ns = sum(it["sel"] for it in items)
                label = f" ▸ {val}  ({ns}/{len(items)}) "
                self.put(scr, y, 0, (label + "─" * w)[: w - 1], curses.color_pair(C_HEAD) | curses.A_BOLD | rev)
                continue
            it = val
            if not it["avail"]:
                mark, mattr = "[-]", curses.A_DIM
            elif it["sel"]:
                mark, mattr = "[x]", curses.color_pair(C_SEL) | curses.A_BOLD
            else:
                mark, mattr = "[ ]", 0
            if it["installed"]:
                right, rattr = "installed", curses.color_pair(C_INST) | curses.A_BOLD
            elif not it["avail"]:
                right, rattr = "not available", curses.A_DIM
            elif it["source"] == "aur":
                right, rattr = "AUR: " + " ".join(it["pkgs"]), curses.color_pair(C_AUR)
            elif it["source"] == "rpmfusion":
                right, rattr = "RPM Fusion: " + " ".join(it["pkgs"]), curses.color_pair(C_AUR)
            elif it["source"] == "flatpak":
                right = ("Flatpak: " if t == 0 else "") + it["pkgs"][0]
                rattr = curses.color_pair(C_FLAT)
            else:
                right, rattr = " ".join(it["pkgs"]), curses.A_DIM
            right = right[: max(10, w // 3)]
            dim = curses.A_DIM if not it["avail"] else 0
            name = it["name"][:namew].ljust(namew) + "  "
            descw = max(0, w - 1 - 7 - len(name) - len(right) - 2)
            desc = it["desc"][:descw].ljust(descw)
            self.put(scr, y, 0, "   ", rev)
            self.put(scr, y, 3, mark, mattr | rev)
            self.put(scr, y, 6, " ", rev)
            self.put(scr, y, 7, name, curses.A_BOLD | dim | rev)
            self.put(scr, y, 7 + len(name), desc + "  ", dim | rev)
            self.put(scr, y, 7 + len(name) + descw + 2, right, rattr | rev)

        # scrollbar
        if len(rows) > listh:
            pos = int(self.top[t] / max(1, len(rows) - listh) * (listh - 1))
            for i in range(listh):
                self.put(scr, 3 + i, w - 1, "█" if i == pos else "│", curses.A_DIM)

        ns, nf = len(self.selected(0)), len(self.selected(1))
        status = f" Selected: {ns} system, {nf} flatpak   │   item {self.cursor[t] + 1}/{len(rows)} "
        self.put(scr, h - 3, 0, "─" * (w - 1), curses.A_DIM)
        self.put(scr, h - 2, 0, status, curses.A_BOLD)
        keys = [("↑↓", "move"), ("Space", "select"), ("Tab", "section"), ("←→", "category"),
                ("/", "search"), ("a", "select visible"), ("u", "clear"), ("Enter", "INSTALL"), ("q", "quit")]
        x = 0
        for k, d in keys:
            self.put(scr, h - 1, x, f" {k} ", curses.color_pair(C_KEY) | curses.A_BOLD)
            x += len(k) + 2
            self.put(scr, h - 1, x, f" {d} ")
            x += len(d) + 2
        scr.refresh()

    # -- logic -------------------------------------------------------------
    def toggle(self, rows):
        t = self.tab
        if not rows:
            return
        kind, val = rows[self.cursor[t]]
        if kind == "h":
            vis = [r[1] for r in rows if r[0] == "i" and r[1]["cat"] == val and r[1]["avail"]]
            newv = not all(it["sel"] for it in vis)
            for it in vis:
                it["sel"] = newv
        elif val["avail"]:
            val["sel"] = not val["sel"]
            self.cursor[t] = min(self.cursor[t] + 1, len(rows) - 1)
        else:
            self.msg = f"\"{val['name']}\" is not available for your package manager."

    def run(self, scr):
        curses.curs_set(0)
        scr.keypad(True)
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        curses.init_pair(C_TITLE, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(C_HEAD, curses.COLOR_CYAN, bg)
        curses.init_pair(C_SEL, curses.COLOR_GREEN, bg)
        curses.init_pair(C_INST, curses.COLOR_GREEN, bg)
        curses.init_pair(C_AUR, curses.COLOR_YELLOW, bg)
        curses.init_pair(C_TAB, curses.COLOR_WHITE, bg)
        curses.init_pair(C_TABON, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(C_KEY, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(C_FLAT, curses.COLOR_BLUE, bg)

        while True:
            self.draw(scr)
            try:
                ch = scr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                return "quit"
            rows = self.rows()
            t = self.tab
            h, _ = scr.getmaxyx()
            page = max(1, h - 7)
            self.msg = ""

            if self.searching:
                if ch in ("\n", "\r", curses.KEY_ENTER):
                    self.searching = False
                elif ch == "\x1b":
                    self.searching = False
                    self.query = ""
                elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    self.query = self.query[:-1]
                elif isinstance(ch, str) and ch.isprintable():
                    self.query += ch
                    self.cursor[t] = 0
                continue

            if ch in (curses.KEY_UP, "k"):
                self.cursor[t] = max(0, self.cursor[t] - 1)
            elif ch in (curses.KEY_DOWN, "j"):
                self.cursor[t] = min(len(rows) - 1, self.cursor[t] + 1)
            elif ch == curses.KEY_PPAGE:
                self.cursor[t] = max(0, self.cursor[t] - page)
            elif ch == curses.KEY_NPAGE:
                self.cursor[t] = min(len(rows) - 1, self.cursor[t] + page)
            elif ch in (curses.KEY_HOME, "g"):
                self.cursor[t] = 0
            elif ch in (curses.KEY_END, "G"):
                self.cursor[t] = len(rows) - 1
            elif ch in (curses.KEY_RIGHT, "l"):
                for i in range(self.cursor[t] + 1, len(rows)):
                    if rows[i][0] == "h":
                        self.cursor[t] = self.top[t] = i
                        break
            elif ch in (curses.KEY_LEFT, "h"):
                heads = [i for i, r in enumerate(rows) if r[0] == "h" and i < self.cursor[t]]
                if heads:
                    self.cursor[t] = self.top[t] = heads[-1]
            elif ch == " ":
                self.toggle(rows)
            elif ch in ("\t", curses.KEY_BTAB):
                self.tab = 1 - self.tab
            elif ch == "1":
                self.tab = 0
            elif ch == "2":
                self.tab = 1
            elif ch == "/":
                self.searching = True
                self.query = ""
            elif ch == "\x1b":
                self.query = ""
            elif ch == "a":
                vis = [r[1] for r in rows if r[0] == "i" and r[1]["avail"] and not r[1]["installed"]]
                newv = not all(it["sel"] for it in vis)
                for it in vis:
                    it["sel"] = newv
            elif ch == "u":
                for it in self.tabs[t]:
                    it["sel"] = False
            elif ch in ("\n", "\r", curses.KEY_ENTER, "i"):
                if self.selected(0) or self.selected(1):
                    return "install"
                self.msg = "Nothing selected - use Space to pick programs."
            elif ch in ("q", "Q"):
                return "quit"


# ---------------------------------------------------------------------------
#  Installation
# ---------------------------------------------------------------------------

B, G, R, Y, C, N = "\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[0m"


def ask_yes(prompt):
    return input(prompt).strip().lower() not in ("n", "no")


class Installer:
    def __init__(self, pm, aur, dry, flatpak_user):
        self.pm, self.aur, self.dry, self.flatpak_user = pm, aur, dry, flatpak_user
        self.sudo = [] if os.geteuid() == 0 else ["sudo"]
        self.apt_updated = False

    def run(self, cmd, cwd=None):
        print(f"\n{C}{B}$ {' '.join(cmd)}{N}", flush=True)
        if self.dry:
            return True
        try:
            return subprocess.call(cmd, cwd=cwd) == 0
        except FileNotFoundError:
            print(f"{R}Command not found: {cmd[0]}{N}")
            return False

    def batch(self, prefix, pkgs, installed_fn):
        """Install everything at once; on error, check what actually got installed
        (some distros' post-install hooks fail even though the install worked)
        and retry the rest one by one. Returns the list of failures."""
        if not pkgs:
            return []
        if self.run(prefix + pkgs):
            return []
        if self.dry:
            return []
        have = installed_fn()
        left = [p for p in pkgs if p not in have]
        if not left:
            print(f"{Y}The command reported an error, but all packages are installed "
                  f"(probably a distro post-install hook) - treating as success.{N}")
            return []
        if len(left) > 1:
            print(f"{Y}Batch install failed - retrying {len(left)} package(s) one by one...{N}")
        failed = []
        for p in left:
            if not self.run(prefix + [p]) and p not in installed_fn():
                failed.append(p)
        return failed

    def native_prefix(self):
        if self.pm == "pacman":
            return self.sudo + ["pacman", "-S", "--needed", "--noconfirm"]
        if self.pm == "apt":
            if not self.apt_updated:
                self.run(self.sudo + ["apt-get", "update"])
                self.apt_updated = True
            return self.sudo + ["apt-get", "install", "-y"]
        if self.pm == "dnf":
            return self.sudo + ["dnf", "install", "-y"]
        if self.pm == "zypper":
            return self.sudo + ["zypper", "--non-interactive", "install"]
        return None

    def install_native(self, tokens):
        prefix = self.native_prefix()
        if prefix is None:
            return tokens
        pkgs = [resolve_token(self.pm, t) for t in tokens]
        return self.batch(prefix, pkgs, lambda: installed_native(self.pm))

    def enable_rpmfusion(self):
        if any("rpmfusion" in l for l in _lines(["dnf", "repolist"])):
            return True
        if not ask_yes(f"\n{Y}Some packages come from RPM Fusion, which is not enabled. Enable it? [Y/n] {N}"):
            return False
        ver = (_lines(["rpm", "-E", "%fedora"]) or ["0"])[0].strip()
        base = "https://mirrors.rpmfusion.org"
        return self.run(self.sudo + ["dnf", "install", "-y",
                                     f"{base}/free/fedora/rpmfusion-free-release-{ver}.noarch.rpm",
                                     f"{base}/nonfree/fedora/rpmfusion-nonfree-release-{ver}.noarch.rpm"])

    def bootstrap_yay(self):
        if os.geteuid() == 0:
            print(f"{R}An AUR helper cannot be built as root.{N}")
            return False
        print(f"{B}Installing the AUR helper \"yay\"...{N}")
        if not self.run(self.sudo + ["pacman", "-S", "--needed", "--noconfirm", "git", "base-devel"]):
            return False
        d = tempfile.mkdtemp(prefix="yay-")
        if not self.run(["git", "clone", "https://aur.archlinux.org/yay-bin.git", d + "/yay-bin"]):
            return False
        if not self.run(["makepkg", "-si", "--noconfirm"], cwd=d + "/yay-bin"):
            return False
        self.aur = "yay"
        return True

    def install_aur(self, pkgs):
        if not pkgs:
            return []
        if not self.aur:
            if not ask_yes(f"\n{Y}You selected AUR packages but have neither paru nor yay. Install yay? [Y/n] {N}") \
                    or not self.bootstrap_yay():
                print(f"{R}Skipping AUR packages.{N}")
                return pkgs
        if os.geteuid() == 0:
            print(f"{R}AUR packages must not be built as root - run the script as a normal user.{N}")
            return pkgs
        # No --noconfirm: the AUR is user-submitted, so the helper shows the
        # PKGBUILD for review and asks before building.
        print(f"{Y}AUR packages are user-submitted - review the PKGBUILD when the helper asks.{N}")
        return self.batch([self.aur, "-S", "--needed"], pkgs, lambda: installed_native("pacman"))

    def install_flatpak(self, ids):
        if not ids:
            return []
        if not shutil.which("flatpak"):
            print(f"{Y}Flatpak is not installed - installing it first...{N}")
            if self.install_native(["flatpak"]) and not self.dry:
                print(f"{R}Could not install Flatpak.{N}")
                return ids
        scope = ["--user"] if self.flatpak_user else ["--system"]
        pre = [] if self.flatpak_user else self.sudo
        self.run(pre + ["flatpak", "remote-add", "--if-not-exists"] + scope +
                 ["flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
        return self.batch(pre + ["flatpak", "install", "-y", "--noninteractive"] + scope + ["flathub"],
                          ids, installed_flatpak)


def do_install(app, inst):
    nat = app.selected(0)
    flat = app.selected(1)
    repo = [p for it in nat if it["source"] in ("repo", "rpmfusion") for p in it["pkgs"]]
    aur = [p for it in nat if it["source"] == "aur" for p in it["pkgs"]]
    # Flatpak tab + native apps that fall back to Flatpak (deduplicated, order kept)
    fp = list(dict.fromkeys([it["pkgs"][0] for it in nat if it["source"] == "flatpak"] +
                            [it["pkgs"][0] for it in flat]))
    needs_rpmfusion = any(it["source"] == "rpmfusion" for it in nat)

    print(f"\n{B}══════════ Summary ══════════{N}")
    if repo:
        print(f"{B}Repositories ({inst.pm}):{N} {' '.join(repo)}")
    if aur:
        print(f"{B}AUR ({inst.aur or 'no helper'}):{N} {' '.join(aur)}")
    if fp:
        print(f"{B}Flatpak:{N} {' '.join(fp)}")
    if inst.dry:
        print(f"{Y}DRY RUN (--dry-run): commands will only be printed.{N}")
    if not ask_yes(f"\nInstall {len(nat) + len(flat)} program(s)? [Y/n] "):
        return

    failed = []
    if needs_rpmfusion and not inst.dry and not inst.enable_rpmfusion():
        print(f"{Y}RPM Fusion not enabled - its packages will probably fail.{N}")
    if repo:
        failed += inst.install_native(repo)
    failed += inst.install_aur(aur)
    failed += inst.install_flatpak(fp)

    print(f"\n{B}══════════ Result ══════════{N}")
    if failed:
        print(f"{R}Failed to install:{N} {' '.join(failed)}")
    else:
        print(f"{G}{B}Everything installed successfully!{N}")
    for it in nat + flat:
        if not any(p in failed or any(a in failed for a in p.split("/")) for p in it["pkgs"]):
            it["sel"] = False


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Terminal UI for installing popular Linux programs")
    ap.add_argument("--dry-run", action="store_true", help="only print the commands, install nothing")
    ap.add_argument("--flatpak-user", action="store_true", help="install Flatpaks per-user (no sudo)")
    ap.add_argument("--list", action="store_true", help="print the program list and exit")
    args = ap.parse_args()

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")  # make the Esc key respond instantly
    pm = detect_pm()
    aur = detect_aur_helper() if pm == "pacman" else None
    native = parse_native(pm)
    flatpak_possible = bool(shutil.which("flatpak") or pm)
    flat = parse_flatpak(flatpak_possible)
    prepare_native(native, flat, pm, flatpak_possible)

    if args.list:
        for title, items in (("SYSTEM PACKAGES", native), ("FLATPAK", flat)):
            print(f"\n== {title} ({len(items)}) ==")
            cat = None
            for it in items:
                if it["cat"] != cat:
                    cat = it["cat"]
                    print(f"\n# {cat}")
                tag = {"aur": "AUR ", "rpmfusion": "RPM Fusion ", "flatpak": "Flatpak "}.get(it["source"], "")
                pk = tag + " ".join(it["pkgs"]) if it["avail"] else "(not available)"
                print(f"  {it['name']:<28} {pk}")
        print(f"\nTotal: {len(native) + len(flat)} programs. Package manager: {pm}, AUR helper: {aur}")
        return

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.exit("This script must be run in an interactive terminal.")
    if pm is None:
        print("No supported package manager found (pacman/apt/dnf/zypper) - only Flatpak will be available.")

    pm_label = (pm or "none") + (f" + {aur} (AUR)" if aur else "")
    info = dict(os=os_name(), pm_label=pm_label, flatpak_label="")
    app = App(native, flat, info)
    inst = Installer(pm, aur, args.dry_run, args.flatpak_user)

    while True:
        refresh_installed(native, flat, pm)
        info["flatpak_label"] = "yes" if shutil.which("flatpak") else "no (will be installed)"
        if curses.wrapper(app.run) != "install":
            break
        try:
            do_install(app, inst)
            input(f"\n{B}Press Enter to return to the list...{N}")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            break


if __name__ == "__main__":
    main()
