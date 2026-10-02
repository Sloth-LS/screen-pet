import random
import tkinter as tk

root = tk.Tk()
root.overrideredirect(True)                     # fjern vinduet rundt om
root.attributes("-topmost", True)               # altid øverst
root.wm_attributes("-transparentcolor", "pink") # pink bliver usynlig
root.config(bg="pink")

billede = tk.PhotoImage(file="images/sit.png")
gemt_billede = tk.PhotoImage(file="images/sit_hidden.png")

label = tk.Label(root, image=billede, bg="pink")
label.pack()

gemt = False

# Hvor kamæleonen står på skærmen
x = 200
y = 600
root.geometry(f"+{x}+{y}")


def klik(event):
    global gemt
    if gemt:
        label.config(image=billede)
        gemt = False
    else:
        label.config(image=gemt_billede)
        gemt = True


def luk(event):
    root.destroy()


def hop(trin):
    global x
    x = x + 3                          # lidt frem
    højde = trin * (10 - trin)         # op og ned igen (0 → 25 → 0)
    root.geometry(f"+{x}+{y - højde}")

    if trin < 10:
        root.after(30, hop, trin + 1)  # næste trin af hoppet om 30 ms
    else:
        vent_på_hop()                  # hoppet er færdigt


def vent_på_hop():
    ventetid = random.randint(2000, 6000)   # 2-6 sekunder
    root.after(ventetid, måske_hop)


def måske_hop():
    global x
    if x > root.winfo_screenwidth():   # ude af skærmen? start forfra i venstre side
        x = -300
    if gemt:
        vent_på_hop()                  # den gemmer sig, så den hopper ikke
    else:
        hop(0)


label.bind("<Button-1>", klik)   # venstreklik = gem / vis
label.bind("<Button-3>", luk)    # højreklik = luk

vent_på_hop()
root.mainloop()
