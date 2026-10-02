"""Kamæleon desktop pet 🦎

Venstreklik      = hjerter (klik mange gange hurtigt for en overraskelse)
Træk             = flyt den (den falder ned igen, når du slipper)
Højreklik        = menu (gem dig, auto-camouflage, gå en tur, sov, luk)
Hold musen stille foran den, så skyder den tungen ud efter den!
"""
import ctypes
import ctypes.wintypes
import json
import math
import os
import random
import sys
import time
import tkinter as tk

# --- Indstillinger ---
TRANSPARENT = "#ff00ff"   # denne farve bliver usynlig. Brug den ALDRIG i selve dyret
SIDE = 260                # plads til hver side af kamæleonen (til tungen)
TOP = 170                 # plads over kamæleonen (til hjerter og Z'er)
TICK = 30                 # millisekunder mellem hver opdatering
SLEEP_AFTER = 60          # sekunder uden musebevægelse, før den falder i søvn
GRAVITY = 1.2             # hvor hurtigt den falder
TONGUE_RANGE = 230        # hvor langt tungen kan nå
CAMO_DISTANCE = 160       # hvor tæt musen skal være for auto-camouflage
HOP_FRAMES = 14           # hvor mange trin et hop varer
COMBO_CLICKS = 6          # så mange klik hurtigt efter hinanden = hjerte-eksplosion


def resource(path):
    # Finder filer både når man kører pet.py og når det er pakket som .exe
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path)


def screen_bottom():
    # Spørg Windows hvor "arbejdsområdet" slutter (skærmen minus proceslinjen)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.bottom


# ============================================================
#  Vindue og billeder
# ============================================================
root = tk.Tk()
root.overrideredirect(True)                         # fjern kant og titelbar
root.attributes("-topmost", True)                   # altid øverst
root.wm_attributes("-transparentcolor", TRANSPARENT)
root.config(bg=TRANSPARENT)

with open(resource("images/poses.json")) as f:
    poses = json.load(f)

# Alle billeder: images[stilling, retning, gemt]
images = {}
for name in poses:
    for facing in ("right", "left"):
        for is_hidden in (False, True):
            suffix = ("_left" if facing == "left" else "") + ("_hidden" if is_hidden else "")
            images[name, facing, is_hidden] = tk.PhotoImage(file=resource(f"images/{name}{suffix}.png"))

W = max(img.width() for img in images.values()) + 2 * SIDE
H = max(img.height() for img in images.values()) + TOP
canvas = tk.Canvas(root, width=W, height=H, bg=TRANSPARENT, highlightthickness=0)
canvas.pack()

# Kamæleonen står altid nederst i midten af vinduet
body = canvas.create_image(W // 2, H, anchor="s")

# Pupiller (tegnes af koden, så de kan følge musen)
max_eyes = max(len(p["eyes"]) for p in poses.values())
pupils = [(canvas.create_oval(0, 0, 0, 0, fill="black", outline=""),
           canvas.create_oval(0, 0, 0, 0, fill="white", outline="")) for _ in range(max_eyes)]

# Tungen: en lyserød streg med en kugle for enden
tongue_line = canvas.create_line(0, 0, 0, 0, fill="#e0607e", width=6, state="hidden")
tongue_tip = canvas.create_oval(0, 0, 0, 0, fill="#e0607e", outline="#a03050", state="hidden")


# ============================================================
#  Tilstand (alt det kamæleonen skal huske)
# ============================================================
screen_w = root.winfo_screenwidth()
ground = screen_bottom()

pose = "sit"              # sit / walk / lie
facing = "right"          # right / left
state = "idle"            # idle / walking / sleeping / tongue / falling / dragged
hidden = False            # gemt via menuen eller klik
auto_camo = tk.BooleanVar(value=False)

pet_x = screen_w - 450    # midten af kamæleonen på skærmen
pet_y = ground            # bunden af kamæleonen (fødderne) på skærmen
vy = 0                    # fart op/ned når den falder

hop_t = 0                 # hvor langt den er i det nuværende hop
hops_left = 0             # hvor mange hop der er tilbage på turen
next_idea = time.time() + 5   # hvornår den finder på noget nyt
next_z = 0                # hvornår næste Z kommer, når den sover
tongue_t = 0
tongue_target = (0, 0)
tongue_ready = 0          # tidspunkt hvor tungen må bruges igen

last_mouse = root.winfo_pointerxy()
last_mouse_move = time.time()
click_times = []
press = None              # info om et museklik, der er i gang


# ============================================================
#  Hjælpefunktioner
# ============================================================
def direction():
    return 1 if facing == "right" else -1


def current_image():
    return images[pose, facing, hidden or camo_active()]


def to_canvas(px, py):
    # Laver et punkt i tegningen om til et punkt på canvas (og spejler, hvis den kigger til venstre)
    img = images[pose, facing, False]
    left = W // 2 - img.width() // 2
    top = H - img.height()
    if facing == "left":
        px = img.width() - px
    return left + px, top + py


def mouse_on_canvas():
    mx, my = root.winfo_pointerxy()
    return mx - root.winfo_x(), my - root.winfo_y()


def camo_active():
    if not auto_camo.get():
        return False
    mx, my = root.winfo_pointerxy()
    img = images[pose, facing, False]
    center_y = pet_y - img.height() / 2
    return math.hypot(mx - pet_x, my - center_y) < CAMO_DISTANCE


def head_position():
    # Cirka hvor hovedet er (bruges til hjerter og Z'er)
    img = images[pose, facing, False]
    return W // 2 + direction() * img.width() * 0.32, H - img.height()


def set_pose(new_pose):
    global pose
    pose = new_pose


# ============================================================
#  Hjerter og Z'er
# ============================================================
def heart_points(size):
    # Den klassiske hjerte-formel. t går rundt fra 0 til 2π og tegner omridset.
    points = []
    for i in range(30):
        t = i / 30 * 2 * math.pi
        hx = 16 * math.sin(t) ** 3
        hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points += [hx * size, hy * size]
    return points


def spawn_heart(spread=30):
    x, y = head_position()
    x += random.randint(-spread, spread)
    y += random.randint(-10, 10)
    heart = canvas.create_polygon(heart_points(random.uniform(0.4, 0.8)),
                                  fill="#e8304a", outline="#8a0f22", width=2)
    canvas.move(heart, x, y)
    float_up(heart, y, 0, speed=2, wiggle=1.5, grow=1.0)


def spawn_z():
    x, y = head_position()
    s = 10
    z = canvas.create_line(0, 0, s, 0, 0, s, s, s, fill="#3b6fd6", width=4)
    canvas.move(z, x, y - 10)
    float_up(z, y - 10, 0, speed=1, wiggle=1.0, grow=1.03)


def float_up(item, y, age, speed, wiggle, grow):
    # Flyv op, vrik lidt fra side til side, og forsvind ved toppen
    dx = math.sin(age / 4) * wiggle
    canvas.move(item, dx, -speed)
    if grow != 1.0 and age < 25:         # vokser kun lidt i starten
        x1, y1, x2, y2 = canvas.bbox(item)
        canvas.scale(item, (x1 + x2) / 2, (y1 + y2) / 2, grow, grow)
    if y - speed < 15 or age > 150:
        canvas.delete(item)
    else:
        root.after(TICK, float_up, item, y - speed, age + 1, speed, wiggle, grow)


# ============================================================
#  Handlinger
# ============================================================
def start_walk():
    global state, hop_t, hops_left
    if hidden:
        return
    state = "walking"
    set_pose("walk")
    hop_t = 0
    hops_left = random.randint(2, 7)


def go_to_sleep():
    global state, next_z
    state = "sleeping"
    set_pose("lie")
    next_z = time.time()


def wake_up():
    global state, next_idea
    state = "idle"
    set_pose("sit")
    next_idea = time.time() + random.uniform(2, 5)


def start_tongue(target):
    global state, tongue_t, tongue_target
    state = "tongue"
    tongue_t = 0
    tongue_target = target
    canvas.itemconfig(tongue_line, state="normal")
    canvas.itemconfig(tongue_tip, state="normal")


def happy_jump():
    global state, vy
    state = "falling"
    set_pose("walk")
    vy = -15


def toggle_hide():
    global hidden
    hidden = not hidden


def click():
    global hidden
    if hidden:
        hidden = False                 # klik når den er skjult = vis den igen
        return
    if state == "sleeping":
        wake_up()
    spawn_heart()

    # Hjerte-combo: mange klik hurtigt efter hinanden
    now = time.time()
    click_times.append(now)
    while click_times and now - click_times[0] > 1.5:
        click_times.pop(0)
    if len(click_times) >= COMBO_CLICKS:
        click_times.clear()
        for _ in range(12):
            spawn_heart(spread=90)
        if state in ("idle", "walking"):
            happy_jump()


# ============================================================
#  Musen: klik og træk
# ============================================================
def on_press(event):
    global press
    press = {"x": event.x_root, "y": event.y_root, "pet_x": pet_x, "pet_y": pet_y, "dragging": False}


def on_motion(event):
    global state, pet_x, pet_y
    if press is None:
        return
    dx = event.x_root - press["x"]
    dy = event.y_root - press["y"]
    if not press["dragging"] and math.hypot(dx, dy) > 5:
        press["dragging"] = True
        state = "dragged"
        set_pose("walk")               # spræller med benene, når man holder den
    if press["dragging"]:
        pet_x = press["pet_x"] + dx
        pet_y = min(press["pet_y"] + dy, ground)


def on_release(event):
    global press, state, vy
    if press is None:
        return
    if press["dragging"]:
        state = "falling"              # slip = den falder ned
        vy = 0
    else:
        click()
    press = None


# ============================================================
#  Hovedløkken: kører hvert 30. millisekund
# ============================================================
def update():
    global state, pet_x, pet_y, vy, hop_t, hops_left, facing
    global next_idea, next_z, tongue_t, tongue_ready, last_mouse, last_mouse_move

    now = time.time()

    # Har musen flyttet sig?
    mouse = root.winfo_pointerxy()
    if mouse != last_mouse:
        last_mouse = mouse
        last_mouse_move = now
    mouse_still = now - last_mouse_move

    img = images[pose, facing, False]
    half = img.width() / 2

    # --- Hvad laver den lige nu? ---
    if state == "idle":
        if mouse_still > SLEEP_AFTER:
            go_to_sleep()
        elif now > next_idea:
            idea = random.random()
            if idea < 0.6:
                start_walk()
            elif idea < 0.8:
                facing = "left" if facing == "right" else "right"   # vend om
            next_idea = now + random.uniform(4, 10)

        # Tungen: musen holdes stille lige foran munden
        mouth = poses[pose]["mouth"]
        if (state == "idle" and mouth and not (hidden or camo_active())
                and mouse_still > 0.8 and now > tongue_ready):
            mx, my = to_canvas(mouth["x"], mouth["y"])
            tx, ty = mouse_on_canvas()
            in_front = (tx - mx) * direction() > 20
            if in_front and math.hypot(tx - mx, ty - my) < TONGUE_RANGE:
                start_tongue((tx, ty))

    elif state == "walking":
        hop_t += 1
        pet_x += 4 * direction()
        pet_y = ground - hop_t * (HOP_FRAMES - hop_t) * 0.3     # en lille bue
        # Bounce af siderne: vend om ved kanten af skærmen
        if pet_x + half > screen_w or pet_x - half < 0:
            facing = "left" if facing == "right" else "right"
            pet_x = max(half, min(screen_w - half, pet_x))
        if hop_t >= HOP_FRAMES:
            hop_t = 0
            pet_y = ground
            hops_left -= 1
            if hops_left <= 0:
                wake_up()

    elif state == "sleeping":
        if now > next_z:
            spawn_z()
            next_z = now + 1.3
        # Vågner hvis musen kommer tæt på
        mx, my = root.winfo_pointerxy()
        if math.hypot(mx - pet_x, my - (pet_y - img.height() / 2)) < 200:
            wake_up()

    elif state == "tongue":
        tongue_t += 1
        frames = 8
        p = tongue_t / frames if tongue_t <= frames else 2 - tongue_t / frames   # ud og ind igen
        mouth = poses[pose]["mouth"]
        mx, my = to_canvas(mouth["x"], mouth["y"])
        tx = mx + (tongue_target[0] - mx) * p
        ty = my + (tongue_target[1] - my) * p
        canvas.coords(tongue_line, mx, my, tx, ty)
        canvas.coords(tongue_tip, tx - 7, ty - 7, tx + 7, ty + 7)
        if tongue_t >= frames * 2:
            canvas.itemconfig(tongue_line, state="hidden")
            canvas.itemconfig(tongue_tip, state="hidden")
            tongue_ready = now + random.uniform(3, 8)
            state = "idle"

    elif state == "falling":
        vy += GRAVITY
        pet_y += vy
        if pet_y >= ground:
            pet_y = ground
            if vy > 6:
                vy = -vy * 0.35        # lille bounce når den lander
            else:
                vy = 0
                wake_up()

    # --- Tegn den ---
    canvas.itemconfig(body, image=current_image())

    # Pupillerne følger musen
    eyes = poses[pose]["eyes"]
    mouse_x, mouse_y = mouse_on_canvas()
    for i, (pupil, shine) in enumerate(pupils):
        if i >= len(eyes):
            canvas.itemconfig(pupil, state="hidden")
            canvas.itemconfig(shine, state="hidden")
            continue
        eye = eyes[i]
        cx, cy = to_canvas(eye["x"], eye["y"])
        size = eye["r"] * 0.45
        angle = math.atan2(mouse_y - cy, mouse_x - cx)
        move = min(math.hypot(mouse_x - cx, mouse_y - cy) / 20, eye["r"] - size - 1)
        x = cx + math.cos(angle) * move
        y = cy + math.sin(angle) * move
        canvas.coords(pupil, x - size, y - size, x + size, y + size)
        canvas.coords(shine, x - size * 0.6, y - size * 0.6, x - size * 0.1, y - size * 0.1)
        canvas.itemconfig(pupil, state="normal")
        canvas.itemconfig(shine, state="normal")

    # Flyt vinduet hen, hvor kamæleonen er
    root.geometry(f"+{round(pet_x - W / 2)}+{round(pet_y - H)}")
    root.after(TICK, update)


# ============================================================
#  Menu og start
# ============================================================
menu = tk.Menu(root, tearoff=0)
menu.add_command(label="Gem dig / vis dig", command=toggle_hide)
menu.add_checkbutton(label="Auto-camouflage", variable=auto_camo)
menu.add_command(label="Gå en tur", command=start_walk)
menu.add_command(label="Sov", command=go_to_sleep)
menu.add_separator()
menu.add_command(label="Luk", command=root.destroy)

canvas.bind("<ButtonPress-1>", on_press)
canvas.bind("<B1-Motion>", on_motion)
canvas.bind("<ButtonRelease-1>", on_release)
canvas.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

update()
root.mainloop()
