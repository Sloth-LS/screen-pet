import json
import math
import os
import random
import sys
import time

if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QMenu, QWidget

START_SIZE = 0.5
MIN_SIZE = 0.2
MAX_SIZE = 1.0
SIZES = {"Lille": 0.3, "Mellem": 0.5, "Stor": 0.75, "Kæmpe": 1.0}
SIDE = 260
TOP = 170
TICK = 30
SLEEP_AFTER = 60
GRAVITY = 1.2
TONGUE_RANGE = 230
CAMO_DISTANCE = 160
HOP_FRAMES = 14
COMBO_CLICKS = 6
DOUBLE_CLICK_MS = 350


def resource(path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path)


def heart_shape():
    points = []
    for i in range(30):
        t = i / 30 * 2 * math.pi
        hx = 16 * math.sin(t) ** 3
        hy = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((hx, hy))
    return points


HEART = heart_shape()


class Pet(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)

        with open(resource("images/poses.json")) as f:
            self.full_poses = json.load(f)

        self.originals = {}
        for name in self.full_poses:
            for facing in ("right", "left"):
                for is_hidden in (False, True):
                    suffix = ("_left" if facing == "left" else "") + ("_hidden" if is_hidden else "")
                    self.originals[name, facing, is_hidden] = QPixmap(resource(f"images/{name}{suffix}.png"))

        area = QApplication.primaryScreen().availableGeometry()
        self.screen_left = area.left()
        self.screen_right = area.right()
        self.ground = area.bottom()

        self.pose = "sit"
        self.facing = "right"
        self.state = "idle"
        self.hidden = False
        self.pet_x = self.screen_right - 450
        self.pet_y = self.ground
        self.vy = 0
        self.hop_t = 0
        self.hops_left = 0
        self.next_idea = time.time() + 5
        self.next_z = 0
        self.tongue_t = 0
        self.tongue_target = (0, 0)
        self.tongue_line = None
        self.tongue_ready = 0
        self.last_mouse = QCursor.pos()
        self.last_mouse_move = time.time()
        self.click_times = []
        self.click_count = 0
        self.press = None
        self.effects = []

        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(DOUBLE_CLICK_MS)
        self.click_timer.timeout.connect(self.clicks_done)

        self.size = None
        self.images = {}
        self.poses = {}
        self.build_menu()
        self.set_size(START_SIZE)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK)

    def set_size(self, factor):
        factor = round(max(MIN_SIZE, min(MAX_SIZE, factor)), 2)
        if factor == self.size:
            return
        self.size = factor
        for key, original in self.originals.items():
            w = max(1, round(original.width() * factor))
            h = max(1, round(original.height() * factor))
            self.images[key] = original.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.poses = {}
        for name, p in self.full_poses.items():
            eyes = [{"x": e["x"] * factor, "y": e["y"] * factor, "r": e["r"] * factor} for e in p["eyes"]]
            mouth = None
            if p["mouth"]:
                mouth = {"x": p["mouth"]["x"] * factor, "y": p["mouth"]["y"] * factor}
            self.poses[name] = {"eyes": eyes, "mouth": mouth}
        self.W = max(img.width() for img in self.images.values()) + 2 * round(SIDE * factor)
        self.H = max(img.height() for img in self.images.values()) + TOP
        self.setFixedSize(self.W, self.H)
        for action in self.size_actions:
            action.setChecked(SIZES[action.text()] == factor)
        self.move_window()

    def direction(self):
        return 1 if self.facing == "right" else -1

    def turn_around(self):
        self.facing = "left" if self.facing == "right" else "right"

    def image(self, is_hidden=False):
        return self.images[self.pose, self.facing, is_hidden]

    def mouse_on_screen(self):
        p = QCursor.pos()
        return p.x(), p.y()

    def mouse_on_window(self):
        p = self.mapFromGlobal(QCursor.pos())
        return p.x(), p.y()

    def mouse_near(self, distance):
        mx, my = self.mouse_on_screen()
        center_y = self.pet_y - self.image().height() / 2
        return math.hypot(mx - self.pet_x, my - center_y) < distance * (0.4 + 0.6 * self.size)

    def see_through(self):
        return self.hidden or (self.camo_action.isChecked() and self.mouse_near(CAMO_DISTANCE))

    def body_left_top(self):
        img = self.image()
        return self.W / 2 - img.width() / 2, self.H - img.height()

    def to_window(self, px, py):
        left, top = self.body_left_top()
        if self.facing == "left":
            px = self.image().width() - px
        return left + px, top + py

    def on_body(self, x, y):
        left, top = self.body_left_top()
        img = self.image()
        return left <= x <= left + img.width() and top <= y <= self.H

    def head_position(self):
        img = self.image()
        return self.W / 2 + self.direction() * img.width() * 0.32, self.H - img.height()

    def move_window(self):
        self.move(round(self.pet_x - self.W / 2), round(self.pet_y - self.H))

    def spawn_heart(self, spread=30):
        x, y = self.head_position()
        self.effects.append({
            "kind": "heart", "age": 0, "speed": 2, "wiggle": 1.5, "grow": 1.0,
            "x": x + random.randint(-spread, spread), "y": y + random.randint(-10, 10),
            "scale": random.uniform(0.4, 0.8) * (0.5 + 0.5 * self.size),
        })

    def spawn_z(self):
        x, y = self.head_position()
        self.effects.append({"kind": "z", "age": 0, "speed": 1, "wiggle": 1.0, "grow": 1.03,
                             "x": x, "y": y - 10, "scale": 1.0})

    def move_effects(self):
        for e in self.effects:
            e["x"] += math.sin(e["age"] / 4) * e["wiggle"]
            e["y"] -= e["speed"]
            if e["age"] < 25:
                e["scale"] *= e["grow"]
            e["age"] += 1
        self.effects = [e for e in self.effects if e["y"] > 15 and e["age"] <= 150]

    def start_walk(self):
        if self.hidden:
            return
        self.state = "walking"
        self.pose = "walk"
        self.hop_t = 0
        self.hops_left = random.randint(2, 7)

    def go_to_sleep(self):
        self.state = "sleeping"
        self.pose = "lie"
        self.next_z = time.time()

    def wake_up(self):
        self.state = "idle"
        self.pose = "sit"
        self.next_idea = time.time() + random.uniform(2, 5)

    def start_tongue(self, target):
        self.state = "tongue"
        self.tongue_t = 0
        self.tongue_target = target

    def happy_jump(self):
        self.state = "falling"
        self.pose = "walk"
        self.vy = -15

    def toggle_hide(self):
        self.hidden = not self.hidden

    def click(self):
        self.click_count += 1
        self.click_timer.start()
        if self.hidden:
            return
        if self.state == "sleeping":
            self.wake_up()
        self.spawn_heart()

        now = time.time()
        self.click_times = [t for t in self.click_times if now - t <= 1.5] + [now]
        if len(self.click_times) >= COMBO_CLICKS:
            self.click_times = []
            self.click_count = -1000
            for _ in range(12):
                self.spawn_heart(spread=90)
            if self.state in ("idle", "walking"):
                self.happy_jump()

    def clicks_done(self):
        if self.click_count == 2:
            self.toggle_hide()
        self.click_count = 0

    def mousePressEvent(self, event):
        x, y = event.position().x(), event.position().y()
        if event.button() != Qt.LeftButton or not self.on_body(x, y):
            event.ignore()
            return
        g = event.globalPosition()
        self.press = {"x": g.x(), "y": g.y(), "pet_x": self.pet_x, "pet_y": self.pet_y, "dragging": False}

    def mouseMoveEvent(self, event):
        if self.press is None:
            return
        g = event.globalPosition()
        dx = g.x() - self.press["x"]
        dy = g.y() - self.press["y"]
        if not self.press["dragging"] and math.hypot(dx, dy) > 5:
            self.press["dragging"] = True
            self.state = "dragged"
            self.pose = "walk"
        if self.press["dragging"]:
            self.pet_x = self.press["pet_x"] + dx
            self.pet_y = min(self.press["pet_y"] + dy, self.ground)

    def mouseReleaseEvent(self, event):
        if self.press is None:
            return
        if self.press["dragging"]:
            self.state = "falling"
            self.vy = 0
        else:
            self.click()
        self.press = None

    def wheelEvent(self, event):
        self.set_size(self.size + (0.05 if event.angleDelta().y() > 0 else -0.05))

    def contextMenuEvent(self, event):
        if self.on_body(event.pos().x(), event.pos().y()):
            self.menu.exec(event.globalPos())

    def build_menu(self):
        self.menu = QMenu(self)
        self.menu.addAction("Gem dig / vis dig", self.toggle_hide)
        self.camo_action = self.menu.addAction("Auto-camouflage")
        self.camo_action.setCheckable(True)
        size_menu = self.menu.addMenu("Størrelse")
        group = QActionGroup(self)
        self.size_actions = []
        for label, factor in SIZES.items():
            action = QAction(label, self, checkable=True)
            action.triggered.connect(lambda checked, f=factor: self.set_size(f))
            group.addAction(action)
            size_menu.addAction(action)
            self.size_actions.append(action)
        self.menu.addAction("Gå en tur", self.start_walk)
        self.menu.addAction("Sov", self.go_to_sleep)
        self.menu.addSeparator()
        self.menu.addAction("Luk", QApplication.quit)

    def tick(self):
        now = time.time()

        mouse = QCursor.pos()
        if mouse != self.last_mouse:
            self.last_mouse = mouse
            self.last_mouse_move = now
        mouse_still = now - self.last_mouse_move

        half = self.image().width() / 2

        if self.state == "idle":
            if mouse_still > SLEEP_AFTER:
                self.go_to_sleep()
            elif now > self.next_idea:
                idea = random.random()
                if idea < 0.45:
                    self.start_walk()
                elif idea < 0.65:
                    self.turn_around()
                elif idea < 0.9:
                    self.pose = "walk" if self.pose == "sit" else "sit"
                self.next_idea = now + random.uniform(4, 10)

            mouth = self.poses[self.pose]["mouth"]
            if (self.state == "idle" and mouth and not self.see_through()
                    and mouse_still > 0.8 and now > self.tongue_ready):
                mx, my = self.to_window(mouth["x"], mouth["y"])
                tx, ty = self.mouse_on_window()
                in_front = (tx - mx) * self.direction() > 20
                if in_front and math.hypot(tx - mx, ty - my) < TONGUE_RANGE * self.size:
                    self.start_tongue((tx, ty))

        elif self.state == "walking":
            self.hop_t += 1
            self.pet_x += (1 + 3 * self.size) * self.direction()
            self.pet_y = self.ground - self.hop_t * (HOP_FRAMES - self.hop_t) * 0.3 * self.size
            if self.pet_x + half > self.screen_right or self.pet_x - half < self.screen_left:
                self.turn_around()
                self.pet_x = max(self.screen_left + half, min(self.screen_right - half, self.pet_x))
            if self.hop_t >= HOP_FRAMES:
                self.hop_t = 0
                self.pet_y = self.ground
                self.hops_left -= 1
                if self.hops_left <= 0:
                    self.wake_up()
                    if random.random() < 0.5:
                        self.pose = "walk"

        elif self.state == "sleeping":
            if now > self.next_z:
                self.spawn_z()
                self.next_z = now + 1.3
            if self.mouse_near(200):
                self.wake_up()

        elif self.state == "tongue":
            self.tongue_t += 1
            frames = 8
            p = self.tongue_t / frames if self.tongue_t <= frames else 2 - self.tongue_t / frames
            mouth = self.poses[self.pose]["mouth"]
            mx, my = self.to_window(mouth["x"], mouth["y"])
            tx = mx + (self.tongue_target[0] - mx) * p
            ty = my + (self.tongue_target[1] - my) * p
            self.tongue_line = (mx, my, tx, ty)
            if self.tongue_t >= frames * 2:
                self.tongue_line = None
                self.tongue_ready = now + random.uniform(3, 8)
                self.state = "idle"

        elif self.state == "falling":
            self.vy += GRAVITY
            self.pet_y += self.vy
            if self.pet_y >= self.ground:
                self.pet_y = self.ground
                if self.vy > 6:
                    self.vy = -self.vy * 0.35
                else:
                    self.vy = 0
                    self.wake_up()

        self.move_effects()
        self.move_window()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        left, top = self.body_left_top()

        if self.see_through():
            painter.setOpacity(0.01)
            painter.drawPixmap(QPointF(left, top), self.image())
            painter.setOpacity(1.0)
            painter.drawPixmap(QPointF(left, top), self.image(is_hidden=True))
        else:
            painter.drawPixmap(QPointF(left, top), self.image())

        mouse_x, mouse_y = self.mouse_on_window()
        for eye in self.poses[self.pose]["eyes"]:
            cx, cy = self.to_window(eye["x"], eye["y"])
            r = eye["r"] * 0.45
            angle = math.atan2(mouse_y - cy, mouse_x - cx)
            move = max(0, min(math.hypot(mouse_x - cx, mouse_y - cy) / 20, eye["r"] - r - 1))
            x = cx + math.cos(angle) * move
            y = cy + math.sin(angle) * move
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("black"))
            painter.drawEllipse(QPointF(x, y), r, r)
            painter.setBrush(QColor("white"))
            painter.drawEllipse(QPointF(x - r * 0.35, y - r * 0.35), r * 0.25, r * 0.25)

        if self.tongue_line:
            mx, my, tx, ty = self.tongue_line
            painter.setPen(QPen(QColor("#e0607e"), max(2, 6 * self.size), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(mx, my), QPointF(tx, ty))
            tip = 7 * (0.4 + 0.6 * self.size)
            painter.setPen(QPen(QColor("#a03050"), 1))
            painter.setBrush(QColor("#e0607e"))
            painter.drawEllipse(QPointF(tx, ty), tip, tip)

        for e in self.effects:
            s = e["scale"]
            if e["kind"] == "heart":
                painter.setPen(QPen(QColor("#8a0f22"), 2))
                painter.setBrush(QColor("#e8304a"))
                painter.drawPolygon(QPolygonF([QPointF(e["x"] + hx * s, e["y"] + hy * s) for hx, hy in HEART]))
            else:
                painter.setPen(QPen(QColor("#3b6fd6"), 4))
                z = [(0, 0), (10, 0), (0, 10), (10, 10)]
                painter.drawPolyline(QPolygonF([QPointF(e["x"] + zx * s, e["y"] + zy * s) for zx, zy in z]))


app = QApplication(sys.argv)
pet = Pet()
pet.show()
sys.exit(app.exec())