# 🦎 Chameleon Desktop Pet

A hand-drawn chameleon that lives at the bottom of your screen. It hops around, sleeps,
catches your cursor with its tongue, and can camouflage itself so it's never in your way.

Made for [Hack Club Playground](https://playground.hackclub.com).

## What it does

| Do this | And the chameleon... |
|---|---|
| Click it | shows you some love ❤️ |
| Click it 6 times fast | explodes in hearts and jumps for joy |
| Drag it | wiggles its legs, and falls back down when you let go |
| Hold your mouse still in front of it | shoots its tongue at your cursor 👅 |
| Leave your computer for a minute | falls asleep 💤 (move your mouse close to wake it) |
| Right-click → *Gem dig / vis dig* | camouflages: only its outline and eyes stay visible |
| Right-click → *Auto-camouflage* | hides automatically whenever your mouse comes close |
| Right-click → *Luk* | closes it |

It also wanders around on its own, turns around at the screen edges, and its eyes
follow your mouse.

## Download

Grab `Kamaeleon.exe` from the releases page and double-click it. Windows only.

## Run from source

Needs Python 3.10+ on Windows.

```
pip install pillow
python prepare.py     # makes the images in images/ from the drawings in drawings/
python pet.py
```

## Build the .exe

```
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name Kamaeleon --add-data "images;images" pet.py
```

The exe ends up in `dist/`.

## Files

```
drawings/      my original drawings (green + outline version of each pose)
images/        prepared images, made by prepare.py
prepare.py     crops, scales and mirrors the drawings, and erases the drawn pupils
pet.py         the pet itself
min_pet.py     the tiny first version (30 lines) – a good place to start reading
```

## Credits

All art is hand-drawn by me. I wrote this while learning Python, with help from
Claude (AI) for explaining and writing parts of the code.
