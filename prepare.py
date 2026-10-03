"""Gør tegningerne i drawings/ klar til pet.py.

For hver stilling er der to tegninger: en grøn og en outline (gennemsigtig krop).
  1. Visk den tegnede pupil ud (pet.py tegner en ny, der kan bevæge sig)
  2. Skær den tomme kant væk
  3. Gør størrelsen større/mindre med SCALE
  4. Gør bløde kanter skarpe (Windows-tricket med den usynlige farve kan ikke "halvt")
  5. Lav spejlvendte udgaver (_left), så den kan gå mod venstre
Gemmer billederne i images/ og øjnenes/mundens placering i images/poses.json.

Kør:  python prepare.py
"""
import json
import os

from PIL import Image, ImageDraw

SCALE = 1.0   # 0.5 = halv størrelse, 2.0 = dobbelt størrelse

# Øjnene i tegningerne: midte (x, y) og radius af indersiden af øjet.
# Lad listen være tom, hvis pupillen bare skal blive, som du har tegnet den.
# "mouth" er spidsen af munden, hvor tungen kommer ud (None = ingen tunge).
DRAWINGS = {
    "sit":  {"eyes": [(436, 156, 17)], "mouth": (480, 181)},
    "walk": {"eyes": [(494, 133, 20)], "mouth": None},
    "lie":  {"eyes": [], "mouth": None},
}


def erase_pupils(green, outline, eyes):
    draw_green = ImageDraw.Draw(green)
    draw_outline = ImageDraw.Draw(outline)
    for x, y, r in eyes:
        box = (x - r + 2, y - r + 2, x + r - 2, y + r - 2)
        # Den farve der er mest af inde i øjet (pupillen er mindre end resten)
        inside = [green.getpixel((px, py)) for px in range(x - r + 3, x + r - 2)
                  for py in range(y - r + 3, y + r - 2) if (px - x) ** 2 + (py - y) ** 2 < (r - 3) ** 2]
        body_color = max(set(inside), key=inside.count)
        draw_green.ellipse(box, fill=body_color)    # grøn igen
        draw_outline.ellipse(box, fill=(0, 0, 0, 0))  # gennemsigtig igen


def sharpen_edges(image):
    image.putdata([p[:3] + (255,) if p[3] >= 128 else (0, 0, 0, 0)
                   for p in image.get_flattened_data()])


def body_area(image):
    # Hvor mange pixels kroppen fylder
    return sum(1 for a in image.getchannel("A").get_flattened_data() if a >= 128)


os.makedirs("images", exist_ok=True)
pose_data = {}

# Alle stillinger skaleres, så kroppen fylder lige så meget som den første ("sit").
first = next(iter(DRAWINGS))
target_area = body_area(Image.open(f"drawings/{first}_green.png").convert("RGBA"))

for name, info in DRAWINGS.items():
    green = Image.open(f"drawings/{name}_green.png").convert("RGBA")
    outline = Image.open(f"drawings/{name}_outline.png").convert("RGBA")
    # Areal vokser med længde², så vi tager kvadratroden for at få en længde-faktor
    scale = SCALE * (target_area / body_area(green)) ** 0.5
    erase_pupils(green, outline, info["eyes"])

    # Skær samme kant af begge, så de passer oven i hinanden
    left, top, right, bottom = green.getchannel("A").getbbox()
    green = green.crop((left, top, right, bottom))
    outline = outline.crop((left, top, right, bottom))

    size = (round(green.width * scale), round(green.height * scale))
    green = green.resize(size, Image.LANCZOS)
    outline = outline.resize(size, Image.LANCZOS)

    sharpen_edges(green)
    sharpen_edges(outline)
    green.save(f"images/{name}.png")
    outline.save(f"images/{name}_hidden.png")
    # Spejlvendte udgaver, så den kan kigge mod venstre
    green.transpose(Image.FLIP_LEFT_RIGHT).save(f"images/{name}_left.png")
    outline.transpose(Image.FLIP_LEFT_RIGHT).save(f"images/{name}_left_hidden.png")

    mouth = info["mouth"]
    pose_data[name] = {
        "eyes": [{"x": round((x - left) * scale), "y": round((y - top) * scale), "r": round(r * scale, 1)}
                 for x, y, r in info["eyes"]],
        "mouth": None if mouth is None else
                 {"x": round((mouth[0] - left) * scale), "y": round((mouth[1] - top) * scale)},
    }
    print(f"{name}: {size}, {pose_data[name]}")

with open("images/poses.json", "w") as f:
    json.dump(pose_data, f, indent=2)
