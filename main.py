"""
ASHFALL  -  a top-down fantasy action-adventure RPG made with Pygame.

Run with:   python ashfall.py
Requires:   pygame 2.x   (pip install pygame)

CONTROLS
  WASD / Arrows   move                 Mouse       aim
  Left click      use selected item    Right click quick-draw bow (hold)
  Shift / Space   dash (blink with the Null Compass)
  R               relic ability (Frost Nova: Mirrorstep Charm + a staff)
  E               interact / talk      Q           drink a potion
  1-9 / wheel     choose hotbar slot   I / Tab     inventory & relics
  J               quest journal        ESC         pause / back
  F5 / F9         quick save / load
"""
import asyncio
import json
import math
import os
import random

import traceback

import pygame

# ============================================================
# CONSTANTS
# ============================================================

WIDTH, HEIGHT = 960, 640
FPS = 60
TILE = 32
SAVE_VERSION = 3
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(BASE_DIR, "ashfall_save.json")
LEGACY_SAVE_FILE = os.path.join(BASE_DIR, "ashfall2_save.json")
ERROR_LOG = os.path.join(BASE_DIR, "ashfall_errors.log")

V = pygame.Vector2

WHITE = (242, 240, 224)
BLACK = (8, 9, 13)
DARK = (16, 18, 24)
UI_BG = (20, 22, 30)
UI_BG2 = (31, 34, 45)
EDGE = (76, 83, 97)
RED = (211, 72, 78)
GREEN = (83, 199, 121)
BLUE = (82, 159, 225)
ICE = (165, 225, 255)
GOLD = (239, 190, 70)
EMBER = (232, 105, 59)
ORANGE = (255, 140, 40)
PURPLE = (155, 94, 211)
ASH = (145, 148, 158)
PARCHMENT = (226, 207, 160)
INK = (62, 44, 30)

# Realm ids. Ids are fixed; the travel order is PROGRESSION.
EMBER_ID, FROZEN_ID, STARFALL_ID, VOID_ID = 0, 1, 2, 3
REALM_NAMES = ["EMBER REALM", "FROZEN REALM", "STARFALL REALM", "VOID REALM"]
REALM_SHORT = ["Ember", "Frozen", "Starfall", "Void"]
REALM_COLORS = [EMBER, BLUE, GOLD, PURPLE]
PROGRESSION = [EMBER_ID, FROZEN_ID, VOID_ID, STARFALL_ID]
REALM_DIFFICULTY = {EMBER_ID: 1.0, FROZEN_ID: 1.7, VOID_ID: 2.5, STARFALL_ID: 3.5}
GOLD_RATE = 0.4   # global multiplier on every gold reward
REALM_RECOMMENDED_LEVEL = {EMBER_ID: 8, FROZEN_ID: 20, VOID_ID: 28, STARFALL_ID: 36}

# Boss tuning.  (hp multiplier, damage multiplier, attack-rate multiplier, extra-attack level)
# THREAT = base hp x hp_mult x dmg_mult x rate_mult.  The ordering is enforced by test_balance.py:
#   Ember realm < Frozen realm < Void realm < Starfall realm < Ember secret < Frozen secret < Void secret < Starfall secret
REALM_BOSS_TUNE = {EMBER_ID: (1.35, 1.0, 1.10, 1), FROZEN_ID: (1.8, 1.45, 1.20, 1),
                   VOID_ID: (2.3, 2.0, 1.30, 2), STARFALL_ID: (2.9, 2.6, 1.40, 3)}
SECRET_BOSS_TUNE = {EMBER_ID: (2.0, 3.0, 1.50, 2), FROZEN_ID: (2.1, 3.6, 1.55, 2),
                    VOID_ID: (2.2, 4.2, 1.60, 3), STARFALL_ID: (2.3, 4.8, 1.70, 3)}
REALM_BOSS_BASE_HP = {EMBER_ID: 1700, FROZEN_ID: 2300, VOID_ID: 2800, STARFALL_ID: 3300}
SECRET_BOSS_BASE_HP = {EMBER_ID: 6000, FROZEN_ID: 6500, VOID_ID: 8000, STARFALL_ID: 9500}
MAX_HIT_FRACTION = 0.45   # no single hit can take more than this share of max HP


def boss_threat(base_hp, tune):
    return base_hp * tune[0] * tune[1] * tune[2]


# Game states
MENU, PLAYING, DIALOGUE, PAUSE, DEAD, SHOP, INVENTORY, BOOK, JOURNAL, ARCADE, VICTORY = range(11)


# ============================================================
# HELPERS
# ============================================================

def clamp(value, lo, hi):
    return lo if value < lo else hi if value > hi else value


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def from_angle(angle, length=1.0):
    return V(math.cos(angle) * length, math.sin(angle) * length)


def angle_to(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def angle_diff(a, b):
    d = (a - b + math.pi) % math.tau - math.pi
    return abs(d)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = clamp(t, 0, 1)
    return (int(c1[0] + (c2[0] - c1[0]) * t), int(c1[1] + (c2[1] - c1[1]) * t), int(c1[2] + (c2[2] - c1[2]) * t))


def point_segment_distance(p, a, b):
    ab = V(b) - V(a)
    if ab.length_squared() == 0:
        return dist(p, a)
    t = clamp((V(p) - V(a)).dot(ab) / ab.length_squared(), 0, 1)
    return dist(p, V(a) + ab * t)


def ipos(p):
    return int(p[0]), int(p[1])


def log_error(context):
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {context} ---\n")
            fh.write(traceback.format_exc())
    except Exception:
        pass


# ============================================================
# TEXT / DRAWING
# ============================================================

_fonts = {}
_text_cache = {}


def get_font(size):
    f = _fonts.get(size)
    if f is None:
        f = pygame.font.Font(None, size)
        _fonts[size] = f
    return f


def render_text(text, size, color):
    key = (text, size, color)
    img = _text_cache.get(key)
    if img is None:
        if len(_text_cache) > 1500:
            _text_cache.clear()
        img = get_font(size).render(str(text), True, color)
        _text_cache[key] = img
    return img


def draw_text(surf, text, pos, color=WHITE, size=20, center=False, right=False, shadow=True):
    text = str(text)
    img = render_text(text, size, color)
    x, y = int(pos[0]), int(pos[1])
    if center:
        x -= img.get_width() // 2
    elif right:
        x -= img.get_width()
    if shadow:
        surf.blit(render_text(text, size, (0, 0, 0)), (x + 1, y + 1))
    surf.blit(img, (x, y))
    return img.get_width()


def wrap_text(text, size, width):
    font = get_font(size)
    lines = []
    for paragraph in str(text).split("\n"):
        current = ""
        for word in paragraph.split():
            test = (current + " " + word).strip()
            if font.size(test)[0] > width and current:
                lines.append(current)
                current = word
            else:
                current = test
        lines.append(current)
    return lines


_alpha_cache = {}


def alpha_rect(surf, rect, color, alpha):
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return
    key = (rect.width, rect.height, color, alpha)
    img = _alpha_cache.get(key)
    if img is None:
        if len(_alpha_cache) > 200:
            _alpha_cache.clear()
        img = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        img.fill((*color, alpha))
        _alpha_cache[key] = img
    surf.blit(img, rect.topleft)


def panel(surf, rect, border=EDGE, fill=UI_BG, alpha=235, width=2):
    alpha_rect(surf, rect, fill, alpha)
    pygame.draw.rect(surf, border, rect, width)


_glow_cache = {}


def glow(surf, pos, radius, color, strength=90):
    radius = max(2, int(radius))
    key = (radius, color, strength)
    img = _glow_cache.get(key)
    if img is None:
        if len(_glow_cache) > 300:
            _glow_cache.clear()
        img = pygame.Surface((radius * 2, radius * 2))
        img.fill((0, 0, 0))
        for i in range(6, 0, -1):
            r = int(radius * i / 6)
            k = strength / 255.0 * (1 - i / 7) * 0.5
            pygame.draw.circle(img, (int(color[0] * k), int(color[1] * k), int(color[2] * k)), (radius, radius), r)
        _glow_cache[key] = img
    surf.blit(img, (int(pos[0]) - radius, int(pos[1]) - radius), special_flags=pygame.BLEND_ADD)


def dashed_circle(surf, color, center, radius, width=2, segments=18, phase=0.0):
    for i in range(segments):
        if i % 2:
            continue
        a0 = phase + i * math.tau / segments
        a1 = phase + (i + 1) * math.tau / segments
        rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        rect.center = ipos(center)
        if radius > 2:
            pygame.draw.arc(surf, color, rect, -a1, -a0, width)


# ============================================================
# PARTICLES / FLOATING TEXT
# ============================================================

class Particle:
    __slots__ = ("pos", "vel", "color", "life", "max_life", "size", "gravity", "drag")

    def __init__(self, pos, vel, color, life=0.5, size=3, gravity=0.0, drag=0.0):
        self.pos = V(pos)
        self.vel = V(vel)
        self.color = color
        self.life = life
        self.max_life = max(0.01, life)
        self.size = size
        self.gravity = gravity
        self.drag = drag

    def update(self, dt):
        self.vel.y += self.gravity * dt
        if self.drag:
            self.vel *= max(0.0, 1 - self.drag * dt)
        self.pos += self.vel * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf, cam):
        s = max(1, int(self.size * self.life / self.max_life))
        pygame.draw.rect(surf, self.color, (int(self.pos.x - cam.x) - s, int(self.pos.y - cam.y) - s, s * 2, s * 2))


class FloatText:
    __slots__ = ("pos", "text", "color", "life", "size")

    def __init__(self, pos, text, color=WHITE, life=1.0, size=18):
        self.pos = V(pos)
        self.text = str(text)
        self.color = color
        self.life = life
        self.size = size

    def update(self, dt):
        self.pos.y -= 30 * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf, cam):
        draw_text(surf, self.text, (self.pos.x - cam.x, self.pos.y - cam.y), self.color, self.size, center=True)


# ============================================================
# ITEMS
# ============================================================

WEAPON_KINDS = ("sword", "greatsword", "bow", "staff")
STACKABLE = ("potion", "material", "food")
EFFECT_NAMES = {
    "burn": "Burning hits", "slow": "Chilling hits", "void": "Void hits (blinks foes)",
    "star": "Radiant hits", "heal": "Restores 60 HP (less if chained, 6s cooldown)", "regen": "Regenerate 6 HP/s for 30s",
    "might": "+20% damage for 60s", "hearty": "+40 max HP for 90s", "swift": "+15% speed for 60s",
}
RARITY_COLORS = {"Common": ASH, "Rare": BLUE, "Epic": PURPLE, "Legendary": GOLD}


class Item:
    def __init__(self, name, kind, power=0, effect=None, stack=1, value=None, desc=""):
        self.name = name
        self.kind = kind
        self.power = int(power)
        self.effect = effect
        self.stack = max(1, int(stack))
        self.value = int(value) if value is not None else self.default_value()
        self.desc = desc

    def default_value(self):
        if self.kind == "potion":
            return 25
        if self.kind == "food":
            return 30
        if self.kind == "material":
            return 40 + self.power * 6
        return 30 + self.power * 14

    @property
    def rarity(self):
        if self.kind in STACKABLE:
            return "Common" if self.power < 30 else "Epic" if self.power < 50 else "Legendary"
        if self.power >= 50:
            return "Legendary"
        if self.power >= 34:
            return "Epic"
        if self.power >= 18:
            return "Rare"
        return "Common"

    @property
    def color(self):
        if self.kind == "potion":
            return GREEN
        if self.kind == "food":
            return ORANGE
        return RARITY_COLORS[self.rarity]

    @property
    def is_weapon(self):
        return self.kind in WEAPON_KINDS

    def stat_line(self):
        if self.is_weapon:
            return f"{self.rarity} {self.kind} - Power {self.power}"
        if self.kind == "armor":
            return f"{self.rarity} armor - Defense {self.power}"
        if self.kind in ("potion", "food"):
            return EFFECT_NAMES.get(self.effect, "Consumable")
        return f"{self.rarity} material"

    def copy(self, stack=None):
        return Item(self.name, self.kind, self.power, self.effect, self.stack if stack is None else stack, self.value, self.desc)

    def to_dict(self):
        return {"name": self.name, "kind": self.kind, "power": self.power, "effect": self.effect,
                "stack": self.stack, "value": self.value, "desc": self.desc}

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict):
            return None
        kind = d.get("kind", "material")
        if kind not in WEAPON_KINDS + STACKABLE + ("armor",):
            kind = "material"
        return Item(str(d.get("name", "Item")), kind, int(d.get("power", 0) or 0), d.get("effect"),
                    int(d.get("stack", 1) or 1), d.get("value"), str(d.get("desc", "") or ""))


def potion(stack=1):
    return Item("Health Potion", "potion", 0, "heal", stack, 25, "A bitter herbal brew.")


# name, kind, power, effect
REALM_KITS = {
    EMBER_ID: [("Ember Blade", "sword", 22, "burn"), ("Ember Bow", "bow", 22, "burn"),
               ("Ember Staff", "staff", 23, "burn"), ("Ember Armor", "armor", 20, None)],
    FROZEN_ID: [("Frozen Blade", "sword", 31, "slow"), ("Frozen Bow", "bow", 31, "slow"),
                ("Frozen Staff", "staff", 32, "slow"), ("Frozen Armor", "armor", 28, None)],
    VOID_ID: [("Void Blade", "sword", 40, "void"), ("Void Bow", "bow", 40, "void"),
              ("Void Staff", "staff", 41, "void"), ("Void Armor", "armor", 36, None)],
    STARFALL_ID: [("Starfall Blade", "sword", 50, "star"), ("Starfall Bow", "bow", 50, "star"),
                  ("Starfall Staff", "staff", 52, "star"), ("Starfall Armor", "armor", 45, None)],
}

DUNGEON_KITS = {
    2: [("Graveborn Sabre", "sword", 20, None), ("Graveborn Mail", "armor", 18, None)],
    4: [("Dread Knight Greatsword", "greatsword", 31, None), ("Dread Knight Plate", "armor", 27, None)],
    6: [("Molten Longbow", "bow", 40, None), ("Molten Carapace", "armor", 35, None)],
    8: [("Cathedral Warstaff", "staff", 50, None), ("Cathedral Vestments", "armor", 43, None)],
    10: [("Last Star Edge", "sword", 60, None), ("Last Star Bulwark", "armor", 52, None)],
}

SECRET_MERCHANT_STOCK = {
    EMBER_ID: [("Hermit's Forgehammer", "greatsword", 36, "burn", 1900), ("Cinderweave Cloak", "armor", 30, None, 1750)],
    FROZEN_ID: [("Scribe's Glass Staff", "staff", 42, "slow", 2400), ("Mirrorplate", "armor", 37, None, 2300)],
    VOID_ID: [("Null-Edge", "sword", 50, "void", 3200), ("Signal Longbow", "bow", 50, "void", 3200)],
    STARFALL_ID: [("Cartographer's Star Bow", "bow", 60, "star", 4200), ("Celestial Aegis", "armor", 52, None, 4100)],
}


def kit_item(entry):
    name, kind, power, effect = entry[:4]
    return Item(name, kind, power, effect)


# ============================================================
# RELICS
# ============================================================

RELICS = {
    "cinderheart": {"name": "Cinderheart Sigil", "color": ORANGE, "major": True, "source": "Ashen Behemoth (Ember)",
                    "desc": "Swords and greatswords blaze orange-red and set foes on fire. You cannot be set ablaze and take half damage from fire."},
    "mirrorstep": {"name": "Mirrorstep Charm", "color": ICE, "major": True, "source": "Mirror Warden (Frozen)",
                   "desc": "+18% move speed, immune to slows and slippery ice. Staves glow light blue and gain FROST NOVA (R): freezes nearby foes. 12s cooldown."},
    "nullcompass": {"name": "Null Compass", "color": PURPLE, "major": True, "source": "Null Maw (Void)",
                    "desc": "+10% move speed. Your dash becomes a purple BLINK that teleports you forward through enemies."},
    "starlens": {"name": "Falling-Star Lens", "color": GOLD, "major": True, "source": "Astral Clockwork (Starfall)",
                 "desc": "Bows and staves fire faster golden projectiles that pierce through up to four foes."},
    "bellchime": {"name": "Bellkeeper's Chime", "color": EMBER, "major": False, "source": "Cinder Bell Grove treasure",
                  "desc": "+8% gold from defeated foes."},
    "mirrorcrown": {"name": "Mirror Crown Shard", "color": BLUE, "major": False, "source": "Mirror Lake treasure",
                    "desc": "+12 maximum health."},
    "vaultkey": {"name": "Null Vault Key", "color": PURPLE, "major": False, "source": "Null Station Vault treasure",
                 "desc": "Health regenerates 50% faster."},
    "constellation": {"name": "Constellation Shard", "color": GOLD, "major": False, "source": "Fallen Constellation treasure",
                      "desc": "+5% damage with every weapon."},
    "arcadestar": {"name": "Arcade Star Pin", "color": GREEN, "major": False, "source": "Milo's arcade (gold medal)",
                   "desc": "Dash cooldown reduced by 12%."},
}
REALM_MAJOR_RELIC = {EMBER_ID: "cinderheart", FROZEN_ID: "mirrorstep", VOID_ID: "nullcompass", STARFALL_ID: "starlens"}
REALM_TREASURE_RELIC = {EMBER_ID: "bellchime", FROZEN_ID: "mirrorcrown", VOID_ID: "vaultkey", STARFALL_ID: "constellation"}
TREASURE_MAPS = {EMBER_ID: "Cinder Bell Map", FROZEN_ID: "Mirror Lake Map", VOID_ID: "Null Station Map", STARFALL_ID: "Fallen Constellation Map"}


# ============================================================
# INVENTORY
# ============================================================

class Inventory:
    SIZE = 27
    HOTBAR = 9

    def __init__(self):
        self.slots = [None] * self.SIZE
        self.selected = 0
        self.armor = None

    def add(self, item):
        if item is None:
            return True
        if item.kind in STACKABLE:
            for existing in self.slots:
                if existing and existing.name == item.name and existing.kind == item.kind:
                    existing.stack += item.stack
                    return True
        for i, existing in enumerate(self.slots):
            if existing is None:
                self.slots[i] = item
                return True
        return False

    def free_slots(self):
        return sum(1 for s in self.slots if s is None)

    def selected_item(self):
        return self.slots[self.selected]

    def select(self, index):
        self.selected = int(clamp(index, 0, self.HOTBAR - 1))

    def count(self, kind=None, name=None):
        total = 0
        for item in self.slots:
            if item and (kind is None or item.kind == kind) and (name is None or item.name == name):
                total += item.stack
        return total

    def take_one(self, kind=None, name=None):
        # Prefer non-hotbar stacks so the hotbar stays stable.
        order = list(range(self.HOTBAR, self.SIZE)) + list(range(self.HOTBAR))
        for i in order:
            item = self.slots[i]
            if item and (kind is None or item.kind == kind) and (name is None or item.name == name):
                item.stack -= 1
                if item.stack <= 0:
                    self.slots[i] = None
                return True
        return False

    def first_of_kind(self, kind):
        for i in range(self.SIZE):
            item = self.slots[i]
            if item and item.kind == kind:
                return item
        return None


# ============================================================
# ICONS (procedural)
# ============================================================

def draw_item_icon(surf, item, rect):
    rect = pygame.Rect(rect)
    cx, cy = rect.center
    s = min(rect.width, rect.height) / 48.0
    c = item.color
    k = item.kind
    if k == "sword":
        pygame.draw.line(surf, (215, 220, 230), (cx - 12 * s, cy + 12 * s), (cx + 12 * s, cy - 12 * s), max(2, int(4 * s)))
        pygame.draw.line(surf, c, (cx - 15 * s, cy + 5 * s), (cx - 5 * s, cy + 15 * s), max(2, int(4 * s)))
        pygame.draw.line(surf, (110, 80, 50), (cx - 12 * s, cy + 12 * s), (cx - 17 * s, cy + 17 * s), max(2, int(4 * s)))
    elif k == "greatsword":
        pygame.draw.line(surf, (200, 205, 215), (cx - 13 * s, cy + 13 * s), (cx + 15 * s, cy - 15 * s), max(3, int(7 * s)))
        pygame.draw.line(surf, c, (cx - 17 * s, cy + 5 * s), (cx - 5 * s, cy + 17 * s), max(2, int(5 * s)))
    elif k == "bow":
        pygame.draw.arc(surf, (160, 110, 60), (cx - 16 * s, cy - 16 * s, 26 * s, 32 * s), -1.4, 1.4, max(2, int(4 * s)))
        pygame.draw.line(surf, c, (cx + 1 * s, cy - 15 * s), (cx + 1 * s, cy + 15 * s), max(1, int(2 * s)))
    elif k == "staff":
        pygame.draw.line(surf, (130, 95, 60), (cx - 10 * s, cy + 16 * s), (cx + 8 * s, cy - 10 * s), max(2, int(4 * s)))
        pygame.draw.circle(surf, c, (int(cx + 10 * s), int(cy - 12 * s)), max(3, int(6 * s)))
    elif k == "armor":
        pts = [(cx - 14 * s, cy - 12 * s), (cx + 14 * s, cy - 12 * s), (cx + 11 * s, cy + 14 * s), (cx - 11 * s, cy + 14 * s)]
        pygame.draw.polygon(surf, (70, 75, 88), pts)
        pygame.draw.polygon(surf, c, pts, max(2, int(3 * s)))
    elif k == "potion":
        pygame.draw.rect(surf, (210, 225, 215), (cx - 4 * s, cy - 15 * s, 8 * s, 7 * s))
        pygame.draw.circle(surf, GREEN, (int(cx), int(cy + 4 * s)), max(4, int(11 * s)))
        pygame.draw.circle(surf, (190, 255, 210), (int(cx - 4 * s), int(cy)), max(1, int(3 * s)))
    elif k == "food":
        pygame.draw.ellipse(surf, (120, 80, 50), (cx - 15 * s, cy - 2 * s, 30 * s, 14 * s))
        pygame.draw.ellipse(surf, ORANGE, (cx - 12 * s, cy - 8 * s, 24 * s, 12 * s))
    else:
        pygame.draw.polygon(surf, c, [(cx, cy - 14 * s), (cx + 11 * s, cy), (cx, cy + 14 * s), (cx - 11 * s, cy)])
        pygame.draw.polygon(surf, WHITE, [(cx, cy - 6 * s), (cx + 4 * s, cy), (cx, cy + 6 * s), (cx - 4 * s, cy)])


def draw_relic_icon(surf, key, rect, dim=False):
    rect = pygame.Rect(rect)
    data = RELICS.get(key)
    if not data:
        return
    c = data["color"] if not dim else mix(data["color"], (40, 40, 50), 0.6)
    cx, cy = rect.center
    r = min(rect.width, rect.height) // 2 - 6
    if key == "cinderheart":
        pygame.draw.polygon(surf, c, [(cx, cy - r), (cx + r * .7, cy), (cx, cy + r), (cx - r * .7, cy)])
        pygame.draw.circle(surf, (255, 220, 120), (cx, cy), max(2, r // 3))
    elif key == "mirrorstep":
        pygame.draw.circle(surf, c, (cx, cy), r, 3)
        pygame.draw.line(surf, WHITE, (cx - r * .5, cy + r * .5), (cx + r * .5, cy - r * .5), 2)
    elif key == "nullcompass":
        pygame.draw.circle(surf, c, (cx, cy), r, 3)
        pygame.draw.polygon(surf, WHITE, [(cx, cy - r + 3), (cx + 4, cy), (cx, cy + r - 3), (cx - 4, cy)])
    elif key == "starlens":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * .45
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(surf, c, pts)
    else:
        pygame.draw.circle(surf, c, (cx, cy), r)
        pygame.draw.circle(surf, WHITE, (cx, cy), max(2, r // 3), 2)


# ============================================================
# SHARED CIRCLE CACHE (translucent fills)
# ============================================================

_circle_cache = {}


def alpha_circle(surf, center, radius, color, alpha):
    radius = int(radius)
    if radius <= 0:
        return
    alpha = int(clamp(alpha, 0, 255)) // 8 * 8
    key = (radius, color, alpha)
    img = _circle_cache.get(key)
    if img is None:
        if len(_circle_cache) > 400:
            _circle_cache.clear()
        img = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(img, (*color, alpha), (radius + 1, radius + 1), radius)
        _circle_cache[key] = img
    surf.blit(img, (int(center[0]) - radius - 1, int(center[1]) - radius - 1))


# ============================================================
# PROJECTILES
# ============================================================

class Projectile:
    def __init__(self, pos, vel, damage, owner="enemy", radius=6, color=EMBER, life=2.5, effect=None,
                 pierce=0, element=None, kind="orb", homing=0.0, bounces=0, trail=None, knock=60):
        self.pos = V(pos)
        self.vel = V(vel)
        self.damage = damage
        self.owner = owner
        self.radius = radius
        self.color = color
        self.life = life
        self.effect = effect
        self.pierce = pierce
        self.element = element
        self.kind = kind
        self.homing = homing
        self.bounces = bounces
        self.trail = trail
        self.knock = knock
        self.hit = set()
        self.anim = random.random() * 6

    def update(self, dt, scene):
        self.anim += dt
        self.life -= dt
        if self.life <= 0:
            return False
        if self.homing and self.owner == "enemy":
            desired = angle_to(self.pos, game.player.pos)
            current = math.atan2(self.vel.y, self.vel.x)
            delta = (desired - current + math.pi) % math.tau - math.pi
            current += clamp(delta, -self.homing * dt, self.homing * dt)
            self.vel = from_angle(current, self.vel.length())
        nxt = self.pos + self.vel * dt
        if scene.blocks_projectile(nxt):
            if self.bounces > 0:
                self.bounces -= 1
                if scene.blocks_projectile(V(nxt.x, self.pos.y)):
                    self.vel.x *= -1
                if scene.blocks_projectile(V(self.pos.x, nxt.y)):
                    self.vel.y *= -1
                return True
            burst(self.pos, self.color, 4, (20, 80), .25, 2)
            return False
        self.pos = nxt
        if self.trail and random.random() < .6:
            game.particles.append(Particle(self.pos, -self.vel * .05, self.trail, .3, 2))
        if self.owner == "player":
            for target in scene.targets():
                if not target.alive or id(target) in self.hit:
                    continue
                if dist(self.pos, target.pos) < self.radius + target.radius:
                    self.hit.add(id(target))
                    knock = self.vel.normalize() * self.knock if self.vel.length() else None
                    target.take_damage(self.damage, self.effect, knock)
                    if self.pierce <= 0:
                        return False
                    self.pierce -= 1
            if hasattr(scene, "projectile_hits_object") and scene.projectile_hits_object(self):
                return False
        else:
            p = game.player
            if dist(self.pos, p.pos) < self.radius + p.RADIUS:
                p.take_damage(self.damage, self.element)
                if self.effect == "burn":
                    p.apply_burn(2.0)
                elif self.effect == "freeze":
                    p.apply_freeze(0.9)
                elif self.effect == "slow":
                    p.apply_slow(1.6)
                return False
        return True

    def draw(self, surf, cam):
        x, y = self.pos.x - cam.x, self.pos.y - cam.y
        if self.kind == "arrow":
            d = self.vel.normalize() if self.vel.length() else V(1, 0)
            tail = V(x, y) - d * 16
            if self.color == GOLD:
                glow(surf, (x, y), 14, GOLD, 120)
            pygame.draw.line(surf, self.color, ipos(tail), (int(x), int(y)), 3)
            pygame.draw.circle(surf, WHITE, (int(x), int(y)), 2)
        elif self.kind == "shard":
            d = self.vel.normalize() if self.vel.length() else V(1, 0)
            side = V(-d.y, d.x)
            pts = [V(x, y) + d * self.radius * 1.6, V(x, y) + side * self.radius * .6, V(x, y) - d * self.radius, V(x, y) - side * self.radius * .6]
            pygame.draw.polygon(surf, self.color, [ipos(p) for p in pts])
            pygame.draw.polygon(surf, WHITE, [ipos(p) for p in pts], 1)
        else:
            pulse = math.sin(self.anim * 14) * 1.5
            if self.owner == "player":
                glow(surf, (x, y), self.radius * 2.6, self.color, 110)
            pygame.draw.circle(surf, self.color, (int(x), int(y)), int(self.radius + pulse))
            pygame.draw.circle(surf, WHITE, (int(x), int(y)), max(2, self.radius // 3))
            if self.effect == "burn":
                pygame.draw.circle(surf, GOLD, (int(x), int(y)), int(self.radius + 3), 1)
            elif self.effect in ("freeze", "slow"):
                pygame.draw.circle(surf, ICE, (int(x), int(y)), int(self.radius + 3), 1)


def burst(pos, color, n=10, speed=(40, 140), life=.5, size=3, gravity=0):
    if len(game.particles) > 1400:
        return
    for _ in range(n):
        game.particles.append(Particle(pos, from_angle(random.random() * math.tau, random.uniform(*speed)), color, life * random.uniform(.6, 1.2), size, gravity))


# ============================================================
# TELEGRAPHED HAZARDS
# ============================================================

class Hazard:
    """A warned area of danger. shape: circle / ring / line / rect."""

    def __init__(self, pos, radius=40, warn=.8, active=.35, damage=20, color=RED, shape="circle",
                 element=None, effect=None, end=None, width=30, inner=0, tick=.5, label=None, rect=None):
        ctx = getattr(game, "boss_ctx", None)
        if ctx is not None:
            damage = max(1, int(damage * ctx.dmg_mult)) if damage > 0 else damage
            warn = max(.55, warn / (1 + (ctx.rate - 1) * .5))
        self.pos = V(pos)
        self.radius = radius
        self.warn = warn
        self.active = active
        self.damage = damage
        self.color = color
        self.shape = shape
        self.element = element
        self.effect = effect
        self.end = V(end) if end is not None else None
        self.width = width
        self.inner = inner
        self.tick = tick
        self.label = label
        self.rect = pygame.Rect(rect) if rect is not None else None
        self.t = 0.0
        self.cool = 0.0
        self.alive = True

    @property
    def is_active(self):
        return self.warn <= self.t < self.warn + self.active

    def contains(self, p, pad=0):
        if self.shape == "circle":
            return dist(p, self.pos) < self.radius + pad
        if self.shape == "ring":
            d = dist(p, self.pos)
            return self.inner - pad <= d <= self.radius + pad
        if self.shape == "line":
            return point_segment_distance(p, self.pos, self.end) < self.width / 2 + pad
        if self.shape == "rect":
            return self.rect.inflate(pad * 2, pad * 2).collidepoint(p)
        return False

    def update(self, dt):
        self.t += dt
        self.cool -= dt
        if self.t >= self.warn + self.active:
            self.alive = False
            return False
        if self.damage > 0 and self.is_active and self.cool <= 0 and self.contains(game.player.pos, game.player.RADIUS * .6):
            self.cool = self.tick
            game.player.take_damage(self.damage, self.element)
            if self.effect == "burn":
                game.player.apply_burn(2.0)
            elif self.effect == "freeze":
                game.player.apply_freeze(1.0)
            elif self.effect == "slow":
                game.player.apply_slow(1.5)
        return True

    def draw(self, surf, cam):
        p = self.pos - cam
        warning = self.t < self.warn
        frac = clamp(self.t / max(.01, self.warn), 0, 1)
        if self.shape == "circle":
            if warning:
                alpha_circle(surf, p, self.radius, self.color, 25 + 45 * frac)
                pygame.draw.circle(surf, self.color, ipos(p), int(self.radius), 2)
                pygame.draw.circle(surf, self.color, ipos(p), max(1, int(self.radius * frac)), 1)
            else:
                alpha_circle(surf, p, self.radius, self.color, 105)
                pygame.draw.circle(surf, mix(self.color, WHITE, .5), ipos(p), int(self.radius), 2)
        elif self.shape == "ring":
            col = self.color
            if warning:
                pygame.draw.circle(surf, col, ipos(p), int(self.radius), 1)
                if self.inner > 2:
                    pygame.draw.circle(surf, col, ipos(p), int(self.inner), 1)
            else:
                w = max(2, int(self.radius - self.inner))
                pygame.draw.circle(surf, col, ipos(p), int(self.radius), w)
                pygame.draw.circle(surf, WHITE, ipos(p), int(self.radius), 2)
        elif self.shape == "line":
            e = self.end - cam
            if warning:
                pygame.draw.line(surf, self.color, ipos(p), ipos(e), max(1, int(self.width * .25 * frac) + 1))
            else:
                pygame.draw.line(surf, self.color, ipos(p), ipos(e), int(self.width))
                pygame.draw.line(surf, WHITE, ipos(p), ipos(e), max(2, int(self.width * .3)))
        elif self.shape == "rect":
            r = self.rect.move(-int(cam.x), -int(cam.y))
            if warning:
                alpha_rect(surf, r, self.color, int(30 + 50 * frac))
                pygame.draw.rect(surf, self.color, r, 2)
            else:
                alpha_rect(surf, r, self.color, 150)
                pygame.draw.rect(surf, WHITE, r, 2)
        if self.label and warning:
            draw_text(surf, self.label, (p.x, p.y - 8), WHITE, 16, center=True)


# ============================================================
# LOOT
# ============================================================

class Loot:
    def __init__(self, pos, kind, amount=1):
        self.pos = V(pos) + V(random.uniform(-10, 10), random.uniform(-10, 10))
        self.kind = kind
        self.amount = amount
        self.anim = random.random() * 6
        self.alive = True
        self.age = 0

    def update(self, dt):
        self.anim += dt * 5
        self.age += dt
        p = game.player
        d = dist(self.pos, p.pos)
        if d < 110 and self.age > .25:
            self.pos += (p.pos - self.pos).normalize() * min(d, 360 * dt) if d > 1 else V()
        if d < 22:
            self.alive = False
            if self.kind == "gold":
                p.gold += self.amount
                game.float_text(self.pos, f"+{self.amount}g", GOLD, size=16)
            elif self.kind == "potion":
                if p.inv.add(potion()):
                    game.float_text(self.pos, "+Potion", GREEN)
                else:
                    p.gold += 5
                    game.float_text(self.pos, "Bag full +5g", GOLD)
            elif self.kind == "ember":
                p.embers += self.amount
                game.float_text(self.pos, f"+{self.amount} ember", EMBER)
            elif self.kind == "heart":
                p.heal(25)
            game.sound("pickup")
            burst(self.pos, GOLD if self.kind == "gold" else GREEN if self.kind in ("potion", "heart") else EMBER, 6, (30, 90), .3, 2)
        return self.alive and self.age < 60

    def draw(self, surf, cam):
        x, y = int(self.pos.x - cam.x), int(self.pos.y - cam.y + math.sin(self.anim) * 3)
        if self.kind == "gold":
            pygame.draw.circle(surf, GOLD, (x, y), 6)
            pygame.draw.circle(surf, (255, 235, 140), (x - 2, y - 2), 2)
        elif self.kind == "potion":
            pygame.draw.rect(surf, (210, 225, 215), (x - 3, y - 10, 6, 4))
            pygame.draw.circle(surf, GREEN, (x, y), 7)
        elif self.kind == "heart":
            pygame.draw.circle(surf, RED, (x - 3, y - 2), 4)
            pygame.draw.circle(surf, RED, (x + 3, y - 2), 4)
            pygame.draw.polygon(surf, RED, [(x - 7, y), (x + 7, y), (x, y + 7)])
        else:
            pygame.draw.polygon(surf, EMBER, [(x, y - 8), (x + 6, y), (x, y + 8), (x - 6, y)])
            pygame.draw.rect(surf, GOLD, (x - 1, y - 4, 3, 8))


# ============================================================
# ENEMIES
# ============================================================

ENEMY_STATS = {
    #           hp  speed dmg  xp  radius ranged  proj_speed  cooldown
    "crawler": (40, 108, 8, 12, 12, 0.25, 270, 1.7),
    "wraith": (54, 84, 10, 18, 13, 0.45, 250, 1.4),
    "brute": (115, 58, 15, 30, 17, 0.15, 230, 1.8),
    "shooter": (46, 70, 11, 20, 13, 1.0, 300, 1.15),
    "mage": (66, 60, 13, 26, 13, 1.0, 215, 1.6),
    "guard": (90, 80, 13, 28, 14, 0.5, 280, 1.3),
    # Detecting drone: shielded, fast, dodges, fires bursts and lasers. Deliberately overpowered.
    "drone": (160, 128, 15, 70, 15, 1.0, 400, 0.75),
}

ELITE_AFFIXES = {
    "swift": ("SWIFT", (120, 230, 255)),
    "armored": ("ARMORED", (190, 190, 205)),
    "regenerating": ("REGENERATING", (110, 230, 130)),
    "volatile": ("VOLATILE", (255, 150, 60)),
    "shielded": ("SHIELDED", (120, 170, 255)),
    "frenzied": ("FRENZIED", (255, 90, 90)),
}


def make_elite(e, affix=None):
    """Turn an enemy into an elite with one random affix (more HP, damage, XP and gold)."""
    if e.is_boss or e.affix:
        return e
    affix = affix or random.choice(list(ELITE_AFFIXES))
    e.affix = affix
    e.max_hp = int(e.max_hp * 2.2)
    e.hp = e.max_hp
    e.damage = int(e.damage * 1.25)
    e.xp = int(e.xp * 3)
    e.radius = int(e.radius * 1.15)
    if affix == "swift":
        e.speed *= 1.45
        e.cooldown *= .75
    elif affix == "armored":
        e.armor_frac = .4
    elif affix == "shielded":
        e.shield_max = e.max_hp * .5
        e.shield = e.shield_max
    elif affix == "frenzied":
        e.damage = int(e.damage * 1.3)
        e.cooldown *= .6
    elif affix == "volatile":
        def boom(en):
            if getattr(game.scene, "hazards", None) is not None:
                game.scene.hazards.append(Hazard(en.pos, 85, .7, .3, max(1, int(en.damage * 1.3)), ORANGE, label="BLAST"))
        prev = e.on_death
        e.on_death = (lambda en, prev=prev: (prev(en) if prev else None, boom(en)))
    return e


class Enemy:
    is_boss = False

    def __init__(self, pos, kind="crawler", scale=1.0, tint=None, aggro=360):
        stats = ENEMY_STATS.get(kind, ENEMY_STATS["crawler"])
        self.kind = kind
        self.pos = V(pos)
        self.home = V(pos)
        self.scale = scale
        self.max_hp = int(stats[0] * scale)
        self.hp = self.max_hp
        self.speed = stats[1] * (1 + .1 * (scale - 1))
        self.damage = max(1, int(stats[2] * scale))
        self.xp = int(stats[3] * (1 + .4 * (scale - 1)))
        self.radius = stats[4]
        self.ranged = random.random() < stats[5]
        self.proj_speed = stats[6] * (1 + .12 * (scale - 1))
        self.cooldown = stats[7] / (1 + .25 * (scale - 1))
        self.tint = tint
        self.aggro = aggro
        self.alive = True
        self.anim = random.random() * 6
        self.flash = 0
        self.atk_cd = random.uniform(.6, 1.6)
        self.contact_cd = 0
        self.knock = V()
        self.burn = 0
        self.burn_tick = 0
        self.slow = 0
        self.freeze = 0
        self.star = 0
        self.star_tick = 0
        self.void_hits = 0
        self.provoked = False
        self.wander_target = V(pos)
        self.wander_timer = random.uniform(0, 3)
        self.gold_mult = 1.0
        self.drops = True
        self.on_death = None
        self.affix = None
        self.armor_frac = 0.0
        self.shield = 0.0
        self.shield_max = 0.0
        self.shield_idle = 0.0
        self.dash_cd = 0.0
        self.volley = 0
        self.name_tag = None
        if kind == "drone":
            self.ranged = True
            self.shield_max = self.max_hp * .6
            self.shield = self.shield_max

    # ---- status ----
    def apply_effect(self, effect, power=1.0):
        if effect == "burn":
            if self.burn <= 0:
                self.burn_tick = .5
            self.burn = max(self.burn, 3.0)
        elif effect == "slow":
            self.slow = max(self.slow, 2.2)
        elif effect == "freeze":
            self.freeze = max(self.freeze, 2.5 * power * (.3 if self.is_boss else 1))
        elif effect == "star":
            self.star = max(self.star, 2.5)
        elif effect == "void":
            self.void_hits += 1
            self.slow = max(self.slow, 1.0)
            if self.void_hits % 3 == 0 and not self.is_boss:
                scene = game.scene
                for _ in range(12):
                    cand = self.pos + from_angle(random.random() * math.tau, random.uniform(90, 170))
                    if not scene.blocked(cand, self.radius) and dist(cand, game.player.pos) > 110:
                        burst(self.pos, PURPLE, 10, (40, 120), .4, 3)
                        self.pos = cand
                        game.float_text(self.pos, "VOID BLINK", PURPLE, size=15)
                        break

    def take_damage(self, amount, effect=None, knock=None):
        if not self.alive:
            return
        amount = max(1, int(amount * (1 - self.armor_frac)))
        self.shield_idle = 0.0
        if self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
            if self.shield <= 0:
                game.float_text(self.pos + V(0, -self.radius - 18), "SHIELD DOWN", ICE, .8, 15)
                burst(self.pos, ICE, 14, (50, 140), .4, 3)
            if amount <= 0:
                self.flash = .12
                self.provoked = True
                game.float_text(self.pos + V(random.uniform(-8, 8), -self.radius - 6), "shield", ICE, .4, 13)
                return
        if self.kind == "drone" and self.dash_cd <= 0 and random.random() < .45 and not self.freeze > 0:
            self.dash_cd = 1.5
            side = from_angle(angle_to(self.pos, game.player.pos) + math.pi / 2 * random.choice((-1, 1)), 80)
            self.pos = game.scene.move(self.pos, side, self.radius)
            burst(self.pos, (90, 240, 255), 8, (40, 120), .3, 2)
        self.hp -= amount
        self.flash = .12
        self.provoked = True
        if knock is not None and not self.is_boss:
            self.knock += V(knock) * (0.6 if self.kind == "brute" else 1.0)
        if effect:
            self.apply_effect(effect)
        game.float_text(self.pos + V(random.uniform(-8, 8), -self.radius - 6), str(amount),
                        ORANGE if effect == "burn" else ICE if effect in ("slow", "freeze") else WHITE, .6, 16)
        if len(game.particles) < 1200:
            burst(self.pos, self.tint or EMBER, 4, (40, 110), .25, 2)
        if self.hp <= 0:
            self.die()

    def die(self):
        if not self.alive:
            return
        self.alive = False
        burst(self.pos, (128, 80, 73), 14, (60, 160), .5, 3, 90)
        game.on_enemy_killed(self)
        if self.on_death:
            self.on_death(self)

    def tick_status(self, dt):
        self.anim += dt
        self.flash = max(0, self.flash - dt)
        self.atk_cd -= dt
        self.contact_cd -= dt
        self.slow = max(0, self.slow - dt)
        self.freeze = max(0, self.freeze - dt)
        self.dash_cd = max(0, self.dash_cd - dt)
        if self.shield_max > 0:
            self.shield_idle += dt
            if self.shield_idle > 3.0 and self.shield < self.shield_max:
                self.shield = min(self.shield_max, self.shield + self.shield_max * .18 * dt)
        if self.affix == "regenerating" and self.hp < self.max_hp:
            self.hp = min(self.max_hp, self.hp + self.max_hp * .03 * dt)
        if self.burn > 0:
            self.burn -= dt
            self.burn_tick -= dt
            if self.burn_tick <= 0:
                self.burn_tick = .5
                self.take_damage(4 + self.max_hp * .012)
                if random.random() < .7:
                    game.particles.append(Particle(self.pos + V(random.uniform(-8, 8), -6), (random.uniform(-15, 15), -50), ORANGE, .4, 3))
        if self.star > 0:
            self.star -= dt
            self.star_tick -= dt
            if self.star_tick <= 0:
                self.star_tick = .6
                self.take_damage(5 + self.max_hp * .01)

    def speed_factor(self):
        if self.freeze > 0:
            return 0.0
        return .5 if self.slow > 0 else 1.0

    def update(self, dt, scene):
        self.tick_status(dt)
        if not self.alive:
            return
        if self.knock.length_squared() > 1:
            self.pos = scene.move(self.pos, self.knock * dt, self.radius)
            self.knock *= max(0, 1 - 8 * dt)
        if self.freeze > 0:
            return
        player = game.player
        d = dist(self.pos, player.pos)
        engaged = d < self.aggro or (self.provoked and d < self.aggro * 2)
        sf = self.speed_factor()
        if engaged:
            to_player = player.pos - self.pos
            direction = to_player.normalize() if to_player.length() > 0 else V()
            if self.kind == "drone":
                if d < 210:
                    direction = -direction
                elif d < 320:
                    direction = V(-direction.y, direction.x) * (1 if int(self.anim * .7) % 2 else -1)
            elif self.kind in ("shooter", "mage") and d < 170:
                direction = -direction  # kite
            elif self.kind in ("shooter", "mage") and d < 240:
                direction = V(-direction.y, direction.x) * (1 if int(self.anim) % 4 < 2 else -1)
            self.pos = scene.move(self.pos, direction * self.speed * sf * dt, self.radius)
            if self.ranged and self.atk_cd <= 0 and d < (520 if self.kind == "drone" else 430) and scene.line_clear(self.pos, player.pos):
                self.shoot(player)
                self.atk_cd = self.cooldown * random.uniform(.85, 1.2)
            if d < self.radius + player.RADIUS + 6 and self.contact_cd <= 0:
                player.take_damage(self.damage)
                self.contact_cd = 1.0
        else:
            self.wander_timer -= dt
            if self.wander_timer <= 0:
                self.wander_timer = random.uniform(2, 4.5)
                self.wander_target = self.home + V(random.uniform(-90, 90), random.uniform(-90, 90))
            delta = self.wander_target - self.pos
            if delta.length() > 6:
                self.pos = scene.move(self.pos, delta.normalize() * self.speed * .35 * sf * dt, self.radius)

    def shoot(self, player):
        base = angle_to(self.pos, player.pos)
        dmg = max(1, int(self.damage * .9))
        col = self.tint or {"mage": BLUE, "shooter": GOLD, "wraith": PURPLE}.get(self.kind, EMBER)
        if self.kind == "drone":
            self.volley += 1
            col = (90, 240, 255)
            for off in (-.14, 0, .14):
                game.enemy_shot(self.pos, base + off, self.proj_speed, dmg, col, 5)
            if self.volley % 3 == 0 and getattr(game.scene, "hazards", None) is not None:
                game.scene.hazards.append(Hazard(self.pos, 0, .75, .35, max(1, int(self.damage * 1.5)), (120, 250, 255), shape="line",
                                                 end=self.pos + from_angle(base, 900), width=34, label="LASER"))
            if self.volley % 5 == 0:
                for i in range(8):
                    game.enemy_shot(self.pos, i * math.tau / 8 + self.anim, self.proj_speed * .55, max(1, dmg // 2), col, 5, life=2.4)
        elif self.kind == "mage":
            game.enemy_shot(self.pos, base, self.proj_speed, dmg, col, 8, homing=.8)
        elif self.kind == "shooter" and self.scale > 1.3:
            for off in (-.12, .12):
                game.enemy_shot(self.pos, base + off, self.proj_speed, dmg, col, 5)
        else:
            game.enemy_shot(self.pos, base, self.proj_speed, dmg, col, 6)

    def draw(self, surf, cam):
        x = int(self.pos.x - cam.x)
        y = int(self.pos.y - cam.y + math.sin(self.anim * 7) * 2)
        if x < -60 or x > WIDTH + 60 or y < -60 or y > HEIGHT + 60:
            return
        pygame.draw.ellipse(surf, (0, 0, 0), (x - self.radius, y + self.radius - 4, self.radius * 2, 8))
        if self.tint:
            pygame.draw.circle(surf, self.tint, (x, y), self.radius + 6, 1)
        k = self.kind
        if k == "crawler":
            pygame.draw.ellipse(surf, (196, 84, 66), (x - 12, y - 7, 24, 15))
            pygame.draw.rect(surf, (75, 38, 42), (x - 9, y - 12, 18, 7))
            for lx in (-10, -4, 4, 10):
                pygame.draw.line(surf, (90, 40, 40), (x + lx, y + 4), (x + lx * 1.3, y + 10), 2)
            pygame.draw.rect(surf, WHITE, (x - 6, y - 10, 3, 3))
            pygame.draw.rect(surf, WHITE, (x + 3, y - 10, 3, 3))
        elif k == "wraith":
            pygame.draw.polygon(surf, (116, 86, 157), [(x, y - 18), (x + 13, y - 2), (x + 9, y + 15), (x, y + 8), (x - 9, y + 15), (x - 13, y - 2)])
            pygame.draw.rect(surf, (218, 201, 240), (x - 7, y - 5, 4, 4))
            pygame.draw.rect(surf, (218, 201, 240), (x + 3, y - 5, 4, 4))
        elif k == "shooter":
            pygame.draw.circle(surf, (206, 150, 54), (x, y), 13)
            pygame.draw.arc(surf, (110, 80, 50), (x + 4, y - 14, 14, 28), -1.4, 1.4, 3)
            pygame.draw.rect(surf, WHITE, (x - 6, y - 5, 4, 4))
            pygame.draw.rect(surf, WHITE, (x + 2, y - 5, 4, 4))
        elif k == "mage":
            pygame.draw.polygon(surf, (77, 120, 201), [(x, y - 22), (x + 14, y + 12), (x - 14, y + 12)])
            pygame.draw.circle(surf, (190, 225, 255), (x, y - 4), 5)
            glow(surf, (x + 12, y - 12), 10, BLUE, 80)
            pygame.draw.circle(surf, ICE, (x + 12, y - 12), 3)
        elif k == "drone":
            bob = int(math.sin(self.anim * 5) * 3)
            pygame.draw.circle(surf, (44, 52, 68), (x, y + bob), 15)
            pygame.draw.circle(surf, (110, 120, 140), (x, y + bob), 15, 2)
            pygame.draw.circle(surf, (20, 22, 30), (x, y + bob), 8)
            eye = from_angle(angle_to(self.pos, game.player.pos), 4)
            pygame.draw.circle(surf, (90, 240, 255), (int(x + eye.x), int(y + bob + eye.y)), 4)
            for kk in (-1, 1):
                pygame.draw.line(surf, (110, 120, 140), (x + kk * 14, y - 3 + bob), (x + kk * 24, y - 9 + bob), 3)
                pygame.draw.circle(surf, (90, 240, 255), (x + kk * 24, y - 9 + bob), 3)
            glow(surf, (x, y + bob), 32, (90, 240, 255), 80)
        elif k == "guard":
            pygame.draw.rect(surf, (90, 96, 110), (x - 11, y - 10, 22, 24))
            pygame.draw.rect(surf, (140, 145, 160), (x - 9, y - 22, 18, 13))
            pygame.draw.rect(surf, RED, (x - 6, y - 17, 12, 3))
            pygame.draw.line(surf, (200, 200, 210), (x + 12, y - 14), (x + 12, y + 12), 3)
        else:  # brute
            pygame.draw.rect(surf, (105, 74, 62), (x - 16, y - 14, 32, 30))
            pygame.draw.rect(surf, (144, 98, 75), (x - 12, y - 23, 24, 11))
            pygame.draw.rect(surf, (42, 33, 36), (x - 8, y - 20, 5, 4))
            pygame.draw.rect(surf, (42, 33, 36), (x + 3, y - 20, 5, 4))
        if self.affix:
            name, col = ELITE_AFFIXES[self.affix]
            pygame.draw.circle(surf, col, (x, y), self.radius + 9, 2)
            pygame.draw.circle(surf, GOLD, (x, y), self.radius + 12, 1)
            draw_text(surf, (self.name_tag + " - " if self.name_tag else "") + name, (x, y - self.radius - 26), col, 13, center=True)
        elif self.name_tag:
            draw_text(surf, self.name_tag, (x, y - self.radius - 26), GOLD, 14, center=True)
        if self.shield > 0:
            alpha_circle(surf, (x, y), self.radius + 7, ICE, 38 + 40 * self.shield / max(1, self.shield_max))
            pygame.draw.circle(surf, ICE, (x, y), self.radius + 7, 1)
        if self.freeze > 0:
            pygame.draw.rect(surf, ICE, (x - self.radius - 3, y - self.radius - 6, self.radius * 2 + 6, self.radius * 2 + 10), 2)
        if self.burn > 0:
            pygame.draw.circle(surf, ORANGE, (x, y), self.radius + 3, 1)
        if self.star > 0:
            pygame.draw.circle(surf, GOLD, (x, y), self.radius + 8, 2)
        if self.flash > 0:
            pygame.draw.circle(surf, WHITE, (x, y), self.radius + 2, 2)
        if self.hp < self.max_hp:
            w = self.radius * 2 + 10
            pygame.draw.rect(surf, (20, 20, 24), (x - w // 2, y - self.radius - 14, w, 5))
            pygame.draw.rect(surf, RED, (x - w // 2 + 1, y - self.radius - 13, int((w - 2) * max(0, self.hp) / self.max_hp), 3))


class Boss(Enemy):
    """Base for every boss. Subclasses implement think(dt, scene) and draw_body()."""
    is_boss = True
    thresholds = (0.66, 0.33)
    phase_names = ()

    def __init__(self, pos, name, hp, radius=40, color=RED, contact=20):
        super().__init__(pos, "brute", 1.0)
        self.name = name
        self.max_hp = int(hp)
        self.hp = self.max_hp
        self.radius = radius
        self.color = color
        self.damage = contact
        self.phase = 1
        self.immune = False
        self.timers = {}
        self.ranged = False
        self.xp = 0
        self.drops = False
        self.intro = 1.2
        self.tuned = False
        self.dmg_mult = 1.0
        self.rate = 1.0
        self.spd_mult = 1.0
        self.extra = 0

    def tune_values(self):
        """(hp, dmg, rate, extra) multipliers, looked up by boss kind. Overridden for dungeon bosses."""
        kind = getattr(self, "boss_kind", "")
        rid = getattr(self, "rid", None)
        if kind == "realm" and rid in REALM_BOSS_TUNE:
            return REALM_BOSS_TUNE[rid]
        if kind == "secret" and rid in SECRET_BOSS_TUNE:
            return SECRET_BOSS_TUNE[rid]
        return (1.0, 1.0, 1.0, 0)

    def apply_tune(self):
        self.tuned = True
        hp, dm, rate, extra = self.tune_values()
        self.max_hp = int(self.max_hp * hp)
        self.hp = self.max_hp
        # secret bosses scale damage through their own d() helper
        self.dmg_mult = 1.0 if getattr(self, "boss_kind", "") == "secret" else dm
        self.damage = max(1, int(self.damage * dm))
        self.rate = rate
        self.spd_mult = 1 + (rate - 1) * .6
        self.extra = extra

    def extra_attacks(self, dt, scene):
        """Generic pressure attacks layered on top of every boss in later realms."""
        if self.extra <= 0:
            return
        hz = getattr(scene, "hazards", None)
        p = game.player.pos
        if self.timer("x_ring", dt, 7.0 / self.rate):
            n = 10 + 2 * self.extra
            off = random.random() * math.tau
            for i in range(n):
                game.enemy_shot(self.pos, off + i * math.tau / n, 170, max(1, int(12 * self.dmg_mult)), self.color, 7, life=2.6)
        if self.extra >= 2 and hz is not None and self.timer("x_rain", dt, 9.0 / self.rate):
            for k in range(3 + self.extra):
                tp = scene.find_free(p + from_angle(random.random() * math.tau, random.uniform(0, 110)), 20) if hasattr(scene, "find_free") else p
                hz.append(Hazard(tp, 52, .9 + .12 * k, .3, max(1, int(16 * self.dmg_mult)), self.color))
        if self.extra >= 3 and hz is not None and self.timer("x_beam", dt, 11.0 / self.rate):
            a = angle_to(self.pos, p)
            hz.append(Hazard(self.pos, 0, .95, .4, max(1, int(22 * self.dmg_mult)), self.color, shape="line",
                             end=self.pos + from_angle(a, 1200), width=46, label="BEAM"))

    def timer(self, key, dt, period):
        """Returns True each time `period` seconds have elapsed for this key."""
        period = period / max(.1, self.rate)
        t = self.timers.get(key, period) - dt
        if t <= 0:
            self.timers[key] = period
            return True
        self.timers[key] = t
        return False

    def ratio(self):
        return max(0, self.hp) / max(1, self.max_hp)

    def compute_phase(self):
        r = self.ratio()
        return 1 + sum(1 for th in self.thresholds if r <= th)

    def damage_mult(self):
        return 1.0

    def take_damage(self, amount, effect=None, knock=None):
        if not self.alive or self.intro > 0:
            return
        if self.immune:
            if random.random() < .3:
                game.float_text(self.pos + V(0, -self.radius - 10), "IMMUNE", ASH, .5, 16)
            return
        mult = self.damage_mult()
        if mult < 1 and random.random() < .15:
            game.float_text(self.pos + V(0, -self.radius - 22), "RESISTED", ASH, .5, 15)
        super().take_damage(max(1, amount * mult), effect if effect != "void" else "slow", None)

    def update(self, dt, scene):
        if not self.tuned:
            self.apply_tune()
        if self.intro > 0:
            self.intro -= dt
            self.anim += dt
            return
        self.tick_status(dt)
        if not self.alive:
            return
        new_phase = self.compute_phase()
        if new_phase > self.phase:
            self.phase = new_phase
            self.timers.clear()
            self.on_phase(new_phase)
        if self.freeze > 0:
            return
        game.boss_ctx = self
        try:
            self.think(dt, scene)
            if self.alive:
                self.extra_attacks(dt, scene)
        finally:
            game.boss_ctx = None
        if self.alive and dist(self.pos, game.player.pos) < self.radius + game.player.RADIUS and self.contact_cd <= 0:
            game.player.take_damage(self.damage)
            self.contact_cd = 1.0

    def on_phase(self, phase):
        label = self.phase_names[phase - 1] if phase - 1 < len(self.phase_names) else f"PHASE {phase}"
        game.banner(f"PHASE {phase}", label, self.color)
        game.shake(.35)

    def think(self, dt, scene):
        pass

    def chase(self, dt, scene, speed, min_dist=0):
        d = game.player.pos - self.pos
        if d.length() > max(4, min_dist):
            self.pos = scene.move(self.pos, d.normalize() * speed * self.spd_mult * self.speed_factor() * dt, self.radius * .7)

    def die(self):
        if not self.alive:
            return
        self.alive = False
        for _ in range(3):
            burst(self.pos, self.color, 30, (60, 280), 1.0, 4)
        game.shake(.6)
        game.on_boss_defeated(self)

    def draw(self, surf, cam):
        x, y = int(self.pos.x - cam.x), int(self.pos.y - cam.y)
        if self.intro > 0:
            alpha_circle(surf, (x, y), self.radius * (1.4 - self.intro * .3), self.color, 70)
        pygame.draw.ellipse(surf, (0, 0, 0), (x - self.radius, y + self.radius - 8, self.radius * 2, 16))
        self.draw_body(surf, x, y)
        if self.freeze > 0:
            pygame.draw.circle(surf, ICE, (x, y), self.radius + 6, 3)
        if self.burn > 0:
            pygame.draw.circle(surf, ORANGE, (x, y), self.radius + 3, 2)
        if self.immune:
            pygame.draw.circle(surf, WHITE, (x, y), self.radius + 12 + int(math.sin(self.anim * 6) * 3), 3)
        if self.flash > 0:
            pygame.draw.circle(surf, WHITE, (x, y), self.radius, 2)

    def draw_body(self, surf, x, y):
        pygame.draw.circle(surf, self.color, (x, y), self.radius)
        pygame.draw.circle(surf, WHITE, (x - self.radius // 3, y - 6), 5)
        pygame.draw.circle(surf, WHITE, (x + self.radius // 3, y - 6), 5)


# ============================================================
# PLAYER
# ============================================================

def renown_points():
    g = globals().get("game")
    try:
        return sum(1 for st in g.realm_states.values() for v in st.bounty.values() if v["s"] == 2)
    except Exception:
        return 0


def xp_needed(level):
    return int(90 * 1.22 ** (level - 1))


class Player:
    RADIUS = 12

    def __init__(self):
        self.pos = V(0, 0)
        self.vel = V()
        self.facing = V(1, 0)
        self.level = 1
        self.xp = 0
        self.base_max_hp = 120
        self.hp = 120.0
        self.gold = 50
        self.embers = 0
        self.inv = Inventory()
        for entry in [("Rusty Sword", "sword", 10, None), ("Hunting Bow", "bow", 9, None), ("Oak Staff", "staff", 9, None)]:
            self.inv.add(kit_item(entry))
        self.inv.add(potion(3))
        self.inv.armor = Item("Padded Vest", "armor", 6)
        self.relics_owned = []
        self.relic_slots = [None] * 4
        self.treasure_maps = []
        # timers
        self.swing = 0.0
        self.swing_total = 0.0
        self.swing_kind = None
        self.swing_hit = False
        self.attack_cd = 0.0
        self.bow_charge = None
        self.bow_item = None
        self.dash_time = 0.0
        self.dash_cd = 0.0
        self.dash_dir = V(1, 0)
        self.invuln = 0.0
        self.hurt = 0.0
        self.regen_delay = 0.0
        self.burn = 0.0
        self.burn_tick = 0.0
        self.slow = 0.0
        self.freeze = 0.0
        self.nova_cd = 0.0
        self.buffs = {}
        self.anim = 0.0
        self.step = 0.0
        self.external = V()
        self.on_ice = False
        self.blink_trail = []

    # ---------------- relics / derived stats ----------------
    def has_relic(self, key):
        return key in self.relic_slots

    def gain_relic(self, key):
        if key in self.relics_owned or key not in RELICS:
            return False
        self.relics_owned.append(key)
        for i in range(4):
            if self.relic_slots[i] is None:
                self.relic_slots[i] = key
                break
        return True

    def toggle_relic(self, key):
        if key not in self.relics_owned:
            return
        if key in self.relic_slots:
            self.relic_slots[self.relic_slots.index(key)] = None
        elif None in self.relic_slots:
            self.relic_slots[self.relic_slots.index(None)] = key
        else:
            game.float_text(self.pos, "All 4 relic slots are full", RED)
        self.hp = min(self.hp, self.max_hp)

    @property
    def max_hp(self):
        bonus = (12 if self.has_relic("mirrorcrown") else 0) + 2 * renown_points()
        if self.buffs.get("hearty", 0) > 0:
            bonus += 40
        return self.base_max_hp + bonus

    @property
    def armor_value(self):
        return self.inv.armor.power if self.inv.armor else 0

    def move_speed(self):
        s = 205.0
        if self.has_relic("mirrorstep"):
            s *= 1.18
        if self.has_relic("nullcompass"):
            s *= 1.10
        if self.buffs.get("swift", 0) > 0:
            s *= 1.15
        if self.slow > 0 and not self.has_relic("mirrorstep"):
            s *= .55
        return s

    def damage_mult(self):
        m = 1.0
        if self.buffs.get("aid", 0) > 0:
            m *= 1.10
        if self.has_relic("constellation"):
            m *= 1.05
        if self.buffs.get("might", 0) > 0:
            m *= 1.2
        return m

    def selected(self):
        return self.inv.selected_item()

    def weapon(self):
        item = self.selected()
        return item if item and item.is_weapon else None

    # ---------------- update ----------------
    def update(self, dt, scene):
        self.anim += dt
        for name in list(self.buffs):
            self.buffs[name] -= dt
            if self.buffs[name] <= 0:
                del self.buffs[name]
                self.hp = min(self.hp, self.max_hp)
        self.attack_cd = max(0, self.attack_cd - dt)
        self.potion_cd = max(0, getattr(self, "potion_cd", 0) - dt)
        self.potion_idle = getattr(self, "potion_idle", 99) + dt
        if self.potion_idle > 25:
            self.potion_chain = 0
        self.dash_cd = max(0, self.dash_cd - dt)
        self.invuln = max(0, self.invuln - dt)
        self.hurt = max(0, self.hurt - dt)
        self.regen_delay = max(0, self.regen_delay - dt)
        self.slow = max(0, self.slow - dt)
        self.freeze = max(0, self.freeze - dt)
        self.nova_cd = max(0, self.nova_cd - dt)
        if self.burn > 0:
            self.burn -= dt
            self.burn_tick -= dt
            if self.burn_tick <= 0:
                self.burn_tick = 1.0
                self.take_damage(3, "fire", ignore_invuln=True, quiet=True)
                game.particles.append(Particle(self.pos + V(random.uniform(-6, 6), -10), (0, -50), ORANGE, .4, 3))
        # regeneration
        if self.regen_delay <= 0 and 0 < self.hp < self.max_hp:
            rate = 2.0 * (1.5 if self.has_relic("vaultkey") else 1)
            self.hp = min(self.max_hp, self.hp + rate * dt)
        if self.buffs.get("regen", 0) > 0 and self.hp > 0:
            self.hp = min(self.max_hp, self.hp + 6 * dt)

        keys = pygame.key.get_pressed()
        move = V((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]),
                 (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]))
        if move.length_squared() > 0:
            move = move.normalize()
        aim = game.mouse_world() - self.pos
        if aim.length() > 4:
            self.facing = aim.normalize()

        if self.freeze > 0:
            desired = V()
        else:
            desired = move * self.move_speed()
        if self.dash_time > 0:
            self.dash_time -= dt
            self.vel = self.dash_dir * 650
        elif self.on_ice and not self.has_relic("mirrorstep"):
            self.vel += (desired - self.vel) * min(1, dt * 2.0)
        else:
            self.vel = desired
        delta = (self.vel + self.external) * dt
        self.external = V()
        if delta.length_squared() > 0:
            self.pos = scene.move(self.pos, delta, self.RADIUS)
        if move.length_squared() > 0:
            self.step += dt * 10
        else:
            self.step = 0
        self.on_ice = False

        # melee swing resolution
        if self.swing > 0:
            self.swing -= dt
            if not self.swing_hit and self.swing <= self.swing_total * .55:
                self.swing_hit = True
                self.resolve_melee()
        if self.bow_charge is not None:
            self.bow_charge = min(1.0, self.bow_charge + dt * 1.25)
        self.blink_trail = [(p, t - dt) for p, t in self.blink_trail if t - dt > 0]

    # ---------------- actions ----------------
    def use_primary(self):
        item = self.selected()
        if self.freeze > 0 or self.dash_time > 0:
            return
        if item is None:
            self.start_swing("fist")
        elif item.kind in ("sword", "greatsword"):
            self.start_swing(item.kind)
        elif item.kind == "bow":
            self.begin_bow(item)
        elif item.kind == "staff":
            self.cast_bolt(item)
        elif item.kind in ("potion", "food"):
            self.consume(item)
        else:
            game.float_text(self.pos, f"{item.name} can't be used", ASH)

    def start_swing(self, kind):
        if self.swing > 0 or self.attack_cd > 0:
            return
        self.swing_kind = kind
        self.swing_total = {"greatsword": .55, "fist": .3}.get(kind, .34)
        self.swing = self.swing_total
        self.swing_hit = False
        self.attack_cd = self.swing_total + .04
        game.sound("swing")

    def resolve_melee(self):
        weapon = self.weapon()
        power = weapon.power if weapon and weapon.kind in ("sword", "greatsword") else 0
        if self.swing_kind == "greatsword":
            dmg, reach, arc = 24 + power * 1.25 + self.level * 3, 104, 1.05
        elif self.swing_kind == "sword":
            dmg, reach, arc = 14 + power + self.level * 2, 80, .85
        else:
            dmg, reach, arc = 8 + self.level, 52, .7
        dmg *= self.damage_mult()
        fiery = self.has_relic("cinderheart") and self.swing_kind in ("sword", "greatsword")
        effect = weapon.effect if weapon and weapon.kind in ("sword", "greatsword") else None
        base = math.atan2(self.facing.y, self.facing.x)
        hit_any = False
        for t in game.scene.targets():
            if not t.alive:
                continue
            d = dist(self.pos, t.pos)
            if d < reach + t.radius and (d < t.radius + 18 or angle_diff(angle_to(self.pos, t.pos), base) < arc):
                t.take_damage(dmg, effect, self.facing * (260 if self.swing_kind == "greatsword" else 170))
                if fiery and t.alive and hasattr(t, "apply_effect"):
                    t.apply_effect("burn")
                hit_any = True
        game.scene.melee_hits_object(self.pos + self.facing * reach * .6, reach, dmg)
        tip = self.pos + self.facing * reach * .8
        col = ORANGE if fiery else WHITE
        for _ in range(10 if fiery else 6):
            a = base + random.uniform(-arc, arc)
            game.particles.append(Particle(self.pos + from_angle(a, reach * .7), from_angle(a, random.uniform(40, 120)), col, .25, 3))
        if hit_any:
            game.shake(.08 if self.swing_kind != "greatsword" else .16)
            game.sound("hit")
        if fiery:
            game.particles.append(Particle(tip, (0, -40), EMBER, .4, 4))

    def ranged_bonus(self):
        lens = self.has_relic("starlens")
        return (4 if lens else 0), (1.18 if lens else 1.0), (GOLD if lens else None)

    def begin_bow(self, item):
        if self.attack_cd > 0 or self.bow_charge is not None:
            return
        self.bow_item = item
        self.bow_charge = 0.0

    def quick_bow(self):
        bow = self.weapon() if self.weapon() and self.weapon().kind == "bow" else self.inv.first_of_kind("bow")
        if bow is None:
            game.float_text(self.pos, "No bow in your bag", ASH)
            return
        if self.freeze > 0:
            return
        self.begin_bow(bow)

    def release_bow(self):
        if self.bow_charge is None:
            return
        charge = self.bow_charge
        item = self.bow_item
        self.bow_charge = None
        self.bow_item = None
        if item is None or item not in self.inv.slots:
            return
        pierce, speed_mult, gold_col = self.ranged_bonus()
        dmg = (10 + item.power + self.level * 2) * (.45 + .75 * charge) * self.damage_mult()
        speed = (420 + 300 * charge) * speed_mult
        game.player_shot(Projectile(self.pos + self.facing * 16, self.facing * speed, dmg, "player", 5,
                                    gold_col or (224, 211, 178), 1.6, item.effect, pierce, kind="arrow",
                                    trail=GOLD if gold_col else None))
        self.attack_cd = .32
        game.sound("bow")

    def cast_bolt(self, item):
        if self.attack_cd > 0:
            return
        pierce, speed_mult, gold_col = self.ranged_bonus()
        frosty = self.has_relic("mirrorstep")
        color = gold_col or (ICE if frosty else BLUE)
        dmg = (9 + item.power * .85 + self.level * 1.8) * self.damage_mult()
        game.player_shot(Projectile(self.pos + self.facing * 18, self.facing * 440 * speed_mult, dmg, "player", 7, color,
                                    1.5, item.effect, pierce, kind="orb", trail=color))
        self.attack_cd = .3
        game.sound("bolt")

    def relic_ability(self):
        if not self.has_relic("mirrorstep"):
            game.float_text(self.pos, "No relic ability equipped", ASH)
            return
        weapon = self.weapon()
        if not weapon or weapon.kind != "staff":
            game.float_text(self.pos, "Hold a staff to cast Frost Nova", ICE)
            return
        if self.nova_cd > 0:
            game.float_text(self.pos, f"Frost Nova {self.nova_cd:.0f}s", ASH)
            return
        self.nova_cd = 12.0
        radius = 175
        for t in game.scene.targets():
            if t.alive and dist(self.pos, t.pos) < radius + t.radius:
                t.take_damage((18 + weapon.power) * self.damage_mult(), None)
                if t.alive and hasattr(t, "apply_effect"):
                    t.apply_effect("freeze")
        for i in range(36):
            a = i * math.tau / 36
            game.particles.append(Particle(self.pos, from_angle(a, 420), ICE, .4, 4, drag=2))
        game.flash_ring(self.pos, radius, ICE)
        game.float_text(self.pos + V(0, -30), "FROST NOVA", ICE)
        game.shake(.2)

    def dash(self, scene):
        if self.dash_cd > 0 or self.freeze > 0 or self.dash_time > 0:
            return
        keys = pygame.key.get_pressed()
        move = V((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]),
                 (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]))
        direction = move.normalize() if move.length_squared() else V(self.facing)
        cd_mult = .88 if self.has_relic("arcadestar") else 1.0
        if self.has_relic("nullcompass"):
            # Blink: teleport to the furthest clear point along a straight line.
            start = V(self.pos)
            best = V(self.pos)
            for i in range(1, 25):
                cand = start + direction * (i * 8)
                if scene.blocked(cand, self.RADIUS):
                    break
                best = cand
            if best == start:
                return
            for i in range(8):
                self.blink_trail.append((start.lerp(best, i / 8), .35))
            burst(start, PURPLE, 14, (40, 140), .4, 3)
            self.pos = best
            burst(best, PURPLE, 14, (40, 140), .4, 3)
            self.invuln = max(self.invuln, .32)
            self.dash_cd = .9 * cd_mult
            self.vel = V()
            game.sound("blink")
            return
        self.dash_dir = direction
        self.dash_time = .17
        self.dash_cd = .75 * cd_mult
        self.invuln = max(self.invuln, .26)
        burst(self.pos, BLUE, 8, (30, 80), .3, 4)
        game.sound("dash")

    def consume(self, item):
        if item.kind == "potion":
            if self.hp >= self.max_hp:
                game.float_text(self.pos, "Health is full", ASH)
                return
            if getattr(self, "potion_cd", 0) > 0:
                game.float_text(self.pos, f"Potion cooling down ({self.potion_cd:.0f}s)", ASH)
                return
            self.inv.take_one(name=item.name, kind="potion")
            chain = getattr(self, "potion_chain", 0)
            self.heal(max(18, int(60 * (.7 ** chain))))
            self.potion_chain = chain + 1
            self.potion_cd = 6.0
            self.potion_idle = 0.0
            burst(self.pos, GREEN, 16, (40, 100), .6, 3)
        elif item.kind == "food":
            self.inv.take_one(name=item.name, kind="food")
            dur = {"regen": 30, "might": 60, "hearty": 90, "swift": 60}.get(item.effect, 30)
            self.buffs[item.effect] = dur
            if item.effect == "hearty":
                self.hp += 40
            game.float_text(self.pos, f"{item.name}: {EFFECT_NAMES.get(item.effect, '')}", ORANGE)
        game.sound("pickup")

    def drink_potion(self):
        if self.inv.count(kind="potion") <= 0:
            game.float_text(self.pos, "Out of potions", RED)
            return
        item = next(i for i in self.inv.slots if i and i.kind == "potion")
        self.consume(item)

    def heal(self, amount):
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        if self.hp > before:
            game.float_text(self.pos, f"+{int(self.hp - before)}", GREEN)

    # ---------------- damage ----------------
    def apply_burn(self, duration=2.0):
        if self.has_relic("cinderheart"):
            return
        if self.burn <= 0:
            self.burn_tick = 1.0
        self.burn = max(self.burn, duration)
        self.regen_delay = max(self.regen_delay, duration)

    def apply_freeze(self, duration=1.0):
        if self.freeze <= 0:
            game.float_text(self.pos, "FROZEN", ICE)
        self.freeze = max(self.freeze, duration)
        self.bow_charge = None

    def apply_slow(self, duration=1.5):
        if not self.has_relic("mirrorstep"):
            self.slow = max(self.slow, duration)

    def take_damage(self, amount, element=None, ignore_invuln=False, quiet=False):
        if game.state != PLAYING or self.hp <= 0 or game.god_mode:
            return
        if self.invuln > 0 and not ignore_invuln:
            return
        if element == "fire" and self.has_relic("cinderheart"):
            amount *= .5
        if self.buffs.get("aid", 0) > 0:
            amount *= .8
        reduced = max(1, int(amount - self.armor_value * .25))
        reduced = min(reduced, max(1, int(self.max_hp * MAX_HIT_FRACTION)))
        self.hp -= reduced
        self.regen_delay = 3.0
        if not ignore_invuln:
            self.invuln = .5
            self.hurt = .2
            game.shake(.15)
        if not quiet or reduced > 2:
            game.float_text(self.pos + V(0, -24), f"-{reduced}", RED)
        game.sound("hurt")
        if self.hp <= 0:
            self.hp = 0
            game.on_player_death()

    def instant_defeat(self, reason):
        if game.state != PLAYING or game.god_mode:
            return
        self.hp = 0
        game.death_reason = reason
        game.on_player_death()

    def gain_xp(self, amount):
        self.xp += int(amount)
        while self.xp >= xp_needed(self.level):
            self.xp -= xp_needed(self.level)
            self.level += 1
            self.base_max_hp += 12
            self.hp = self.max_hp
            game.float_text(self.pos + V(0, -40), f"LEVEL UP!  {self.level}", GOLD, 1.6, 26)
            burst(self.pos, GOLD, 30, (60, 200), .9, 3)
            game.sound("level")

    # ---------------- drawing ----------------
    def draw(self, surf, cam):
        for p, t in self.blink_trail:
            alpha_circle(surf, p - cam, 12, PURPLE, int(200 * t))
        x, y = int(self.pos.x - cam.x), int(self.pos.y - cam.y)
        bob = int(math.sin(self.step) * 2) if self.step else int(math.sin(self.anim * 2))
        y += bob
        pygame.draw.ellipse(surf, (0, 0, 0), (x - 12, y + 16, 24, 8))
        if self.dash_time > 0:
            pygame.draw.circle(surf, BLUE, (x, y), 22, 2)
        null = self.has_relic("nullcompass")
        cloak = (110, 60, 170) if null else (52, 66, 98)
        body = WHITE if self.hurt > 0 else (63, 116, 178)
        if null:
            glow(surf, (x, y + 6), 26, PURPLE, 70)
        # cloak
        pygame.draw.polygon(surf, cloak, [(x - 12, y - 2), (x + 12, y - 2), (x + 14, y + 18), (x - 14, y + 18)])
        pygame.draw.rect(surf, body, (x - 9, y - 4, 18, 18))
        armor = self.inv.armor
        if armor:
            pygame.draw.rect(surf, armor.color, (x - 9, y - 4, 18, 18), 2)
        # head
        pygame.draw.rect(surf, (226, 177, 132), (x - 8, y - 21, 16, 16))
        pygame.draw.rect(surf, (60, 40, 32), (x - 9, y - 24, 18, 6))
        if self.facing.x >= 0:
            pygame.draw.rect(surf, (20, 25, 34), (x + 1, y - 15, 3, 3))
            pygame.draw.rect(surf, (20, 25, 34), (x + 5, y - 15, 2, 3))
        else:
            pygame.draw.rect(surf, (20, 25, 34), (x - 4, y - 15, 3, 3))
            pygame.draw.rect(surf, (20, 25, 34), (x - 7, y - 15, 2, 3))
        feet = (130, 70, 200) if null else (45, 49, 61)
        pygame.draw.rect(surf, feet, (x - 10, y + 15, 8, 6))
        pygame.draw.rect(surf, feet, (x + 2, y + 15, 8, 6))
        self.draw_weapon(surf, x, y)
        if self.burn > 0:
            pygame.draw.circle(surf, ORANGE, (x, y), 26 + int(math.sin(self.anim * 9) * 2), 2)
        if self.freeze > 0:
            pygame.draw.rect(surf, ICE, (x - 16, y - 28, 32, 52), 2)
        if self.invuln > 0 and self.hurt <= 0 and int(self.invuln * 20) % 2 == 0:
            pygame.draw.circle(surf, WHITE, (x, y), 24, 1)

    def draw_weapon(self, surf, x, y):
        item = self.selected()
        kind = self.swing_kind if self.swing > 0 else (item.kind if item else None)
        base = math.atan2(self.facing.y, self.facing.x)
        origin = V(x, y + 2)
        fiery = self.has_relic("cinderheart")
        if self.bow_charge is not None:
            side = V(-self.facing.y, self.facing.x)
            center = origin + self.facing * 18
            top = origin + side * 16 - self.facing * 2
            bot = origin - side * 16 - self.facing * 2
            col = GOLD if self.has_relic("starlens") else (156, 104, 65)
            if self.has_relic("starlens"):
                glow(surf, center, 22, GOLD, 90)
            pygame.draw.line(surf, col, ipos(top), ipos(center), 3)
            pygame.draw.line(surf, col, ipos(center), ipos(bot), 3)
            back = center - self.facing * (6 + 16 * self.bow_charge)
            pygame.draw.line(surf, WHITE, ipos(top), ipos(back), 1)
            pygame.draw.line(surf, WHITE, ipos(back), ipos(bot), 1)
            if self.bow_charge >= 1:
                pygame.draw.circle(surf, GOLD, ipos(back), 4)
            return
        if self.swing > 0 and kind in ("sword", "greatsword", "fist"):
            progress = 1 - self.swing / max(.01, self.swing_total)
            spread = 1.25 if kind == "greatsword" else 1.0
            a = base - spread + 2 * spread * progress
            length = {"greatsword": 70, "sword": 54, "fist": 22}[kind]
            end = origin + from_angle(a, length)
            col = (225, 228, 235)
            if fiery and kind != "fist":
                glow(surf, end, 30, ORANGE, 130)
                col = (255, 170, 80)
            pygame.draw.line(surf, col, ipos(origin), ipos(end), 8 if kind == "greatsword" else 5)
            pygame.draw.line(surf, (255, 248, 211) if not fiery else (255, 230, 120), ipos(origin), ipos(end), 2)
            arc_rect = pygame.Rect(0, 0, length * 2, length * 2)
            arc_rect.center = ipos(origin)
            pygame.draw.arc(surf, ORANGE if fiery else WHITE, arc_rect, -(a + .35), -(a - .35), 3)
            return
        if item is None or not item.is_weapon:
            return
        tip = origin + self.facing * 28
        if item.kind in ("sword", "greatsword"):
            length = 34 if item.kind == "greatsword" else 26
            tip = origin + self.facing * length
            col = (190, 192, 200)
            if fiery:
                glow(surf, tip, 18 + int(math.sin(self.anim * 10) * 3), ORANGE, 110)
                col = (255, 120, 60)
                if random.random() < .3:
                    game.particles.append(Particle(tip + V(game.cam.x, game.cam.y), (random.uniform(-10, 10), -45), random.choice((ORANGE, EMBER, GOLD)), .4, 2))
            pygame.draw.line(surf, col, ipos(origin), ipos(tip), 5 if item.kind == "greatsword" else 3)
        elif item.kind == "staff":
            tip = origin + self.facing * 26
            pygame.draw.line(surf, (130, 95, 60), ipos(origin - self.facing * 6), ipos(tip), 3)
            if self.has_relic("mirrorstep"):
                glow(surf, tip, 20, ICE, 140)
                pygame.draw.circle(surf, ICE, ipos(tip), 6)
            elif self.has_relic("starlens"):
                glow(surf, tip, 18, GOLD, 120)
                pygame.draw.circle(surf, GOLD, ipos(tip), 5)
            else:
                pygame.draw.circle(surf, BLUE, ipos(tip), 5)
            if self.has_relic("starlens") and self.has_relic("mirrorstep"):
                pygame.draw.circle(surf, GOLD, ipos(tip), 8, 1)
        elif item.kind == "bow":
            side = V(-self.facing.y, self.facing.x)
            c = origin + self.facing * 14
            col = GOLD if self.has_relic("starlens") else (156, 104, 65)
            if self.has_relic("starlens"):
                glow(surf, c, 16, GOLD, 80)
            pygame.draw.line(surf, col, ipos(c + side * 13), ipos(c + self.facing * 4), 3)
            pygame.draw.line(surf, col, ipos(c + self.facing * 4), ipos(c - side * 13), 3)


# ============================================================
# INTERACTABLES / NPCS
# ============================================================

class Interactable:
    def __init__(self, pos, label, action, radius=66, visible=None, draw_fn=None):
        self.pos = V(pos)
        self.label = label
        self.action = action
        self.radius = radius
        self.visible = visible
        self.draw_fn = draw_fn
        self.anim = random.random() * 6

    def is_visible(self):
        return self.visible() if callable(self.visible) else True

    def get_label(self):
        return self.label() if callable(self.label) else self.label

    def update(self, dt):
        self.anim += dt

    def draw(self, surf, cam):
        if self.draw_fn:
            self.draw_fn(surf, self.pos - cam, self)


class NPC(Interactable):
    def __init__(self, name, role, pos, color, talk, marker=None, hair=(60, 40, 30), robe=None, visible=None):
        super().__init__(pos, f"Talk to {name}", talk, 70, visible)
        self.name = name
        self.role = role
        self.color = color
        self.marker = marker
        self.hair = hair
        self.robe = robe or color

    def draw(self, surf, cam):
        x, y = int(self.pos.x - cam.x), int(self.pos.y - cam.y)
        if x < -80 or x > WIDTH + 80 or y < -80 or y > HEIGHT + 80:
            return
        y += int(math.sin(self.anim * 2) * 1.5)
        pygame.draw.ellipse(surf, (0, 0, 0), (x - 12, y + 16, 24, 8))
        pygame.draw.polygon(surf, self.robe, [(x - 11, y - 3), (x + 11, y - 3), (x + 14, y + 19), (x - 14, y + 19)])
        pygame.draw.rect(surf, mix(self.robe, BLACK, .35), (x - 11, y + 4, 22, 3))
        pygame.draw.rect(surf, (226, 180, 140), (x - 8, y - 20, 16, 16))
        pygame.draw.rect(surf, self.hair, (x - 9, y - 23, 18, 6))
        pygame.draw.rect(surf, self.hair, (x - 9, y - 20, 3, 8))
        pygame.draw.rect(surf, DARK, (x - 4, y - 14, 3, 3))
        pygame.draw.rect(surf, DARK, (x + 2, y - 14, 3, 3))
        draw_text(surf, self.name, (x, y - 42), WHITE, 17, center=True)
        draw_text(surf, self.role, (x, y - 30), mix(self.color, WHITE, .3), 14, center=True)
        mark = self.marker() if callable(self.marker) else None
        if mark:
            text, col = mark
            pulse = int(math.sin(self.anim * 5) * 2)
            draw_text(surf, text, (x, y - 62 + pulse), col, 26, center=True)


def draw_portal(surf, p, color, t, label=None, radius=26, active=True):
    x, y = int(p[0]), int(p[1])
    pulse = math.sin(t * 3) * 3
    if active:
        glow(surf, (x, y), radius * 2, color, 80)
    pygame.draw.circle(surf, mix(color, BLACK, .6), (x, y), int(radius + 6 + pulse), 4)
    pygame.draw.circle(surf, color if active else ASH, (x, y), radius, 3)
    pygame.draw.circle(surf, (14, 12, 22), (x, y), radius - 7)
    if active:
        for i in range(6):
            a = t * 1.6 + i * math.tau / 6
            q = (x + math.cos(a) * (radius - 12), y + math.sin(a) * (radius - 12))
            pygame.draw.circle(surf, color, ipos(q), 3)
    if label:
        draw_text(surf, label, (x, y - radius - 26), color if active else ASH, 17, center=True)


# ============================================================
# SCENES
# ============================================================

class Scene:
    fixed_camera = True
    key = "scene"
    title = ""
    hub = False          # safe to save here and restore on load
    allow_escape = False  # ESC offers "leave" from this scene

    def __init__(self):
        self.enemies = []
        self.interactables = []
        self.hazards = []
        self.time = 0.0
        self.width = WIDTH
        self.height = HEIGHT
        self.bg = (22, 22, 28)
        self.accent = GOLD
        self.boss = None

    # ---- geometry ----
    def spawn(self):
        return V(self.width / 2, self.height / 2)

    def is_solid(self, p):
        return not (0 <= p[0] < self.width and 0 <= p[1] < self.height)

    def blocked(self, p, r):
        x, y = p[0], p[1]
        rr = r * .75
        return (self.is_solid((x, y)) or self.is_solid((x - rr, y)) or self.is_solid((x + rr, y))
                or self.is_solid((x, y - rr)) or self.is_solid((x, y + rr)))

    def blocks_projectile(self, p):
        return self.is_solid(p)

    def line_clear(self, a, b):
        d = dist(a, b)
        steps = int(d / 18) + 1
        for i in range(1, steps):
            t = i / steps
            if self.blocks_projectile((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)):
                return False
        return True

    def move(self, pos, delta, r):
        pos = V(pos)
        if delta.length_squared() == 0:
            return pos
        if self.blocked(pos, r):
            # Already overlapping something (e.g. after a geometry change): let it slide out.
            out = pos + delta
            out.x = clamp(out.x, 4, self.width - 4)
            out.y = clamp(out.y, 4, self.height - 4)
            return out
        n = max(1, int(delta.length() / 6) + 1)
        step = delta / n
        for _ in range(n):
            nx = V(pos.x + step.x, pos.y)
            if not self.blocked(nx, r):
                pos = nx
            ny = V(pos.x, pos.y + step.y)
            if not self.blocked(ny, r):
                pos = ny
        return pos

    def find_free(self, p, r=14, max_radius=320):
        p = V(p)
        if not self.blocked(p, r):
            return p
        for radius in range(12, max_radius, 12):
            for i in range(16):
                q = p + from_angle(i * math.tau / 16, radius)
                if 0 < q.x < self.width and 0 < q.y < self.height and not self.blocked(q, r):
                    return q
        return p

    # ---- combat ----
    def targets(self):
        return [e for e in self.enemies if e.alive] + self.extra_targets()

    def extra_targets(self):
        return []

    def melee_hits_object(self, center, reach, dmg):
        pass

    def add_enemy(self, enemy):
        enemy.pos = self.find_free(enemy.pos, enemy.radius)
        enemy.home = V(enemy.pos)
        self.enemies.append(enemy)
        return enemy

    # ---- lifecycle ----
    def on_enter(self):
        pass

    def on_exit(self):
        pass

    def update(self, dt):
        self.time += dt
        for it in self.interactables:
            it.update(dt)
        for e in list(self.enemies):
            if e.alive:
                e.update(dt, self)
        self.enemies = [e for e in self.enemies if e.alive]
        self.hazards = [h for h in self.hazards if h.update(dt)]

    def objective(self):
        """(text, world position or None) shown in the tracker/compass."""
        return None, None

    # ---- drawing ----
    def draw_ground(self, surf, cam):
        surf.fill(self.bg)

    def draw_objects(self, surf, cam):
        for it in self.interactables:
            if it.is_visible():
                it.draw(surf, cam)

    def draw_hazards(self, surf, cam):
        for h in self.hazards:
            h.draw(surf, cam)

    def draw_top(self, surf, cam):
        pass


class TileWorld(Scene):
    """Large scrolling map backed by a character grid; pre-rendered on enter."""
    fixed_camera = False
    SOLID = set("TWBRCX#")

    def __init__(self, tw, th, fill="g"):
        super().__init__()
        self.tw, self.th = tw, th
        self.width, self.height = tw * TILE, th * TILE
        self.grid = [[fill] * tw for _ in range(th)]
        self.surface = None
        self.rng = random.Random(1)

    def tile(self, tx, ty):
        if 0 <= tx < self.tw and 0 <= ty < self.th:
            return self.grid[ty][tx]
        return None

    def set_rect(self, x, y, w, h, ch, only=None):
        for ty in range(max(0, y), min(self.th, y + h)):
            for tx in range(max(0, x), min(self.tw, x + w)):
                if only is None or self.grid[ty][tx] in only:
                    self.grid[ty][tx] = ch

    def set_disc(self, cx, cy, r, ch, only=None):
        for ty in range(int(cy - r - 1), int(cy + r + 2)):
            for tx in range(int(cx - r - 1), int(cx + r + 2)):
                if 0 <= tx < self.tw and 0 <= ty < self.th and math.hypot(tx - cx, ty - cy) <= r:
                    if only is None or self.grid[ty][tx] in only:
                        self.grid[ty][tx] = ch

    def is_solid(self, p):
        tx, ty = int(p[0] // TILE), int(p[1] // TILE)
        if p[0] < 0 or p[1] < 0 or tx >= self.tw or ty >= self.th:
            return True
        return self.grid[ty][tx] in self.SOLID

    def tile_center(self, tx, ty):
        return V(tx * TILE + TILE / 2, ty * TILE + TILE / 2)

    def reachable_from(self, tx, ty):
        seen = {(tx, ty)}
        stack = [(tx, ty)]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and 0 <= nx < self.tw and 0 <= ny < self.th and self.grid[ny][nx] not in self.SOLID:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen

    def ensure_reachable(self, start, points, floor):
        """Carve an L-shaped corridor to any key point that obstacles cut off."""
        for _ in range(3):
            reach = self.reachable_from(*start)
            for (px, py) in points:
                if (px, py) in reach:
                    continue
                x, y = px, py
                while x != start[0]:
                    for oy in (-1, 0, 1):
                        if self.tile(x, y + oy) in self.SOLID and self.tile(x, y + oy) != "B":
                            self.grid[y + oy][x] = floor
                    x += 1 if start[0] > x else -1
                while y != start[1]:
                    for ox in (-1, 0, 1):
                        if self.tile(x + ox, y) in self.SOLID and self.tile(x + ox, y) != "B":
                            self.grid[y][x + ox] = floor
                    y += 1 if start[1] > y else -1

    def render_tile(self, surf, tx, ty, ch, rect, rng):
        pygame.draw.rect(surf, (60, 90, 60), rect)

    def render_static(self, surf):
        pass

    def prerender(self):
        surf = pygame.Surface((self.width, self.height)).convert()
        rng = random.Random(7)
        for ty in range(self.th):
            for tx in range(self.tw):
                self.render_tile(surf, tx, ty, self.grid[ty][tx], pygame.Rect(tx * TILE, ty * TILE, TILE, TILE), rng)
        self.render_static(surf)
        self.surface = surf

    def on_enter(self):
        if self.surface is None:
            self.prerender()

    def on_exit(self):
        self.surface = None

    def draw_ground(self, surf, cam):
        if self.surface is None:
            self.prerender()
        surf.fill(BLACK)
        surf.blit(self.surface, (0, 0), pygame.Rect(int(cam.x), int(cam.y), WIDTH, HEIGHT))


class Arena(Scene):
    """Fixed-screen room bounded by a rectangle plus optional solid walls."""
    fixed_camera = True

    def __init__(self, play=pygame.Rect(40, 70, 880, 515)):
        super().__init__()
        self.play = pygame.Rect(play)
        self.walls = []

    def is_solid(self, p):
        if not self.play.collidepoint(p):
            return True
        for w in self.walls:
            if w.collidepoint(p):
                return True
        return False

    def draw_floor(self, surf, base, line, step=40):
        surf.fill(mix(base, BLACK, .45))
        pygame.draw.rect(surf, base, self.play)
        for x in range(self.play.left, self.play.right, step):
            pygame.draw.line(surf, line, (x, self.play.top), (x, self.play.bottom), 1)
        for y in range(self.play.top, self.play.bottom, step):
            pygame.draw.line(surf, line, (self.play.left, y), (self.play.right, y), 1)
        pygame.draw.rect(surf, mix(line, WHITE, .2), self.play, 3)

    def draw_walls(self, surf, fill, edge):
        for w in self.walls:
            pygame.draw.rect(surf, fill, w)
            pygame.draw.rect(surf, edge, w, 2)


# ============================================================
# STORY DATA
# ============================================================

# Each task: (kind, label, story text). kinds: interact / stealth / fight
QUEST_DATA = {
    EMBER_ID: [
        ("The Cinder Caravan", "CINDER OUTPOST", "Sera", "Guide", [
            ("search", "Inspect the shattered supply wagon", "The caravan is wrecked. Someone wanted these supplies badly."),
            ("collect", "Gather the scattered ember crates", "Five crates survived the raid. Raiders are still picking through the ash."),
            ("defend", "Hold the wagon until the furnace relights", "The raiders come back for the cargo. Keep the furnace-wagon alive."),
            ("escort", "Escort the cargo-bearer to the outpost gate", "The bearer made it. The outpost furnaces roar back to life."),
        ]),
        ("The Molten Ledger", "MOLTEN QUARRY", "King Vael", "Castle Keeper", [
            ("search", "Find the hidden foundry entrance", "Fresh hammer marks reveal a back entrance into the quarry."),
            ("stealth", "Steal the smelter ledger", "The ledger names the people supplying the dragon cult. Don't be seen."),
            ("gauntlet", "Run the vent gallery with the ledger", "Steam vents and slag jets fire in rhythm. Time your run."),
            ("hunt", "Slay the Foundry Overseer", "The Overseer will not let the ledger leave the quarry."),
            ("puzzle", "Open the Dragonforged vault valves", "The valves open in the order the old smelters chalked on the wall."),
        ]),
        ("Dragon's Wake", "DRAGON CRAG", "Rook", "Cave Scout", [
            ("puzzle", "Break the wardstones in the right order", "The wardstones crack apart one after the other."),
            ("collect", "Gather the dragon-scale shards", "Shards of cooling scale lie across the crag floor."),
            ("survive", "Survive the crag collapse", "The mountain shakes. Rocks and fire rain down."),
            ("hunt", "Slay the Cult Magus", "The cultist magus is drawing power from the last wardstone."),
            ("defend", "Hold the Sanctum gate while it unseals", "The cult throws everything at the gate. Hold until it opens."),
        ]),
    ],
    FROZEN_ID: [
        ("The Frozen Archive Heist", "FROZEN ARCHIVE", "Nivi", "Guide", [
            ("search", "Find the sealed archive door", "The archive is locked from the inside. Something important is hidden here."),
            ("puzzle", "Decipher the study's rune lock", "The runes light in an order hinted by the frozen tablet."),
            ("fight", "Steal the Frost Codex - you are discovered", "You grab the book, but the mage spots you. Fight!"),
            ("gauntlet", "Flee through the ward-lit stacks", "Ward beams sweep the stacks. Cross without being burned."),
        ]),
        ("The Whiteout Relay", "WINTER MAGE TOWER", "Abbot Korr", "Monastery Keeper", [
            ("collect", "Gather the humming aurora shards", "Shards of the old relay lie scattered under the ice."),
            ("puzzle", "Retune the Aurora Relay", "The relay sings in a pattern. Match it."),
            ("defend", "Hold the relay while the storm attacks", "Frost wraiths are drawn to the repaired light."),
            ("hunt", "Slay the Storm Herald", "The Herald rides the whiteout and will not stop."),
            ("survive", "Endure the whiteout blizzard", "The storm calms behind you. The throne road stands exposed."),
        ]),
        ("The Frostheart Oath", "FROST THRONE", "Ysolde", "Aurora Keeper", [
            ("collect", "Recover the three oath-shards", "The throne's seal needs its shattered oath."),
            ("puzzle", "Break the ice seals in oath order", "A deep bell sounds inside the glacier."),
            ("fight", "Defeat the Frost Throne guardians", "Ancient sentinels rise from the snow."),
            ("escort", "Escort the Aurora Keeper to the citadel gate", "The Keeper must reach the gate alive."),
            ("defend", "Hold the citadel gate", "The Frostheart is waiting beyond. Hold the line until the gate opens."),
        ]),
    ],
    STARFALL_ID: [
        ("The Fallen Choir", "CLOUD GARDEN", "Astra", "Guide", [
            ("search", "Find the first fallen hymn fragment", "The fragment glows softly beneath a broken cloud bridge."),
            ("collect", "Gather the scattered choir notes", "The notes drift through the gardens, guarded by winged sentinels."),
            ("hunt", "Slay the Sentinel Cantor", "The choir's cantor still sings through its attacks."),
            ("puzzle", "Restore the fallen choir", "Sing the hymn in order. The road to the cathedral appears."),
        ]),
        ("The Glass Cathedral", "GLASS CATHEDRAL", "Seren", "Sky Archivist", [
            ("puzzle", "Open the reliquary with the choir notes", "The doors open only for the old choir note, played in order."),
            ("gauntlet", "Cross the prism nave and take the Sun Relic", "Light beams cut across the nave. Cross when the gaps open."),
            ("fight", "Fight the awakened cathedral guardians", "The relic woke every sentinel in the hall."),
            ("escort", "Escort the Archivist's lantern across the nave", "Light from the relic forms a bridge to the upper gate."),
            ("stealth", "Slip past the sentinels to the Seraph's stair", "The stair opens into the final region."),
        ]),
        ("Seraph's Judgment", "SERAPH'S GATE", "Oria", "Oracle", [
            ("puzzle", "Activate the celestial seals in order", "Stars ignite above the gate, one by one."),
            ("survive", "Withstand the judgment storm", "The clouds part around a distant throne - then fire."),
            ("hunt", "Slay the Fallen Choir Champion", "The final champion descends from the cathedral sky."),
            ("defend", "Protect the Oracle's beacon", "The Oracle needs time. Hold the beacon."),
            ("fight", "Break the last guardian wave", "The last chamber opens. There will be no more warnings."),
        ]),
    ],
    VOID_ID: [
        ("Dead Signal", "DERELICT DOCK", "Vex", "Guide", [
            ("search", "Find the dead communications console", "The station's distress signal has been looping for years."),
            ("collect", "Recover the memory-core fragments", "Someone erased most of the logs. Fragments remain, and so do scavenger drones."),
            ("fight", "Destroy the scavenger drone swarm", "The drones recognize the fragments and attack immediately."),
            ("puzzle", "Upload the recovered signal", "Enter the carrier sequence. The station answers."),
        ]),
        ("Reactor Sabotage", "REACTOR RING", "Commander Nyx", "Commander", [
            ("search", "Find the station access card", "The engineer's card is on the restricted side of the reactor."),
            ("stealth", "Steal the reactor access card from the drone ring", "Security drones sweep the ring. They do not miss."),
            ("hunt", "Destroy the Warden Drone", "A heavy security drone locks on. There is no quiet way out now."),
            ("gauntlet", "Cross the reactor vent ring", "Plasma vents cycle in the ring. Cross."),
            ("defend", "Defend the signal disruptor while it charges", "The disruptor needs time. Security floods the ring."),
        ]),
        ("Singularity Descent", "SINGULARITY SPIRE", "Kiro", "Engineer", [
            ("gauntlet", "Cross the failing descent catwalk", "Gravity pulses along the spire. Time your run."),
            ("collect", "Recover the anomaly cores", "Anomaly cores float in the dark. The swarm follows them."),
            ("survive", "Survive the anomaly swarm", "The pylon's failure summons things that should not be here."),
            ("puzzle", "Shut down the pylons in sequence", "The path to the Admiral is stable for a few moments."),
            ("hunt", "Destroy the Gate Sentinel", "Beyond this gate, the station answers to nobody."),
        ]),
    ],
}

QUEST_KIND_NAMES = {
    "search": "INVESTIGATION", "stealth": "INFILTRATION", "fight": "AMBUSH", "interact": "TASK",
    "collect": "SALVAGE", "defend": "DEFENCE", "puzzle": "PUZZLE", "hunt": "HUNT",
    "gauntlet": "GAUNTLET", "survive": "SURVIVAL", "escort": "ESCORT",
}

REALM_INFO = {
    EMBER_ID: {"giver": "Mira", "title": "Emberfall Expedition", "boss": "EMBERFANG, THE EMBER DRAGON", "lair": "DRAGON'S SANCTUM",
               "world_guide": "Ember Waystone", "merchant": "Forge Hermit", "adventurer": "Kael the Ashbound",
               "side": "The Last Ember Bell", "side_desc": "Three forgotten forge bells still hang somewhere in the ash. Ring all three and the mountain will remember its old paths.",
               "side_marks": "forge bell", "secret_boss": "THE ASHEN BEHEMOTH", "discovery": "EMBER FORGE RUN",
               "treasure": "CINDER BELL GROVE", "reward": 260},
    FROZEN_ID: {"giver": "Eira", "title": "Heart of Winter", "boss": "THE FROSTHEART COLOSSUS", "lair": "FROST CITADEL",
                "world_guide": "Niva", "merchant": "Mirror Scribe", "adventurer": "Seren the Mirrorwalker",
                "side": "The Three Silent Mirrors", "side_desc": "Three mirrors lie face-down in the snow. Wake them, and the lake will show you what it is hiding.",
                "side_marks": "silent mirror", "secret_boss": "THE MIRROR WARDEN", "discovery": "FROZEN MIRROR MAZE",
                "treasure": "MIRROR LAKE TREASURE", "reward": 380},
    STARFALL_ID: {"giver": "Solan", "title": "Shards of Heaven", "boss": "THE SERAPH OF THE FALLEN SKY", "lair": "SKY CATHEDRAL",
                  "world_guide": "Lumen", "merchant": "Star Cartographer", "adventurer": "Orin the Star-Seeker",
                  "side": "The Constellation Thief", "side_desc": "A thief stole three stars from my chart. They fell somewhere in the clouds. Return them to the sky.",
                  "side_marks": "stolen star", "secret_boss": "THE ASTRAL CLOCKWORK", "discovery": "STARFALL CONSTELLATION",
                  "treasure": "FALLEN CONSTELLATION GROVE", "reward": 650},
    VOID_ID: {"giver": "Nova", "title": "Void Signal", "boss": "THE VOID ADMIRAL", "lair": "ADMIRAL'S WAR ROOM",
              "world_guide": "Proxy", "merchant": "Null Merchant", "adventurer": "Veyra the Voidrunner",
              "side": "The Null Cartographer", "side_desc": "A cartographer vanished mapping this station. Her three survey beacons are still out there, broadcasting nothing.",
              "side_marks": "survey beacon", "secret_boss": "THE NULL MAW", "discovery": "VOID SIGNAL HUNT",
              "treasure": "NULL STATION VAULT", "reward": 500},
}


# ============================================================
# BOUNTIES (side-quest revamp), DIALOGUE RIDDLES, ORDERING RIDDLES
# ============================================================
# kinds: slay / elite / wanted / camp / survey / cache / riddle
SIDE_QUESTS = {
    EMBER_ID: [
        dict(id="e_cull", name="Ashfall Cull", kind="slay", n=10, enemy=["crawler"], req=0, text="Crawlers are eating the road. Kill 10 of them."),
        dict(id="e_cache", name="The Smith's Strongboxes", kind="cache", n=3, req=0, text="Dig up three strongboxes buried in the ash. Glowing ground gives them away."),
        dict(id="e_elite", name="Elite Hunter", kind="elite", n=3, req=1, text="Slay 3 elite monsters (the ones ringed in gold)."),
        dict(id="e_wanted", name="Wanted: Cinderjaw", kind="wanted", n=1, enemy=["brute"], req=1, target="CINDERJAW", text="A brute the size of a wagon. It has a name: Cinderjaw."),
        dict(id="e_survey", name="Chart the Vents", kind="survey", n=3, req=1, text="Walk to three survey stakes the scouts left behind. Mind the lava."),
        dict(id="e_camp", name="Raider Camp", kind="camp", n=1, enemy=["crawler", "shooter", "brute"], req=2, text="A raider camp squats somewhere off the road. Clear it out."),
        dict(id="e_riddle", name="The Ashen Sphinx", kind="riddle", n=3, req=2, text="The Sphinx near the keeper's stone asks three riddles. Answer all three in a row."),
    ],
    FROZEN_ID: [
        dict(id="f_cull", name="Wraith Winter", kind="slay", n=12, enemy=["wraith"], req=0, text="Slay 12 frost wraiths haunting the snowfields."),
        dict(id="f_cache", name="Frozen Supply Drops", kind="cache", n=3, req=0, text="Three supply drops lie buried under drifts. Dig them out."),
        dict(id="f_elite", name="Elite Hunter", kind="elite", n=3, req=1, text="Slay 3 elite monsters."),
        dict(id="f_wanted", name="Wanted: Rimefang", kind="wanted", n=1, enemy=["brute"], req=1, target="RIMEFANG", text="A giant of the glacier. Hunters call it Rimefang."),
        dict(id="f_survey", name="Mark the Safe Ice", kind="survey", n=3, req=1, text="Reach three marker poles on the far side of the lakes."),
        dict(id="f_camp", name="Rookery Camp", kind="camp", n=1, enemy=["wraith", "mage", "shooter"], req=2, text="A wraith rookery has dug in. Break it."),
        dict(id="f_riddle", name="The Winter Oracle", kind="riddle", n=3, req=2, text="The Oracle poses three riddles. One wrong answer and you start over."),
    ],
    VOID_ID: [
        dict(id="v_cull", name="Drone Purge", kind="slay", n=6, enemy=["drone"], req=0, text="Destroy 6 detecting drones. They are shielded, they dodge, and they hit hard."),
        dict(id="v_cache", name="Salvage Pods", kind="cache", n=3, req=0, text="Three escape pods drifted down. Crack them open."),
        dict(id="v_elite", name="Elite Hunter", kind="elite", n=4, req=1, text="Destroy 4 elite units."),
        dict(id="v_wanted", name="Wanted: Unit 7", kind="wanted", n=1, enemy=["drone"], req=1, target="UNIT 7", text="A rogue security drone, serial 7. Heavily upgraded."),
        dict(id="v_survey", name="Signal Triangulation", kind="survey", n=3, req=1, text="Stand at three relay points to triangulate the signal."),
        dict(id="v_camp", name="Drone Nest", kind="camp", n=1, enemy=["drone", "guard", "mage"], req=2, text="A nest of drones guards a stolen core. Wipe it out."),
        dict(id="v_riddle", name="The Null Oracle", kind="riddle", n=3, req=2, text="The Oracle's riddles are math and logic. Three correct in a row."),
    ],
    STARFALL_ID: [
        dict(id="s_cull", name="Sky Cull", kind="slay", n=10, enemy=["wraith", "mage"], req=0, text="Slay 10 wraiths or mages of the fallen sky."),
        dict(id="s_cache", name="Fallen Star Shards", kind="cache", n=3, req=0, text="Three star shards lie where they fell. Gather them."),
        dict(id="s_elite", name="Elite Hunter", kind="elite", n=4, req=1, text="Slay 4 elite monsters."),
        dict(id="s_wanted", name="Wanted: The Gilded Sentinel", kind="wanted", n=1, enemy=["guard"], req=1, target="GILDED SENTINEL", text="A choir guardian that never fell silent."),
        dict(id="s_survey", name="Chart the Star Gates", kind="survey", n=3, req=1, text="Stand beneath three constellations to chart the gates."),
        dict(id="s_camp", name="Choir Remnant Camp", kind="camp", n=1, enemy=["wraith", "mage", "shooter", "guard"], req=2, text="The choir's remnants camp in the clouds. Disperse them."),
        dict(id="s_riddle", name="The Star Sphinx", kind="riddle", n=3, req=2, text="The Sphinx asks three riddles of the old sky. Answer all three."),
    ],
}
BOUNTY_BY_ID = {q["id"]: (rid, q) for rid, qs in SIDE_QUESTS.items() for q in qs}
KEEPERS = {EMBER_ID: "Ashen Sphinx", FROZEN_ID: "Winter Oracle", VOID_ID: "Null Oracle", STARFALL_ID: "Star Sphinx"}

# (question, [options], index of the right one). Three are asked per attempt, options reshuffled.
RIDDLE_BANK = {
    EMBER_ID: [
        ("The more of me you take, the more you leave behind. What am I?", ["Footsteps", "Embers", "Coins", "Shadows"], 0),
        ("I have cities but no houses, mountains but no trees, and water but no fish.", ["A map", "A bell", "A forge", "A coin"], 0),
        ("I eat, I breathe, and I die the moment I touch water.", ["Fire", "A dragon", "A smith", "Smoke"], 0),
        ("A smith forges 3 swords a day for 3 days, then rests 2 days, then repeats. How many swords in 10 days?", ["18", "21", "24", "30"], 0),
        ("A furnace burns 3 logs the first hour, 6 the second, 9 the third, and so on. How many logs in 5 hours?", ["45", "30", "36", "40"], 0),
        ("Two guards stand at two doors: one always lies, one always tells the truth. One door is safe. You may ask one question. Which is best?",
         ["Ask one what the other says; do the opposite", "Ask one which door is safe; obey", "Ask each of them their name", "Flip a coin"], 0),
    ],
    FROZEN_ID: [
        ("I come out at night without being called, and I am lost in the day without being stolen.", ["Stars", "Wraiths", "Dreams", "Snowflakes"], 0),
        ("A lake holds 100 units of ice. Each day 10% of the remaining ice melts. How much remains after 2 days?", ["81", "80", "79", "90"], 0),
        ("Three travellers cross a bridge at night with one lantern, two at a time. They take 1, 2 and 5 minutes. Fastest total time?", ["8 minutes", "9 minutes", "10 minutes", "7 minutes"], 0),
        ("I am taken from a mine and shut in a wooden case from which I am never released, yet nearly everyone uses me.", ["Pencil lead", "Iron", "Frost", "A key"], 0),
        ("What comes next: 2, 6, 12, 20, 30, ... ?", ["42", "40", "44", "36"], 0),
        ("'Brothers and sisters I have none, but that man's father is my father's son.' Whose portrait is it?", ["His own son's", "His own", "His father's", "His nephew's"], 0),
    ],
    VOID_ID: [
        ("A reactor doubles its charge every hour and is full after 12 hours. When was it half full?", ["11 hours", "6 hours", "10 hours", "9 hours"], 0),
        ("What comes next: 1, 1, 2, 3, 5, 8, 13, ... ?", ["21", "18", "20", "26"], 0),
        ("Which of these numbers is prime?", ["59", "51", "57", "63"], 0),
        ("One drone circles the ring in 12 minutes, another in 18. They cross the gate together now. When next together?", ["36 minutes", "24 minutes", "30 minutes", "72 minutes"], 0),
        ("A signal halves at every relay. After 6 relays you measure 2 units. What was the original strength?", ["128", "64", "72", "12"], 0),
        ("Eight cores look identical; one is heavier. With a balance scale, what is the fewest weighings that always finds it?", ["2", "1", "3", "4"], 0),
    ],
    STARFALL_ID: [
        ("I am always coming but never arrive. What am I?", ["Tomorrow", "Dawn", "A comet", "A star"], 0),
        ("Delta outshines Alpha. Alpha outshines Beta. Gamma is dimmer than Beta. Which star is the second dimmest?", ["Beta", "Alpha", "Gamma", "Delta"], 0),
        ("Comets return every 12, 8 and 6 years. All appear this year. In how many years do all three next appear together?", ["24", "48", "36", "12"], 0),
        ("How many times can you subtract 5 from 25?", ["Once", "Five times", "Never", "Four times"], 0),
        ("Half the choir flew away, then a third of those who remained left. 12 are still singing. How many were there at first?", ["36", "24", "48", "30"], 0),
        ("Knights always tell the truth; liars always lie. A says: 'We are both liars.' What are A and B?", ["A lies, B is truthful", "Both are truthful", "Both lie", "A is truthful, B lies"], 0),
    ],
}

# Ordering riddles are generated: a random order is chosen, then true clues are added until exactly one order fits.
ORDER_LABELS = {
    EMBER_ID: ["Cinder", "Iron", "Ash", "Glass", "Brass", "Copper"],
    FROZEN_ID: ["Rime", "Hoar", "Sleet", "Glint", "Frost", "Drift"],
    VOID_ID: ["Alpha", "Delta", "Sigma", "Omega", "Theta", "Kappa"],
    STARFALL_ID: ["Vega", "Lyra", "Sirius", "Altair", "Deneb", "Rigel"],
}
ORDER_INTRO = {
    EMBER_ID: "Wake the bells in the one true order.",
    FROZEN_ID: "Touch the mirrors in the one true order.",
    VOID_ID: "Ping the beacons in the one true order.",
    STARFALL_ID: "Light the stars in the one true order.",
}
ORDER_SIZES = {EMBER_ID: (4, 4, 5), FROZEN_ID: (4, 5, 5), VOID_ID: (5, 5, 6), STARFALL_ID: (5, 6, 6)}


def gen_ordering_riddle(labels, rng):
    """Returns (clue strings, solution as list of labels).  Guaranteed unique."""
    import itertools
    n = len(labels)
    sol = labels[:]
    rng.shuffle(sol)
    pos = {l: i for i, l in enumerate(sol)}
    cons = []   # (text, predicate over a position dict)
    for a in labels:
        for b in labels:
            if a == b:
                continue
            if pos[a] < pos[b]:
                cons.append((f"{a} comes before {b}.", (lambda p, a=a, b=b: p[a] < p[b])))
            if pos[a] == pos[b] + 1:
                cons.append((f"{a} comes right after {b}.", (lambda p, a=a, b=b: p[a] == p[b] + 1)))
            if a < b and abs(pos[a] - pos[b]) > 1:
                cons.append((f"{a} and {b} are never side by side.", (lambda p, a=a, b=b: abs(p[a] - p[b]) > 1)))
            for c in labels:
                if c in (a, b):
                    continue
                if b < c and (pos[b] < pos[a] < pos[c] or pos[c] < pos[a] < pos[b]):
                    cons.append((f"{a} sits somewhere between {b} and {c}.", (lambda p, a=a, b=b, c=c: p[b] < p[a] < p[c] or p[c] < p[a] < p[b])))
        if pos[a] != 0:
            cons.append((f"{a} is not first.", (lambda p, a=a: p[a] != 0)))
        if pos[a] != n - 1:
            cons.append((f"{a} is not last.", (lambda p, a=a: p[a] != n - 1)))
        cons.append((f"{a} is in an {'odd' if pos[a] % 2 == 0 else 'even'} place.", (lambda p, a=a, par=pos[a] % 2: p[a] % 2 == par)))
    perms = [dict(zip(labels, pr)) for pr in itertools.permutations(range(n))]
    rng.shuffle(cons)
    chosen = []
    alive = perms
    for text, pred in cons:
        new = [p for p in alive if pred(p)]
        if len(new) < len(alive):
            chosen.append((text, pred))
            alive = new
        if len(alive) == 1:
            break
    # prune clues that are not needed
    for item in list(chosen):
        rest = [c for c in chosen if c is not item]
        if len([p for p in perms if all(pred(p) for _, pred in rest)]) == 1:
            chosen = rest
    rng.shuffle(chosen)
    return [t for t, _ in chosen], sol


class QuestLine:
    def __init__(self, rid, index):
        self.rid = rid
        self.index = index
        title, area, giver, role, tasks = QUEST_DATA[rid][index]
        self.title, self.area, self.giver, self.giver_role, self.tasks = title, area, giver, role, tasks
        self.started = False
        self.complete = False
        self.step = 0

    @property
    def task(self):
        if not self.started or self.complete or self.step >= len(self.tasks):
            return None
        return self.tasks[self.step]

    @property
    def task_label(self):
        t = self.task
        return t[1] if t else ("COMPLETE" if self.complete else "Not started")

    def advance(self):
        self.step += 1
        if self.step >= len(self.tasks):
            self.complete = True
        return self.complete

    def to_dict(self):
        return {"started": self.started, "complete": self.complete, "step": self.step}

    def load(self, d):
        if isinstance(d, dict):
            self.started = bool(d.get("started", False))
            self.complete = bool(d.get("complete", False))
            self.step = int(clamp(int(d.get("step", 0) or 0), 0, len(self.tasks)))
            if self.complete:
                self.started = True
                self.step = len(self.tasks)


class RealmState:
    def __init__(self, rid):
        self.rid = rid
        self.lines = [QuestLine(rid, i) for i in range(3)]
        self.boss_defeated = False
        self.side = "hidden"   # hidden -> active -> return -> complete
        self.side_step = 0
        self.side_found = [False, False, False]
        self.discovery_clears = 0
        self.treasure_claimed = False
        self.secret_defeated = False
        self.ghost_bonus = 0
        self.bounty = {}      # id -> {"s": 0 new / 1 active / 2 done, "p": progress, "hit": [bool, ...]}

    def current_line(self):
        for line in self.lines:
            if line.started and not line.complete:
                return line
        return None

    def next_line_to_start(self):
        for i, line in enumerate(self.lines):
            if not line.started:
                if i == 0 or self.lines[i - 1].complete:
                    return line
                return None
        return None

    def completed(self):
        return sum(1 for line in self.lines if line.complete)

    def boss_unlocked(self):
        return self.lines[2].complete

    def to_dict(self):
        return {"lines": [l.to_dict() for l in self.lines], "boss_defeated": self.boss_defeated, "side": self.side,
                "side_found": self.side_found, "discovery_clears": self.discovery_clears,
                "treasure_claimed": self.treasure_claimed, "secret_defeated": self.secret_defeated,
                "bounty": {k: {"s": v["s"], "p": v["p"], "hit": list(v["hit"])} for k, v in self.bounty.items()}}

    def load(self, d):
        if not isinstance(d, dict):
            return
        for line, ld in zip(self.lines, d.get("lines", []) or []):
            line.load(ld)
        self.boss_defeated = bool(d.get("boss_defeated", False))
        side = d.get("side", "hidden")
        self.side = side if side in ("hidden", "active", "return", "complete") else "hidden"
        found = d.get("side_found", [False] * 3)
        self.side_found = [bool(x) for x in (list(found) + [False] * 3)[:3]]
        self.discovery_clears = int(d.get("discovery_clears", 0) or 0)
        self.treasure_claimed = bool(d.get("treasure_claimed", False))
        self.secret_defeated = bool(d.get("secret_defeated", False))
        self.bounty = {}
        raw = d.get("bounty", {}) or {}
        if isinstance(raw, dict):
            for q in SIDE_QUESTS[self.rid]:
                v = raw.get(q["id"])
                if isinstance(v, dict):
                    hit = [bool(x) for x in (list(v.get("hit", [])) + [False] * 3)[:3]]
                    self.bounty[q["id"]] = {"s": int(clamp(int(v.get("s", 0) or 0), 0, 2)), "p": max(0, int(v.get("p", 0) or 0)), "hit": hit}

    def bstate(self, qid):
        return self.bounty.setdefault(qid, {"s": 0, "p": 0, "hit": [False, False, False]})

    def active_bounties(self):
        return [q for q in SIDE_QUESTS[self.rid] if self.bounty.get(q["id"], {}).get("s") == 1]


# ============================================================
# TILE PAINTING
# ============================================================

def paint_tree(surf, x, y, leaf=(36, 84, 52), leaf2=(52, 108, 66)):
    pygame.draw.rect(surf, (73, 53, 39), (x + 12, y + 16, 8, 14))
    pygame.draw.circle(surf, leaf, (x + 16, y + 12), 15)
    pygame.draw.circle(surf, leaf2, (x + 12, y + 8), 8)


def paint_building(surf, rect, wall, roof, trim, label=None, door=True):
    pygame.draw.rect(surf, wall, rect)
    pygame.draw.rect(surf, mix(wall, BLACK, .3), rect, 3)
    roof_pts = [(rect.left - 10, rect.top + 26), (rect.centerx, rect.top - 22), (rect.right + 10, rect.top + 26)]
    pygame.draw.polygon(surf, roof, roof_pts)
    pygame.draw.polygon(surf, mix(roof, BLACK, .35), roof_pts, 3)
    for wx in (rect.left + 14, rect.right - 34):
        pygame.draw.rect(surf, (35, 32, 40), (wx, rect.top + 40, 20, 16))
        pygame.draw.rect(surf, trim, (wx, rect.top + 40, 20, 16), 2)
    if door:
        pygame.draw.rect(surf, (38, 30, 28), (rect.centerx - 13, rect.bottom - 40, 26, 40))
        pygame.draw.rect(surf, trim, (rect.centerx - 13, rect.bottom - 40, 26, 40), 2)
    if label:
        img = render_text(label, 18, trim)
        bg = pygame.Rect(0, 0, img.get_width() + 12, 20)
        bg.center = (rect.centerx, rect.top + 14)
        pygame.draw.rect(surf, (20, 18, 24), bg)
        surf.blit(img, (bg.x + 6, bg.y + 2))


# ============================================================
# HOMEWORLD
# ============================================================

class HomeWorld(TileWorld):
    key = "home"
    title = "HOMEWORLD"
    hub = True
    CENTER = (36, 26)

    def __init__(self):
        super().__init__(72, 52, "g")
        self.accent = GOLD
        rng = random.Random(20)
        for _ in range(60):
            cx, cy = rng.randrange(3, 69), rng.randrange(3, 49)
            if math.hypot(cx - 36, cy - 26) < 13:
                continue
            self.set_disc(cx, cy, rng.randrange(1, 4), "a", only="g")
        self.set_disc(36, 26, 8.5, "s")
        self.set_rect(6, 25, 60, 3, "p", only="ga")
        self.set_rect(35, 4, 3, 44, "p", only="ga")
        for cx, cy, r in [(13, 12, 4), (60, 40, 4.5), (12, 40, 3.5), (58, 10, 3)]:
            self.set_disc(cx, cy, r, "W")
        # village buildings (tile rects)
        self.buildings = [
            ((41, 15, 7, 5), (95, 70, 55), (150, 60, 40), EMBER, "BRAM'S FORGE"),
            ((25, 15, 7, 5), (70, 95, 70), (60, 120, 70), GREEN, "PIP'S HERBS"),
            ((25, 32, 7, 5), (100, 80, 60), (150, 100, 60), ORANGE, "WREN'S KITCHEN"),
            ((41, 32, 7, 5), (70, 80, 105), (60, 90, 140), BLUE, "VALE'S MAPS"),
        ]
        for (x, y, w, h), *_ in self.buildings:
            self.set_rect(x, y, w, h, "B")
        self.grid[38][45] = "C"   # Milo's arcade cabinet
        self.grid[38][46] = "C"
        trees = []
        for _ in range(140):
            tx, ty = rng.randrange(1, 71), rng.randrange(1, 51)
            if math.hypot(tx - 36, ty - 26) < 14 or self.grid[ty][tx] not in "ga":
                continue
            if abs(ty - 26) <= 3 or abs(tx - 36) <= 3:
                continue
            self.grid[ty][tx] = "T"
            trees.append((tx, ty))
        for x in range(self.tw):
            self.grid[0][x] = self.grid[self.th - 1][x] = "T"
        for y in range(self.th):
            self.grid[y][0] = self.grid[y][self.tw - 1] = "T"
        # Key positions
        self.gates = {EMBER_ID: (8, 26), FROZEN_ID: (36, 6), VOID_ID: (64, 26), STARFALL_ID: (36, 46)}
        key_tiles = [self.CENTER, (36, 20), (44, 21), (28, 21), (28, 31), (44, 31), (43, 39)] + [(gx + (2 if gx < 36 else -2 if gx > 36 else 0), gy + (2 if gy < 26 else -2 if gy > 26 else 0)) for gx, gy in self.gates.values()]
        for kt in key_tiles:
            self.set_disc(kt[0], kt[1], 1.5, "p", only="Ta")
        self.ensure_reachable(self.CENTER, key_tiles, "g")
        self.build_interactables()
        self.spawn_points = []
        for _ in range(400):
            tx, ty = rng.randrange(3, 69), rng.randrange(3, 49)
            if math.hypot(tx - 36, ty - 26) < 15 or self.grid[ty][tx] in self.SOLID:
                continue
            if any(math.hypot(tx - gx, ty - gy) < 6 for gx, gy in self.gates.values()):
                continue
            self.spawn_points.append(self.tile_center(tx, ty))
        self.respawn_timer = 0
        for i in range(12):
            self.spawn_wild(rng)

    def spawn_wild(self, rng=random):
        if not self.spawn_points:
            return
        for _ in range(10):
            p = rng.choice(self.spawn_points)
            if dist(p, game.player.pos) > 420 if game.player else True:
                break
        kind = rng.choice(["crawler", "crawler", "wraith", "shooter", "brute"])
        self.add_enemy(Enemy(p, kind, .85))

    def spawn(self):
        return self.tile_center(36, 29)

    def build_interactables(self):
        tc = self.tile_center
        self.interactables = []

        for rid, (gx, gy) in self.gates.items():
            info = REALM_INFO[rid]
            npc_tile = (gx + (2 if gx < 36 else -2 if gx > 36 else 0), gy + (2 if gy < 26 else -2 if gy > 26 else 0))
            hair = [(160, 50, 30), (200, 220, 240), (230, 200, 100), (40, 30, 60)][rid]
            self.interactables.append(NPC(info["giver"], f"{REALM_SHORT[rid]} Quest Giver", tc(*npc_tile), REALM_COLORS[rid],
                                          (lambda r=rid: game.talk_quest_giver(r)), (lambda r=rid: game.giver_marker(r)), hair))
            self.interactables.append(Interactable(tc(gx, gy), (lambda r=rid: f"{REALM_SHORT[r]} Gate ({game.home_quest_status(r)})"),
                                                   (lambda r=rid: game.talk_quest_giver(r)), 60,
                                                   draw_fn=(lambda s, p, it, r=rid: draw_portal(s, p, REALM_COLORS[r], self.time, REALM_NAMES[r], 28, game.home_quest_status(r) in ("active", "ready", "done")))))
        self.interactables += [
            NPC("Bram", "Blacksmith", tc(44, 21), EMBER, lambda: game.open_bram(), None, (40, 30, 30), (90, 70, 60)),
            NPC("Pip", "Herbalist", tc(28, 21), GREEN, lambda: game.open_pip(), None, (140, 90, 40)),
            NPC("Wren", "Cook", tc(28, 31), ORANGE, lambda: game.open_wren(), None, (200, 120, 60)),
            NPC("Vale", "Cartographer", tc(44, 31), BLUE, lambda: game.talk_vale(), None, (80, 80, 90)),
            NPC("Milo", "Arcade Master", tc(43, 39), GOLD, lambda: game.talk_milo(), lambda: ("*", GOLD), (240, 220, 120), (120, 60, 160)),
            Interactable(tc(36, 20), "Enter the Dungeon", lambda: game.enter_dungeon_hub(), 60,
                         draw_fn=lambda s, p, it: draw_portal(s, p, PURPLE, self.time, "DUNGEON", 30)),
        ]

    def update(self, dt):
        super().update(dt)
        self.respawn_timer -= dt
        if self.respawn_timer <= 0:
            self.respawn_timer = 12
            if len(self.enemies) < 12:
                self.spawn_wild()

    def objective(self):
        for rid in PROGRESSION:
            status = game.home_quest_status(rid)
            giver = REALM_INFO[rid]["giver"]
            pos = self.tile_center(*self.gates[rid])
            if status == "available":
                return f"Talk to {giver} to begin {REALM_INFO[rid]['title']}", pos
            if status == "active":
                return f"Travel to the {REALM_NAMES[rid].title()} through {giver}'s gate", pos
            if status == "ready":
                return f"Return to {giver} for your reward", pos
        return "All realms restored. Explore, hunt secrets, clear the dungeon.", None

    def render_tile(self, surf, tx, ty, ch, rect, rng):
        if ch in "gT":
            c = (43 + rng.randrange(6), 72 + rng.randrange(8), 54 + rng.randrange(5))
        elif ch == "a":
            c = (54 + rng.randrange(6), 55 + rng.randrange(5), 60)
        elif ch == "p":
            c = (110 + rng.randrange(8), 90 + rng.randrange(6), 66)
        elif ch == "s":
            c = (84 + rng.randrange(8), 86 + rng.randrange(6), 94)
        elif ch == "W":
            c = (38, 83 + rng.randrange(6), 110)
        else:
            c = (80, 84, 90)
        pygame.draw.rect(surf, c, rect)
        if ch == "g" and rng.random() < .18:
            pygame.draw.rect(surf, (62, 98, 66), (rect.x + rng.randrange(4, 24), rect.y + rng.randrange(4, 22), 2, 6))
        if ch == "g" and rng.random() < .03:
            pygame.draw.circle(surf, random.Random(tx * 99 + ty).choice([(230, 200, 90), (220, 120, 150), (180, 180, 240)]), (rect.x + 16, rect.y + 16), 3)
        if ch == "s":
            pygame.draw.rect(surf, (70, 72, 80), rect, 1)
        if ch == "W" and rng.random() < .2:
            pygame.draw.line(surf, (90, 150, 180), (rect.x + 6, rect.y + 14), (rect.x + 18, rect.y + 14), 1)
        if ch == "T":
            paint_tree(surf, rect.x, rect.y - 4)

    def render_static(self, surf):
        for (x, y, w, h), wall, roof, trim, label in self.buildings:
            paint_building(surf, pygame.Rect(x * TILE, y * TILE, w * TILE, h * TILE), wall, roof, trim, label)
        # Milo's arcade cabinets
        for tx in (45, 46):
            r = pygame.Rect(tx * TILE + 2, 38 * TILE - 14, TILE - 4, TILE + 12)
            pygame.draw.rect(surf, (90, 40, 130), r)
            pygame.draw.rect(surf, GOLD, r, 2)
            pygame.draw.rect(surf, (30, 200, 180), (r.x + 4, r.y + 6, r.width - 8, 14))
        draw_text(surf, "MILO'S ARCADE - FREE PLAY", (46 * TILE, 37 * TILE - 30), GOLD, 18, center=True)
        # plaza ring
        pygame.draw.circle(surf, (110, 112, 120), (36 * TILE + 16, 26 * TILE + 16), 8 * TILE, 3)
        draw_text(surf, "ASHFALL VILLAGE", (36 * TILE + 16, 26 * TILE + 4), (200, 200, 210), 22, center=True)


# ============================================================
# REALM WORLDS
# ============================================================

REALM_ENEMY_TYPES = {
    EMBER_ID: ["crawler", "brute", "shooter", "crawler"],
    FROZEN_ID: ["wraith", "shooter", "mage", "brute"],
    STARFALL_ID: ["wraith", "mage", "shooter", "guard"],
    VOID_ID: ["drone", "wraith", "brute", "drone", "mage", "guard"],
}

REALM_PALETTE = {
    #               ground                path              rock              feature
    EMBER_ID: ((72, 36, 26), (112, 54, 30), (60, 44, 40), (170, 60, 20)),
    FROZEN_ID: ((150, 175, 195), (110, 145, 170), (90, 120, 150), (120, 190, 230)),
    STARFALL_ID: ((70, 66, 104), (150, 138, 186), (110, 100, 150), (12, 12, 30)),
    VOID_ID: ((22, 22, 44), (62, 46, 92), (48, 42, 70), (6, 4, 14)),
}


ENCLAVES = {EMBER_ID: (7, 7), FROZEN_ID: (6, 19), STARFALL_ID: (66, 17), VOID_ID: (7, 19)}


class RealmWorld(TileWorld):
    hub = True

    def __init__(self, rid):
        super().__init__(72, 52, ".")
        self.rid = rid
        self.key = f"realm{rid}"
        self.title = REALM_NAMES[rid]
        self.accent = REALM_COLORS[rid]
        self.info = REALM_INFO[rid]
        self.state = game.realm_states[rid]
        rng = random.Random(100 + rid)
        # --- key layout (tile coordinates) ---
        self.spawn_tile = (36, 45)
        self.portal_tile = (36, 48)
        self.building_rects = [(12, 25, 7, 5), (33, 9, 7, 5), (55, 25, 7, 5)]
        self.doors = [(x + w // 2, y + h) for x, y, w, h in self.building_rects]
        self.boss_rect = (61, 39, 6, 5)
        self.boss_door = (64, 44)
        self.enclave = ENCLAVES[rid]
        self.merchant_tile = ENCLAVES[rid]
        self.board_tile = (29, 42)
        self.keeper_tile = (43, 42)
        self.treasure_tile = (51, 6)
        self.secret_gate_tile = (65, 6)
        self.adventurer_tile = (61, 9)
        self.discovery_tile = (7, 44)
        self.guide_tile = (31, 46)
        self.shop_tile = (41, 46)
        self.side_tiles = [[(24, 19), (47, 21), (25, 41)], [(22, 17), (46, 23), (52, 40)],
                           [(18, 38), (44, 20), (66, 30)], [(20, 17), (48, 22), (67, 15)]][rid]
        self.paths = [(35, 33, 3, 14), (13, 32, 48, 3), (35, 15, 3, 18), (57, 30, 3, 4), (14, 30, 3, 3),
                      (35, 7, 3, 9), (35, 7, 30, 3), (63, 33, 3, 12), (6, 32, 9, 3), (6, 32, 3, 13)]
        for x, y, w, h in self.paths:
            self.set_rect(x, y, w, h, "p")
        # --- terrain features ---
        feature = {EMBER_ID: "L", FROZEN_ID: "I", STARFALL_ID: "X", VOID_ID: "X"}[rid]
        protected = self.protected_tiles()
        for _ in range(16 if feature != "I" else 9):
            cx, cy = rng.randrange(4, 68), rng.randrange(4, 48)
            r = rng.uniform(1.5, 3.2) if feature != "I" else rng.uniform(3, 5)
            if any(math.hypot(cx - px, cy - py) < r + 2.5 for px, py in protected):
                continue
            self.set_disc(cx, cy, r, feature, only=".")
        for _ in range(130):
            tx, ty = rng.randrange(2, 70), rng.randrange(2, 50)
            if self.grid[ty][tx] != "." or any(abs(tx - px) <= 2 and abs(ty - py) <= 2 for px, py in protected):
                continue
            self.grid[ty][tx] = "R"
        # buildings & boss lair
        for x, y, w, h in self.building_rects:
            self.set_rect(x, y, w, h, "B")
        bx, by, bw, bh = self.boss_rect
        self.set_rect(bx, by, bw, bh, "B")
        # Hidden merchant enclave: a ring of rock with one narrow gap facing east.
        ex, ey = self.enclave
        for ty in range(ey - 5, ey + 6):
            for tx in range(ex - 5, ex + 6):
                if 0 < tx < 71 and 0 < ty < 51:
                    d = math.hypot(tx - ex, ty - ey)
                    if 3.6 <= d <= 5.2:
                        # a short stretch of the ring is FAKE rock ("F"): it looks solid but can be walked through
                        toward = math.atan2(self.th / 2 - ey, self.tw / 2 - ex)
                        ang = math.atan2(ty - ey, tx - ex)
                        self.grid[ty][tx] = "F" if angle_diff(ang, toward) < .26 else "R"
                    elif d < 3.6:
                        self.grid[ty][tx] = "."
        # world border
        for x in range(self.tw):
            self.grid[0][x] = self.grid[self.th - 1][x] = "R"
        for y in range(self.th):
            self.grid[y][0] = self.grid[y][self.tw - 1] = "R"
        stand = [self.board_tile, self.keeper_tile, self.spawn_tile, self.portal_tile, self.boss_door, self.merchant_tile, self.treasure_tile,
                 self.secret_gate_tile, self.adventurer_tile, self.discovery_tile, self.guide_tile, self.shop_tile] + self.doors + self.side_tiles + [self.giver_tile(i) for i in range(3)]
        for st in stand:
            if self.grid[st[1]][st[0]] in self.SOLID or self.grid[st[1]][st[0]] in "LX":
                self.grid[st[1]][st[0]] = "."
        self.ensure_reachable(self.spawn_tile, stand, ".")
        # realm mechanics
        self.vents = [V(18, 16), V(28, 37), V(50, 18)]
        self.wells = [V(23, 22), V(45, 27), V(56, 16)]
        self.star_gates = [V(20, 22), V(30, 13), V(47, 36), V(62, 18)]
        self.gate_cd = 0
        self.mechanic_t = 0.0
        self.build_interactables()
        self.respawn_timer = 10
        for _ in range(38):
            self.spawn_enemy(rng, initial=True)

    def protected_tiles(self):
        pts = [self.board_tile, self.keeper_tile, self.spawn_tile, self.portal_tile, self.boss_door, self.treasure_tile, self.secret_gate_tile,
               self.adventurer_tile, self.discovery_tile, self.guide_tile, self.shop_tile] + self.doors + self.side_tiles
        for x, y, w, h in self.paths:
            for ty in range(y, y + h, 2):
                for tx in range(x, x + w, 2):
                    pts.append((tx, ty))
        for x, y, w, h in self.building_rects + [self.boss_rect]:
            pts.append((x + w // 2, y + h // 2))
        return pts

    def bounty_points(self, qi, n):
        rng = random.Random(self.rid * 7919 + qi * 104729)
        reach = self.reachable_from(*self.spawn_tile)
        keys = [self.spawn_tile, self.portal_tile, self.boss_door, self.merchant_tile, self.treasure_tile] + self.doors + self.side_tiles
        cands = [(x, y) for (x, y) in reach if 5 < x < 66 and 5 < y < 46 and self.grid[y][x] in ".p"
                 and math.hypot(x - self.spawn_tile[0], y - self.spawn_tile[1]) > 11 and all(math.hypot(x - kx, y - ky) > 4 for kx, ky in keys)
                 and all(self.grid[y + dy][x + dx] in ".p" for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
        cands.sort()
        out = []
        for _ in range(500):
            if len(out) >= n or not cands:
                break
            c = rng.choice(cands)
            if all(math.hypot(c[0] - o[0], c[1] - o[1]) > 12 for o in out):
                out.append(c)
        while len(out) < n:
            out.append(self.spawn_tile)
        return [self.tile_center(*c) for c in out]

    def random_far_point(self, min_dist=600):
        for _ in range(60):
            tx, ty = random.randrange(4, 68), random.randrange(4, 48)
            if self.grid[ty][tx] in self.SOLID or self.grid[ty][tx] in "LXF":
                continue
            p = self.tile_center(tx, ty)
            if dist(p, game.player.pos) >= min_dist and math.hypot(tx - self.enclave[0], ty - self.enclave[1]) > 7:
                return p
        return self.tile_center(*self.spawn_tile) + V(300, 0)

    def draw_board(self, surf, p):
        x, y = int(p.x), int(p.y)
        st = self.state
        pygame.draw.rect(surf, (0, 0, 0), (x - 24, y + 14, 48, 8))
        pygame.draw.rect(surf, (100, 70, 44), (x - 4, y - 4, 8, 28))
        pygame.draw.rect(surf, (128, 92, 58), (x - 26, y - 34, 52, 36))
        pygame.draw.rect(surf, (64, 44, 30), (x - 26, y - 34, 52, 36), 3)
        for k, (dx, dy) in enumerate(((-18, -28), (-2, -29), (10, -25), (-12, -14), (4, -14))):
            pygame.draw.rect(surf, PARCHMENT, (x + dx, y + dy, 11, 10))
        avail = any(st.bstate(q["id"])["s"] == 0 and st.completed() >= q["req"] for q in SIDE_QUESTS[self.rid])
        if avail:
            draw_text(surf, "!", (x, y - 52 + int(math.sin(self.time * 4) * 2)), GOLD, 22, center=True)

    def draw_cache(self, surf, p):
        x, y = int(p.x), int(p.y)
        glow(surf, (x, y), 30, GOLD, 50 + int(math.sin(self.time * 3 + x) * 14))
        pygame.draw.ellipse(surf, (60, 46, 36), (x - 12, y - 4, 24, 12))
        pygame.draw.line(surf, GOLD, (x - 5, y), (x + 5, y), 2)

    def giver_tile(self, i):
        dx, dy = self.doors[i]
        return (dx - 3, dy + 1)

    def spawn(self):
        return self.tile_center(*self.spawn_tile)

    def spawn_enemy(self, rng=random, initial=False):
        for _ in range(40):
            tx, ty = rng.randrange(3, 69), rng.randrange(3, 49)
            if self.grid[ty][tx] in self.SOLID or self.grid[ty][tx] in "LX":
                continue
            p = self.tile_center(tx, ty)
            if math.hypot(tx - self.spawn_tile[0], ty - self.spawn_tile[1]) < 11:
                continue
            if math.hypot(tx - self.enclave[0], ty - self.enclave[1]) < 7:
                continue
            if not initial and dist(p, game.player.pos) < 500:
                continue
            kind = rng.choice(REALM_ENEMY_TYPES[self.rid])
            en = self.add_enemy(Enemy(p, kind, REALM_DIFFICULTY[self.rid], REALM_COLORS[self.rid]))
            if rng.random() < .07 + .03 * PROGRESSION.index(self.rid):
                make_elite(en)
            return

    # ---------------- interactables ----------------
    def build_interactables(self):
        tc = self.tile_center
        rid = self.rid
        col = self.accent
        info = self.info
        st = self.state
        self.interactables = [
            Interactable(tc(*self.portal_tile), "Return to the Homeworld", lambda: game.go_home(), 60,
                         draw_fn=lambda s, p, it: draw_portal(s, p, col, self.time, "HOME PORTAL", 26)),
            NPC(info["world_guide"], "World Guide", tc(*self.guide_tile), col, lambda: game.talk_world_guide(rid),
                None, (200, 200, 210)) if rid != EMBER_ID else
            Interactable(tc(*self.guide_tile), "Read the Ember Waystone", lambda: game.talk_world_guide(rid), 60,
                         draw_fn=lambda s, p, it: self.draw_waystone(s, p)),
            NPC("Wandering Trader", "World Shop", tc(*self.shop_tile), GOLD, lambda: game.open_realm_shop(rid), None, (90, 60, 40), (110, 80, 60)),
            NPC(info["merchant"], "Secret Merchant", tc(*self.merchant_tile), PURPLE, lambda: game.talk_secret_merchant(rid),
                lambda: game.merchant_marker(rid), (30, 30, 30), (60, 40, 80),
                visible=lambda: dist(game.player.pos, tc(*self.merchant_tile)) < 150),
            Interactable(tc(*self.board_tile), "Read the Bounty Board", lambda: game.open_board(rid), 62,
                         draw_fn=lambda s, p, it: self.draw_board(s, p)),
            NPC(KEEPERS[rid], "Riddle Keeper", tc(*self.keeper_tile), GOLD, lambda: game.talk_keeper(rid),
                lambda: (("?", GOLD) if st.bstate(SIDE_QUESTS[rid][6]["id"])["s"] == 1 else None), (200, 190, 160), (110, 90, 150)),
            NPC(info["adventurer"], "Adventurer", tc(*self.adventurer_tile), col, lambda: game.open_boss_journal(rid),
                lambda: ("?", WHITE), (120, 90, 60), (80, 70, 60)),
            Interactable(tc(*self.secret_gate_tile), lambda: f"Enter {info['secret_boss'].title()}'s lair" if st.side == "complete" else "Sealed hidden gate",
                         lambda: game.try_secret_boss(rid), 64, draw_fn=lambda s, p, it: self.draw_secret_gate(s, p)),
            Interactable(tc(*self.treasure_tile), "Treasure gate", lambda: game.try_treasure(rid), 64,
                         draw_fn=lambda s, p, it: draw_portal(s, p, GOLD, self.time, "TREASURE GATE", 24, TREASURE_MAPS[rid] in game.player.treasure_maps)),
            Interactable(tc(*self.discovery_tile), f"Enter {info['discovery'].title()}", lambda: game.enter_discovery(rid), 64,
                         draw_fn=lambda s, p, it: draw_portal(s, p, mix(col, WHITE, .3), self.time, info["discovery"], 26)),
            Interactable(tc(*self.boss_door), lambda: f"Enter {info['lair'].title()}" if st.boss_unlocked() else "Sealed gate",
                         lambda: game.try_realm_boss(rid), 70),
        ]
        for i in range(3):
            line = st.lines[i]
            self.interactables.append(NPC(line.giver, line.giver_role, tc(*self.giver_tile(i)), col,
                                          (lambda i=i: game.talk_realm_giver(rid, i)), (lambda i=i: game.realm_giver_marker(rid, i)),
                                          [(150, 60, 40), (120, 120, 130), (40, 40, 40)][i]))
            self.interactables.append(Interactable(tc(*self.doors[i]) + V(0, 4), (lambda i=i: f"Enter {st.lines[i].area.title()}"),
                                                   (lambda i=i: game.enter_quest_building(rid, i)), 56))
        self.bounty_pts = {}
        for qi, q in enumerate(SIDE_QUESTS[rid]):
            if q["kind"] in ("cache", "survey", "camp"):
                pts = self.bounty_points(qi, 1 if q["kind"] == "camp" else 3)
                self.bounty_pts[q["id"]] = pts
                if q["kind"] == "cache":
                    for k, pt in enumerate(pts):
                        self.interactables.append(Interactable(pt, "Dig here", (lambda qid=q["id"], k=k: game.dig_cache(rid, qid, k)), 56,
                                                               visible=(lambda qid=q["id"], k=k: st.bstate(qid)["s"] == 1 and not st.bstate(qid)["hit"][k]),
                                                               draw_fn=(lambda s_, p_, it_: self.draw_cache(s_, p_))))
        for j in range(3):
            self.interactables.append(Interactable(tc(*self.side_tiles[j]), f"Inspect the {info['side_marks']}",
                                                   (lambda j=j: game.find_side_mark(rid, j)), 60,
                                                   visible=(lambda j=j: st.side == "active" and not st.side_found[j]),
                                                   draw_fn=(lambda s, p, it: self.draw_side_mark(s, p))))

    # ---------------- update ----------------
    def update(self, dt):
        super().update(dt)
        self.mechanic_t += dt
        self.gate_cd = max(0, self.gate_cd - dt)
        game.bounty_tick(self, dt)
        self.respawn_timer -= dt
        if self.respawn_timer <= 0:
            self.respawn_timer = 7
            if len(self.enemies) < 38:
                self.spawn_enemy()
        p = game.player
        tx, ty = int(p.pos.x // TILE), int(p.pos.y // TILE)
        ch = self.tile(tx, ty)
        if ch == "I":
            p.on_ice = True
        if ch == "L" and not p.has_relic("cinderheart"):
            p.take_damage(7, "fire")
            p.apply_burn(1.5)
        if self.rid == EMBER_ID:
            if self.vent_active():
                for v in self.vents:
                    if dist(p.pos, self.tile_center(int(v.x), int(v.y))) < 70 and not p.has_relic("cinderheart"):
                        p.take_damage(12, "fire")
                        p.apply_burn(2)
        elif self.rid == VOID_ID:
            for w in self.wells:
                c = self.tile_center(int(w.x), int(w.y))
                d = c - p.pos
                if 18 < d.length() < 180 and not p.has_relic("nullcompass"):
                    p.external += d.normalize() * 95 * (1 - d.length() / 200)
                for e in self.enemies:
                    de = c - e.pos
                    if 18 < de.length() < 180:
                        e.pos = self.move(e.pos, de.normalize() * 40 * dt, e.radius)
        elif self.rid == STARFALL_ID:
            g = self.star_gates[self.active_gate()]
            if self.gate_cd <= 0 and dist(p.pos, self.tile_center(int(g.x), int(g.y))) < 50:
                self.gate_cd = 2.0
                p.dash_cd = 0
                p.heal(10)
                burst(p.pos, GOLD, 20, (50, 150), .6, 3)
                game.float_text(p.pos + V(0, -30), "STAR GATE: dash refreshed", GOLD)

    def vent_active(self):
        return (self.mechanic_t % 4.5) > 3.4

    def active_gate(self):
        return int(self.mechanic_t / 2.5) % len(self.star_gates)

    def objective(self):
        st = self.state
        tc = self.tile_center
        line = st.current_line()
        if line:
            return f"{line.title}: {line.task_label}", tc(*self.doors[line.index])
        nxt = st.next_line_to_start()
        if nxt:
            return f"Talk to {nxt.giver} to start {nxt.title}", tc(*self.giver_tile(nxt.index))
        if st.boss_unlocked() and not st.boss_defeated:
            return f"Enter {self.info['lair'].title()} and defeat {self.info['boss'].title()}", tc(*self.boss_door)
        if st.side == "active":
            for j in range(3):
                if not st.side_found[j]:
                    return f"Side quest: find the {self.info['side_marks']}s ({sum(st.side_found)}/3)", tc(*self.side_tiles[j])
        if st.side == "return":
            return f"Return to the {self.info['merchant']}", tc(*self.merchant_tile)
        if st.boss_defeated:
            return f"Return home to {self.info['giver']}", tc(*self.portal_tile)
        b = game.bounty_objective(self)
        if b:
            return b
        return "Explore the realm", None

    # ---------------- drawing ----------------
    def render_tile(self, surf, tx, ty, ch, rect, rng):
        ground, path, rock, feat = REALM_PALETTE[self.rid]
        if ch == "F":
            ch = "R"
        j = rng.randrange(-6, 7)
        c = ground
        if ch == "p":
            c = path
        elif ch in "LIX":
            c = feat
        base = (clamp(c[0] + j, 0, 255), clamp(c[1] + j, 0, 255), clamp(c[2] + j, 0, 255))
        pygame.draw.rect(surf, base, rect)
        rid = self.rid
        if ch == "." and rng.random() < .12:
            dc = mix(ground, WHITE, .15) if rid != VOID_ID else (60, 40, 100)
            pygame.draw.rect(surf, dc, (rect.x + rng.randrange(4, 26), rect.y + rng.randrange(4, 26), 3, 3))
        if ch == "L":
            if rng.random() < .4:
                pygame.draw.circle(surf, (255, 150, 50), (rect.x + rng.randrange(6, 26), rect.y + rng.randrange(6, 26)), 3)
        elif ch == "I":
            if rng.random() < .3:
                pygame.draw.line(surf, WHITE, (rect.x + 4, rect.y + rng.randrange(4, 28)), (rect.x + 20, rect.y + rng.randrange(4, 28)), 1)
        elif ch == "X":
            if rid == STARFALL_ID and rng.random() < .15:
                pygame.draw.circle(surf, WHITE, (rect.x + rng.randrange(4, 28), rect.y + rng.randrange(4, 28)), 1)
            if rid == VOID_ID and rng.random() < .15:
                pygame.draw.circle(surf, PURPLE, (rect.x + rng.randrange(4, 28), rect.y + rng.randrange(4, 28)), 1)
        elif ch == "R":
            if rid == EMBER_ID:
                pygame.draw.polygon(surf, rock, [(rect.x + 2, rect.bottom), (rect.x + 10, rect.y + 4), (rect.x + 22, rect.y + 2), (rect.right - 2, rect.bottom)])
                pygame.draw.circle(surf, EMBER, (rect.x + 15, rect.y + 12), 2)
            elif rid == FROZEN_ID:
                pygame.draw.polygon(surf, (190, 230, 250), [(rect.x + 4, rect.bottom), (rect.x + 16, rect.y), (rect.right - 4, rect.bottom)])
                pygame.draw.line(surf, WHITE, (rect.x + 16, rect.y + 2), (rect.x + 16, rect.bottom - 2), 1)
            elif rid == STARFALL_ID:
                pygame.draw.polygon(surf, (200, 190, 240), [(rect.x + 8, rect.bottom), (rect.x + 16, rect.y), (rect.right - 8, rect.bottom)])
                pygame.draw.circle(surf, GOLD, (rect.x + 16, rect.y + 6), 2)
            else:
                pygame.draw.rect(surf, rock, rect.inflate(-4, -4))
                pygame.draw.rect(surf, PURPLE, rect.inflate(-4, -4), 1)
                pygame.draw.line(surf, (90, 70, 130), (rect.x + 4, rect.y + 16), (rect.right - 4, rect.y + 16), 1)

    def render_static(self, surf):
        names = [l.area for l in self.state.lines]
        walls = [((92, 46, 30), (130, 55, 30)), ((70, 100, 125), (110, 160, 195)), ((95, 85, 125), (150, 135, 185)), ((40, 30, 62), (75, 48, 108))][self.rid]
        for (x, y, w, h), name in zip(self.building_rects, names):
            paint_building(surf, pygame.Rect(x * TILE, y * TILE, w * TILE, h * TILE), walls[0], walls[1], self.accent, name)
        bx, by, bw, bh = self.boss_rect
        r = pygame.Rect(bx * TILE, by * TILE, bw * TILE, bh * TILE)
        pygame.draw.polygon(surf, mix(self.accent, BLACK, .6), [(r.left - 12, r.bottom), (r.left + 10, r.top + 30), (r.centerx, r.top - 30), (r.right - 10, r.top + 30), (r.right + 12, r.bottom)])
        pygame.draw.polygon(surf, self.accent, [(r.left + 10, r.bottom), (r.centerx, r.top - 10), (r.right - 10, r.bottom)], 4)
        pygame.draw.rect(surf, (8, 8, 12), (r.centerx - 22, r.bottom - 56, 44, 56))
        draw_text(surf, self.info["lair"], (r.centerx, r.top - 56), GOLD, 20, center=True)

    def draw_objects(self, surf, cam):
        tc = self.tile_center
        if self.rid == EMBER_ID:
            active = self.vent_active()
            for v in self.vents:
                p = tc(int(v.x), int(v.y)) - cam
                if active:
                    alpha_circle(surf, p, 70, ORANGE, 120)
                    for _ in range(2):
                        game.particles.append(Particle(p + cam + V(random.uniform(-40, 40), random.uniform(-40, 40)), (0, -120), ORANGE, .5, 3))
                else:
                    pygame.draw.circle(surf, EMBER, ipos(p), 70, 1)
                pygame.draw.circle(surf, (40, 20, 15), ipos(p), 16)
                pygame.draw.circle(surf, ORANGE, ipos(p), 16, 2)
                draw_text(surf, "VENT", (p.x, p.y + 20), EMBER, 15, center=True)
        elif self.rid == VOID_ID:
            for w in self.wells:
                p = tc(int(w.x), int(w.y)) - cam
                for k in range(3):
                    rr = int(180 - ((self.time * 60 + k * 60) % 180))
                    pygame.draw.circle(surf, (80, 40, 120), ipos(p), max(4, rr), 1)
                pygame.draw.circle(surf, (5, 3, 10), ipos(p), 18)
                pygame.draw.circle(surf, PURPLE, ipos(p), 18, 2)
                draw_text(surf, "GRAVITY WELL", (p.x, p.y + 22), PURPLE, 15, center=True)
        elif self.rid == STARFALL_ID:
            act = self.active_gate()
            for i, g in enumerate(self.star_gates):
                p = tc(int(g.x), int(g.y)) - cam
                on = i == act
                if on:
                    glow(surf, p, 50, GOLD, 90)
                pygame.draw.circle(surf, GOLD if on else (120, 105, 155), ipos(p), 30 if on else 20, 3)
                pygame.draw.line(surf, WHITE, (p.x - 22, p.y), (p.x + 22, p.y), 1)
                pygame.draw.line(surf, WHITE, (p.x, p.y - 22), (p.x, p.y + 22), 1)
        super().draw_objects(surf, cam)
        # boss door state
        p = tc(*self.boss_door) - cam - V(0, 30)
        if self.state.boss_unlocked():
            glow(surf, p, 40, self.accent, 100)
            draw_text(surf, "OPEN", (p.x, p.y - 10), GREEN, 16, center=True)
        else:
            draw_text(surf, "SEALED", (p.x, p.y - 10), ASH, 16, center=True)

    def draw_waystone(self, surf, p):
        x, y = int(p.x), int(p.y)
        pygame.draw.polygon(surf, (70, 50, 45), [(x - 14, y + 16), (x - 10, y - 24), (x + 10, y - 24), (x + 14, y + 16)])
        pygame.draw.polygon(surf, EMBER, [(x - 14, y + 16), (x - 10, y - 24), (x + 10, y - 24), (x + 14, y + 16)], 2)
        glow(surf, (x, y - 6), 18, ORANGE, 90)
        draw_text(surf, "EMBER WAYSTONE", (x, y - 44), EMBER, 16, center=True)

    def draw_secret_gate(self, surf, p):
        open_ = self.state.side == "complete"
        x, y = int(p.x), int(p.y)
        col = PURPLE if open_ else (70, 60, 80)
        pts = [(x, y - 34), (x + 28, y), (x, y + 34), (x - 28, y)]
        if open_ and not self.state.secret_defeated:
            glow(surf, (x, y), 60, self.accent, 90)
        pygame.draw.polygon(surf, (15, 10, 22), pts)
        pygame.draw.polygon(surf, col, pts, 3)
        label = "OPTIONAL BOSS" if open_ else "SEALED"
        if self.state.secret_defeated:
            label = "CONQUERED"
        draw_text(surf, label, (x, y - 54), col if not self.state.secret_defeated else GREEN, 17, center=True)

    def draw_side_mark(self, surf, p):
        x, y = int(p.x), int(p.y)
        pulse = math.sin(self.time * 4) * 4
        glow(surf, (x, y), 34 + pulse, GOLD, 90)
        if self.rid == EMBER_ID:
            pygame.draw.polygon(surf, (150, 110, 50), [(x - 12, y + 10), (x - 8, y - 12), (x + 8, y - 12), (x + 12, y + 10)])
            pygame.draw.circle(surf, GOLD, (x, y + 12), 4)
        elif self.rid == FROZEN_ID:
            pygame.draw.rect(surf, (180, 220, 240), (x - 10, y - 16, 20, 30))
            pygame.draw.rect(surf, WHITE, (x - 10, y - 16, 20, 30), 2)
        elif self.rid == STARFALL_ID:
            pygame.draw.polygon(surf, GOLD, [(x, y - 14), (x + 5, y - 4), (x + 15, y - 4), (x + 7, y + 3), (x + 10, y + 14), (x, y + 7), (x - 10, y + 14), (x - 7, y + 3), (x - 15, y - 4), (x - 5, y - 4)])
        else:
            pygame.draw.rect(surf, (60, 60, 80), (x - 6, y - 16, 12, 28))
            pygame.draw.circle(surf, PURPLE, (x, y - 18), 6)
        draw_text(surf, "SIDE QUEST", (x, y - 40), GOLD, 15, center=True)


# ============================================================
# QUEST INTERIORS (multi-room story buildings)
# ============================================================

R = pygame.Rect
INTERIOR_LAYOUTS = [
    [R(300, 150, 40, 150), R(600, 340, 40, 150)],
    [R(250, 260, 180, 30), R(530, 260, 180, 30), R(465, 140, 30, 110)],
    [R(220, 140, 60, 60), R(220, 430, 60, 60), R(450, 250, 60, 120), R(650, 150, 60, 60), R(650, 420, 60, 60)],
    [R(230, 80, 36, 300), R(430, 260, 36, 300), R(630, 80, 36, 300)],
    [R(200, 180, 560, 30), R(200, 410, 560, 30), R(470, 210, 30, 60)],
    [R(260, 170, 40, 40), R(260, 410, 40, 40), R(460, 290, 40, 40), R(660, 170, 40, 40), R(660, 410, 40, 40), R(380, 120, 200, 24)],
]
STEALTH_LAYOUTS = [
    {"walls": [R(250, 160, 70, 70), R(250, 390, 70, 70), R(450, 260, 70, 100), R(640, 140, 70, 60), R(640, 420, 70, 60)],
     "patrols": [[(400, 140), (400, 480)], [(580, 470), (580, 130)], [(760, 230), (760, 400)]]},
    {"walls": [R(220, 120, 40, 200), R(380, 300, 40, 200), R(540, 120, 40, 200), R(700, 300, 40, 200)],
     "patrols": [[(310, 470), (310, 140)], [(470, 140), (470, 470)], [(630, 470), (630, 140)]]},
    {"walls": [R(200, 250, 120, 40), R(400, 150, 40, 120), R(400, 360, 40, 120), R(560, 250, 120, 40), R(740, 150, 40, 90), R(740, 380, 40, 90)],
     "patrols": [[(300, 140), (300, 200), (520, 200), (520, 140)], [(520, 460), (300, 460), (300, 380)], [(650, 380), (850, 380), (850, 200), (650, 200)]]},
]


# ============================================================
# THEMED QUEST INTERIORS
# ============================================================
# Every quest building (12 of them) has its own look: floor, walls, props,
# back-wall decoration, lighting, ambient particles, door style and guard
# type.  Rooms inside a building also change layout from step to step.

ROOM_TOP = 132          # the back-wall band occupies y = 80 .. ROOM_TOP

BOOK_COLORS = [(196, 58, 58), (58, 108, 196), (66, 158, 88), (222, 170, 52), (148, 78, 182),
               (232, 118, 46), (58, 168, 178), (204, 88, 140), (124, 66, 42), (232, 228, 206),
               (96, 70, 160), (170, 196, 60)]


def _pillars(xs, ys, s=40):
    return [R(x - s // 2, y - s // 2, s, s) for y in ys for x in xs]


def _rotunda():
    out = []
    for i in range(8):
        a = i * math.tau / 8 + math.pi / 8
        x = 480 + math.cos(a) * 200
        y = 350 + math.sin(a) * 118
        out.append(R(int(x) - 22, int(y) - 22, 44, 44))
    out.append(R(450, 320, 60, 60))
    return out


# Walls are all kept clear of the left lobby (x < 150) and the right lobby
# (x > 800) so the doors and stairs are always reachable.
ROOM_LAYOUTS = [
    # 0 pillared hall
    _pillars((260, 410, 560, 710), (210, 450)) + [R(380, 318, 200, 26)],
    # 1 side rooms
    [R(170, 252, 250, 22), R(520, 252, 260, 22), R(170, 390, 250, 22), R(520, 390, 260, 22),
     R(330, 124, 22, 128), R(620, 124, 22, 128), R(330, 412, 22, 148), R(620, 412, 22, 148)],
    # 2 vault ring
    [R(340, 222, 280, 22), R(340, 404, 280, 22), R(340, 244, 22, 52), R(340, 352, 22, 52),
     R(598, 244, 22, 52), R(598, 352, 22, 52),
     R(190, 180, 90, 22), R(680, 180, 90, 22), R(190, 470, 90, 22), R(680, 470, 90, 22)],
    # 3 serpentine
    [R(250, 124, 24, 238), R(420, 262, 24, 298), R(590, 124, 24, 238), R(740, 262, 24, 298)],
    # 4 stalls
    [R(260, 124, 22, 128), R(420, 124, 22, 128), R(580, 124, 22, 128), R(740, 124, 22, 128),
     R(260, 408, 22, 152), R(420, 408, 22, 152), R(580, 408, 22, 152), R(740, 408, 22, 152)],
    # 5 quarters
    [R(170, 236, 200, 22), R(590, 236, 200, 22), R(170, 396, 200, 22), R(590, 396, 200, 22),
     R(468, 124, 24, 112), R(468, 420, 24, 140)],
    # 6 inner chamber
    [R(340, 232, 100, 22), R(520, 232, 100, 22), R(340, 398, 100, 22), R(520, 398, 100, 22),
     R(340, 254, 22, 46), R(340, 352, 22, 46), R(598, 254, 22, 46), R(598, 352, 22, 46),
     R(200, 175, 36, 36), R(724, 175, 36, 36), R(200, 450, 36, 36), R(724, 450, 36, 36)],
    # 7 benches
    [R(190, 176, 200, 24), R(570, 176, 200, 24), R(190, 456, 200, 24), R(570, 456, 200, 24),
     R(330, 304, 300, 24)],
    # 8 scatter
    [R(210, 165, 70, 50), R(330, 430, 90, 60), R(450, 175, 60, 110), R(560, 390, 100, 50),
     R(690, 195, 60, 90), R(250, 305, 50, 50), R(700, 455, 80, 40), R(420, 335, 70, 30)],
    # 9 slalom
    [R(200, 160, 22, 150), R(310, 300, 22, 150), R(420, 160, 22, 150), R(530, 300, 22, 150),
     R(640, 160, 22, 150), R(750, 300, 22, 150)],
    # 10 storage blocks
    [R(220, 170, 200, 100), R(540, 170, 200, 100), R(220, 380, 200, 100), R(540, 380, 200, 100),
     R(450, 296, 60, 44)],
    # 11 rotunda
    _rotunda(),
]


def _pal(floor, alt, wall, edge, mat, trim, glow):
    return {"floor": floor, "alt": alt, "wall": wall, "edge": edge, "mat": mat, "trim": trim, "glow": glow}


# Per-quest visual identity.  Key = (realm id, quest index).
ROOM_THEMES = {
    # ---------------- EMBER ----------------
    (EMBER_ID, 0): dict(name="Cinder Outpost", floor="ashdirt", upper="planks", wall="timber", pillar="barrels",
                        back="outpost", door="timber", ambient="embers", guard="soldier",
                        decor=["tracks", "scorch", "scorch", "bones"],
                        containers=["crate", "barrel", "barrel", "cart", "chest", "crate", "shelf", "toolrack"],
                        pal=_pal((96, 76, 58), (78, 60, 46), (86, 58, 36), (190, 128, 66), (128, 90, 56), (220, 156, 74), (255, 150, 60))),
    (EMBER_ID, 1): dict(name="Molten Quarry Foundry", floor="grating", upper="planks", wall="brick", pillar="furnace",
                        back="foundry", door="metal", ambient="sparks", guard="soldier",
                        decor=["hazard", "cracks", "stain", "rug"],
                        containers=["drawer", "desk", "locker", "toolrack", "anvil", "crate", "cabinet", "shelf"],
                        pal=_pal((52, 48, 52), (38, 34, 38), (98, 46, 38), (214, 96, 52), (96, 98, 110), (255, 140, 60), (255, 110, 40))),
    (EMBER_ID, 2): dict(name="Dragon Crag", floor="lavacrack", upper="lavacrack", wall="rock", pillar="rock",
                        back="crag", door="rock", ambient="embers", guard="soldier",
                        decor=["bones", "scorch", "glyph", "cracks"],
                        containers=["chest", "urn", "crate", "barrel", "altar", "toolrack", "urn"],
                        pal=_pal((44, 30, 30), (34, 22, 24), (74, 46, 40), (220, 90, 40), (96, 66, 52), (255, 120, 50), (255, 90, 30))),
    # ---------------- FROZEN ----------------
    (FROZEN_ID, 0): dict(name="Frozen Archive", floor="flagstone", upper="planks", wall="stone", pillar="bookstack",
                         back="archive", door="arch", ambient="motes", guard="warden",
                         decor=["rug", "papers", "papers", "glyph"],
                         containers=["bookcase", "bookcase", "shelf", "desk", "chest", "cabinet", "bookcase", "drawer"],
                         pal=_pal((78, 90, 116), (60, 72, 98), (62, 74, 100), (150, 190, 240), (96, 72, 54), (170, 210, 255), (150, 200, 255))),
    (FROZEN_ID, 1): dict(name="Winter Mage Tower", floor="ice", upper="ice", wall="ice", pillar="icecrystal",
                         back="tower", door="crystal", ambient="snow", guard="warden",
                         decor=["frost", "cracks", "frost", "glyph"],
                         containers=["icechest", "shelf", "crate", "bookcase", "terminal", "cabinet", "barrel"],
                         pal=_pal((148, 190, 222), (120, 166, 204), (150, 190, 226), (230, 248, 255), (130, 170, 205), (210, 240, 255), (160, 220, 255))),
    (FROZEN_ID, 2): dict(name="Frost Throne", floor="slab", upper="slab", wall="stone", pillar="statue",
                         back="throne", door="arch", ambient="snow", guard="warden",
                         decor=["runner", "frost", "glyph"],
                         containers=["chest", "altar", "urn", "icechest", "toolrack", "cabinet"],
                         pal=_pal((36, 52, 92), (28, 42, 78), (46, 64, 108), (120, 170, 240), (80, 100, 140), (150, 200, 255), (110, 170, 255))),
    # ---------------- STARFALL ----------------
    (STARFALL_ID, 0): dict(name="Cloud Garden", floor="gardentile", upper="gardentile", wall="hedge", pillar="bush",
                           back="garden", door="hedge", ambient="petals", guard="sentinel",
                           decor=["flowers", "flowers", "petals", "glyph"],
                           containers=["urn", "altar", "urn", "chest", "bookcase", "cabinet"],
                           pal=_pal((190, 200, 190), (170, 184, 172), (64, 130, 76), (190, 230, 130), (190, 180, 160), (255, 226, 140), (255, 240, 190))),
    (STARFALL_ID, 1): dict(name="Glass Cathedral", floor="checker", upper="checker", wall="glass", pillar="column",
                           back="cathedral", door="arch", ambient="motes", guard="sentinel",
                           decor=["lightbeams", "runner", "glyph"],
                           containers=["altar", "chest", "urn", "bookcase", "cabinet", "desk", "shelf"],
                           pal=_pal((226, 220, 206), (190, 184, 176), (170, 190, 220), (255, 226, 150), (200, 180, 140), (255, 215, 110), (255, 230, 170))),
    (STARFALL_ID, 2): dict(name="Seraph's Gate", floor="starfield", upper="starfield", wall="gilded", pillar="statue",
                           back="seraph", door="gold", ambient="stars", guard="sentinel",
                           decor=["seal", "starlines"],
                           containers=["altar", "urn", "chest", "bookcase", "cabinet"],
                           pal=_pal((28, 24, 62), (20, 16, 48), (46, 38, 90), (255, 214, 100), (96, 80, 130), (255, 214, 100), (255, 220, 130))),
    # ---------------- VOID ----------------
    (VOID_ID, 0): dict(name="Derelict Dock", floor="plating", upper="plating", wall="metal", pillar="cargo",
                       back="dock", door="metal", ambient="sparks", guard="drone",
                       decor=["hazard", "cables", "stain"],
                       containers=["crate", "locker", "terminal", "trash can", "barrel", "toolrack", "cabinet"],
                       pal=_pal((58, 62, 72), (46, 50, 60), (70, 76, 90), (255, 170, 60), (110, 118, 134), (255, 190, 80), (255, 150, 60))),
    (VOID_ID, 1): dict(name="Reactor Ring", floor="hex", upper="hex", wall="metal", pillar="pylon",
                       back="reactor", door="metal", ambient="motes", guard="drone",
                       decor=["hazard", "cables", "ring"],
                       containers=["terminal", "locker", "desk", "drawer", "crate", "cabinet", "toolrack"],
                       pal=_pal((26, 40, 52), (18, 30, 42), (36, 62, 78), (80, 230, 240), (70, 100, 120), (90, 240, 250), (70, 230, 255))),
    (VOID_ID, 2): dict(name="Singularity Spire", floor="void", upper="void", wall="voidcrystal", pillar="voidcrystal",
                       back="spire", door="rift", ambient="motes", guard="drone",
                       decor=["rift", "debris", "glyph"],
                       containers=["terminal", "crate", "locker", "chest", "trash can", "toolrack"],
                       pal=_pal((20, 14, 34), (14, 10, 26), (44, 28, 74), (190, 110, 255), (80, 56, 110), (200, 130, 255), (170, 90, 255))),
}
THEME_ORDER = sorted(ROOM_THEMES.keys())



# ------------------------------------------------------------
# FLOORS  (drawn once per room onto a cached background)
# ------------------------------------------------------------
def _speckle(surf, rect, rng, cols, n):
    for _ in range(n):
        x = rng.randint(rect.left, rect.right)
        y = rng.randint(rect.top, rect.bottom)
        surf.set_at((x, y), rng.choice(cols)) if 0 <= x < surf.get_width() and 0 <= y < surf.get_height() else None


def floor_planks(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    y = rect.top
    while y < rect.bottom:
        h = 22
        x = rect.left - rng.randint(0, 70)
        while x < rect.right:
            w = rng.randint(90, 170)
            col = mix(mix(base, alt, rng.random()), BLACK, rng.random() * .12)
            pygame.draw.rect(surf, col, (x, y, w, h))
            pygame.draw.rect(surf, mix(col, BLACK, .5), (x, y, w, h), 1)
            for _ in range(2):
                gy = y + rng.randint(4, h - 4)
                gx = x + rng.randint(4, max(5, w // 2))
                pygame.draw.line(surf, mix(col, BLACK, .22), (gx, gy), (gx + rng.randint(14, 46), gy))
            if rng.random() < .2:
                pygame.draw.ellipse(surf, mix(col, BLACK, .35), (x + rng.randint(8, w - 16), y + 6, 7, 9), 1)
            pygame.draw.circle(surf, mix(col, BLACK, .5), (x + 4, y + 5), 1)
            pygame.draw.circle(surf, mix(col, BLACK, .5), (x + w - 5, y + h - 6), 1)
            x += w
        y += h


def floor_flagstone(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(mix(base, BLACK, .55), rect)
    y = rect.top - rng.randint(0, 20)
    while y < rect.bottom:
        h = rng.randint(34, 52)
        x = rect.left - rng.randint(0, 50)
        while x < rect.right:
            w = rng.randint(52, 100)
            col = mix(base, alt, rng.random())
            col = mix(col, WHITE if rng.random() < .5 else BLACK, rng.random() * .08)
            r = pygame.Rect(x + 1, y + 1, w - 2, h - 2)
            pygame.draw.rect(surf, col, r, border_radius=3)
            pygame.draw.line(surf, mix(col, WHITE, .14), (r.left + 3, r.top + 1), (r.right - 3, r.top + 1))
            if rng.random() < .25:
                cx = r.left + rng.randint(6, max(7, r.w - 6))
                pygame.draw.line(surf, mix(col, BLACK, .3), (cx, r.top + 3), (cx + rng.randint(-8, 8), r.bottom - 3))
            x += w
        y += h


def floor_checker(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    s = 48
    for j, y in enumerate(range(rect.top, rect.bottom, s)):
        for i, x in enumerate(range(rect.left, rect.right, s)):
            col = base if (i + j) % 2 == 0 else alt
            pygame.draw.rect(surf, col, (x, y, s, s))
            if rng.random() < .4:
                a = (x + rng.randint(4, s - 4), y + rng.randint(4, s - 4))
                pygame.draw.line(surf, mix(col, WHITE, .25), a, (a[0] + rng.randint(-14, 14), a[1] + rng.randint(-14, 14)))
    for x in range(rect.left, rect.right, s * 4):
        pygame.draw.line(surf, pal["trim"], (x, rect.top), (x, rect.bottom), 2)
    for y in range(rect.top, rect.bottom, s * 4):
        pygame.draw.line(surf, pal["trim"], (rect.left, y), (rect.right, y), 2)


def floor_grating(surf, rect, pal, rng):
    surf.fill(pal["alt"], rect)
    # glowing channel under the grating
    for _ in range(9):
        x = rng.randint(rect.left, rect.right - 80)
        y = rng.randint(rect.top, rect.bottom - 24)
        pygame.draw.rect(surf, mix(pal["glow"], BLACK, .45), (x, y, rng.randint(60, 220), rng.choice((10, 14, 22))))
    for x in range(rect.left, rect.right, 8):
        pygame.draw.line(surf, (24, 22, 26), (x, rect.top), (x, rect.bottom))
    for y in range(rect.top, rect.bottom, 8):
        pygame.draw.line(surf, (30, 28, 32), (rect.left, y), (rect.right, y))
    for x in range(rect.left, rect.right, 96):
        pygame.draw.line(surf, mix(pal["floor"], WHITE, .15), (x, rect.top), (x, rect.bottom), 3)
    for y in range(rect.top, rect.bottom, 96):
        pygame.draw.line(surf, mix(pal["floor"], WHITE, .15), (rect.left, y), (rect.right, y), 3)


def floor_ice(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(base, rect)
    for _ in range(30):
        c = (rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pygame.draw.ellipse(surf, mix(base, alt, rng.random()), (c[0], c[1], rng.randint(40, 120), rng.randint(24, 70)))
    for y in range(rect.top, rect.bottom, 80):
        for x in range(rect.left, rect.right, 96):
            pygame.draw.rect(surf, mix(base, WHITE, .35), (x, y, 96, 80), 1)
    for _ in range(22):   # cracks
        p = V(rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pts = [ipos(p)]
        a = rng.random() * math.tau
        for _k in range(rng.randint(3, 6)):
            a += rng.uniform(-.9, .9)
            p = p + from_angle(a, rng.randint(14, 34))
            pts.append(ipos(p))
        pygame.draw.lines(surf, mix(base, WHITE, .75), False, pts, 1)
        pygame.draw.lines(surf, mix(base, alt, .9), False, [(x + 1, y + 1) for x, y in pts], 1)


def floor_slab(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    s = 96
    for j, y in enumerate(range(rect.top, rect.bottom, s)):
        for i, x in enumerate(range(rect.left, rect.right, s)):
            col = mix(base, alt, ((i * 7 + j * 3) % 5) / 5)
            pygame.draw.rect(surf, col, (x, y, s, s))
            pygame.draw.rect(surf, mix(col, WHITE, .12), (x + 3, y + 3, s - 6, s - 6), 1)
            pygame.draw.rect(surf, mix(col, BLACK, .55), (x, y, s, s), 2)
            if rng.random() < .3:
                pygame.draw.line(surf, mix(col, WHITE, .2), (x + 10, y + rng.randint(10, 80)), (x + rng.randint(30, 80), y + rng.randint(10, 80)))


def floor_gardentile(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    s = 56
    for j, y in enumerate(range(rect.top, rect.bottom, s)):
        for i, x in enumerate(range(rect.left, rect.right, s)):
            col = base if (i + j) % 2 == 0 else alt
            pygame.draw.rect(surf, col, (x, y, s, s))
            pygame.draw.rect(surf, mix(col, BLACK, .2), (x, y, s, s), 1)
    for _ in range(70):   # moss + grass tufts
        x, y = rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom)
        g = rng.choice([(96, 160, 90), (120, 180, 100), (80, 140, 84)])
        pygame.draw.ellipse(surf, g, (x, y, rng.randint(8, 22), rng.randint(5, 12)))
        for k in range(3):
            pygame.draw.line(surf, mix(g, WHITE, .2), (x + 4 + k * 3, y + 4), (x + 3 + k * 3, y - 3))
    for _ in range(36):   # tiny flowers
        x, y = rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom)
        c = rng.choice([(255, 240, 200), (255, 190, 220), (190, 210, 255), (255, 226, 120)])
        pygame.draw.circle(surf, c, (x, y), 2)
        pygame.draw.circle(surf, (230, 170, 60), (x, y), 1)


def floor_starfield(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    h = rect.h
    for i in range(0, h, 4):
        pygame.draw.rect(surf, mix(base, alt, i / h), (rect.left, rect.top + i, rect.w, 4))
    pts = []
    for _ in range(46):
        p = (rng.randint(rect.left + 10, rect.right - 10), rng.randint(rect.top + 10, rect.bottom - 10))
        pts.append(p)
    for k, p in enumerate(pts):
        for q in pts[k + 1:k + 4]:
            if dist(p, q) < 140:
                pygame.draw.line(surf, mix(pal["trim"], alt, .65), p, q, 1)
    for p in pts:
        pygame.draw.circle(surf, pal["trim"], p, 2)
        pygame.draw.circle(surf, WHITE, p, 1)
    for _ in range(160):
        surf.set_at((rng.randint(rect.left, rect.right - 1), rng.randint(rect.top, rect.bottom - 1)),
                    rng.choice([(200, 200, 255), (255, 240, 200), (140, 140, 200)]))


def floor_plating(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    sw, sh = 120, 80
    for j, y in enumerate(range(rect.top, rect.bottom, sh)):
        for i, x in enumerate(range(rect.left - (sw // 2 if j % 2 else 0), rect.right, sw)):
            col = mix(base, alt, rng.random())
            pygame.draw.rect(surf, col, (x, y, sw, sh))
            pygame.draw.rect(surf, mix(col, BLACK, .5), (x, y, sw, sh), 2)
            pygame.draw.line(surf, mix(col, WHITE, .12), (x + 2, y + 2), (x + sw - 3, y + 2))
            for cx, cy in ((x + 7, y + 7), (x + sw - 8, y + 7), (x + 7, y + sh - 8), (x + sw - 8, y + sh - 8)):
                pygame.draw.circle(surf, mix(col, BLACK, .5), (cx, cy), 2)
                pygame.draw.circle(surf, mix(col, WHITE, .2), (cx - 1, cy - 1), 1)


def _hex_pts(cx, cy, r):
    return [(cx + math.cos(math.pi / 3 * k + math.pi / 6) * r, cy + math.sin(math.pi / 3 * k + math.pi / 6) * r) for k in range(6)]


def floor_hex(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(alt, rect)
    r = 30
    w = math.sqrt(3) * r
    for j in range(-1, int(rect.h / (r * 1.5)) + 2):
        for i in range(-1, int(rect.w / w) + 2):
            cx = rect.left + i * w + (w / 2 if j % 2 else 0)
            cy = rect.top + j * r * 1.5
            col = mix(base, alt, rng.random() * .6)
            if rng.random() < .08:
                col = mix(col, pal["glow"], .3)
            pts = _hex_pts(cx, cy, r - 2)
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, mix(pal["glow"], alt, .65), pts, 1)


def floor_ashdirt(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(base, rect)
    for _ in range(90):
        c = (rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pygame.draw.ellipse(surf, mix(base, alt, rng.random()), (c[0], c[1], rng.randint(30, 110), rng.randint(14, 46)))
    _speckle(surf, rect, rng, [mix(base, WHITE, .2), mix(base, BLACK, .3), mix(base, (255, 150, 60), .15)], 2500)
    for _ in range(40):   # small stones
        x, y = rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom)
        pygame.draw.ellipse(surf, mix(base, WHITE, .25), (x, y, rng.randint(4, 9), rng.randint(3, 6)))
        pygame.draw.ellipse(surf, mix(base, BLACK, .4), (x, y + 3, rng.randint(4, 9), 3), 1)


def floor_lavacrack(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(base, rect)
    for _ in range(40):
        c = (rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pygame.draw.polygon(surf, mix(base, alt, rng.random()), [(c[0] + rng.randint(-40, 40), c[1] + rng.randint(-30, 30)) for _ in range(5)])
    for _ in range(26):
        p = V(rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pts = [ipos(p)]
        a = rng.random() * math.tau
        for _k in range(rng.randint(4, 8)):
            a += rng.uniform(-.8, .8)
            p = p + from_angle(a, rng.randint(16, 40))
            pts.append(ipos(p))
        pygame.draw.lines(surf, mix(pal["glow"], BLACK, .6), False, pts, 5)
        pygame.draw.lines(surf, pal["glow"], False, pts, 2)
        pygame.draw.lines(surf, (255, 220, 140), False, pts, 1)


def floor_void(surf, rect, pal, rng):
    base, alt = pal["floor"], pal["alt"]
    surf.fill(alt, rect)
    for _ in range(60):
        c = (rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom))
        pts = [(c[0] + rng.randint(-50, 50), c[1] + rng.randint(-40, 40)) for _ in range(rng.randint(4, 6))]
        pygame.draw.polygon(surf, mix(base, alt, rng.random()), pts)
        pygame.draw.polygon(surf, mix(pal["glow"], alt, .7), pts, 1)
    for _ in range(18):
        x, y = rng.randint(rect.left, rect.right), rng.randint(rect.top, rect.bottom)
        pygame.draw.line(surf, pal["glow"], (x, y), (x + rng.randint(-60, 60), y + rng.randint(-40, 40)), 1)
    for _ in range(200):
        surf.set_at((rng.randint(rect.left, rect.right - 1), rng.randint(rect.top, rect.bottom - 1)),
                    rng.choice([(120, 90, 200), (200, 160, 255), (80, 60, 140)]))


FLOOR_STYLES = {
    "planks": floor_planks, "flagstone": floor_flagstone, "checker": floor_checker, "grating": floor_grating,
    "ice": floor_ice, "slab": floor_slab, "gardentile": floor_gardentile, "starfield": floor_starfield,
    "plating": floor_plating, "hex": floor_hex, "ashdirt": floor_ashdirt, "lavacrack": floor_lavacrack,
    "void": floor_void,
}


# ------------------------------------------------------------
# WALLS
# ------------------------------------------------------------
def wall_timber(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(base, r)
    if r.w >= r.h:
        for x in range(r.left, r.right, 14):
            pygame.draw.line(surf, mix(base, BLACK, .35), (x, r.top), (x, r.bottom))
            pygame.draw.line(surf, mix(base, WHITE, .1), (x + 1, r.top), (x + 1, r.bottom))
        for y in (r.top + 3, r.bottom - 6):
            pygame.draw.rect(surf, mix(base, BLACK, .5), (r.left, y, r.w, 4))
    else:
        for y in range(r.top, r.bottom, 14):
            pygame.draw.line(surf, mix(base, BLACK, .35), (r.left, y), (r.right, y))
            pygame.draw.line(surf, mix(base, WHITE, .1), (r.left, y + 1), (r.right, y + 1))
        for x in (r.left + 3, r.right - 6):
            pygame.draw.rect(surf, mix(base, BLACK, .5), (x, r.top, 4, r.h))
    for _ in range(max(2, (r.w * r.h) // 900)):
        pygame.draw.circle(surf, (40, 34, 30), (rng.randint(r.left + 2, r.right - 3), rng.randint(r.top + 2, r.bottom - 3)), 1)


def wall_brick(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(mix(base, BLACK, .5), r)
    row = 0
    for y in range(r.top, r.bottom, 10):
        off = 0 if row % 2 == 0 else 10
        for x in range(r.left - off, r.right, 20):
            br = pygame.Rect(x + 1, y + 1, 18, 8).clip(r)
            if br.w > 0 and br.h > 0:
                pygame.draw.rect(surf, mix(base, rng.choice([WHITE, BLACK]), rng.random() * .15), br)
        row += 1


def wall_stone(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(mix(base, BLACK, .45), r)
    y = r.top
    while y < r.bottom:
        h = rng.randint(14, 22)
        x = r.left
        while x < r.right:
            w = rng.randint(22, 44)
            br = pygame.Rect(x + 1, y + 1, w - 2, h - 2).clip(r)
            if br.w > 0 and br.h > 0:
                c = mix(base, rng.choice([WHITE, BLACK]), rng.random() * .12)
                pygame.draw.rect(surf, c, br)
                pygame.draw.line(surf, mix(c, WHITE, .15), br.topleft, (br.right, br.top))
            x += w
        y += h


def wall_rock(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(base, r)
    for _ in range(max(4, (r.w * r.h) // 500)):
        c = (rng.randint(r.left, r.right), rng.randint(r.top, r.bottom))
        pts = [(c[0] + rng.randint(-14, 14), c[1] + rng.randint(-12, 12)) for _ in range(5)]
        pygame.draw.polygon(surf, mix(base, rng.choice([WHITE, BLACK]), rng.random() * .22), pts)
    for _ in range(max(1, (r.w + r.h) // 120)):
        a = (rng.randint(r.left, r.right), rng.randint(r.top, r.bottom))
        b = (a[0] + rng.randint(-24, 24), a[1] + rng.randint(-24, 24))
        pygame.draw.line(surf, mix(pal["glow"], BLACK, .5), a, b, 3)
        pygame.draw.line(surf, pal["glow"], a, b, 1)


def wall_ice(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(base, r)
    for k in range(-r.h, r.w, 18):
        pygame.draw.line(surf, mix(base, WHITE, .5), (r.left + k, r.bottom), (r.left + k + r.h, r.top), 2)
    for _ in range(max(2, (r.w * r.h) // 700)):
        c = (rng.randint(r.left, r.right), rng.randint(r.top, r.bottom))
        pygame.draw.polygon(surf, mix(base, WHITE, .3), [(c[0], c[1] - 6), (c[0] + 5, c[1]), (c[0], c[1] + 6), (c[0] - 5, c[1])])
    for x in range(r.left + 4, r.right - 4, 12):   # icicles
        h = rng.randint(5, 11)
        pygame.draw.polygon(surf, (235, 250, 255), [(x, r.bottom), (x + 5, r.bottom), (x + 2, r.bottom + h)])


def wall_hedge(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(mix(base, BLACK, .4), r)
    for _ in range(max(6, (r.w * r.h) // 160)):
        c = (rng.randint(r.left, r.right), rng.randint(r.top, r.bottom))
        pygame.draw.circle(surf, mix(base, rng.choice([WHITE, BLACK]), rng.random() * .3), c, rng.randint(6, 11))
    for _ in range(max(2, (r.w * r.h) // 900)):
        c = (rng.randint(r.left + 3, r.right - 3), rng.randint(r.top + 3, r.bottom - 3))
        pygame.draw.circle(surf, rng.choice([(255, 240, 200), (255, 190, 220), (255, 226, 120)]), c, 2)


def wall_glass(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(mix(base, WHITE, .1), r)
    s = 22
    for y in range(r.top, r.bottom, s):
        for x in range(r.left, r.right, s):
            tint = rng.choice([(150, 190, 240), (210, 170, 240), (240, 200, 150), (170, 230, 210)])
            c = mix(base, tint, .55)
            pygame.draw.polygon(surf, c, [(x, y), (x + s, y), (x, y + s)])
            pygame.draw.polygon(surf, mix(c, WHITE, .25), [(x + s, y), (x + s, y + s), (x, y + s)])
    for y in range(r.top, r.bottom, s):
        pygame.draw.line(surf, pal["edge"], (r.left, y), (r.right, y))
    for x in range(r.left, r.right, s):
        pygame.draw.line(surf, pal["edge"], (x, r.top), (x, r.bottom))


def wall_gilded(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(base, r)
    inner = r.inflate(-8, -8)
    if inner.w > 4 and inner.h > 4:
        pygame.draw.rect(surf, mix(base, BLACK, .3), inner)
        pygame.draw.rect(surf, pal["trim"], inner, 1)
    for _ in range(max(1, (r.w * r.h) // 1200)):
        c = (rng.randint(r.left + 6, r.right - 6), rng.randint(r.top + 6, r.bottom - 6))
        pygame.draw.circle(surf, pal["trim"], c, 2)


def wall_metal(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(base, r)
    if r.w >= r.h:
        for x in range(r.left, r.right, 48):
            pygame.draw.line(surf, mix(base, BLACK, .5), (x, r.top), (x, r.bottom), 2)
            pygame.draw.circle(surf, mix(base, WHITE, .3), (x + 5, r.top + 5), 1)
            pygame.draw.circle(surf, mix(base, WHITE, .3), (x + 5, r.bottom - 6), 1)
        pygame.draw.rect(surf, pal["edge"], (r.left + 3, r.centery - 1, r.w - 6, 2))
    else:
        for y in range(r.top, r.bottom, 48):
            pygame.draw.line(surf, mix(base, BLACK, .5), (r.left, y), (r.right, y), 2)
            pygame.draw.circle(surf, mix(base, WHITE, .3), (r.left + 5, y + 5), 1)
            pygame.draw.circle(surf, mix(base, WHITE, .3), (r.right - 6, y + 5), 1)
        pygame.draw.rect(surf, pal["edge"], (r.centerx - 1, r.top + 3, 2, r.h - 6))


def wall_voidcrystal(surf, r, pal, rng):
    base = pal["wall"]
    surf.fill(mix(base, BLACK, .35), r)
    for _ in range(max(3, (r.w * r.h) // 420)):
        c = (rng.randint(r.left, r.right), rng.randint(r.top, r.bottom))
        pts = [(c[0] + rng.randint(-16, 16), c[1] + rng.randint(-14, 14)) for _ in range(4)]
        pygame.draw.polygon(surf, mix(base, rng.choice([WHITE, pal["edge"]]), rng.random() * .3), pts)
        pygame.draw.polygon(surf, mix(pal["edge"], base, .5), pts, 1)


WALL_STYLES = {
    "timber": wall_timber, "brick": wall_brick, "stone": wall_stone, "rock": wall_rock, "ice": wall_ice,
    "hedge": wall_hedge, "glass": wall_glass, "gilded": wall_gilded, "metal": wall_metal,
    "voidcrystal": wall_voidcrystal,
}


def draw_wall_block(surf, r, theme, rng):
    pal = theme["pal"]
    alpha_rect(surf, (r.x + 4, r.bottom, r.w, 8), BLACK, 95)
    surf.set_clip(r)
    WALL_STYLES[theme["wall"]](surf, r, pal, rng)
    surf.set_clip(None)
    pygame.draw.line(surf, mix(pal["wall"], WHITE, .35), (r.left, r.top), (r.right - 1, r.top), 2)
    pygame.draw.rect(surf, mix(pal["wall"], BLACK, .55), r, 2)
    pygame.draw.rect(surf, mix(pal["edge"], BLACK, .2), r.inflate(-2, -2), 1)


# ------------------------------------------------------------
# PILLAR / PROP BLOCKS (small solid walls become furniture)
# ------------------------------------------------------------
def prop_barrels(surf, r, pal, rng, lights):
    n = max(1, r.w // 28)
    for i in range(max(1, r.h // 28)):
        for j in range(n):
            cx = r.left + 14 + j * 28 if r.w >= 28 else r.centerx
            cy = r.top + 16 + i * 28
            pygame.draw.ellipse(surf, (0, 0, 0), (cx - 13, cy + 8, 26, 9))
            pygame.draw.rect(surf, (116, 78, 46), (cx - 11, cy - 11, 22, 24), border_radius=4)
            pygame.draw.ellipse(surf, (150, 106, 64), (cx - 11, cy - 15, 22, 10))
            pygame.draw.ellipse(surf, (80, 54, 32), (cx - 11, cy - 15, 22, 10), 1)
            for yy in (cy - 5, cy + 6):
                pygame.draw.line(surf, (60, 50, 44), (cx - 11, yy), (cx + 11, yy), 2)


def prop_furnace(surf, r, pal, rng, lights):
    pygame.draw.rect(surf, (60, 56, 60), r)
    pygame.draw.rect(surf, (36, 34, 38), r, 3)
    m = pygame.Rect(0, 0, max(10, r.w // 2), max(10, r.h // 3))
    m.center = (r.centerx, r.centery + r.h // 6)
    pygame.draw.rect(surf, (255, 120, 40), m, border_radius=4)
    pygame.draw.rect(surf, (255, 210, 120), m.inflate(-8, -8), border_radius=3)
    pygame.draw.rect(surf, (20, 18, 20), m, 3, border_radius=4)
    lights.append((m.centerx, m.centery, 78, pal["glow"]))
    pygame.draw.rect(surf, (40, 38, 42), (r.centerx - 6, r.top - 10, 12, 14))


def prop_rock(surf, r, pal, rng, lights):
    pts = []
    cx, cy = r.center
    for k in range(9):
        a = k * math.tau / 9
        pts.append((cx + math.cos(a) * r.w * rng.uniform(.4, .6), cy + math.sin(a) * r.h * rng.uniform(.4, .62)))
    pygame.draw.polygon(surf, (0, 0, 0), [(x + 3, y + 5) for x, y in pts])
    pygame.draw.polygon(surf, pal["wall"], pts)
    pygame.draw.polygon(surf, mix(pal["wall"], WHITE, .25), [pts[0], pts[1], pts[2], (cx, cy)])
    pygame.draw.polygon(surf, mix(pal["wall"], BLACK, .5), pts, 2)
    pygame.draw.line(surf, pal["glow"], (cx - 4, cy), (cx + 6, cy + 8), 1)


def prop_bookstack(surf, r, pal, rng, lights):
    y = r.bottom - 2
    w = r.w
    while y > r.top + 4:
        bw = rng.randint(int(w * .7), w)
        bh = rng.randint(6, 9)
        x = r.left + (w - bw) // 2 + rng.randint(-3, 3)
        c = rng.choice(BOOK_COLORS)
        pygame.draw.rect(surf, c, (x, y - bh, bw, bh))
        pygame.draw.rect(surf, mix(c, BLACK, .4), (x, y - bh, bw, bh), 1)
        pygame.draw.rect(surf, (236, 228, 200), (x + 2, y - bh + 2, bw - 4, 2))
        y -= bh
    pygame.draw.rect(surf, mix(pal["wall"], BLACK, .5), r, 1)


def prop_icecrystal(surf, r, pal, rng, lights):
    cx = r.centerx
    for k, (dx, hh, ww) in enumerate(((-r.w // 4, .8, .34), (r.w // 5, 1.0, .4), (0, .6, .3))):
        h = int(r.h * hh)
        w = int(r.w * ww)
        x = cx + dx
        pts = [(x, r.bottom - h), (x + w // 2, r.bottom - h // 3), (x + w // 3, r.bottom), (x - w // 3, r.bottom), (x - w // 2, r.bottom - h // 3)]
        pygame.draw.polygon(surf, mix((170, 220, 250), WHITE, k * .15), pts)
        pygame.draw.polygon(surf, (235, 250, 255), pts, 2)
        pygame.draw.line(surf, WHITE, (x, r.bottom - h + 3), (x - w // 6, r.bottom - 4), 1)
    lights.append((r.centerx, r.centery, 60, pal["glow"]))


def prop_statue(surf, r, pal, rng, lights):
    pygame.draw.rect(surf, mix(pal["wall"], BLACK, .3), (r.left, r.bottom - 12, r.w, 12))
    pygame.draw.rect(surf, mix(pal["wall"], WHITE, .2), (r.left + 3, r.bottom - 12, r.w - 6, 3))
    cx = r.centerx
    body = mix(pal["edge"], WHITE, .35) if pal["wall"][2] > 80 else mix(pal["wall"], WHITE, .45)
    pygame.draw.polygon(surf, body, [(cx - 8, r.bottom - 12), (cx - 6, r.top + 14), (cx + 6, r.top + 14), (cx + 8, r.bottom - 12)])
    pygame.draw.circle(surf, body, (cx, r.top + 9), 7)
    pygame.draw.polygon(surf, mix(body, BLACK, .15), [(cx - 6, r.top + 18), (cx - 20, r.top + 6), (cx - 8, r.top + 28)])
    pygame.draw.polygon(surf, mix(body, BLACK, .15), [(cx + 6, r.top + 18), (cx + 20, r.top + 6), (cx + 8, r.top + 28)])
    pygame.draw.circle(surf, pal["trim"], (cx, r.top + 1), 8, 1)


def prop_bush(surf, r, pal, rng, lights):
    for _ in range(max(8, (r.w * r.h) // 120)):
        c = (rng.randint(r.left + 6, r.right - 6), rng.randint(r.top + 6, r.bottom - 6))
        pygame.draw.circle(surf, mix((52, 120, 66), rng.choice([WHITE, BLACK]), rng.random() * .25), c, rng.randint(7, 12))
    for _ in range(6):
        pygame.draw.circle(surf, rng.choice([(255, 190, 220), (255, 240, 200), (255, 226, 120)]),
                           (rng.randint(r.left + 6, r.right - 6), rng.randint(r.top + 6, r.bottom - 6)), 3)


def prop_column(surf, r, pal, rng, lights):
    cx, cy = r.center
    rad = min(r.w, r.h) // 2
    pygame.draw.circle(surf, (0, 0, 0), (cx + 3, cy + 5), rad)
    pygame.draw.rect(surf, mix(pal["floor"], BLACK, .15), r, border_radius=4)
    pygame.draw.circle(surf, pal["floor"], (cx, cy), rad - 3)
    pygame.draw.circle(surf, mix(pal["floor"], WHITE, .4), (cx - rad // 4, cy - rad // 4), rad // 2)
    pygame.draw.circle(surf, pal["trim"], (cx, cy), rad - 3, 2)


def prop_cargo(surf, r, pal, rng, lights):
    col = rng.choice([(176, 82, 60), (70, 110, 150), (190, 150, 60), (80, 130, 100)])
    pygame.draw.rect(surf, mix(col, BLACK, .15), r)
    horiz = r.w >= r.h
    n = max(2, (r.w if horiz else r.h) // 12)
    for i in range(n):
        if horiz:
            x = r.left + 3 + i * (r.w - 6) // n
            pygame.draw.line(surf, mix(col, BLACK, .35), (x, r.top + 2), (x, r.bottom - 3), 2)
        else:
            y = r.top + 3 + i * (r.h - 6) // n
            pygame.draw.line(surf, mix(col, BLACK, .35), (r.left + 2, y), (r.right - 3, y), 2)
    pygame.draw.rect(surf, mix(col, WHITE, .3), r, 2)
    pygame.draw.rect(surf, (20, 20, 24), (r.left + 4, r.top + 4, 10, 6))


def prop_pylon(surf, r, pal, rng, lights):
    pygame.draw.rect(surf, mix(pal["wall"], BLACK, .3), r)
    pygame.draw.rect(surf, pal["edge"], r, 2)
    cx, cy = r.center
    pygame.draw.circle(surf, mix(pal["glow"], BLACK, .5), (cx, cy), min(r.w, r.h) // 2 - 4)
    pygame.draw.circle(surf, pal["glow"], (cx, cy), min(r.w, r.h) // 3)
    pygame.draw.circle(surf, WHITE, (cx, cy), min(r.w, r.h) // 6)
    lights.append((cx, cy, 70, pal["glow"]))


def prop_voidcrystal(surf, r, pal, rng, lights):
    cx = r.centerx
    for dx, hh in ((-r.w // 4, .8), (r.w // 5, 1.0), (0, .65)):
        h = int(r.h * hh)
        w = int(r.w * .38)
        x = cx + dx
        pts = [(x, r.bottom - h), (x + w // 2, r.bottom - h // 2), (x + w // 3, r.bottom), (x - w // 3, r.bottom), (x - w // 2, r.bottom - h // 2)]
        pygame.draw.polygon(surf, mix(pal["wall"], BLACK, .3), pts)
        pygame.draw.polygon(surf, pal["glow"], pts, 2)
    lights.append((cx, r.centery, 60, pal["glow"]))


PROP_STYLES = {
    "barrels": prop_barrels, "furnace": prop_furnace, "rock": prop_rock, "bookstack": prop_bookstack,
    "icecrystal": prop_icecrystal, "statue": prop_statue, "bush": prop_bush, "column": prop_column,
    "cargo": prop_cargo, "pylon": prop_pylon, "voidcrystal": prop_voidcrystal,
}



# ------------------------------------------------------------
# BACK WALLS (the band along the top of every room)
# ------------------------------------------------------------
def _books_row(surf, rect, rng, cols=None):
    """Fill rect with upright, colourful books."""
    x = rect.left + 1
    while x < rect.right - 3:
        w = rng.randint(4, 8)
        if x + w > rect.right - 1:
            break
        h = rng.randint(max(6, rect.h - 8), rect.h - 1)
        c = rng.choice(cols or BOOK_COLORS)
        pygame.draw.rect(surf, c, (x, rect.bottom - h, w, h))
        pygame.draw.rect(surf, mix(c, BLACK, .45), (x, rect.bottom - h, w, h), 1)
        pygame.draw.line(surf, mix(c, WHITE, .35), (x + 1, rect.bottom - h + 2), (x + 1, rect.bottom - 3))
        if rng.random() < .5:
            pygame.draw.rect(surf, mix(c, (240, 220, 140), .6), (x, rect.bottom - h + 3, w, 2))
        x += w
        if rng.random() < .07:
            x += rng.randint(5, 9)


def back_outpost(surf, B, th, rng, lights):
    pal = th["pal"]
    x = B.left
    while x < B.right:
        w = rng.randint(16, 22)
        col = mix(pal["wall"], BLACK, rng.random() * .25)
        pygame.draw.rect(surf, col, (x, B.top, w - 1, B.h))
        pygame.draw.line(surf, mix(col, WHITE, .12), (x + 2, B.top), (x + 2, B.bottom))
        x += w
    pygame.draw.rect(surf, mix(pal["wall"], BLACK, .55), (B.left, B.top + 34, B.w, 6))
    for lx in range(150, 900, 190):
        pygame.draw.line(surf, (40, 30, 24), (lx, B.top), (lx, B.top + 14), 2)
        pygame.draw.rect(surf, (70, 50, 32), (lx - 6, B.top + 14, 12, 18))
        pygame.draw.rect(surf, (255, 205, 120), (lx - 4, B.top + 16, 8, 14))
        lights.append((lx, B.top + 26, 80, pal["glow"]))
    for bx, c in ((250, (150, 50, 40)), (560, (60, 60, 70)), (780, (150, 50, 40))):
        pygame.draw.polygon(surf, c, [(bx, B.top + 2), (bx + 26, B.top + 2), (bx + 26, B.top + 36), (bx + 13, B.top + 28), (bx, B.top + 36)])
        pygame.draw.circle(surf, pal["trim"], (bx + 13, B.top + 14), 5, 2)


def back_foundry(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_brick(surf, B, pal, rng)
    for fx in (170, 400, 630, 820):
        m = pygame.Rect(fx - 34, B.top + 14, 68, 38)
        pygame.draw.rect(surf, (28, 24, 28), m.inflate(10, 6), border_radius=6)
        pygame.draw.rect(surf, (255, 110, 36), m, border_radius=14)
        pygame.draw.rect(surf, (255, 200, 110), m.inflate(-22, -16), border_radius=8)
        lights.append((fx, B.top + 34, 100, pal["glow"]))
    for px in (280, 520, 730):
        pygame.draw.rect(surf, (70, 70, 80), (px, B.top, 8, B.h))
        pygame.draw.rect(surf, (110, 110, 124), (px, B.top, 3, B.h))
    for cx in (350, 580):
        for k in range(4):
            pygame.draw.circle(surf, (50, 50, 56), (cx, B.top + 4 + k * 9), 4, 2)


def back_crag(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_rock(surf, B, pal, rng)
    for rx in range(120, 900, 150):   # giant ribs
        pygame.draw.arc(surf, (210, 196, 170), (rx, B.top + 6, 90, 90), 0.2, 2.9, 5)
    cx = 480   # dragon skull
    pygame.draw.polygon(surf, (222, 208, 180), [(cx - 38, B.top + 46), (cx - 30, B.top + 14), (cx + 20, B.top + 10), (cx + 50, B.top + 30), (cx + 36, B.top + 44)])
    pygame.draw.polygon(surf, (222, 208, 180), [(cx - 30, B.top + 14), (cx - 52, B.top + 4), (cx - 22, B.top + 20)])
    pygame.draw.circle(surf, (30, 18, 18), (cx + 6, B.top + 28), 7)
    pygame.draw.circle(surf, pal["glow"], (cx + 6, B.top + 28), 3)
    lights.append((cx + 6, B.top + 28, 70, pal["glow"]))
    for lx in (200, 760):
        pygame.draw.polygon(surf, (255, 110, 40), [(lx - 18, B.bottom), (lx - 10, B.top + 24), (lx, B.top + 34), (lx + 12, B.top + 18), (lx + 18, B.bottom)])
        lights.append((lx, B.top + 36, 90, pal["glow"]))


def back_archive(surf, B, th, rng, lights):
    pal = th["pal"]
    surf.fill(mix(pal["wall"], BLACK, .5), B)
    for row in range(3):
        r = pygame.Rect(B.left + 4, B.top + 4 + row * 16, B.w - 8, 13)
        _books_row(surf, r, rng)
        pygame.draw.rect(surf, (74, 52, 36), (B.left + 4, r.bottom, B.w - 8, 3))
    for px in range(B.left + 4, B.right, 120):
        pygame.draw.rect(surf, (74, 52, 36), (px, B.top, 6, B.h))
    lx = 300
    pygame.draw.line(surf, (110, 80, 50), (lx, B.top + 8), (lx + 12, B.bottom), 3)   # ladder
    pygame.draw.line(surf, (110, 80, 50), (lx + 16, B.top + 8), (lx + 28, B.bottom), 3)
    for k in range(5):
        pygame.draw.line(surf, (110, 80, 50), (lx + 4 + k * 3, B.top + 14 + k * 8), (lx + 20 + k * 3, B.top + 14 + k * 8), 2)
    for cx in (200, 600, 800):
        pygame.draw.rect(surf, (230, 220, 190), (cx - 3, B.top + 22, 6, 14))
        pygame.draw.circle(surf, (255, 210, 120), (cx, B.top + 20), 3)
        lights.append((cx, B.top + 22, 60, (255, 200, 120)))


def back_tower(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_ice(surf, B, pal, rng)
    for wx in (160, 360, 600, 800):
        w = pygame.Rect(wx - 22, B.top + 6, 44, 46)
        pygame.draw.rect(surf, (40, 70, 110), w, border_top_left_radius=22, border_top_right_radius=22)
        for i in range(w.h):
            pygame.draw.line(surf, mix((40, 110, 140), (140, 90, 190), i / w.h), (w.left + 2, w.top + i), (w.right - 3, w.top + i))
        for k in range(5):
            surf.set_at((w.left + rng.randint(4, 38), w.top + rng.randint(10, 40)), WHITE)
        pygame.draw.rect(surf, (230, 248, 255), w, 2, border_top_left_radius=22, border_top_right_radius=22)
        pygame.draw.line(surf, (230, 248, 255), (w.centerx, w.top), (w.centerx, w.bottom), 1)
        lights.append((wx, B.top + 30, 60, (120, 220, 255)))


def back_throne(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_stone(surf, B, pal, rng)
    for bx in (140, 280, 680, 820):
        pygame.draw.polygon(surf, (30, 60, 150), [(bx - 16, B.top), (bx + 16, B.top), (bx + 16, B.bottom - 4), (bx, B.bottom - 14), (bx - 16, B.bottom - 4)])
        pygame.draw.polygon(surf, (150, 200, 255), [(bx, B.top + 12), (bx + 7, B.top + 24), (bx, B.top + 36), (bx - 7, B.top + 24)], 2)
    tx = 480
    pygame.draw.rect(surf, (50, 70, 120), (tx - 40, B.top + 18, 80, 34), border_top_left_radius=30, border_top_right_radius=30)
    pygame.draw.rect(surf, (150, 200, 255), (tx - 40, B.top + 18, 80, 34), 2, border_top_left_radius=30, border_top_right_radius=30)
    pygame.draw.rect(surf, (28, 40, 80), (tx - 24, B.top + 30, 48, 22))
    for k in range(5):
        pygame.draw.polygon(surf, (190, 230, 255), [(tx - 36 + k * 18, B.top + 18), (tx - 28 + k * 18, B.top + 4), (tx - 20 + k * 18, B.top + 18)])
    for bx in (210, 750):
        pygame.draw.rect(surf, (70, 60, 56), (bx - 8, B.top + 24, 16, 8))
        pygame.draw.rect(surf, (150, 220, 255), (bx - 5, B.top + 18, 10, 8))
        lights.append((bx, B.top + 20, 70, (130, 200, 255)))


def back_garden(surf, B, th, rng, lights):
    pal = th["pal"]
    for i in range(B.h):
        pygame.draw.line(surf, mix((150, 210, 250), (255, 240, 220), i / B.h), (B.left, B.top + i), (B.right, B.top + i))
    for cx in range(B.left + 20, B.right, 70):
        pygame.draw.circle(surf, (255, 255, 255), (cx + rng.randint(-10, 10), B.top + rng.randint(8, 24)), rng.randint(8, 14))
    for ax in range(B.left, B.right, 140):    # white arches
        pygame.draw.rect(surf, (236, 232, 222), (ax, B.top, 12, B.h))
        pygame.draw.arc(surf, (236, 232, 222), (ax, B.top - 8, 140, 70), 0, math.pi, 7)
    for _ in range(90):
        c = (rng.randint(B.left, B.right), rng.randint(B.top, B.bottom))
        pygame.draw.circle(surf, mix((52, 120, 66), rng.choice([WHITE, BLACK]), rng.random() * .3), c, rng.randint(4, 8))
    for _ in range(26):
        pygame.draw.circle(surf, rng.choice([(255, 190, 220), (255, 240, 200), (255, 226, 120)]),
                           (rng.randint(B.left, B.right), rng.randint(B.top + 6, B.bottom - 4)), 3)


def back_cathedral(surf, B, th, rng, lights):
    pal = th["pal"]
    surf.fill((70, 70, 96), B)
    cols = [(210, 70, 80), (70, 120, 220), (230, 190, 60), (90, 190, 120), (170, 90, 210)]
    for wx in range(130, 900, 120):
        w = pygame.Rect(wx - 24, B.top + 4, 48, 48)
        pygame.draw.rect(surf, (30, 30, 50), w, border_top_left_radius=24, border_top_right_radius=24)
        for i in range(4):
            for j in range(6):
                c = rng.choice(cols)
                pygame.draw.rect(surf, c, (w.left + 3 + i * 10, w.top + 4 + j * 7, 9, 6))
        pygame.draw.rect(surf, (255, 226, 150), w, 2, border_top_left_radius=24, border_top_right_radius=24)
        lights.append((wx, B.top + 30, 50, rng.choice(cols)))


def back_seraph(surf, B, th, rng, lights):
    pal = th["pal"]
    surf.fill(mix(pal["wall"], BLACK, .5), B)
    pygame.draw.circle(surf, (20, 14, 50), (480, B.bottom + 18), 64)
    for k in range(3):
        pygame.draw.circle(surf, pal["trim"], (480, B.bottom + 18), 64 - k * 14, 2)
    for k in range(12):
        a = k * math.tau / 12
        p1 = (480 + math.cos(a) * 66, B.bottom + 18 + math.sin(a) * 66)
        p2 = (480 + math.cos(a) * 82, B.bottom + 18 + math.sin(a) * 82)
        pygame.draw.line(surf, pal["trim"], p1, p2, 2)
    for _ in range(40):
        surf.set_at((rng.randint(B.left, B.right - 1), rng.randint(B.top, B.bottom - 1)), (255, 240, 200))
    for sx in (160, 300, 660, 800):
        pygame.draw.polygon(surf, pal["trim"], [(sx, B.top + 10), (sx + 6, B.top + 24), (sx + 20, B.top + 26), (sx + 9, B.top + 34), (sx + 12, B.top + 48), (sx, B.top + 40), (sx - 12, B.top + 48), (sx - 9, B.top + 34), (sx - 20, B.top + 26), (sx - 6, B.top + 24)])
    lights.append((480, B.top + 20, 110, pal["glow"]))


def back_dock(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_metal(surf, B, pal, rng)
    for vx in (170, 360, 620, 810):   # viewports onto space
        v = pygame.Rect(vx - 40, B.top + 10, 80, 34)
        pygame.draw.rect(surf, (6, 8, 18), v, border_radius=10)
        for _ in range(14):
            surf.set_at((rng.randint(v.left + 3, v.right - 4), rng.randint(v.top + 3, v.bottom - 4)), rng.choice([WHITE, (160, 190, 255)]))
        pygame.draw.rect(surf, (140, 148, 164), v, 3, border_radius=10)
    for px in (260, 500, 720):
        pygame.draw.rect(surf, (90, 96, 112), (px, B.top, 10, B.h))
    for rx in (130, 860):
        pygame.draw.circle(surf, (255, 60, 50), (rx, B.top + 12), 5)
        lights.append((rx, B.top + 12, 60, (255, 60, 50)))


def back_reactor(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_metal(surf, B, pal, rng)
    c = pygame.Rect(380, B.top + 4, 200, 44)
    pygame.draw.rect(surf, (8, 20, 28), c, border_radius=18)
    for i in range(c.h - 8):
        pygame.draw.line(surf, mix((10, 80, 100), pal["glow"], 1 - abs(i - 18) / 22), (c.left + 6, c.top + 4 + i), (c.right - 7, c.top + 4 + i))
    pygame.draw.rect(surf, (140, 160, 176), c, 3, border_radius=18)
    lights.append((480, B.top + 26, 130, pal["glow"]))
    for px in (150, 270, 690, 810):
        pygame.draw.rect(surf, (30, 50, 62), (px - 7, B.top, 14, B.h))
        for k in range(5):
            pygame.draw.rect(surf, pal["glow"], (px - 4, B.top + 4 + k * 9, 8, 4))


def back_spire(surf, B, th, rng, lights):
    pal = th["pal"]
    wall_voidcrystal(surf, B, pal, rng)
    pts = [(480, B.top), (500, B.top + 14), (472, B.top + 26), (506, B.top + 40), (484, B.bottom)]
    pygame.draw.polygon(surf, (6, 2, 16), [(440, B.top), (520, B.top)] + pts[::-1][:4])
    pygame.draw.lines(surf, pal["glow"], False, pts, 3)
    for sx in (200, 330, 640, 780):
        pygame.draw.polygon(surf, mix(pal["wall"], pal["glow"], .3), [(sx, B.top + 6), (sx + 8, B.top + 24), (sx, B.top + 40), (sx - 8, B.top + 24)])
        pygame.draw.polygon(surf, pal["glow"], [(sx, B.top + 6), (sx + 8, B.top + 24), (sx, B.top + 40), (sx - 8, B.top + 24)], 1)
    lights.append((480, B.top + 26, 120, pal["glow"]))


BACK_STYLES = {
    "outpost": back_outpost, "foundry": back_foundry, "crag": back_crag, "archive": back_archive,
    "tower": back_tower, "throne": back_throne, "garden": back_garden, "cathedral": back_cathedral,
    "seraph": back_seraph, "dock": back_dock, "reactor": back_reactor, "spire": back_spire,
}


# ------------------------------------------------------------
# FLAT FLOOR DECOR  (rugs, stains, glyphs ... never blocks movement)
# ------------------------------------------------------------
def _decor_rug(surf, p, th, rng):
    pal = th["pal"]
    w, h = rng.randint(120, 190), rng.randint(70, 110)
    r = pygame.Rect(0, 0, w, h)
    r.center = ipos(p)
    c = rng.choice([(150, 50, 56), (50, 70, 140), (60, 110, 80), (140, 100, 50)])
    c = mix(c, pal["floor"], .25)
    pygame.draw.rect(surf, c, r, border_radius=6)
    pygame.draw.rect(surf, mix(c, WHITE, .35), r.inflate(-12, -12), 2, border_radius=4)
    pygame.draw.rect(surf, mix(c, BLACK, .4), r, 2, border_radius=6)
    pygame.draw.circle(surf, mix(c, WHITE, .35), r.center, min(w, h) // 5, 2)
    for i in range(0, w, 8):
        pygame.draw.line(surf, mix(c, WHITE, .5), (r.left + i, r.top - 3), (r.left + i, r.top))
        pygame.draw.line(surf, mix(c, WHITE, .5), (r.left + i, r.bottom), (r.left + i, r.bottom + 3))


def _decor_scorch(surf, p, th, rng):
    for k in range(4):
        pygame.draw.ellipse(surf, mix(th["pal"]["floor"], BLACK, .3 + k * .12), (p[0] - 34 + k * 5, p[1] - 22 + k * 3, 68 - k * 10, 44 - k * 6))
    pygame.draw.circle(surf, (255, 130, 50), ipos(p), 3)


def _decor_bones(surf, p, th, rng):
    for _ in range(4):
        a = V(p) + V(rng.randint(-20, 20), rng.randint(-12, 12))
        b = a + from_angle(rng.random() * math.tau, rng.randint(10, 18))
        pygame.draw.line(surf, (222, 210, 184), ipos(a), ipos(b), 3)
        pygame.draw.circle(surf, (222, 210, 184), ipos(a), 3)
        pygame.draw.circle(surf, (222, 210, 184), ipos(b), 3)
    pygame.draw.circle(surf, (236, 226, 200), ipos(p), 8)
    pygame.draw.circle(surf, (30, 24, 24), (int(p[0]) - 3, int(p[1]) - 1), 2)
    pygame.draw.circle(surf, (30, 24, 24), (int(p[0]) + 3, int(p[1]) - 1), 2)


def _decor_tracks(surf, p, th, rng):
    c = mix(th["pal"]["floor"], BLACK, .3)
    for off in (-6, 6):
        pts = [(p[0] - 90 + i * 18, p[1] + off + math.sin(i * .9) * 5) for i in range(11)]
        pygame.draw.lines(surf, c, False, pts, 2)


def _decor_hazard(surf, p, th, rng):
    r = pygame.Rect(0, 0, rng.choice((120, 160, 200)), 14)
    r.center = ipos(p)
    pygame.draw.rect(surf, (28, 28, 30), r)
    for x in range(r.left - 14, r.right, 18):
        pygame.draw.polygon(surf, th["pal"]["trim"], [(x, r.bottom), (x + 9, r.bottom), (x + 23, r.top), (x + 14, r.top)])
    surf.set_clip(None)
    pygame.draw.rect(surf, (10, 10, 12), r, 1)


def _decor_cracks(surf, p, th, rng):
    pal = th["pal"]
    pts = [ipos(p)]
    q = V(p)
    a = rng.random() * math.tau
    for _ in range(rng.randint(3, 6)):
        a += rng.uniform(-.9, .9)
        q = q + from_angle(a, rng.randint(14, 30))
        pts.append(ipos(q))
    pygame.draw.lines(surf, mix(pal["glow"], BLACK, .5), False, pts, 4)
    pygame.draw.lines(surf, pal["glow"], False, pts, 1)


def _decor_stain(surf, p, th, rng):
    c = mix(th["pal"]["floor"], BLACK, .45)
    pygame.draw.ellipse(surf, c, (p[0] - 26, p[1] - 14, 52, 28))
    pygame.draw.ellipse(surf, mix(c, (200, 60, 30), .3), (p[0] - 14, p[1] - 7, 28, 14))


def _decor_papers(surf, p, th, rng):
    for _ in range(6):
        c = V(p) + V(rng.randint(-26, 26), rng.randint(-16, 16))
        pts = [c + V(-7, -5).rotate(rng.randint(0, 90)), c + V(7, -5).rotate(rng.randint(0, 90)),
               c + V(7, 5).rotate(rng.randint(0, 90)), c + V(-7, 5).rotate(rng.randint(0, 90))]
        pygame.draw.polygon(surf, (232, 224, 200), [ipos(x) for x in pts])
        pygame.draw.line(surf, (150, 140, 120), ipos(c + V(-4, 0)), ipos(c + V(4, 0)))


def _decor_glyph(surf, p, th, rng):
    pal = th["pal"]
    r = rng.randint(34, 52)
    pygame.draw.circle(surf, mix(pal["trim"], pal["floor"], .55), ipos(p), r, 2)
    pygame.draw.circle(surf, mix(pal["trim"], pal["floor"], .55), ipos(p), r - 9, 1)
    for k in range(6):
        a = k * math.tau / 6
        pygame.draw.line(surf, mix(pal["trim"], pal["floor"], .55), ipos(V(p) + from_angle(a, r - 9)), ipos(V(p) + from_angle(a + 2 * math.tau / 6, r - 9)), 1)


def _decor_frost(surf, p, th, rng):
    for k in range(5):
        pygame.draw.ellipse(surf, mix((200, 230, 250), th["pal"]["floor"], k * .18), (p[0] - 40 + k * 7, p[1] - 22 + k * 4, 80 - k * 14, 44 - k * 8))
    for _ in range(8):
        a = rng.random() * math.tau
        pygame.draw.line(surf, WHITE, ipos(p), ipos(V(p) + from_angle(a, rng.randint(10, 26))), 1)


def _decor_runner(surf, p, th, rng):
    pal = th["pal"]
    c = (150, 40, 56) if th["floor"] != "slab" else (30, 50, 130)
    r = pygame.Rect(150, 296, 700, 56)
    pygame.draw.rect(surf, c, r)
    pygame.draw.rect(surf, pal["trim"], r.inflate(-8, -8), 2)
    for x in range(r.left + 30, r.right, 70):
        pygame.draw.polygon(surf, pal["trim"], [(x, r.centery - 8), (x + 8, r.centery), (x, r.centery + 8), (x - 8, r.centery)], 1)
    pygame.draw.rect(surf, mix(c, BLACK, .5), r, 2)


def _decor_flowers(surf, p, th, rng):
    pygame.draw.ellipse(surf, (80, 140, 84), (p[0] - 32, p[1] - 20, 64, 40))
    for _ in range(16):
        c = V(p) + V(rng.randint(-28, 28), rng.randint(-16, 16))
        col = rng.choice([(255, 190, 220), (255, 240, 200), (255, 226, 120), (190, 210, 255)])
        for k in range(5):
            pygame.draw.circle(surf, col, ipos(c + from_angle(k * math.tau / 5, 3)), 2)
        pygame.draw.circle(surf, (230, 170, 60), ipos(c), 1)


def _decor_petals(surf, p, th, rng):
    for _ in range(10):
        c = V(p) + V(rng.randint(-40, 40), rng.randint(-22, 22))
        pygame.draw.ellipse(surf, rng.choice([(255, 200, 224), (255, 240, 220)]), (c.x, c.y, 6, 3))


def _decor_lightbeams(surf, p, th, rng):
    cols = [(210, 70, 80), (70, 120, 220), (230, 190, 60), (90, 190, 120), (170, 90, 210)]
    tmp = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for k, wx in enumerate(range(130, 900, 120)):
        c = cols[k % len(cols)]
        pts = [(wx - 20, ROOM_TOP), (wx + 20, ROOM_TOP), (wx + 90, ROOM_TOP + 380), (wx + 20, ROOM_TOP + 380)]
        pygame.draw.polygon(tmp, (*c, 34), pts)
    surf.blit(tmp, (0, 0))


def _decor_seal(surf, p, th, rng):
    pal = th["pal"]
    c = (480, 345)
    for r, w in ((150, 3), (126, 1), (96, 2)):
        pygame.draw.circle(surf, mix(pal["trim"], pal["floor"], .35), c, r, w)
    for k in range(12):
        a = k * math.tau / 12
        pygame.draw.line(surf, mix(pal["trim"], pal["floor"], .45), ipos(V(c) + from_angle(a, 96)), ipos(V(c) + from_angle(a, 150)), 1)
    star = [ipos(V(c) + from_angle(-math.pi / 2 + k * math.tau * 2 / 5, 96)) for k in range(5)]
    pygame.draw.polygon(surf, mix(pal["trim"], pal["floor"], .45), star, 2)


def _decor_starlines(surf, p, th, rng):
    pass


def _decor_cables(surf, p, th, rng):
    c = V(p)
    pts = [ipos(c)]
    for k in range(6):
        c = c + V(rng.randint(20, 46), rng.randint(-18, 18))
        pts.append(ipos(c))
    pygame.draw.lines(surf, (20, 22, 26), False, pts, 5)
    pygame.draw.lines(surf, rng.choice([(200, 60, 50), (60, 140, 200), (220, 180, 60)]), False, pts, 2)


def _decor_ring(surf, p, th, rng):
    pal = th["pal"]
    for r, w in ((130, 2), (110, 1)):
        pygame.draw.circle(surf, mix(pal["glow"], pal["floor"], .55), (480, 345), r, w)
    for k in range(8):
        a = k * math.tau / 8
        pygame.draw.circle(surf, pal["glow"], ipos(V(480, 345) + from_angle(a, 120)), 3)


def _decor_rift(surf, p, th, rng):
    pal = th["pal"]
    pts = []
    c = V(p)
    for k in range(7):
        a = k * math.tau / 7
        pts.append(ipos(c + from_angle(a, rng.randint(12, 36))))
    pygame.draw.polygon(surf, (4, 2, 12), pts)
    pygame.draw.polygon(surf, pal["glow"], pts, 2)


def _decor_debris(surf, p, th, rng):
    pal = th["pal"]
    for _ in range(5):
        c = V(p) + V(rng.randint(-30, 30), rng.randint(-20, 20))
        pts = [ipos(c + from_angle(k * math.tau / 4 + rng.random(), rng.randint(3, 8))) for k in range(4)]
        pygame.draw.polygon(surf, mix(pal["wall"], BLACK, .2), pts)
        pygame.draw.polygon(surf, pal["glow"], pts, 1)


DECOR_STYLES = {
    "rug": _decor_rug, "scorch": _decor_scorch, "bones": _decor_bones, "tracks": _decor_tracks,
    "hazard": _decor_hazard, "cracks": _decor_cracks, "stain": _decor_stain, "papers": _decor_papers,
    "glyph": _decor_glyph, "frost": _decor_frost, "runner": _decor_runner, "flowers": _decor_flowers,
    "petals": _decor_petals, "lightbeams": _decor_lightbeams, "seal": _decor_seal, "starlines": _decor_starlines,
    "cables": _decor_cables, "ring": _decor_ring, "rift": _decor_rift, "debris": _decor_debris,
}



# ------------------------------------------------------------
# SEARCHABLE CONTAINER SPRITES (cached per object)
# ------------------------------------------------------------
def _book(s, x, base_y, w, h, c, rng):
    if rng.random() < .1:   # leaning book
        pts = [(x, base_y), (x + w, base_y), (x + w + 4, base_y - h + 2), (x + 4, base_y - h)]
        pygame.draw.polygon(s, c, pts)
        pygame.draw.polygon(s, mix(c, BLACK, .45), pts, 1)
        return w + 4
    pygame.draw.rect(s, c, (x, base_y - h, w, h))
    pygame.draw.rect(s, mix(c, BLACK, .45), (x, base_y - h, w, h), 1)
    pygame.draw.line(s, mix(c, WHITE, .35), (x + 1, base_y - h + 2), (x + 1, base_y - 3))
    if rng.random() < .55:
        pygame.draw.rect(s, mix(c, (240, 220, 140), .6), (x, base_y - h + 3, w, 2))
    return w


def _shelf_books(s, rect, rows, rng, wood):
    rh = rect.h // rows
    for i in range(rows):
        row = pygame.Rect(rect.left, rect.top + i * rh, rect.w, rh)
        pygame.draw.rect(s, mix(wood, BLACK, .6), row)
        base_y = row.bottom - 3
        x = row.left + 2
        while x < row.right - 4:
            if rng.random() < .09:   # decoration between the books
                d = rng.choice(("jar", "skull", "candle", "scroll"))
                if d == "jar":
                    pygame.draw.rect(s, (110, 200, 150), (x, base_y - 9, 6, 9), border_radius=2)
                    pygame.draw.rect(s, (230, 230, 220), (x, base_y - 11, 6, 3))
                elif d == "skull":
                    pygame.draw.circle(s, (230, 222, 200), (x + 4, base_y - 5), 4)
                elif d == "candle":
                    pygame.draw.rect(s, (240, 230, 200), (x + 1, base_y - 8, 4, 8))
                    pygame.draw.circle(s, (255, 190, 80), (x + 3, base_y - 10), 2)
                else:
                    pygame.draw.rect(s, (226, 207, 160), (x, base_y - 7, 8, 7), border_radius=3)
                x += 10
                continue
            w = rng.randint(4, 8)
            if x + w > row.right - 3:
                break
            h = rng.randint(max(6, rh - 9), rh - 4)
            x += _book(s, x, base_y, w, h, rng.choice(BOOK_COLORS), rng) + 0
        pygame.draw.rect(s, wood, (row.left, row.bottom - 3, row.w, 3))
        pygame.draw.line(s, mix(wood, WHITE, .25), (row.left, row.bottom - 3), (row.right, row.bottom - 3))


def _cs_bookcase(s, cx, cy, th, rng, rows=4):
    wood = mix(th["pal"]["mat"], BLACK, .15)
    body = pygame.Rect(cx - 29, cy - 40, 58, 70)
    pygame.draw.rect(s, wood, body)
    pygame.draw.rect(s, mix(wood, WHITE, .2), (body.left - 2, body.top - 5, body.w + 4, 6))
    inner = pygame.Rect(body.left + 4, body.top + 4, body.w - 8, body.h - 8)
    _shelf_books(s, inner, rows, rng, wood)
    pygame.draw.rect(s, mix(wood, BLACK, .6), body, 2)
    pygame.draw.rect(s, mix(wood, BLACK, .4), (body.left, body.bottom, 5, 3))
    pygame.draw.rect(s, mix(wood, BLACK, .4), (body.right - 5, body.bottom, 5, 3))


def _cs_shelf(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], BLACK, .1)
    body = pygame.Rect(cx - 27, cy - 24, 54, 52)
    pygame.draw.rect(s, wood, body)
    inner = pygame.Rect(body.left + 4, body.top + 4, body.w - 8, body.h - 8)
    _shelf_books(s, inner, 2, rng, wood)
    pygame.draw.rect(s, mix(wood, BLACK, .6), body, 2)
    # a lamp or candle on top
    if rng.random() < .5:
        pygame.draw.rect(s, (240, 230, 200), (cx + 12, body.top - 8, 5, 8))
        pygame.draw.circle(s, (255, 190, 80), (cx + 14, body.top - 11), 3)
    else:
        pygame.draw.circle(s, (110, 200, 150), (cx - 14, body.top - 5), 5)
        pygame.draw.rect(s, (230, 230, 220), (cx - 17, body.top - 11, 6, 3))


def _cs_cabinet(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], BLACK, .05)
    body = pygame.Rect(cx - 26, cy - 34, 52, 64)
    pygame.draw.rect(s, wood, body)
    pygame.draw.rect(s, mix(wood, WHITE, .2), (body.left - 2, body.top - 4, body.w + 4, 5))
    for dx in (0, 25):
        d = pygame.Rect(body.left + 3 + dx, body.top + 5, 22, body.h - 10)
        pygame.draw.rect(s, mix(wood, BLACK, .15), d)
        pygame.draw.rect(s, mix(wood, BLACK, .5), d, 1)
        pygame.draw.rect(s, mix(wood, WHITE, .18), d.inflate(-8, -10), 1)
    pygame.draw.circle(s, th["pal"]["trim"], (cx - 4, cy), 2)
    pygame.draw.circle(s, th["pal"]["trim"], (cx + 4, cy), 2)
    pygame.draw.rect(s, mix(wood, BLACK, .6), body, 2)


def _cs_drawer(s, cx, cy, th, rng):
    wood = th["pal"]["mat"]
    body = pygame.Rect(cx - 30, cy - 20, 60, 46)
    pygame.draw.rect(s, wood, body)
    pygame.draw.rect(s, mix(wood, WHITE, .22), (body.left - 1, body.top - 3, body.w + 2, 5))
    for i in range(3):
        d = pygame.Rect(body.left + 4, body.top + 5 + i * 13, body.w - 8, 11)
        pygame.draw.rect(s, mix(wood, BLACK, .12), d)
        pygame.draw.rect(s, mix(wood, BLACK, .5), d, 1)
        pygame.draw.circle(s, th["pal"]["trim"], d.center, 2)
    pygame.draw.rect(s, mix(wood, BLACK, .6), body, 2)
    pygame.draw.circle(s, (230, 200, 120), (cx - 18, body.top - 7), 4)
    pygame.draw.rect(s, (200, 60, 60), (cx + 8, body.top - 8, 8, 6))
    pygame.draw.rect(s, (60, 100, 200), (cx + 10, body.top - 13, 8, 5))


def _cs_desk(s, cx, cy, th, rng):
    wood = th["pal"]["mat"]
    pygame.draw.rect(s, mix(wood, BLACK, .3), (cx - 32, cy - 4, 6, 28))
    pygame.draw.rect(s, mix(wood, BLACK, .3), (cx + 26, cy - 4, 6, 28))
    pygame.draw.rect(s, mix(wood, BLACK, .12), (cx - 26, cy + 2, 52, 16))
    pygame.draw.rect(s, mix(wood, BLACK, .5), (cx - 26, cy + 2, 52, 16), 1)
    pygame.draw.circle(s, th["pal"]["trim"], (cx, cy + 10), 2)
    top = pygame.Rect(cx - 36, cy - 14, 72, 18)
    pygame.draw.rect(s, mix(wood, WHITE, .2), top, border_radius=3)
    pygame.draw.rect(s, mix(wood, BLACK, .5), top, 1, border_radius=3)
    pygame.draw.rect(s, (236, 228, 204), (cx - 24, cy - 12, 18, 12))
    pygame.draw.line(s, (150, 140, 120), (cx - 22, cy - 8), (cx - 9, cy - 8))
    for i, c in enumerate(rng.sample(BOOK_COLORS, 3)):
        pygame.draw.rect(s, c, (cx + 6, cy - 22 + i * 4 - 0, 18, 5))
        pygame.draw.rect(s, mix(c, BLACK, .45), (cx + 6, cy - 22 + i * 4, 18, 5), 1)
    pygame.draw.circle(s, (30, 30, 40), (cx - 2, cy - 6), 3)


def _cs_crate(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], (110, 78, 48), .4)
    r = pygame.Rect(cx - 25, cy - 22, 50, 46)
    pygame.draw.rect(s, wood, r)
    for y in range(r.top + 11, r.bottom, 11):
        pygame.draw.line(s, mix(wood, BLACK, .4), (r.left, y), (r.right, y))
    pygame.draw.rect(s, mix(wood, BLACK, .35), r, 4)
    pygame.draw.line(s, mix(wood, BLACK, .35), r.topleft, r.bottomright, 3)
    pygame.draw.line(s, mix(wood, BLACK, .35), r.topright, r.bottomleft, 3)
    pygame.draw.rect(s, mix(wood, BLACK, .6), r, 2)
    for p in (r.topleft, r.topright, r.bottomleft, r.bottomright):
        pygame.draw.circle(s, (170, 170, 160), (p[0] + (3 if p[0] == r.left else -3), p[1] + (3 if p[1] == r.top else -3)), 1)


def _cs_barrel(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], (116, 78, 46), .4)
    pygame.draw.rect(s, wood, (cx - 19, cy - 20, 38, 42), border_radius=8)
    for x in range(cx - 14, cx + 18, 8):
        pygame.draw.line(s, mix(wood, BLACK, .3), (x, cy - 19), (x, cy + 20))
    pygame.draw.ellipse(s, mix(wood, WHITE, .2), (cx - 19, cy - 27, 38, 15))
    pygame.draw.ellipse(s, mix(wood, BLACK, .5), (cx - 19, cy - 27, 38, 15), 2)
    for y in (cy - 10, cy + 12):
        pygame.draw.line(s, (60, 54, 52), (cx - 19, y), (cx + 19, y), 3)


def _cs_chest(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], (116, 78, 46), .35)
    body = pygame.Rect(cx - 28, cy - 4, 56, 28)
    pygame.draw.rect(s, wood, body)
    pygame.draw.rect(s, mix(wood, BLACK, .2), (cx - 28, cy - 22, 56, 20), border_top_left_radius=20, border_top_right_radius=20)
    for x in (cx - 18, cx + 14):
        pygame.draw.rect(s, (70, 64, 60), (x, cy - 22, 5, 46))
    pygame.draw.rect(s, mix(wood, BLACK, .6), body, 2)
    pygame.draw.rect(s, th["pal"]["trim"], (cx - 5, cy - 6, 10, 10), border_radius=2)
    pygame.draw.circle(s, (30, 24, 20), (cx, cy - 1), 2)


def _cs_trash(s, cx, cy, th, rng):
    pygame.draw.ellipse(s, (96, 100, 108), (cx - 21, cy - 18, 42, 44))
    pygame.draw.ellipse(s, (60, 62, 70), (cx - 21, cy - 24, 42, 14))
    pygame.draw.ellipse(s, (130, 134, 142), (cx - 21, cy - 24, 42, 14), 2)
    for x in range(cx - 14, cx + 16, 9):
        pygame.draw.line(s, (70, 72, 80), (x, cy - 10), (x, cy + 22))
    for _ in range(3):
        pygame.draw.circle(s, (232, 226, 206), (cx + rng.randint(-10, 10), cy - 24 + rng.randint(-2, 2)), 4)


def _cs_locker(s, cx, cy, th, rng):
    m = th["pal"]["mat"]
    body = pygame.Rect(cx - 19, cy - 36, 38, 68)
    pygame.draw.rect(s, m, body)
    pygame.draw.rect(s, mix(m, WHITE, .2), (body.left, body.top, body.w, 4))
    for i in range(4):
        pygame.draw.line(s, mix(m, BLACK, .55), (cx - 12, cy - 30 + i * 4), (cx + 12, cy - 30 + i * 4), 2)
    pygame.draw.rect(s, mix(m, BLACK, .3), (cx - 13, cy - 8, 26, 34), 1)
    pygame.draw.rect(s, (220, 220, 230), (cx + 6, cy + 4, 3, 10))
    pygame.draw.rect(s, th["pal"]["trim"], (cx - 8, cy - 18, 16, 6))
    pygame.draw.rect(s, mix(m, BLACK, .6), body, 2)


def _cs_cart(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], (116, 78, 46), .4)
    pygame.draw.rect(s, wood, (cx - 30, cy - 16, 60, 26))
    pygame.draw.rect(s, mix(wood, BLACK, .5), (cx - 30, cy - 16, 60, 26), 2)
    for x in range(cx - 24, cx + 28, 12):
        pygame.draw.line(s, mix(wood, BLACK, .35), (x, cy - 15), (x, cy + 9))
    pygame.draw.ellipse(s, (210, 196, 150), (cx - 22, cy - 26, 22, 16))
    pygame.draw.ellipse(s, (196, 150, 100), (cx + 2, cy - 24, 20, 14))
    pygame.draw.circle(s, (70, 56, 44), (cx - 20, cy + 16), 9)
    pygame.draw.circle(s, wood, (cx - 20, cy + 16), 6, 2)
    pygame.draw.circle(s, (70, 56, 44), (cx + 20, cy + 16), 9)
    pygame.draw.circle(s, wood, (cx + 20, cy + 16), 6, 2)
    pygame.draw.line(s, wood, (cx - 30, cy - 4), (cx - 46, cy + 8), 3)


def _cs_toolrack(s, cx, cy, th, rng):
    wood = mix(th["pal"]["mat"], BLACK, .2)
    pygame.draw.rect(s, wood, (cx - 28, cy - 30, 56, 56))
    pygame.draw.rect(s, mix(wood, BLACK, .55), (cx - 28, cy - 30, 56, 56), 2)
    pygame.draw.line(s, (60, 54, 52), (cx - 26, cy - 14), (cx + 26, cy - 14), 3)
    pygame.draw.line(s, (60, 54, 52), (cx - 26, cy + 8), (cx + 26, cy + 8), 3)
    pygame.draw.line(s, (150, 150, 160), (cx - 18, cy - 14), (cx - 18, cy - 28), 3)
    pygame.draw.rect(s, (150, 150, 160), (cx - 24, cy - 30, 12, 6))
    pygame.draw.line(s, (130, 90, 56), (cx, cy - 12), (cx, cy + 20), 3)
    pygame.draw.polygon(s, (150, 150, 160), [(cx - 8, cy - 14), (cx + 8, cy - 14), (cx + 4, cy - 6), (cx - 4, cy - 6)])
    pygame.draw.line(s, (170, 170, 180), (cx + 16, cy - 10), (cx + 16, cy + 22), 3)
    pygame.draw.line(s, (170, 170, 180), (cx + 21, cy - 10), (cx + 21, cy + 22), 2)


def _cs_anvil(s, cx, cy, th, rng):
    pygame.draw.rect(s, (96, 66, 44), (cx - 14, cy + 4, 28, 22), border_radius=3)
    pygame.draw.polygon(s, (86, 88, 100), [(cx - 30, cy - 10), (cx + 28, cy - 10), (cx + 14, cy), (cx + 10, cy + 6), (cx - 10, cy + 6), (cx - 14, cy)])
    pygame.draw.polygon(s, (130, 134, 146), [(cx - 30, cy - 10), (cx + 28, cy - 10), (cx + 24, cy - 14), (cx - 24, cy - 14)])
    pygame.draw.polygon(s, (46, 46, 54), [(cx - 30, cy - 10), (cx + 28, cy - 10), (cx + 14, cy), (cx + 10, cy + 6), (cx - 10, cy + 6), (cx - 14, cy)], 2)
    pygame.draw.circle(s, (255, 140, 50), (cx + 4, cy - 17), 3)


def _cs_urn(s, cx, cy, th, rng):
    c = mix(th["pal"]["mat"], WHITE, .3)
    pts = [(cx - 8, cy - 28), (cx + 8, cy - 28), (cx + 10, cy - 20), (cx + 22, cy - 6), (cx + 16, cy + 18), (cx + 8, cy + 24), (cx - 8, cy + 24), (cx - 16, cy + 18), (cx - 22, cy - 6), (cx - 10, cy - 20)]
    pygame.draw.polygon(s, c, pts)
    pygame.draw.polygon(s, mix(c, WHITE, .4), [(cx - 14, cy - 6), (cx - 8, cy - 14), (cx - 6, cy + 10), (cx - 12, cy + 12)])
    pygame.draw.polygon(s, mix(c, BLACK, .5), pts, 2)
    pygame.draw.line(s, th["pal"]["trim"], (cx - 20, cy - 2), (cx + 20, cy - 2), 3)
    pygame.draw.line(s, th["pal"]["trim"], (cx - 14, cy + 12), (cx + 14, cy + 12), 2)


def _cs_altar(s, cx, cy, th, rng):
    st = mix(th["pal"]["mat"], WHITE, .25)
    pygame.draw.rect(s, st, (cx - 30, cy - 4, 60, 28))
    pygame.draw.rect(s, mix(st, WHITE, .2), (cx - 34, cy - 12, 68, 10))
    pygame.draw.rect(s, mix(st, BLACK, .5), (cx - 34, cy - 12, 68, 36), 2)
    pygame.draw.rect(s, th["pal"]["trim"], (cx - 24, cy - 12, 48, 5))
    for dx in (-22, 22):
        pygame.draw.rect(s, (240, 230, 200), (cx + dx - 2, cy - 26, 5, 14))
        pygame.draw.circle(s, (255, 200, 100), (cx + dx, cy - 28), 3)
    pygame.draw.circle(s, th["pal"]["glow"], (cx, cy - 18), 5)


def _cs_terminal(s, cx, cy, th, rng):
    pal = th["pal"]
    pygame.draw.rect(s, (40, 46, 58), (cx - 26, cy - 8, 52, 30), border_radius=3)
    pygame.draw.polygon(s, (50, 56, 70), [(cx - 24, cy - 8), (cx + 24, cy - 8), (cx + 20, cy - 32), (cx - 20, cy - 32)])
    pygame.draw.rect(s, mix(pal["glow"], BLACK, .65), (cx - 17, cy - 29, 34, 18))
    for i in range(4):
        pygame.draw.line(s, pal["glow"], (cx - 14, cy - 26 + i * 4), (cx - 14 + rng.randint(8, 28), cy - 26 + i * 4))
    for i in range(5):
        pygame.draw.rect(s, rng.choice([(200, 60, 50), (60, 200, 100), (220, 180, 60)]), (cx - 20 + i * 9, cy + 6, 6, 4))
    pygame.draw.rect(s, (110, 118, 134), (cx - 26, cy - 8, 52, 30), 2, border_radius=3)


def _cs_icechest(s, cx, cy, th, rng):
    pygame.draw.rect(s, (150, 200, 235), (cx - 27, cy - 6, 54, 28), border_radius=3)
    pygame.draw.rect(s, (190, 230, 250), (cx - 27, cy - 18, 54, 16), border_top_left_radius=14, border_top_right_radius=14)
    for x in (cx - 16, cx + 10):
        pygame.draw.line(s, (255, 255, 255), (x, cy - 18), (x + 4, cy + 20), 1)
    pygame.draw.rect(s, (230, 248, 255), (cx - 27, cy - 18, 54, 40), 2, border_radius=3)
    pygame.draw.polygon(s, (255, 255, 255), [(cx - 6, cy - 28), (cx - 1, cy - 18), (cx - 11, cy - 18)])
    pygame.draw.polygon(s, (255, 255, 255), [(cx + 10, cy - 24), (cx + 14, cy - 18), (cx + 6, cy - 18)])
    pygame.draw.rect(s, (90, 150, 210), (cx - 4, cy - 6, 8, 8), border_radius=2)


# ---- objective-style containers (what the quest text actually asks for) ----
def _cs_wagon(s, cx, cy, th, rng):
    wood = (112, 78, 46)
    pygame.draw.rect(s, wood, (cx - 34, cy - 22, 68, 38))
    pygame.draw.rect(s, (70, 48, 30), (cx - 34, cy - 22, 68, 38), 3)
    pygame.draw.line(s, (70, 48, 30), (cx - 34, cy - 4), (cx + 34, cy - 4), 3)
    pygame.draw.polygon(s, (210, 196, 150), [(cx - 24, cy - 22), (cx - 6, cy - 34), (cx + 10, cy - 22)])
    pygame.draw.circle(s, (60, 48, 40), (cx - 24, cy + 18), 10)
    pygame.draw.circle(s, wood, (cx - 24, cy + 18), 7, 2)
    pygame.draw.circle(s, (60, 48, 40), (cx + 24, cy + 18), 10)
    pygame.draw.circle(s, wood, (cx + 24, cy + 18), 7, 2)
    pygame.draw.line(s, (60, 40, 30), (cx - 34, cy + 6), (cx - 50, cy + 14), 4)


def _cs_cargo(s, cx, cy, th, rng):
    pygame.draw.rect(s, (92, 62, 38), (cx - 34, cy - 20, 68, 42))
    pygame.draw.rect(s, th["pal"]["trim"], (cx - 34, cy - 20, 68, 42), 2)
    pygame.draw.line(s, th["pal"]["trim"], (cx - 34, cy), (cx + 34, cy), 2)
    pygame.draw.rect(s, (230, 200, 120), (cx - 8, cy - 8, 16, 12))
    pygame.draw.rect(s, (60, 40, 30), (cx - 8, cy - 8, 16, 12), 1)


def _cs_door(s, cx, cy, th, rng):
    pal = th["pal"]
    pygame.draw.rect(s, mix(pal["wall"], BLACK, .4), (cx - 29, cy - 38, 58, 74), border_top_left_radius=26, border_top_right_radius=26)
    pygame.draw.rect(s, (14, 12, 18), (cx - 23, cy - 33, 46, 68), border_top_left_radius=22, border_top_right_radius=22)
    pygame.draw.rect(s, pal["edge"], (cx - 23, cy - 33, 46, 68), 3, border_top_left_radius=22, border_top_right_radius=22)
    pygame.draw.line(s, pal["edge"], (cx, cy - 33), (cx, cy + 35), 2)
    pygame.draw.circle(s, pal["trim"], (cx + 8, cy + 2), 3)
    pygame.draw.circle(s, pal["trim"], (cx - 8, cy + 2), 3)


def _cs_relay(s, cx, cy, th, rng):
    pal = th["pal"]
    pygame.draw.rect(s, (36, 42, 56), (cx - 22, cy + 6, 44, 18), border_radius=3)
    pygame.draw.polygon(s, (60, 70, 90), [(cx - 8, cy + 6), (cx + 8, cy + 6), (cx + 4, cy - 30), (cx - 4, cy - 30)])
    pygame.draw.circle(s, pal["glow"], (cx, cy - 34), 7)
    pygame.draw.circle(s, WHITE, (cx, cy - 34), 3)
    pygame.draw.arc(s, pal["glow"], (cx - 16, cy - 50, 32, 32), .6, 2.5, 2)
    pygame.draw.rect(s, pal["trim"], (cx - 14, cy + 11, 28, 4))


def _cs_console(s, cx, cy, th, rng):
    _cs_terminal(s, cx, cy, th, rng)


def _cs_crystal(s, cx, cy, th, rng):
    pal = th["pal"]
    for dx, hh, ww, c in ((-12, 34, 14, pal["glow"]), (8, 42, 16, mix(pal["glow"], WHITE, .4)), (-1, 24, 12, mix(pal["glow"], WHITE, .15))):
        pts = [(cx + dx, cy + 20 - hh), (cx + dx + ww // 2, cy + 6), (cx + dx + ww // 3, cy + 22), (cx + dx - ww // 3, cy + 22), (cx + dx - ww // 2, cy + 6)]
        pygame.draw.polygon(s, c, pts)
        pygame.draw.polygon(s, WHITE, pts, 2)


def _cs_orb(s, cx, cy, th, rng):
    pal = th["pal"]
    pygame.draw.circle(s, pal["trim"], (cx, cy), 24, 3)
    pygame.draw.circle(s, mix(pal["glow"], BLACK, .4), (cx, cy), 18)
    pygame.draw.circle(s, pal["glow"], (cx, cy), 10)
    pygame.draw.circle(s, WHITE, (cx - 3, cy - 3), 3)
    pygame.draw.line(s, pal["trim"], (cx - 16, cy), (cx + 16, cy), 1)


CONTAINER_SPRITES = {
    "bookcase": _cs_bookcase, "shelf": _cs_shelf, "cabinet": _cs_cabinet, "drawer": _cs_drawer, "desk": _cs_desk,
    "crate": _cs_crate, "barrel": _cs_barrel, "chest": _cs_chest, "trash can": _cs_trash, "locker": _cs_locker,
    "cart": _cs_cart, "toolrack": _cs_toolrack, "anvil": _cs_anvil, "urn": _cs_urn, "altar": _cs_altar,
    "terminal": _cs_terminal, "icechest": _cs_icechest,
    "wagon": _cs_wagon, "cargo": _cs_cargo,
    "gate": _cs_door, "archive door": _cs_door, "study door": _cs_door, "passage": _cs_door, "hidden entrance": _cs_door,
    "reliquary": _cs_door,
    "relay": _cs_relay, "console": _cs_console, "tether": _cs_relay, "pylon": _cs_relay, "disruptor": _cs_console,
    "memory core": _cs_orb, "access card": _cs_drawer,
    "crystal": _cs_crystal, "hymn fragment": _cs_crystal, "relic": _cs_crystal,
    "choir": _cs_altar, "stair": _cs_orb,
}


def build_container_sprite(kind, th, seed, searched):
    rng = random.Random(seed)
    s = pygame.Surface((120, 110), pygame.SRCALPHA)
    cx, cy = 60, 62
    pygame.draw.ellipse(s, (0, 0, 0, 90), (cx - 30, cy + 14, 60, 14))
    CONTAINER_SPRITES.get(kind, _cs_cabinet)(s, cx, cy, th, rng)
    if searched:
        # rummaged: darker, with books / scraps spilled on the floor
        dark = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 0))
        s.blit(dark, (0, 0))
        s.fill((150, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if kind in ("bookcase", "shelf", "desk", "drawer", "cabinet"):
            for k in range(3):
                _book(s, cx - 24 + k * 15 + rng.randint(-3, 3), cy + 32 + rng.randint(-1, 2), 12, 6, rng.choice(BOOK_COLORS), rng)
        else:
            for _ in range(3):
                pygame.draw.circle(s, (232, 226, 206), (cx + rng.randint(-26, 26), cy + 28 + rng.randint(-2, 3)), 3)
    return s


# ------------------------------------------------------------
# DOORS
# ------------------------------------------------------------
def draw_room_door(surf, p, th, color, label, t):
    x, y = ipos(p)
    pal = th["pal"]
    style = th["door"]
    if color == GOLD:
        glow(surf, (x, y), 64 + math.sin(t * 4) * 5, GOLD, 80)
    frame = mix(pal["wall"], BLACK, .3)
    if style == "timber":
        pygame.draw.rect(surf, (28, 20, 16), (x - 18, y - 42, 36, 84))
        for dx in (-18, 0):
            pygame.draw.rect(surf, (110, 76, 46), (x + dx + 1, y - 40, 17, 80))
            pygame.draw.line(surf, (70, 48, 30), (x + dx + 8, y - 40), (x + dx + 8, y + 40))
        for yy in (-26, 8, 30):
            pygame.draw.line(surf, (60, 58, 60), (x - 18, y + yy), (x + 18, y + yy), 3)
        pygame.draw.rect(surf, (80, 56, 34), (x - 22, y - 46, 44, 7))
    elif style == "metal":
        pygame.draw.rect(surf, (12, 14, 20), (x - 18, y - 42, 36, 84))
        pygame.draw.rect(surf, (96, 104, 120), (x - 18, y - 42, 36, 84), 3)
        for yy in range(-36, 36, 12):
            pygame.draw.polygon(surf, (255, 200, 60) if color != GREEN else (90, 210, 130),
                                [(x - 12, y + yy + 8), (x - 4, y + yy), (x + 4, y + yy), (x - 4, y + yy + 8)], 0)
            pygame.draw.polygon(surf, (30, 30, 34), [(x + 4, y + yy + 8), (x + 12, y + yy), (x + 6, y + yy), (x - 2, y + yy + 8)], 0)
        pygame.draw.rect(surf, color, (x - 2, y - 40, 4, 80))
    elif style == "rock":
        pts = [(x - 20, y + 42), (x - 18, y - 14), (x - 8, y - 38), (x + 4, y - 44), (x + 16, y - 30), (x + 20, y + 42)]
        pygame.draw.polygon(surf, (8, 4, 6), pts)
        pygame.draw.polygon(surf, mix(pal["wall"], BLACK, .2), pts, 4)
        pygame.draw.line(surf, pal["glow"], (x - 8, y - 38), (x - 14, y - 6), 2)
    elif style == "crystal":
        pts = [(x - 20, y + 42), (x - 20, y - 12), (x, y - 46), (x + 20, y - 12), (x + 20, y + 42)]
        pygame.draw.polygon(surf, (30, 60, 100), pts)
        pygame.draw.polygon(surf, (225, 246, 255), pts, 3)
        pygame.draw.line(surf, (255, 255, 255), (x, y - 44), (x, y + 40), 1)
        pygame.draw.polygon(surf, (255, 255, 255), [(x - 20, y - 12), (x - 28, y - 22), (x - 18, y - 24)])
    elif style == "hedge":
        pygame.draw.rect(surf, (20, 40, 28), (x - 17, y - 36, 34, 78), border_top_left_radius=17, border_top_right_radius=17)
        rr = random.Random(x * 7 + y)
        for _ in range(26):
            a = rr.random() * math.pi
            c = (x + int(math.cos(a) * 21), y - 34 + int(-math.sin(a) * 26) + rr.randint(0, 30))
            pygame.draw.circle(surf, (60 + rr.randint(0, 40), 130 + rr.randint(0, 40), 70), c, rr.randint(4, 7))
        pygame.draw.arc(surf, (255, 226, 140), (x - 20, y - 46, 40, 40), 0, math.pi, 3)
    elif style == "gold":
        pygame.draw.rect(surf, (10, 6, 28), (x - 18, y - 42, 36, 84), border_top_left_radius=18, border_top_right_radius=18)
        pygame.draw.rect(surf, (255, 214, 100), (x - 18, y - 42, 36, 84), 3, border_top_left_radius=18, border_top_right_radius=18)
        pygame.draw.polygon(surf, (255, 214, 100), [(x, y - 20), (x + 4, y - 8), (x + 16, y - 8), (x + 6, y), (x + 10, y + 12), (x, y + 5), (x - 10, y + 12), (x - 6, y), (x - 16, y - 8), (x - 4, y - 8)], 1)
    elif style == "rift":
        pygame.draw.ellipse(surf, (4, 2, 12), (x - 18, y - 42, 36, 84))
        for k in range(3):
            pygame.draw.ellipse(surf, mix(pal["glow"], BLACK, k * .3), (x - 18 + k * 4, y - 42 + k * 8, 36 - k * 8, 84 - k * 16), 2)
        for k in range(6):
            a = t * 2 + k
            pygame.draw.circle(surf, pal["glow"], (x + int(math.cos(a) * 9), y + int(math.sin(a * 1.3) * 30)), 2)
    else:   # arch
        pygame.draw.rect(surf, (12, 12, 20), (x - 18, y - 42, 36, 84), border_top_left_radius=18, border_top_right_radius=18)
        pygame.draw.rect(surf, mix(pal["edge"], WHITE, .1), (x - 18, y - 42, 36, 84), 3, border_top_left_radius=18, border_top_right_radius=18)
        pygame.draw.polygon(surf, pal["edge"], [(x - 5, y - 44), (x + 5, y - 44), (x + 3, y - 36), (x - 3, y - 36)])
    pygame.draw.rect(surf, color, (x - 18, y - 42, 36, 84), 1)
    draw_text(surf, label, (x, y - 62), color, 16, center=True)


# ------------------------------------------------------------
# OBJECTIVE PROPS  (non-search interact rooms)
# ------------------------------------------------------------
def draw_objective_prop(surf, p, th, label, t):
    x, y = ipos(p)
    pal = th["pal"]
    low = label.lower()
    g = pal["glow"]
    pulse = math.sin(t * 4)
    glow(surf, (x, y), 52 + pulse * 5, GOLD, 70)
    pygame.draw.ellipse(surf, (0, 0, 0), (x - 24, y + 16, 48, 12))
    if "wardstone" in low:
        pts = [(x - 16, y + 22), (x - 12, y - 18), (x - 2, y - 36), (x + 10, y - 22), (x + 16, y + 22)]
        pygame.draw.polygon(surf, (74, 58, 54), pts)
        pygame.draw.polygon(surf, (36, 28, 28), pts, 3)
        for k in range(3):
            pygame.draw.line(surf, g, (x - 6, y - 14 + k * 11), (x + 6, y - 10 + k * 11), 2)
        pygame.draw.line(surf, g, (x - 2, y - 36), (x + 4, y - 8), 1)
        glow(surf, (x, y - 6), 40, g, 110)
    elif "seal" in low and th["pal"]["glow"][2] > 200 and th["pal"]["glow"][0] < 200:   # frozen ice seal
        pts = [(x + math.cos(k * math.tau / 6) * 26, y + math.sin(k * math.tau / 6) * 20) for k in range(6)]
        pygame.draw.polygon(surf, (120, 170, 220), pts)
        pygame.draw.polygon(surf, (235, 250, 255), pts, 3)
        for k in range(3):
            a = k * math.pi / 3
            pygame.draw.line(surf, WHITE, (x + math.cos(a) * 18, y + math.sin(a) * 14), (x - math.cos(a) * 18, y - math.sin(a) * 14), 2)
        glow(surf, (x, y), 40, g, 110)
    elif "seal" in low:   # celestial seal
        pygame.draw.circle(surf, (20, 14, 50), (x, y), 26)
        pygame.draw.circle(surf, (255, 214, 100), (x, y), 26, 3)
        star = [(x + math.cos(-math.pi / 2 + k * math.tau * 2 / 5 + t * .6) * 18, y + math.sin(-math.pi / 2 + k * math.tau * 2 / 5 + t * .6) * 18) for k in range(5)]
        pygame.draw.polygon(surf, (255, 214, 100), star, 2)
        glow(surf, (x, y), 44, (255, 220, 130), 120)
    elif "pylon" in low or "tether" in low:
        pygame.draw.polygon(surf, (50, 36, 80), [(x - 10, y + 22), (x - 14, y - 10), (x, y - 36), (x + 14, y - 10), (x + 10, y + 22)])
        pygame.draw.polygon(surf, g, [(x - 10, y + 22), (x - 14, y - 10), (x, y - 36), (x + 14, y - 10), (x + 10, y + 22)], 2)
        for k in range(3):
            a = t * 2 + k * 2.1
            pygame.draw.circle(surf, g, (x + int(math.cos(a) * 22), y - 6 + int(math.sin(a) * 8)), 3)
        glow(surf, (x, y - 8), 50, g, 120)
    elif "relay" in low:
        _cs_relay(surf, x, y + 4, th, random.Random(1))
        glow(surf, (x, y - 30), 50, g, 120)
    elif "gate" in low or "stair" in low:
        pw = 30
        pygame.draw.rect(surf, mix(pal["wall"], BLACK, .3), (x - pw, y - 36, pw * 2, 62), border_top_left_radius=24, border_top_right_radius=24)
        pygame.draw.rect(surf, pal["edge"], (x - pw, y - 36, pw * 2, 62), 3, border_top_left_radius=24, border_top_right_radius=24)
        pygame.draw.line(surf, pal["edge"], (x, y - 36), (x, y + 26), 2)
        pygame.draw.rect(surf, GOLD, (x - 7, y - 4, 14, 12), border_radius=2)
        pygame.draw.circle(surf, (30, 24, 20), (x, y), 2)
    elif any(w in low for w in ("console", "signal", "upload", "disruptor")):
        _cs_terminal(surf, x, y, th, random.Random(2))
        glow(surf, (x, y - 14), 40, g, 100)
    elif any(w in low for w in ("reliquary", "shrine")):
        pygame.draw.rect(surf, (236, 228, 206), (x - 26, y - 4, 52, 26), border_radius=3)
        pygame.draw.rect(surf, (255, 214, 100), (x - 26, y - 4, 52, 26), 2, border_radius=3)
        pygame.draw.rect(surf, (236, 228, 206), (x - 20, y - 30, 40, 28), border_top_left_radius=20, border_top_right_radius=20)
        pygame.draw.rect(surf, (255, 214, 100), (x - 20, y - 30, 40, 28), 2, border_top_left_radius=20, border_top_right_radius=20)
        pygame.draw.circle(surf, (255, 240, 190), (x, y - 14), 6)
        glow(surf, (x, y - 14), 36, (255, 230, 170), 120)
    elif any(w in low for w in ("hymn", "choir")):
        pygame.draw.ellipse(surf, (230, 224, 206), (x - 28, y + 2, 56, 22))
        pygame.draw.ellipse(surf, (255, 226, 150), (x - 28, y + 2, 56, 22), 2)
        pygame.draw.polygon(surf, (255, 214, 100), [(x - 12, y - 6), (x + 12, y - 6), (x + 16, y + 6), (x - 16, y + 6)])
        pygame.draw.circle(surf, (255, 240, 190), (x, y + 6), 4)
        for k in range(3):
            pygame.draw.circle(surf, (255, 240, 190), (x - 16 + k * 16, y - 20 - int(abs(math.sin(t * 2 + k)) * 8)), 3)
    elif any(w in low for w in ("crate", "cargo", "ledger", "codex", "card", "core", "relic", "key", "fragment", "book")):
        pygame.draw.rect(surf, (110, 80, 50), (x - 20, y - 14, 40, 30), border_radius=3)
        pygame.draw.rect(surf, GOLD, (x - 20, y - 14, 40, 30), 2, border_radius=3)
        pygame.draw.line(surf, GOLD, (x - 20, y), (x + 20, y), 2)
    else:
        pygame.draw.circle(surf, pal["trim"], (x, y), 20, 3)
        pygame.draw.circle(surf, WHITE, (x, y), 6)


# ------------------------------------------------------------
# GUARD (styles: soldier / warden / sentinel / drone)
# ------------------------------------------------------------
class Guard:
    """Patrolling stealth guard with a vision cone."""
    VIEW_RANGE = 185
    VIEW_ANGLE = 0.55
    STYLES = {
        "soldier": {"cone": (255, 230, 140), "body": (96, 100, 116), "head": (156, 160, 176)},
        "warden": {"cone": (170, 220, 255), "body": (70, 100, 170), "head": (214, 232, 252)},
        "sentinel": {"cone": (255, 236, 160), "body": (238, 226, 192), "head": (255, 246, 220)},
        "drone": {"cone": (90, 240, 255), "body": (44, 52, 68), "head": (90, 240, 255)},
    }

    def __init__(self, points, speed=60, style="soldier"):
        self.points = [V(p) for p in points]
        self.pos = V(self.points[0])
        self.target = 1 % len(self.points)
        self.speed = speed * (1.45 if style == "drone" else 1.0)
        self.VIEW_RANGE = 285 if style == "drone" else 185
        self.VIEW_ANGLE = 0.72 if style == "drone" else 0.55
        self.gain = 1.9 if style == "drone" else 1.0
        self.facing = 0.0
        self.pause = 0.0
        self.look = 0.0
        self.style = style if style in self.STYLES else "soldier"

    def update(self, dt):
        self.look += dt
        if self.pause > 0:
            self.pause -= dt
            self.facing += math.sin(self.look * 2.5) * dt * 1.2
            return
        tgt = self.points[self.target]
        d = tgt - self.pos
        if d.length() < 4:
            self.target = (self.target + 1) % len(self.points)
            self.pause = .3 if self.style == "drone" else 1.1
            return
        self.facing = math.atan2(d.y, d.x)
        self.pos += d.normalize() * min(d.length(), self.speed * dt)

    def sees(self, scene, p):
        d = dist(self.pos, p)
        if d > self.VIEW_RANGE:
            return 0.0
        if angle_diff(angle_to(self.pos, p), self.facing) > self.VIEW_ANGLE:
            return 0.0
        if not scene.line_clear(self.pos, p):
            return 0.0
        return (1.4 - d / self.VIEW_RANGE) * self.gain

    def draw_cone(self, surf, alerting, scene):
        """Wall-clipped, layered vision cone with a bright outline."""
        col = (255, 70, 55) if alerting else self.STYLES[self.style]["cone"]
        rays = 19
        lengths = []
        for i in range(rays):
            a = self.facing - self.VIEW_ANGLE + i * self.VIEW_ANGLE * 2 / (rays - 1)
            d = from_angle(a, 1)
            length = self.VIEW_RANGE
            for step in range(6, self.VIEW_RANGE + 1, 6):
                if scene.is_solid(self.pos + d * step):
                    length = step
                    break
            lengths.append((a, length))
        origin = ipos(self.pos)
        for frac, alpha in ((1.0, 54), (.7, 60), (.42, 72)):
            pts = [origin]
            for a, length in lengths:
                pts.append(ipos(self.pos + from_angle(a, min(length, self.VIEW_RANGE * frac))))
            pygame.draw.polygon(surf, (*col, alpha), pts)
        edge = [ipos(self.pos + from_angle(a, length)) for a, length in lengths]
        pygame.draw.lines(surf, (*col, 200), False, edge, 2)
        pygame.draw.line(surf, (*col, 190), origin, edge[0], 2)
        pygame.draw.line(surf, (*col, 190), origin, edge[-1], 2)

    def draw(self, surf):
        x, y = ipos(self.pos)
        st = self.STYLES[self.style]
        if self.style == "drone":
            bob = int(math.sin(self.look * 4) * 3)
            pygame.draw.ellipse(surf, (0, 0, 0), (x - 12, y + 16, 24, 7))
            pygame.draw.circle(surf, st["body"], (x, y - 4 + bob), 13)
            pygame.draw.circle(surf, (110, 120, 140), (x, y - 4 + bob), 13, 2)
            pygame.draw.circle(surf, (20, 22, 30), (x, y - 4 + bob), 7)
            eye = from_angle(self.facing, 4)
            pygame.draw.circle(surf, st["head"], (int(x + eye.x), int(y - 4 + bob + eye.y)), 4)
            for k in (-1, 1):
                pygame.draw.line(surf, (110, 120, 140), (x + k * 12, y - 6 + bob), (x + k * 20, y - 10 + bob), 3)
                pygame.draw.circle(surf, st["head"], (x + k * 20, y - 10 + bob), 3)
            glow(surf, (x, y - 4 + bob), 30, st["cone"], 90)
            return
        pygame.draw.ellipse(surf, (0, 0, 0), (x - 12, y + 12, 24, 8))
        if self.style == "warden":
            pygame.draw.polygon(surf, st["body"], [(x - 9, y - 8), (x + 9, y - 8), (x + 14, y + 16), (x - 14, y + 16)])
            pygame.draw.polygon(surf, mix(st["body"], BLACK, .3), [(x - 9, y - 8), (x + 9, y - 8), (x + 14, y + 16), (x - 14, y + 16)], 2)
            pygame.draw.circle(surf, st["body"], (x, y - 14), 10)
            pygame.draw.circle(surf, st["head"], (x, y - 13), 5)
            sx = x + 15
            pygame.draw.line(surf, (110, 80, 56), (sx, y - 20), (sx, y + 14), 3)
            pygame.draw.circle(surf, (150, 220, 255), (sx, y - 24), 5)
            glow(surf, (sx, y - 24), 22, (150, 220, 255), 100)
        elif self.style == "sentinel":
            for k in (-1, 1):
                pygame.draw.polygon(surf, (255, 255, 250), [(x + k * 8, y - 8), (x + k * 26, y - 22), (x + k * 22, y - 2), (x + k * 12, y + 6)])
                pygame.draw.polygon(surf, (255, 214, 120), [(x + k * 8, y - 8), (x + k * 26, y - 22), (x + k * 22, y - 2), (x + k * 12, y + 6)], 1)
            pygame.draw.rect(surf, st["body"], (x - 10, y - 10, 20, 26), border_radius=4)
            pygame.draw.rect(surf, (255, 214, 100), (x - 10, y - 10, 20, 26), 2, border_radius=4)
            pygame.draw.circle(surf, st["head"], (x, y - 16), 8)
            pygame.draw.ellipse(surf, (255, 226, 130), (x - 9, y - 30, 18, 7), 2)
            eye = from_angle(self.facing, 3)
            pygame.draw.circle(surf, (60, 120, 220), (int(x + eye.x), int(y - 16 + eye.y * .5)), 2)
        else:
            pygame.draw.rect(surf, st["body"], (x - 11, y - 10, 22, 24))
            pygame.draw.rect(surf, mix(st["body"], BLACK, .4), (x - 11, y - 10, 22, 24), 2)
            pygame.draw.rect(surf, st["head"], (x - 9, y - 22, 18, 13))
            pygame.draw.rect(surf, (200, 70, 50), (x - 3, y - 28, 6, 7))
            eye = from_angle(self.facing, 5)
            pygame.draw.circle(surf, GOLD, (int(x + eye.x), int(y - 15 + eye.y * .5)), 3)
            sx = x - 16 if math.cos(self.facing) > 0 else x + 16
            pygame.draw.line(surf, (190, 196, 210), (sx, y - 16), (sx, y + 10), 3)
            pygame.draw.polygon(surf, (210, 216, 230), [(sx - 3, y - 16), (sx + 3, y - 16), (sx, y - 26)])


class QuestInterior(Arena):
    allow_escape = True

    def __init__(self, rid, index):
        super().__init__(R(60, 80, 840, 480))
        self.rid = rid
        self.index = index
        self.key = f"interior{rid}_{index}"
        self.state = game.realm_states[rid]
        self.line = self.state.lines[index]
        self.title = self.line.area
        self.accent = REALM_COLORS[rid]
        self.room_done = False
        self.ambush_started = False
        self.ambush_wave = 0
        self.ambush_timer = 0.0
        self.guards = []
        self.alert = 0.0
        self.alarm = False
        self.detected = False
        self.cone_surface = None
        self.build_room()

    # ---------------- rooms ----------------
    def build_room(self):
        self.enemies = []
        self.hazards = []
        self.guards = []
        self.alert = 0.0
        self.alarm = False
        self.detected = False
        self.room_done = False
        self.ambush_started = False
        self.ambush_wave = 0
        task = self.line.task
        self.kind = task[0] if task else "interact"
        seed = self.rid * 31 + self.index * 7 + self.line.step
        if self.kind == "stealth":
            layout = STEALTH_LAYOUTS[seed % len(STEALTH_LAYOUTS)]
            self.walls = [R(w) for w in layout["walls"]]
            speed = 55 + 10 * self.index + 8 * PROGRESSION.index(self.rid)
            self.guards = [Guard(pts, speed) for pts in layout["patrols"]]
        else:
            self.walls = [R(w) for w in INTERIOR_LAYOUTS[seed % len(INTERIOR_LAYOUTS)]]
        self.objective_pos = self.find_free(V(800, 320), 26)
        self.entry = V(110, 320)
        self.exit_pos = V(880, 320)
        scale = REALM_DIFFICULTY[self.rid] * (1 + .08 * self.index)
        if self.kind == "interact" and self.line.step >= 1:
            rng = random.Random(seed)
            for _ in range(1 + self.index):
                p = V(rng.randint(380, 700), rng.randint(130, 500))
                self.add_enemy(Enemy(p, rng.choice(REALM_ENEMY_TYPES[self.rid]), scale, self.accent, aggro=260))
        self.build_interactables()

    def build_interactables(self):
        self.interactables = [
            Interactable(V(84, 320), "Leave the building (progress is kept)", lambda: game.leave_interior(), 50,
                         draw_fn=lambda s, p, it: self.draw_door(s, p, GREEN, "EXIT")),
        ]
        if self.kind != "fight":
            self.interactables.append(Interactable(self.objective_pos, lambda: self.line.task_label if self.line.task else "",
                                                   self.use_objective, 70, visible=lambda: not self.room_done,
                                                   draw_fn=lambda s, p, it: self.draw_prop(s, p)))
        self.interactables.append(Interactable(self.exit_pos, lambda: "Next room" if not self.line.complete else "Leave - quest complete",
                                               self.next_room, 56, visible=lambda: self.room_done,
                                               draw_fn=lambda s, p, it: self.draw_door(s, p, GOLD, "NEXT" if not self.line.complete else "DONE")))

    def spawn(self):
        return V(self.entry)

    def use_objective(self):
        if self.room_done:
            return
        if self.alarm and any(e.alive for e in self.enemies):
            game.float_text(game.player.pos, "Deal with the guards first!", RED)
            return
        task = self.line.task
        if task is None:
            return
        if self.kind == "stealth" and not self.detected:
            bonus = int((40 + 30 * PROGRESSION.index(self.rid)) * GOLD_RATE)
            game.player.gold += bonus
            game.banner("GHOST", f"Undetected!  +{bonus} gold", GREEN)
        self.complete_room(task)

    def complete_room(self, task):
        self.room_done = True
        game.float_text(self.objective_pos, f"DONE: {task[1]}", GREEN, 1.6)
        game.player.gain_xp(25 + 15 * self.index + 10 * PROGRESSION.index(self.rid))
        finished = self.line.advance()
        nxt = self.line.task
        if finished:
            if self.index == 2:
                game.banner("QUEST COMPLETE", f"{self.line.title} - {REALM_INFO[self.rid]['lair'].title()} is open!", GOLD)
            else:
                game.banner("QUEST COMPLETE", self.line.title, GOLD)
            game.player.gold += int((60 + 40 * self.index) * GOLD_RATE)
            game.autosave()
        game.dialog([(self.line.area, task[2])] + ([("NEXT", nxt[1])] if nxt else []))

    def next_room(self):
        if not self.room_done:
            return
        if self.line.complete:
            game.leave_interior()
            return
        self.build_room()
        game.player.pos = V(self.entry)
        game.clear_projectiles()
        game.fade = 1.0

    # ---------------- update ----------------
    def update(self, dt):
        super().update(dt)
        p = game.player
        if self.kind == "fight" and not self.room_done:
            if not self.ambush_started and p.pos.x > 200:
                self.ambush_started = True
                self.ambush_timer = .6
                game.banner("AMBUSH!", self.line.task_label, RED)
            if self.ambush_started:
                if not any(e.alive for e in self.enemies):
                    self.ambush_timer -= dt
                    waves = 2 + self.index
                    if self.ambush_timer <= 0:
                        if self.ambush_wave < waves:
                            self.spawn_wave()
                            self.ambush_wave += 1
                            self.ambush_timer = 1.0
                        else:
                            self.complete_room(self.line.task)
        if self.guards and not self.alarm:
            seen = 0.0
            for g in self.guards:
                g.update(dt)
                seen = max(seen, g.sees(self, p.pos))
            if seen > 0:
                self.alert = min(100, self.alert + 140 * seen * dt)
                self.detected = self.detected or self.alert > 30
            else:
                self.alert = max(0, self.alert - 25 * dt)
            if self.alert >= 100:
                self.raise_alarm()

    def raise_alarm(self):
        self.alarm = True
        self.detected = True
        game.banner("ALARM!", "The guards have spotted you - fight!", RED)
        scale = REALM_DIFFICULTY[self.rid] * (1 + .08 * self.index)
        for g in self.guards:
            self.add_enemy(Enemy(g.pos, "guard", scale, self.accent, aggro=900))
        for _ in range(2):
            self.add_enemy(Enemy(V(860, random.randint(130, 500)), "guard", scale, self.accent, aggro=900))
        self.guards = []

    def spawn_wave(self):
        scale = REALM_DIFFICULTY[self.rid] * (1 + .1 * self.index)
        count = 5 + self.index + self.line.step // 2 + PROGRESSION.index(self.rid)
        types = REALM_ENEMY_TYPES[self.rid]
        for i in range(count):
            a = i * math.tau / count
            pos = V(560, 320) + from_angle(a, random.uniform(110, 200))
            pos.x = clamp(pos.x, 300, 860)
            pos.y = clamp(pos.y, 110, 530)
            kind = "drone" if (self.rid == VOID_ID and i % 2 == 0) else types[i % len(types)]
            e = self.add_enemy(Enemy(pos, kind, scale, self.accent, aggro=900))
            if i == 0 and (self.index >= 1 or self.ambush_wave >= 1):
                make_elite(e)
            burst(e.pos, self.accent, 12, (40, 120), .5, 3)

    def objective(self):
        if self.room_done:
            return ("Go through the door" if not self.line.complete else "Leave the building"), self.exit_pos
        if self.kind == "fight":
            return f"{self.line.task_label}", None
        if self.kind == "stealth":
            return f"{self.line.task_label} - stay out of sight", self.objective_pos
        return self.line.task_label, self.objective_pos

    # ---------------- draw ----------------
    def draw_ground(self, surf, cam):
        base = mix(REALM_PALETTE[self.rid][0], (40, 40, 48), .55)
        self.draw_floor(surf, base, mix(base, self.accent, .2))
        self.draw_walls(surf, mix(base, BLACK, .4), self.accent)
        for i in range(4):
            x = 150 + i * 220
            pygame.draw.rect(surf, mix(base, BLACK, .25), (x, 84, 60, 10))
        if self.guards:
            if self.cone_surface is None:
                self.cone_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            self.cone_surface.fill((0, 0, 0, 0))
            for g in self.guards:
                g.draw_cone(self.cone_surface, self.alert > 50, self)
            surf.blit(self.cone_surface, (0, 0))

    def draw_objects(self, surf, cam):
        super().draw_objects(surf, cam)
        for g in self.guards:
            g.draw(surf)

    def draw_top(self, surf, cam):
        draw_text(surf, f"{self.line.title}  -  ROOM {min(self.line.step + 1, len(self.line.tasks))} / {len(self.line.tasks)}", (480, 122), self.accent, 17, center=True)
        if self.guards or (self.kind == "stealth" and not self.room_done):
            panel(surf, R(330, 92, 300, 24), RED if self.alert > 60 else EDGE)
            pygame.draw.rect(surf, RED if self.alert > 60 else GOLD, (334, 96, int(292 * self.alert / 100), 16))
            draw_text(surf, "ALERT" if not self.alarm else "ALARM RAISED", (480, 96), WHITE, 16, center=True)

    def draw_prop(self, surf, p):
        x, y = ipos(p)
        label = self.line.task_label.lower()
        glow(surf, (x, y), 46 + math.sin(self.time * 4) * 4, GOLD, 70)
        if any(w in label for w in ("crate", "cargo", "ledger", "codex", "card", "core", "relic", "key", "fragment", "book")):
            pygame.draw.rect(surf, (110, 80, 50), (x - 20, y - 14, 40, 28))
            pygame.draw.rect(surf, GOLD, (x - 20, y - 14, 40, 28), 2)
            pygame.draw.line(surf, GOLD, (x - 20, y), (x + 20, y), 2)
        elif any(w in label for w in ("seal", "wardstone", "pylon", "relay", "lock", "tether", "gate", "stair")):
            pygame.draw.polygon(surf, self.accent, [(x, y - 26), (x + 16, y), (x, y + 26), (x - 16, y)])
            pygame.draw.polygon(surf, WHITE, [(x, y - 26), (x + 16, y), (x, y + 26), (x - 16, y)], 2)
        elif any(w in label for w in ("console", "signal", "upload", "disruptor", "choir", "hymn")):
            pygame.draw.rect(surf, (40, 45, 60), (x - 22, y - 18, 44, 34))
            pygame.draw.rect(surf, self.accent, (x - 18, y - 14, 36, 18))
            pygame.draw.rect(surf, WHITE, (x - 22, y - 18, 44, 34), 2)
        else:
            pygame.draw.circle(surf, self.accent, (x, y), 18, 3)
            pygame.draw.circle(surf, WHITE, (x, y), 6)

    def draw_door(self, surf, p, color, label):
        x, y = ipos(p)
        pygame.draw.rect(surf, (12, 12, 16), (x - 16, y - 40, 32, 80))
        pygame.draw.rect(surf, color, (x - 16, y - 40, 32, 80), 3)
        draw_text(surf, label, (x, y - 58), color, 16, center=True)




# Every investigation objective gets a concrete, semantically correct target.
SEARCH_TARGET_KINDS = {
    # EMBER
    (EMBER_ID, 0, 0): "wagon",
    (EMBER_ID, 0, 1): "drawer",
    (EMBER_ID, 0, 3): "cargo",
    (EMBER_ID, 1, 0): "hidden entrance",
    (EMBER_ID, 1, 1): "drawer",          # smelter ledger
    (EMBER_ID, 1, 3): "desk",            # Dragonforged key
    (EMBER_ID, 1, 4): "gate",
    # FROZEN
    (FROZEN_ID, 0, 0): "archive door",
    (FROZEN_ID, 0, 1): "study door",
    (FROZEN_ID, 0, 3): "bookcase",       # Frost Codex
    (FROZEN_ID, 1, 0): "relay",
    (FROZEN_ID, 1, 1): "crystal",
    (FROZEN_ID, 1, 3): "relay",
    (FROZEN_ID, 1, 4): "passage",
    # STARFALL
    (STARFALL_ID, 0, 0): "hymn fragment",
    (STARFALL_ID, 0, 1): "hymn fragment",
    (STARFALL_ID, 0, 3): "choir",
    (STARFALL_ID, 1, 0): "reliquary",
    (STARFALL_ID, 1, 1): "relic",       # Sun Relic
    (STARFALL_ID, 1, 3): "relic",
    (STARFALL_ID, 1, 4): "stair",
    # VOID
    (VOID_ID, 0, 0): "console",
    (VOID_ID, 0, 1): "memory core",
    (VOID_ID, 0, 3): "console",
    (VOID_ID, 1, 0): "access card",
    (VOID_ID, 1, 1): "drawer",           # reactor access card
    (VOID_ID, 1, 4): "disruptor",
    (VOID_ID, 2, 0): "tether",
    (VOID_ID, 2, 1): "pylon",
    (VOID_ID, 2, 3): "pylon",
    (VOID_ID, 2, 4): "gate",
}

# Searchable kinds that can be placed in the investigation rooms.
SEARCH_KIND_LABELS = {
    "wagon": ["Inspect supply wagon", "Search shattered wagon"],
    "drawer": ["Search drawer", "Open desk drawer", "Inspect lower drawer"],
    "cargo": ["Search cargo", "Inspect sealed cargo"],
    "hidden entrance": ["Inspect hidden entrance", "Search for the back entrance"],
    "desk": ["Search desk", "Inspect writing desk"],
    "gate": ["Inspect gate", "Check sealed gate"],
    "archive door": ["Inspect archive door", "Check sealed archive door"],
    "study door": ["Inspect study entrance", "Check mage's study door"],
    "bookcase": ["Search bookcase", "Check the books", "Inspect bookcase"],
    "relay": ["Inspect Aurora Relay", "Check the relay"],
    "crystal": ["Recover relay crystal", "Search beneath the ice"],
    "passage": ["Inspect whiteout passage", "Check the passage"],
    "hymn fragment": ["Search for hymn fragment", "Recover fallen fragment"],
    "choir": ["Restore fallen choir", "Inspect choir dais"],
    "reliquary": ["Enter reliquary", "Inspect reliquary"],
    "relic": ["Search for Sun Relic", "Take the Sun Relic"],
    "stair": ["Unlock Seraph's stair", "Inspect celestial stair"],
    "console": ["Inspect communications console", "Use station console"],
    "memory core": ["Recover memory core", "Search for black-box core"],
    "access card": ["Find access card", "Search engineer's station"],
    "disruptor": ["Find signal disruptor", "Search equipment crate"],
    "tether": ["Stabilize descent tether", "Inspect descent tether"],
    "pylon": ["Shut down anomaly pylon", "Inspect anomaly pylon"],
    # ordinary containers (decoys)
    "shelf": ["Inspect shelf", "Search dusty shelf", "Check the shelf"],
    "cabinet": ["Open cabinet", "Search cabinet", "Check cabinet"],
    "trash can": ["Inspect trash can", "Search discarded papers", "Check waste bin"],
    "crate": ["Search crate", "Inspect cargo crate", "Check sealed crate"],
    "locker": ["Open locker", "Search locker", "Inspect storage locker"],
    "barrel": ["Search barrel", "Check the barrel", "Inspect barrel"],
    "chest": ["Open chest", "Search old chest", "Check the chest"],
    "cart": ["Search handcart", "Check the cart"],
    "toolrack": ["Search tool rack", "Check the tools"],
    "anvil": ["Inspect anvil", "Check beneath the anvil"],
    "urn": ["Search urn", "Check the urn"],
    "altar": ["Inspect altar", "Search altar cloth"],
    "terminal": ["Check terminal", "Search the terminal"],
    "icechest": ["Chip open ice chest", "Search frozen chest"],
}

DECOY_FLAVOUR = {
    "bookcase": ["Just old books - a few have pages torn out.", "Dusty volumes. Nothing you need.",
                 "A hollow book... with nothing in it."],
    "shelf": ["A few jars and a handful of old books.", "Nothing but dust and cobwebs."],
}
GENERIC_DECOYS = [
    "Old receipts. Nothing useful.", "A broken seal and a pile of dust.",
    "Empty. Someone searched this already.", "A note with half the writing burned away.",
    "Old supplies. Not what you need.", "Nothing but ash and loose scraps.",
]


class QuestSearchable(Interactable):
    """A searchable shelf, drawer, cabinet, desk, crate, or trash can."""

    def __init__(self, scene, pos, kind, label, index, floor=0):
        self.scene = scene
        self.search_kind = kind
        self.searched = False
        self.index = index
        self.floor = floor
        self._sprites = {}
        super().__init__(
            pos,
            label,
            lambda s=self: s.scene.search_container(s),
            58,
            draw_fn=lambda surf, p, it, s=self: s.scene.draw_searchable(surf, p, s),
        )


# ============================================================
# QUEST ROOM MODES  (collect / defend / puzzle / hunt / gauntlet / survive / escort)
# ============================================================
MODE_KINDS = ("collect", "defend", "puzzle", "hunt", "gauntlet", "survive", "escort")
PUZZLE_COLORS = [("Red", (224, 72, 72)), ("Blue", (84, 134, 240)), ("Gold", (238, 198, 72)),
                 ("Green", (84, 204, 116)), ("Violet", (176, 104, 236))]


class QuestModes:
    """Mixin for ExpandedQuestInterior: every quest kind other than search/stealth/fight lives here."""

    def mode_name(self):
        return self.kind if self.kind in MODE_KINDS else None

    def mode_diff(self):
        return REALM_DIFFICULTY[self.rid] * (1 + .08 * self.index)

    def mode_prog(self):
        return PROGRESSION.index(self.rid)

    def mode_enemy(self, pos, kind=None, aggro=900, elite=False, mult=1.0):
        kind = kind or random.choice(REALM_ENEMY_TYPES[self.rid])
        e = self.add_enemy(Enemy(pos, kind, self.mode_diff() * mult, self.accent, aggro))
        if elite:
            make_elite(e)
        return e

    def far_point(self, min_dist=260, rng=None):
        rng = rng or random
        cands = [p for p in self._free if dist(p, game.player.pos) >= min_dist and dist(p, self.entry) >= 160]
        return V(rng.choice(cands)) if cands else V(self.play.center)

    def mode_wave(self, count, aggro=900, home=None, elite_chance=0.0):
        for i in range(count):
            e = self.mode_enemy(self.far_point(300), aggro=aggro, elite=random.random() < elite_chance)
            if home is not None:
                e.home = V(home)
            burst(e.pos, self.accent, 10, (40, 120), .5, 3)

    # ---------------- setup ----------------
    def mode_init(self):
        self.m = {}
        mode = self.mode_name()
        if mode is None or self.line.task is None:
            return
        rng = random.Random(self.seed * 13 + 5)
        getattr(self, "init_" + mode)(rng)

    def init_collect(self, rng):
        slots = self.pick_slots(rng, 7, [(self.entry, 240), (self.exit_pos, 120)], self._free)[:5]
        self.m = {"items": [{"pos": V(p), "got": False} for p in slots], "got": 0, "extra": False}
        for i in range(3 + self.index + self.mode_prog()):
            self.mode_enemy(self.far_point(300, rng), aggro=300, elite=(i == 0 and self.index >= 1))

    def init_defend(self, rng):
        pos = self.find_free(V(540, 340), 40)
        hp = 420 + 110 * self.mode_prog()
        self.m = {"pos": pos, "hp": hp, "max": hp, "prog": 0.0, "dur": 40 + 4 * self.index + 2 * self.mode_prog(),
                  "wave": 0, "wave_t": 3.5, "regen": 0.0}

    def init_survive(self, rng):
        self.m = {"t": 0.0, "dur": 36 + 4 * self.index + 3 * self.mode_prog(), "rain": 1.2, "wave": 6.0, "sweep": 7.0}

    def init_hunt(self, rng):
        types = [k for k in REALM_ENEMY_TYPES[self.rid] if k not in ("crawler",)]
        kind = "drone" if self.rid == VOID_ID else rng.choice(types)
        pos = self.far_point(380, rng)
        t = self.mode_enemy(pos, kind, aggro=460, mult=1.25)
        make_elite(t)
        t.max_hp = int(t.max_hp * 1.9)
        t.hp = t.max_hp
        t.name_tag = self.line.task_label.replace("Slay the ", "").replace("Destroy the ", "")
        t.radius = max(t.radius, 18)
        self.m = {"target": t}
        for i in range(2 + self.index + self.mode_prog()):
            self.mode_enemy(self.far_point(260, rng), aggro=300)

    def init_gauntlet(self, rng):
        ox = self.objective_pos.x
        xs = list(range(250, int(ox) - 70, 112))[:7]
        period = max(2.0, 2.9 - .12 * self.mode_prog())
        self.m = {"cols": [{"x": x, "t": (k % 4) * period / 4 + .8} for k, x in enumerate(xs)], "period": period, "row_t": 5.0}
        for i in range(2 + self.mode_prog()):
            p = self.far_point(380, rng)
            if p.x > 520:
                self.mode_enemy(p, aggro=260)

    def init_puzzle(self, rng):
        prog = self.mode_prog()
        n = 5 if prog >= 2 else 4
        slots = self.pick_slots(rng, n + 2, [(self.entry, 170), (self.exit_pos, 120)], self._free)[:n + 1]
        tablet = V(slots[-1]) if len(slots) > n else self.find_free(V(250, 250), 30)
        slots = slots[:n]
        length = 3 + (1 if prog >= 2 else 0) + (1 if self.line.step >= 3 else 0)
        seq = [rng.randrange(n) for _ in range(length)]
        for i in range(1, length):          # no immediate repeats
            while seq[i] == seq[i - 1]:
                seq[i] = rng.randrange(n)
        self.m = {"plinths": [{"pos": V(p), "ci": i, "lit": False} for i, p in enumerate(slots)], "seq": seq, "prog": 0,
                  "tablet": tablet, "flash": 0.0, "wrong": 0.0}
        self.interactables.append(Interactable(tablet, "Study the tablet", self.puzzle_study, 60,
                                               visible=lambda: not self.room_done,
                                               draw_fn=lambda s, p, it: self.draw_tablet(s, p)))
        for i, pl in enumerate(self.m["plinths"]):
            name = PUZZLE_COLORS[pl["ci"]][0]
            self.interactables.append(Interactable(pl["pos"], f"Touch the {name} plinth", (lambda i=i: self.puzzle_touch(i)), 52,
                                                   visible=lambda: not self.room_done,
                                                   draw_fn=(lambda s, p, it, i=i: self.draw_plinth(s, p, i))))
        for i in range(1 + self.index):
            self.mode_enemy(self.far_point(280, rng), aggro=260)

    def init_escort(self, rng):
        self.m = {"npc": V(self.entry) + V(50, 0), "hp": 130.0, "max": 130.0, "cps": [320, 540, 740], "hit": [False, False, False],
                  "flash": 0.0}

    # ---------------- puzzle actions ----------------
    def puzzle_study(self):
        names = [PUZZLE_COLORS[i][0] for i in self.m["seq"]]
        self.m["flash"] = 0.01
        game.dialog([("TABLET", "The order is carved here:  " + "  >  ".join(names) + "."),
                     ("TABLET", "Touch the plinths in that order. A wrong touch resets the sequence and wakes the room.")])

    def puzzle_touch(self, i):
        m = self.m
        if self.room_done:
            return
        pl = m["plinths"][i]
        if m["seq"][m["prog"]] == pl["ci"]:
            pl["lit"] = True
            m["prog"] += 1
            burst(pl["pos"], PUZZLE_COLORS[pl["ci"]][1], 16, (40, 130), .5, 3)
            game.sound("pickup")
            game.float_text(pl["pos"], f"{m['prog']}/{len(m['seq'])}", GREEN, 1.0, 18)
            if m["prog"] >= len(m["seq"]):
                self.complete_room(self.line.task)
        else:
            m["prog"] = 0
            for p in m["plinths"]:
                p["lit"] = False
            m["wrong"] = .8
            game.banner("WRONG ORDER", "The plinths discharge and the room stirs.", RED, 1.6)
            self.hazards.append(Hazard(pl["pos"], 74, .5, .3, int(13 * REALM_DIFFICULTY[self.rid]), PUZZLE_COLORS[pl["ci"]][1], label="SHOCK"))
            self.mode_enemy(self.far_point(220), aggro=900)

    # ---------------- per-frame ----------------
    def mode_update(self, dt):
        mode = self.mode_name()
        if mode is None or self.room_done or not self.m:
            return
        getattr(self, "upd_" + mode)(dt)

    def upd_collect(self, dt):
        m = self.m
        p = game.player.pos
        for it in m["items"]:
            if not it["got"] and dist(it["pos"], p) < 34:
                it["got"] = True
                m["got"] += 1
                burst(it["pos"], GOLD, 18, (40, 130), .5, 3)
                game.sound("pickup")
                game.float_text(it["pos"], f"{m['got']}/{len(m['items'])}", GOLD, 1.0, 20)
                if m["got"] == 3 and not m["extra"]:
                    m["extra"] = True
                    game.banner("AMBUSH!", "The salvage drew company.", RED, 1.6)
                    self.mode_wave(3 + self.mode_prog(), elite_chance=.2 * min(1, self.index))
        if m["got"] >= len(m["items"]):
            self.complete_room(self.line.task)

    def upd_defend(self, dt):
        m = self.m
        m["prog"] += dt / m["dur"]
        m["wave_t"] -= dt
        if m["wave_t"] <= 0 and m["prog"] < .92:
            m["wave"] += 1
            m["wave_t"] = 8.0
            n = 3 + self.index + self.mode_prog() + m["wave"] // 3
            self.mode_wave(n, aggro=140, home=m["pos"], elite_chance=.15 * min(1, self.index) if m["wave"] % 3 == 0 else 0)
        near = False
        for e in self.enemies:
            if not e.alive:
                continue
            d = dist(e.pos, m["pos"])
            if d < 220:
                near = True
            if d < e.radius + 38:
                m["hp"] -= e.damage * .4 * dt
            if dist(e.pos, game.player.pos) > e.aggro and e.freeze <= 0:
                direction = m["pos"] - e.pos
                if direction.length() > 4:
                    e.pos = self.move(e.pos, direction.normalize() * e.speed * .85 * e.speed_factor() * dt, e.radius)
        if not near:
            m["hp"] = min(m["max"], m["hp"] + 6 * dt)
        if m["hp"] <= 0:
            game.banner("IT FELL", "The objective was destroyed. Hold out again!", RED, 2.0)
            m["hp"] = m["max"]
            m["prog"] = 0
            m["wave"] = 0
            m["wave_t"] = 4.0
            self.enemies = []
            game.clear_projectiles()
        elif m["prog"] >= 1:
            self.enemies = []
            self.hazards = []
            game.clear_projectiles()
            self.complete_room(self.line.task)

    def upd_survive(self, dt):
        m = self.m
        m["t"] += dt
        p = game.player.pos
        diff = REALM_DIFFICULTY[self.rid]
        m["rain"] -= dt
        if m["rain"] <= 0:
            m["rain"] = max(.55, 1.05 - .07 * self.mode_prog())
            for _ in range(2 + self.mode_prog() // 2):
                tp = p + from_angle(random.random() * math.tau, random.uniform(0, 150))
                tp.x = clamp(tp.x, self.play.left + 30, self.play.right - 30)
                tp.y = clamp(tp.y, ROOM_TOP + 20, self.play.bottom - 30)
                self.hazards.append(Hazard(tp, 48, .85, .3, int(12 * diff), self.accent))
        m["sweep"] -= dt
        if m["sweep"] <= 0:
            m["sweep"] = 8.0
            if random.random() < .5:
                y = clamp(p.y + random.uniform(-60, 60), ROOM_TOP + 30, self.play.bottom - 30)
                self.hazards.append(Hazard(V(self.play.left, y), 0, 1.1, .45, int(17 * diff), self.accent, shape="line",
                                           end=V(self.play.right, y), width=46, label="SWEEP"))
            else:
                x = clamp(p.x + random.uniform(-60, 60), self.play.left + 30, self.play.right - 30)
                self.hazards.append(Hazard(V(x, ROOM_TOP), 0, 1.1, .45, int(17 * diff), self.accent, shape="line",
                                           end=V(x, self.play.bottom), width=46, label="SWEEP"))
        m["wave"] -= dt
        if m["wave"] <= 0:
            m["wave"] = 11.0
            self.mode_wave(2 + self.mode_prog())
        if m["t"] >= m["dur"]:
            self.enemies = []
            self.hazards = []
            game.clear_projectiles()
            self.complete_room(self.line.task)

    def upd_hunt(self, dt):
        t = self.m["target"]
        if not t.alive:
            for e in self.enemies:
                e.alive = False
            game.clear_projectiles()
            self.complete_room(self.line.task)

    def upd_gauntlet(self, dt):
        m = self.m
        diff = REALM_DIFFICULTY[self.rid]
        warn = max(.75, 1.0 - .05 * self.mode_prog())
        for c in m["cols"]:
            c["t"] -= dt
            if c["t"] <= 0:
                c["t"] = m["period"]
                self.hazards.append(Hazard(V(c["x"], ROOM_TOP), 0, warn, .5, int(15 * diff), self.accent, shape="line",
                                           end=V(c["x"], self.play.bottom), width=54, label="JET"))
        if self.mode_prog() >= 2:
            m["row_t"] -= dt
            if m["row_t"] <= 0:
                m["row_t"] = 6.0
                y = random.randint(ROOM_TOP + 60, self.play.bottom - 60)
                self.hazards.append(Hazard(V(self.play.left, y), 0, 1.0, .5, int(15 * diff), self.accent, shape="line",
                                           end=V(self.play.right, y), width=48, label="SWEEP"))

    def upd_puzzle(self, dt):
        m = self.m
        m["wrong"] = max(0, m["wrong"] - dt)
        if m["flash"] > 0:
            m["flash"] += dt

    def upd_escort(self, dt):
        m = self.m
        p = game.player.pos
        npc = m["npc"]
        d = dist(npc, p)
        if d > 85:
            m["npc"] = self.move(npc, (p - npc).normalize() * min(135, 60 + d) * dt, 12)
            npc = m["npc"]
        for k, cp in enumerate(m["cps"]):
            if not m["hit"][k] and p.x > cp and dist(npc, p) < 190:
                m["hit"][k] = True
                game.banner("AMBUSH!", "Protect the bearer!", RED, 1.5)
                for i in range(2 + self.index + self.mode_prog() // 2):
                    pos = V(clamp(cp + random.randint(110, 230), 260, 860), random.randint(ROOM_TOP + 40, self.play.bottom - 40))
                    e = self.mode_enemy(pos, aggro=900, elite=(i == 0 and k == 2 and self.index >= 1))
                    burst(e.pos, self.accent, 10, (40, 120), .5, 3)
        for e in self.enemies:
            if not e.alive:
                continue
            dn = dist(e.pos, npc)
            if dn < 260 and dn < dist(e.pos, p) + 40 and e.freeze <= 0:
                e.pos = self.move(e.pos, (npc - e.pos).normalize() * e.speed * .7 * e.speed_factor() * dt, e.radius)
            if dn < e.radius + 16:
                m["hp"] -= e.damage * .5 * dt
                m["flash"] = .15
        for pr in game.projectiles:
            if pr.owner != "player" and dist(pr.pos, npc) < 14:
                m["hp"] -= pr.damage * .5
                pr.alive = False
        m["flash"] = max(0, m["flash"] - dt)
        if m["hp"] <= 0:
            game.banner("THE BEARER FELL", "Try the escort again.", RED, 2.2)
            self.build_room()
            game.player.pos = V(self.entry)
            game.clear_projectiles()
            return
        if all(m["hit"]) and not any(e.alive for e in self.enemies) and dist(npc, self.exit_pos) < 110 and dist(p, self.exit_pos) < 150:
            self.complete_room(self.line.task)

    # ---------------- objective / HUD ----------------
    def mode_objective(self):
        mode = self.mode_name()
        m = self.m
        lab = self.line.task_label
        if mode == "collect":
            left = [it for it in m["items"] if not it["got"]]
            tgt = min(left, key=lambda it: dist(it["pos"], game.player.pos))["pos"] if left else None
            return f"{lab} ({m['got']}/{len(m['items'])})", tgt
        if mode == "defend":
            return f"{lab} ({int(100 * min(1, m['prog']))}%)", m["pos"]
        if mode == "survive":
            return f"{lab} ({max(0, int(m['dur'] - m['t']))}s)", None
        if mode == "hunt":
            t = m["target"]
            return lab, (V(t.pos) if t.alive else None)
        if mode == "gauntlet":
            return f"{lab} - watch the warnings", self.objective_pos
        if mode == "puzzle":
            if m["prog"] == 0:
                return f"{lab} - study the tablet first", m["tablet"]
            return f"{lab} ({m['prog']}/{len(m['seq'])})", None
        if mode == "escort":
            if not all(m["hit"]):
                return f"{lab} - keep the bearer close", None
            return f"{lab} - lead them to the door", self.exit_pos
        return lab, None

    def mode_hud(self):
        mode = self.mode_name()
        m = self.m
        if mode is None or self.room_done or not m:
            return None
        if mode == "collect":
            return ("SALVAGE", m["got"] / len(m["items"]), GOLD)
        if mode == "defend":
            return (f"HOLD  -  objective {int(100 * max(0, m['hp']) / m['max'])}%", min(1, m["prog"]), GREEN if m["hp"] > m["max"] * .35 else RED)
        if mode == "survive":
            return ("SURVIVE", min(1, m["t"] / m["dur"]), ORANGE)
        if mode == "hunt":
            t = m["target"]
            return ((t.name_tag or "TARGET") + (" - " + ELITE_AFFIXES[t.affix][0] if t.affix else ""), max(0, t.hp) / max(1, t.max_hp), RED)
        if mode == "puzzle":
            return ("SEQUENCE", m["prog"] / len(m["seq"]), GOLD)
        if mode == "escort":
            return ("BEARER", max(0, m["hp"]) / m["max"], GREEN if m["hp"] > m["max"] * .4 else RED)
        return None

    # ---------------- drawing ----------------
    def mode_draw(self, surf):
        mode = self.mode_name()
        m = self.m
        if mode is None or not m or self.line.task is None:
            return
        t = self.time
        if mode == "collect":
            for it in m["items"]:
                if it["got"]:
                    continue
                x, y = ipos(it["pos"])
                y += int(math.sin(t * 3 + x) * 4)
                glow(surf, (x, y), 30, GOLD, 90)
                pygame.draw.polygon(surf, mix(self.accent, WHITE, .35), [(x, y - 13), (x + 8, y), (x, y + 13), (x - 8, y)])
                pygame.draw.polygon(surf, WHITE, [(x, y - 13), (x + 8, y), (x, y + 13), (x - 8, y)], 2)
        elif mode == "defend":
            x, y = ipos(m["pos"])
            frac = max(0, m["hp"]) / m["max"]
            glow(surf, (x, y), 52 + int(math.sin(t * 4) * 4), self.accent, 90)
            pygame.draw.rect(surf, (50, 50, 60), (x - 18, y - 6, 36, 22))
            pygame.draw.polygon(surf, mix(self.accent, WHITE, .3), [(x, y - 36), (x + 15, y - 8), (x, y + 6), (x - 15, y - 8)])
            pygame.draw.polygon(surf, WHITE, [(x, y - 36), (x + 15, y - 8), (x, y + 6), (x - 15, y - 8)], 2)
            pygame.draw.rect(surf, (20, 20, 24), (x - 26, y + 20, 52, 6))
            pygame.draw.rect(surf, GREEN if frac > .35 else RED, (x - 25, y + 21, int(50 * frac), 4))
            pygame.draw.arc(surf, GOLD, (x - 30, y - 40, 60, 60), math.pi / 2, math.pi / 2 + math.tau * min(1, m["prog"]), 3)
        elif mode == "escort":
            x, y = ipos(m["npc"])
            glow(surf, (x, y - 14), 40, GOLD, 85)
            pygame.draw.ellipse(surf, (0, 0, 0), (x - 10, y + 12, 20, 7))
            pygame.draw.polygon(surf, (150, 120, 90), [(x - 9, y - 6), (x + 9, y - 6), (x + 12, y + 14), (x - 12, y + 14)])
            pygame.draw.circle(surf, (225, 195, 160), (x, y - 12), 7)
            pygame.draw.line(surf, (110, 80, 50), (x + 12, y - 20), (x + 12, y + 8), 2)
            pygame.draw.circle(surf, GOLD, (x + 12, y - 22), 5)
            frac = max(0, m["hp"]) / m["max"]
            pygame.draw.rect(surf, (20, 20, 24), (x - 18, y - 30, 36, 5))
            pygame.draw.rect(surf, GREEN if frac > .4 else RED, (x - 17, y - 29, int(34 * frac), 3))
            if m["flash"] > 0:
                pygame.draw.circle(surf, WHITE, (x, y - 4), 16, 2)
            if all(m["hit"]):
                pass
        elif mode == "hunt":
            tg = m["target"]
            if tg.alive:
                x, y = ipos(tg.pos)
                pygame.draw.circle(surf, RED, (x, y), tg.radius + 16 + int(math.sin(t * 5) * 2), 1)

    def draw_tablet(self, surf, p):
        x, y = int(p.x), int(p.y)
        glow(surf, (x, y), 36, GOLD, 70)
        pygame.draw.rect(surf, (118, 112, 106), (x - 16, y - 24, 32, 44), border_radius=5)
        pygame.draw.rect(surf, (200, 190, 170), (x - 16, y - 24, 32, 44), 2, border_radius=5)
        for k in range(4):
            pygame.draw.line(surf, (70, 64, 58), (x - 9, y - 14 + k * 9), (x + 9, y - 14 + k * 9), 2)
        draw_text(surf, "TABLET", (x, y - 38), GOLD, 13, center=True)

    def draw_plinth(self, surf, p, i):
        m = self.m
        pl = m["plinths"][i]
        col = PUZZLE_COLORS[pl["ci"]][1]
        x, y = int(p.x), int(p.y)
        lit = pl["lit"]
        flashing = False
        if m["flash"] > 0:
            k = int(m["flash"] / .9)
            if k < len(m["seq"]) and m["seq"][k] == pl["ci"] and (m["flash"] % .9) < .6:
                flashing = True
        if lit or flashing:
            glow(surf, (x, y - 10), 42, col, 130)
        pygame.draw.polygon(surf, mix(col, BLACK, .55 if not (lit or flashing) else 0), [(x - 13, y + 14), (x + 13, y + 14), (x + 9, y - 22), (x - 9, y - 22)])
        pygame.draw.polygon(surf, mix(col, WHITE, .3), [(x - 13, y + 14), (x + 13, y + 14), (x + 9, y - 22), (x - 9, y - 22)], 2)
        pygame.draw.circle(surf, col if (lit or flashing) else mix(col, BLACK, .4), (x, y - 26), 6)


class ExpandedQuestInterior(QuestModes, QuestInterior):
    """
    Themed multi-room quest buildings.  Each of the 12 quest lines has its own
    look; rooms inside a building change layout every step.  Search tasks are
    investigations among decoys; heist tasks add an upstairs floor with
    patrolling guards whose vision cones are always drawn.
    """

    def __init__(self, rid, index):
        self.quest_floor = 0
        self.searchables = []
        self.search_total = 0
        self.search_done = 0
        self.search_target = None
        self.item_found = False
        self.return_required = False
        self.searched_keys = set()
        self.stair_pos = V(850, 190)
        self.amb = []
        self.lights = {}
        self._bg = {}
        self._vig = None
        self.theme = ROOM_THEMES[THEME_ORDER[0]]
        self.theme_idx = 0
        self.search_mode = False
        self.layout_index = 0
        self._free = []
        self.m = {}
        super().__init__(rid, index)

    # ---------------- classification ----------------
    def is_search_task(self):
        task = self.line.task
        return bool(task) and task[0] in ("search", "stealth")

    def is_heist(self):
        return bool(self.line.task and self.line.task[0] == "stealth")

    # ---------------- geometry helpers ----------------
    def compute_reach(self, start, cell=12, r=20):
        play = self.play
        seen = set()
        si, sj = int((start.x - play.left) // cell), int((start.y - play.top) // cell)
        stack = [(si, sj)]
        nx_cells, ny_cells = play.w // cell, play.h // cell
        while stack:
            i, j = stack.pop()
            if (i, j) in seen or not (0 <= i < nx_cells and 0 <= j < ny_cells):
                continue
            if self.blocked(V(play.left + i * cell, play.top + j * cell), r):
                continue
            seen.add((i, j))
            stack.extend(((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))
        return seen

    def clear_of_walls(self, p, m):
        if not self.play.inflate(-2 * m, -2 * m).collidepoint(p):
            return False
        for w in self.walls:
            if w.inflate(2 * m, 2 * m).collidepoint(p):
                return False
        return True

    def seg_clear(self, a, b, r=18):
        d = dist(a, b)
        n = int(d / 10) + 1
        for i in range(n + 1):
            t = i / n
            if self.blocked(V(a) + (V(b) - V(a)) * t, r):
                return False
        return True

    def arrival(self, floor):
        return V(self.entry) if (floor == 0 and not getattr(self, "_came_down", False)) else V(self.stair_pos) + V(-10, 62)

    def pick_slots(self, rng, n, avoid, cand):
        cands = [p for p in cand if all(dist(p, a) >= ar for a, ar in avoid)]
        for gap in (112, 98, 86, 74, 62):
            rng.shuffle(cands)
            out = []
            for p in cands:
                if all(dist(p, q) >= gap for q in out):
                    out.append(p)
                    if len(out) >= n:
                        break
            if len(out) >= min(n, 10):
                return out
        return out

    def make_patrols(self, rng, count, free30, avoid_pts):
        routes = []
        tries = 0
        while len(routes) < count and tries < 400 and free30:
            tries += 1
            start = rng.choice(free30)
            if any(dist(start, a) < 230 for a in avoid_pts) or any(dist(start, r[0]) < 140 for r in routes):
                continue
            route = [start]
            for _ in range(rng.randint(2, 3)):
                for _try in range(40):
                    q = rng.choice(free30)
                    if 130 < dist(q, route[-1]) < 360 and self.seg_clear(route[-1], q):
                        route.append(q)
                        break
            if len(route) >= 3 and not self.seg_clear(route[-1], route[0]):
                route = route[:2]
            if len(route) >= 2:
                routes.append(route)
        return routes

    # ---------------- build ----------------
    def build_room(self):
        self.enemies = []
        self.hazards = []
        self.guards = []
        self.alert = 0.0
        self.alarm = False
        self.detected = False
        self.room_done = False
        self.ambush_started = False
        self.ambush_wave = 0
        task = self.line.task
        self.kind = task[0] if task else "interact"
        key = (self.rid, self.index)
        self.theme = ROOM_THEMES.get(key) or ROOM_THEMES[THEME_ORDER[0]]
        self.theme_idx = THEME_ORDER.index(key) if key in THEME_ORDER else 0
        self.search_mode = bool(task) and self.is_search_task()
        self.quest_floor = 0
        self._came_down = False
        self.searched_keys = set()
        self.searchables = []
        self.search_total = 0
        self.search_done = 0
        self.search_target = None
        self.item_found = False
        self.return_required = False
        self._bg = {}
        self.lights = {}
        self.amb = []
        self.entry = V(110, 320)
        self.exit_pos = V(880, 320)
        self.seed = self.rid * 131 + self.index * 37 + self.line.step * 11
        self.objective_pos = V(800, 320)
        self.setup_floor(0)
        self.mode_init()
        # ambush enemies roam interact rooms (same as the original design)
        if self.kind == "interact" and self.line.step >= 1:
            rng = random.Random(self.seed)
            scale = REALM_DIFFICULTY[self.rid] * (1 + .08 * self.index)
            for _ in range(1 + self.index):
                p = V(rng.randint(380, 700), rng.randint(150, 500))
                self.add_enemy(Enemy(p, rng.choice(REALM_ENEMY_TYPES[self.rid]), scale, self.accent, aggro=260))

    def setup_floor(self, floor):
        self.quest_floor = floor
        th = self.theme
        rng = random.Random(self.seed * 7 + floor * 101 + 13)
        order = random.Random(self.theme_idx * 97 + 11).sample(range(len(ROOM_LAYOUTS)), len(ROOM_LAYOUTS))
        self.layout_index = order[(self.line.step + floor * 6) % len(order)]
        self.walls = [R(self.play.left, self.play.top, self.play.w, ROOM_TOP - self.play.top)]
        self.walls += [R(w) for w in ROOM_LAYOUTS[self.layout_index]]
        heist = self.is_heist()
        reach = self.compute_reach(self.entry)
        cell = 12

        def pts(margin):
            out = []
            for (i, j) in reach:
                p = V(self.play.left + i * cell, self.play.top + j * cell)
                if self.clear_of_walls(p, margin):
                    out.append(p)
            out.sort(key=lambda p: (p.x, p.y))
            return out

        free40 = pts(40)
        free30 = pts(30)
        self._free = free40
        arrive = self.arrival(floor) if heist else V(self.entry)
        avoid = [(self.entry, 120), (V(84, 320), 90), (self.exit_pos, 110), (self.stair_pos, 100), (arrive, 100)]

        # ---- props / containers ----
        self.searchables = []
        self.search_target = None
        its = [Interactable(V(84, 320), "Leave the building (progress is kept)", lambda: game.leave_interior(), 50,
                            draw_fn=lambda s, p, it: self.draw_door(s, p, GREEN, "EXIT"))]
        if heist:
            its.append(Interactable(self.stair_pos, lambda: "Go upstairs" if self.quest_floor == 0 else "Go downstairs",
                                    self.use_stairs, 62,
                                    visible=lambda: (not self.item_found) or self.quest_floor == 1,
                                    draw_fn=lambda s, p, it: self.draw_stairs(s, p)))
        if self.search_mode:
            slots = self.pick_slots(rng, 12, avoid, free40)
            target_kind = SEARCH_TARGET_KINDS.get((self.rid, self.index, self.line.step))
            target_floor = 1 if heist else 0
            target_i = -1
            if floor == target_floor and slots:
                far = [i for i, p in enumerate(slots) if dist(p, arrive) >= 300] or list(range(len(slots)))
                target_i = rng.choice(far)
            pool = list(th["containers"])
            rng.shuffle(pool)
            k = 0
            for i, pos in enumerate(slots):
                if i == target_i and target_kind:
                    kind = target_kind
                else:
                    kind = pool[k % len(pool)]
                    k += 1
                obj = QuestSearchable(self, pos, kind, self._search_label(kind, i), i + floor * 20, floor)
                obj.searched = (floor, i) in self.searched_keys
                if obj.searched:
                    obj.label = "Already searched"
                obj.slot = i
                if i == target_i:
                    self.search_target = obj
                self.searchables.append(obj)
                its.append(obj)
            if floor == target_floor and self.search_target is None and self.searchables:
                self.search_target = self.searchables[0]
            self.search_total = len(self.searchables)
            if self.search_target is not None and floor == target_floor:
                self.objective_pos = V(self.search_target.pos)
        elif self.kind in ("interact", "gauntlet"):
            far = [p for p in free40 if dist(p, self.entry) >= 330 and dist(p, self.exit_pos) >= 110
                   and dist(p, self.stair_pos) >= 100 and (self.kind != "gauntlet" or p.x > 680)] or free40 or [V(800, 320)]
            self.objective_pos = V(rng.choice(far))
            its.append(Interactable(self.objective_pos, lambda: self.line.task_label if self.line.task else "",
                                    self.use_objective, 70, visible=lambda: not self.room_done,
                                    draw_fn=lambda s, p, it: self.draw_prop(s, p)))

        # ---- doors ----
        if self.search_mode and (not heist or floor == 0):
            its.append(Interactable(
                self.exit_pos,
                lambda: ("Return to the quest route" if self.item_found else "Search the room"),
                self.complete_search_route, 60,
                visible=lambda: not self.room_done,
                draw_fn=lambda s, p, it: self.draw_door(s, p, GOLD if self.item_found else EDGE,
                                                        "RETURN" if self.item_found else "SEARCH")))
        its.append(Interactable(
            self.exit_pos,
            lambda: "Next room" if not self.line.complete else "Leave - quest complete",
            self.next_room, 56,
            visible=lambda: self.room_done,
            draw_fn=lambda s, p, it: self.draw_door(s, p, GOLD, "NEXT" if not self.line.complete else "DONE")))
        self.interactables = its

        # ---- guards (heist floors) ----
        self.guards = []
        if heist and not self.alarm:
            count = 2 if floor == 0 else 3
            routes = self.make_patrols(rng, count, free30, [self.entry, arrive])
            speed = 56 + 7 * self.index + 6 * PROGRESSION.index(self.rid) + (6 if floor else 0)
            self.guards = [Guard(r, speed, th["guard"]) for r in routes]
        self.alert = 0.0
        self._bg.pop(floor, None)
        self.cone_surface = None

    def _search_label(self, kind, i):
        labels = SEARCH_KIND_LABELS.get(kind) or ["Search it"]
        return labels[i % len(labels)]

    # ---------------- search flow ----------------
    def search_container(self, container):
        if self.room_done or container.searched:
            return
        if self.alarm and self.is_heist():
            game.float_text(game.player.pos, "The guards are on you!", RED)
            return
        container.searched = True
        container.label = "Already searched"
        self.searched_keys.add((container.floor, container.slot))
        self.search_done += 1
        if container is self.search_target:
            self.item_found = True
            game.float_text(container.pos, "FOUND!", GREEN, 1.5, 22)
            game.banner("ITEM FOUND", self.line.task_label.replace("Find ", "You found "), GREEN, 2.2)
            burst(container.pos, GOLD, 28, (50, 160), .7, 3)
            if self.is_heist():
                self.return_required = True
                game.dialog([
                    ("DISCOVERY", "You found it. Do not linger."),
                    ("TIP", "Get back to the stairs, go downstairs, and make it back to the exit."),
                ])
            return
        flavour = DECOY_FLAVOUR.get(container.search_kind) or GENERIC_DECOYS
        game.float_text(container.pos, random.choice(flavour), ASH, 1.3, 15)
        if self.is_heist() and self.search_done in (4, 8):
            self.alert = min(100, self.alert + 22)
            game.banner("PATROL NEARBY", "Keep moving before the guards notice you.", RED, 1.6)

    def use_stairs(self):
        if not self.is_heist():
            return
        new = 1 - self.quest_floor
        self._came_down = True
        self.setup_floor(new)
        game.player.pos = self.arrival(new)
        if new == 1:
            game.banner("UPSTAIRS", "Search the offices and storage rooms.", self.accent, 1.8)
        elif self.item_found:
            game.banner("BACK DOWN", "Now get out.", GREEN, 1.8)
        else:
            game.banner("DOWNSTAIRS", "You still need to find the objective upstairs.", GOLD, 1.8)
        game.clear_projectiles()
        game.fade = 1.0

    def complete_search_route(self):
        if self.room_done:
            return
        if self.is_heist() and self.quest_floor == 1:
            game.float_text(game.player.pos, "You need to go downstairs.", RED)
            return
        if not self.item_found:
            game.float_text(game.player.pos, "You haven't found the objective yet.", RED)
            return
        if self.alarm and any(e.alive for e in self.enemies):
            game.float_text(game.player.pos, "Deal with the guards first!", RED)
            return
        if self.is_heist() and not self.detected:
            bonus = int((40 + 30 * PROGRESSION.index(self.rid)) * GOLD_RATE)
            game.player.gold += bonus
            game.banner("GHOST", f"Undetected!  +{bonus} gold", GREEN)
        self.complete_room(self.line.task)

    def use_objective(self):
        if self.search_mode:
            self.complete_search_route()
            return
        return super().use_objective()

    def next_room(self):
        if not self.room_done:
            return
        if self.line.complete:
            game.leave_interior()
            return
        self.build_room()
        game.player.pos = V(self.entry)
        game.clear_projectiles()
        game.fade = 1.0

    # ---------------- update ----------------
    def update(self, dt):
        super().update(dt)
        self.mode_update(dt)
        if self.search_mode and self.is_heist() and self.guards and not self.alarm:
            if self.quest_floor == 1 and self.search_done >= 5:
                self.alert = min(100, self.alert + 2.0 * dt)
        self.update_ambient(dt)

    def update_ambient(self, dt):
        kind = self.theme["ambient"]
        pal = self.theme["pal"]
        play = self.play
        if len(self.amb) < 28 and random.random() < dt * 24:
            x = random.uniform(play.left + 6, play.right - 6)
            y = random.uniform(ROOM_TOP + 6, play.bottom - 6)
            if kind == "embers":
                self.amb.append([V(x, play.bottom - 4), V(random.uniform(-14, 14), random.uniform(-60, -30)), random.uniform(2, 4), random.choice([(255, 150, 60), (255, 200, 90), (230, 90, 40)]), 2])
            elif kind == "sparks":
                c = random.choice(self.lights.get(self.quest_floor) or [(x, ROOM_TOP, 0, pal["glow"])])
                self.amb.append([V(c[0], c[1] + 10), V(random.uniform(-70, 70), random.uniform(20, 90)), random.uniform(.3, .8), c[3], 2])
            elif kind == "snow":
                self.amb.append([V(x, ROOM_TOP + 2), V(random.uniform(-10, 10), random.uniform(24, 46)), random.uniform(5, 9), (240, 250, 255), random.choice((2, 2, 3))])
            elif kind == "petals":
                self.amb.append([V(play.left + 4, y), V(random.uniform(14, 34), random.uniform(6, 24)), random.uniform(5, 9), random.choice([(255, 200, 224), (255, 240, 220), (255, 226, 140)]), 3])
            elif kind == "stars":
                self.amb.append([V(x, y), V(0, 0), random.uniform(1, 2.4), random.choice([(255, 240, 200), (255, 214, 100), (200, 210, 255)]), 2])
            else:   # motes
                self.amb.append([V(x, y), V(random.uniform(-8, 8), random.uniform(-14, 4)), random.uniform(3, 6), mix(pal["glow"], WHITE, .3), 2])
        for a in self.amb:
            a[0] += a[1] * dt
            a[2] -= dt
        self.amb = [a for a in self.amb if a[2] > 0 and play.collidepoint(a[0])]

    # ---------------- objective text ----------------
    def objective(self):
        if self.room_done:
            return ("Go through the door" if not self.line.complete else "Leave the building"), self.exit_pos
        if self.mode_name():
            return self.mode_objective()
        if self.kind == "fight":
            return f"{self.line.task_label}  (wave {self.ambush_wave}/{2 + self.index})", None
        if self.search_mode:
            floor_done = sum(1 for k in self.searched_keys if k[0] == self.quest_floor)
            if self.is_heist():
                if self.quest_floor == 0 and not self.item_found:
                    return "Sneak to the stairs and search the upper floor", self.stair_pos
                if self.quest_floor == 1 and not self.item_found:
                    left = [o for o in self.searchables if not o.searched]
                    tgt = min(left, key=lambda o: dist(o.pos, game.player.pos)).pos if left else None
                    return f"Search upstairs ({floor_done}/{self.search_total})", tgt
                if self.quest_floor == 1:
                    return "You found it - go downstairs", self.stair_pos
                return "Get out through the exit door", self.exit_pos
            if not self.item_found:
                return f"Search the room ({floor_done}/{self.search_total})", None
            return "You found it - return to the door", self.exit_pos
        return super().objective()

    # ---------------- drawing ----------------
    def draw_door(self, surf, p, color, label):
        draw_room_door(surf, p, self.theme, color, label, self.time)

    def draw_prop(self, surf, p):
        draw_objective_prop(surf, p, self.theme, self.line.task_label, self.time)

    def draw_stairs(self, surf, p):
        x, y = int(p.x), int(p.y)
        pal = self.theme["pal"]
        up = self.quest_floor == 0
        glow(surf, (x, y), 46, self.accent, 60)
        pygame.draw.rect(surf, mix(pal["wall"], BLACK, .5), (x - 34, y - 24, 68, 48))
        for i in range(6):
            col = mix(pal["wall"], WHITE, .1 + i * .06) if up else mix(pal["wall"], WHITE, .45 - i * .06)
            pygame.draw.rect(surf, col, (x - 30 + i * 10, y - 20 + i * 2, 10, 40 - i * 4))
            pygame.draw.line(surf, mix(col, BLACK, .5), (x - 30 + i * 10, y - 20 + i * 2), (x - 30 + i * 10, y + 20 - i * 2))
        pygame.draw.rect(surf, pal["edge"], (x - 34, y - 24, 68, 48), 2)
        draw_text(surf, "UP" if up else "DOWN", (x, y - 40), self.accent, 16, center=True)

    def draw_searchable(self, surf, p, obj):
        spr = obj._sprites.get(obj.searched)
        if spr is None:
            spr = build_container_sprite(obj.search_kind, self.theme, self.seed * 100 + obj.index * 7 + obj.floor, obj.searched)
            try:
                spr = spr.convert_alpha()
            except Exception:
                pass
            obj._sprites[obj.searched] = spr
        x, y = int(p.x), int(p.y)
        surf.blit(spr, (x - 60, y - 62))
        top = y - 56 + int(math.sin(self.time * 4 + obj.index) * 2)
        if not obj.searched:
            draw_text(surf, "?", (x, top), GOLD, 18, center=True)
        else:
            pygame.draw.lines(surf, GREEN, False, [(x - 6, top + 8), (x - 2, top + 13), (x + 7, top + 2)], 3)

    def get_vignette(self):
        if self._vig is None:
            small = pygame.Surface((48, 32), pygame.SRCALPHA)
            for j in range(32):
                for i in range(48):
                    d = math.hypot((i - 23.5) / 24, (j - 15.5) / 16)
                    small.set_at((i, j), (0, 0, 0, int(clamp((d - .6) * 200, 0, 150))))
            self._vig = pygame.transform.smoothscale(small, (WIDTH, HEIGHT))
        return self._vig

    def get_bg(self, floor):
        bg = self._bg.get(floor)
        if bg is not None:
            return bg
        th = self.theme
        pal = th["pal"]
        rng = random.Random(self.seed * 3 + floor * 17 + 5 + self.layout_index)
        lights = []
        surf = pygame.Surface((WIDTH, HEIGHT))
        surf.fill(mix(pal["wall"], BLACK, .55))
        play = self.play
        frames = [R(0, 0, WIDTH, play.top), R(0, play.bottom, WIDTH, HEIGHT - play.bottom),
                  R(0, play.top, play.left, play.h), R(play.right, play.top, WIDTH - play.right, play.h)]
        for fr in frames:
            draw_wall_block(surf, fr, th, rng)
        style = th["floor"] if floor == 0 else th["upper"]
        surf.set_clip(play)
        FLOOR_STYLES[style](surf, play, pal, rng)
        spots = list(self._free) or [V(480, 340)]
        for name in th["decor"] * (1 if self.search_mode else 2):
            p = V(rng.choice(spots)) if name not in ("runner", "seal", "ring", "lightbeams") else V(480, 345)
            DECOR_STYLES[name](surf, p, th, rng)
        surf.set_clip(None)
        pygame.draw.rect(surf, mix(pal["edge"], BLACK, .3), play, 3)
        # back wall + partition walls / prop blocks
        band = R(play.left, play.top, play.w, ROOM_TOP - play.top)
        draw_wall_block(surf, band, th, rng)
        BACK_STYLES[th["back"]](surf, band, th, rng, lights)
        pygame.draw.rect(surf, mix(pal["wall"], BLACK, .55), band, 2)
        alpha_rect(surf, (band.left, band.bottom, band.w, 10), BLACK, 90)
        for w in self.walls[1:]:
            if max(w.w, w.h) <= 90 and min(w.w, w.h) >= 30:
                alpha_rect(surf, (w.x + 4, w.bottom - 4, w.w, 9), BLACK, 95)
                PROP_STYLES[th["pillar"]](surf, w, pal, rng, lights)
            else:
                draw_wall_block(surf, w, th, rng)
        self._bg[floor] = surf
        self.lights[floor] = lights
        return surf

    def draw_objects(self, surf, cam):
        super().draw_objects(surf, cam)
        self.mode_draw(surf)

    def draw_ground(self, surf, cam):
        floor = self.quest_floor
        surf.blit(self.get_bg(floor), (0, 0))
        for i, (x, y, r, c) in enumerate(self.lights.get(floor, [])):
            flick = 1 + math.sin(self.time * 6 + i * 1.9) * .05 + math.sin(self.time * 13 + i) * .03
            glow(surf, (x, y), int(r * flick / 4) * 4, c, 90)
        if self.guards:
            if self.cone_surface is None:
                self.cone_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            self.cone_surface.fill((0, 0, 0, 0))
            for g in self.guards:
                g.draw_cone(self.cone_surface, self.alert > 50, self)
            surf.blit(self.cone_surface, (0, 0))

    def draw_top(self, surf, cam):
        for pos, vel, life, col, size in self.amb:
            fade = clamp(life / 1.2, 0, 1)
            pygame.draw.circle(surf, mix(BLACK, col, fade), ipos(pos), size)
        surf.blit(self.get_vignette(), (0, 0))
        if self.search_mode:
            if self.is_heist():
                label = f"{self.line.title}  -  {'GROUND FLOOR' if self.quest_floor == 0 else 'UPPER FLOOR'}"
            else:
                label = f"{self.line.title}  -  INVESTIGATION"
        else:
            label = f"{self.line.title}  -  {QUEST_KIND_NAMES.get(self.kind, 'TASK')}  {min(self.line.step + 1, len(self.line.tasks))} / {len(self.line.tasks)}"
        sub = None
        if self.search_mode:
            floor_done = sum(1 for k in self.searched_keys if k[0] == self.quest_floor)
            sub = ("OBJECTIVE FOUND - GET OUT" if self.item_found else f"SEARCHED: {floor_done}/{self.search_total}")
        alpha_rect(surf, R(300, 86, 360, 80), BLACK, 120)
        draw_text(surf, label, (480, 122), self.accent, 17, center=True)
        if sub:
            draw_text(surf, sub, (480, 145), GREEN if self.item_found else WHITE, 15, center=True)
        if self.guards or (self.kind == "stealth" and not self.room_done):
            panel(surf, R(330, 92, 300, 24), RED if self.alert > 60 else EDGE)
            pygame.draw.rect(surf, RED if self.alert > 60 else GOLD, (334, 96, int(292 * self.alert / 100), 16))
            draw_text(surf, "ALERT" if not self.alarm else "ALARM RAISED", (480, 96), WHITE, 16, center=True)
        hud = self.mode_hud()
        if hud:
            label_, frac, col = hud
            panel(surf, R(330, 92, 300, 24), col)
            pygame.draw.rect(surf, col, (334, 96, int(292 * clamp(frac, 0, 1)), 16))
            draw_text(surf, label_, (480, 96), WHITE, 15, center=True)

    # ---- alarm: drones respond with drones, everyone else with elites ----
    def raise_alarm(self):
        self.alarm = True
        self.detected = True
        game.banner("ALARM!", "The guards have spotted you - fight!", RED)
        scale = REALM_DIFFICULTY[self.rid] * (1 + .08 * self.index)
        drone = self.theme.get("guard") == "drone"
        for g in self.guards:
            e = self.add_enemy(Enemy(g.pos, "drone" if drone else "guard", scale, self.accent, aggro=900))
            if not drone and random.random() < .35:
                make_elite(e)
        for _ in range(3 if drone else 2):
            e = self.add_enemy(Enemy(V(860, random.randint(130, 500)), "drone" if drone else "guard", scale, self.accent, aggro=900))
            if not drone and self.index >= 1:
                make_elite(e)
        self.guards = []


# Keep the original stable quest system as the base and swap only the
# themed interior implementation.
QuestInterior = ExpandedQuestInterior

# ============================================================
# DUNGEON
# ============================================================

DUNGEON_GUIDES = ["Tarin", "Mirael", "Boros", "Kess", "Vara", "Dain", "Iris", "Marek", "Sable", "Orin"]
DUNGEON_BOSSES = ["ASH WARDEN", "GRAVEBORN", "EMBER TITAN", "DREAD KNIGHT", "BONE HYDRA",
                  "MOLTEN JUGGERNAUT", "VOID REAVER", "CATHEDRAL BEHEMOTH", "GLASS DEVOURER", "THE LAST STAR"]
DUNGEON_ROOMS = [
    ("THE THRESHOLD", [(7, 5, 4, 1), (7, 14, 4, 1), (20, 5, 4, 1), (20, 14, 4, 1)]),
    ("BROKEN GALLERY", [(6, 5, 1, 4), (6, 12, 1, 4), (25, 5, 1, 4), (25, 12, 1, 4), (13, 9, 6, 1)]),
    ("EMBER WELLS", [(6, 5, 3, 2), (22, 5, 3, 2), (6, 13, 3, 2), (22, 13, 3, 2)]),
    ("WARDEN'S HALL", [(4, 5, 5, 1), (4, 14, 5, 1), (23, 5, 5, 1), (23, 14, 5, 1), (13, 7, 6, 1), (13, 12, 6, 1)]),
    ("ASH CITADEL", [(5, 4, 4, 1), (23, 4, 4, 1), (5, 15, 4, 1), (23, 15, 4, 1), (14, 7, 4, 1)]),
    ("MOLTEN CATACOMBS", [(6, 4, 5, 1), (18, 7, 6, 1), (26, 4, 2, 4), (10, 14, 6, 1)]),
    ("FALLEN OBSERVATORY", [(5, 5, 1, 3), (5, 12, 1, 3), (10, 5, 4, 1), (18, 5, 4, 1), (10, 15, 4, 1), (18, 15, 4, 1), (26, 5, 1, 3), (26, 12, 1, 3)]),
    ("BLACK CATHEDRAL", [(4, 4, 6, 1), (22, 4, 6, 1), (4, 15, 6, 1), (22, 15, 6, 1), (11, 7, 2, 2), (19, 7, 2, 2), (11, 12, 2, 2), (19, 12, 2, 2)]),
    ("GLASS MAZE", [(7, 3, 1, 5), (7, 12, 1, 6), (15, 6, 1, 8), (23, 3, 1, 5), (23, 12, 1, 6)]),
    ("THE LAST STAR", [(4, 4, 6, 1), (22, 4, 6, 1), (4, 15, 6, 1), (22, 15, 6, 1), (13, 8, 6, 1), (13, 12, 6, 1)]),
]
DUNGEON_MOVES = [
    ["spread", "spread", "radial"],
    ["summon", "spread", "aimed"],
    ["slam", "ringwave", "spread"],
    ["charge", "spread", "charge"],
    ["hydra", "hydra", "radial"],
    ["lavatrail", "ringwave", "spread"],
    ["teleport", "radial", "aimed"],
    ["spiral", "radial", "slam"],
    ["shards", "shards", "aimed"],
    ["spiral", "charge", "summon", "slam", "teleport", "shards", "hydra"],
]


class DungeonBoss(Boss):
    def __init__(self, pos, room):
        scale = 1.46 ** room
        super().__init__(pos, DUNGEON_BOSSES[room], 780 * scale, 34 + min(16, room * 2), [EMBER, PURPLE, ORANGE, ASH, WHITE, RED, PURPLE, GOLD, ICE, GOLD][room], int(14 + room * 4))
        self.room = room
        self.boss_kind = "dungeon"
        self.move_index = 0
        self.cooldown = 1.6
        self.charge_dir = None
        self.charge_time = 0
        self.dmg = int((13 + room * 4.6))
        self.base_speed = 60 + room * 6
        self.spiral = 0.0
        self.minions = []

    def think(self, dt, scene):
        if self.charge_time > 0:
            self.charge_time -= dt
            self.pos = scene.move(self.pos, self.charge_dir * (420 + self.room * 20) * dt, self.radius * .7)
            if self.charge_time <= 0:
                self.charge_dir = None
            return
        self.chase(dt, scene, self.base_speed * (1 + .18 * (self.phase - 1)), 120)
        self.cooldown -= dt * (1 + .2 * (self.phase - 1))
        if self.cooldown <= 0:
            moves = DUNGEON_MOVES[self.room]
            move = moves[self.move_index % len(moves)]
            self.move_index += 1
            getattr(self, "move_" + move)(scene)
            self.cooldown = max(.7, 1.8 - self.room * .07)

    def shoot(self, angle, speed=210, radius=8, color=None, **kw):
        game.enemy_shot(self.pos, angle, speed * (1 + self.room * .025), self.dmg, color or self.color, radius, **kw)

    def move_aimed(self, scene):
        self.shoot(angle_to(self.pos, game.player.pos), 280)

    def move_spread(self, scene):
        base = angle_to(self.pos, game.player.pos)
        n = 3 + (self.phase - 1) * 2
        for i in range(n):
            self.shoot(base + (i - (n - 1) / 2) * .22)

    def move_radial(self, scene):
        n = 8 + self.phase * 2
        off = random.random()
        for i in range(n):
            self.shoot(off + i * math.tau / n, 170)

    def move_spiral(self, scene):
        for k in range(3):
            for i in range(6):
                self.shoot(self.spiral + i * math.tau / 6 + k * .12, 160 + k * 25, 7)
        self.spiral += .35

    def move_summon(self, scene):
        self.minions = [m for m in self.minions if m.alive]
        if len(self.minions) >= 4:
            self.move_spread(scene)
            return
        for _ in range(2):
            e = scene.add_enemy(Enemy(self.pos + from_angle(random.random() * math.tau, 70), random.choice(["crawler", "wraith"]), 1.25 ** self.room, self.color, 900))
            e.drops = False
            self.minions.append(e)
        game.float_text(self.pos, "RISE!", self.color)

    def move_slam(self, scene):
        for i in range(1 + (self.phase >= 3)):
            p = game.player.pos + (V(random.uniform(-60, 60), random.uniform(-60, 60)) if i else V())
            scene.hazards.append(Hazard(p, 80, .9, .25, self.dmg + 6, self.color))

    def move_ringwave(self, scene):
        for i in range(3):
            scene.hazards.append(Hazard(self.pos, 90 + i * 70, .7 + i * .35, .25, self.dmg, self.color, "ring", inner=60 + i * 70))

    def move_charge(self, scene):
        self.charge_dir = (game.player.pos - self.pos).normalize() if dist(self.pos, game.player.pos) > 1 else V(1, 0)
        end = self.pos + self.charge_dir * 300
        scene.hazards.append(Hazard(self.pos, 0, .55, .01, 0, RED, "line", end=end, width=self.radius * 2))
        self.charge_time = 0
        self.timers["charge_delay"] = .55
        self.cooldown = 1.2
        self._pending_charge = True

    def update(self, dt, scene):
        if getattr(self, "_pending_charge", False) and self.alive and self.intro <= 0:
            self.timers["charge_delay"] = self.timers.get("charge_delay", 0) - dt
            if self.timers["charge_delay"] <= 0:
                self._pending_charge = False
                self.charge_time = .7
            self.tick_status(dt)
            return
        super().update(dt, scene)

    def move_hydra(self, scene):
        base = angle_to(self.pos, game.player.pos)
        for k, off in enumerate((-.5, 0, .5)):
            origin = self.pos + from_angle(base + off * 2, self.radius)
            a = angle_to(origin, game.player.pos)
            for j in (-.15, .15):
                game.enemy_shot(origin, a + j, 230, self.dmg, [RED, WHITE, GOLD][k], 7)

    def move_lavatrail(self, scene):
        for i in range(4):
            p = self.pos + from_angle(random.random() * math.tau, random.uniform(20, 140))
            scene.hazards.append(Hazard(p, 40, .6, 4.0, int(self.dmg * .6), ORANGE, element="fire", effect="burn"))

    def move_teleport(self, scene):
        for _ in range(16):
            p = game.player.pos + from_angle(random.random() * math.tau, random.uniform(150, 230))
            if not scene.blocked(p, self.radius):
                burst(self.pos, PURPLE, 18, (60, 160), .5, 3)
                self.pos = p
                burst(self.pos, PURPLE, 18, (60, 160), .5, 3)
                break
        self.move_radial(scene)

    def move_shards(self, scene):
        base = angle_to(self.pos, game.player.pos)
        for i in range(5):
            game.enemy_shot(self.pos, base + (i - 2) * .3, 250, self.dmg, ICE, 7, kind="shard", bounces=2, life=4.0)

    def draw_body(self, surf, x, y):
        r = self.radius
        c = self.color
        pygame.draw.circle(surf, mix(c, BLACK, .55), (x, y), r)
        pygame.draw.circle(surf, mix(c, BLACK, .2), (x, y - 6), r - 8)
        pygame.draw.polygon(surf, c, [(x - r * .7, y - r * .6), (x - r * .3, y - r * 1.25), (x, y - r * .75), (x + r * .3, y - r * 1.25), (x + r * .7, y - r * .6)])
        pygame.draw.rect(surf, (25, 20, 28), (x - r * .45, y - 10, r * .9, 14))
        pygame.draw.rect(surf, GOLD, (x - r * .3, y - 7, 6, 6))
        pygame.draw.rect(surf, GOLD, (x + r * .3 - 6, y - 7, 6, 6))
        if self.room == 4:
            for off in (-1, 1):
                pygame.draw.circle(surf, c, (x + off * r, y - r * .6), r // 3)
        if getattr(self, "_pending_charge", False):
            pygame.draw.circle(surf, RED, (x, y), r + 8, 3)


class DungeonHub(Arena):
    key = "dungeon_hub"
    title = "DUNGEON HUB"
    hub = True

    def __init__(self):
        super().__init__(R(40, 70, 880, 515))
        self.accent = PURPLE
        self.interactables = [
            Interactable(V(90, 520), "Return to the Homeworld", lambda: game.go_home(), 60,
                         draw_fn=lambda s, p, it: draw_portal(s, p, PURPLE, self.time, "HOME", 26)),
            NPC("Quartermaster", "Dungeon Armory", V(480, 520), PURPLE, lambda: game.open_dungeon_shop(), None, (50, 50, 60), (70, 50, 90)),
        ]
        for i, name in enumerate(DUNGEON_GUIDES):
            col, row = i % 5, i // 5
            pos = V(150 + col * 165, 170 + row * 180)
            self.interactables.append(NPC(name, f"Room {i + 1} Guide", pos, GOLD,
                                          (lambda i=i: game.talk_dungeon_guide(i)),
                                          (lambda i=i: ("!", GOLD) if i == game.dungeon_progress and i < 10 else (("OK", GREEN) if i < game.dungeon_progress else None)),
                                          (90, 70, 50), (70, 60, 80)))

    def spawn(self):
        return V(480, 440)

    def draw_ground(self, surf, cam):
        self.draw_floor(surf, (34, 33, 44), (44, 42, 56))
        for i in range(10):
            col, row = i % 5, i // 5
            x, y = 150 + col * 165, 170 + row * 180
            unlocked = i <= game.dungeon_progress
            bay = R(x - 50, y + 30, 100, 60)
            pygame.draw.rect(surf, (48, 46, 60) if unlocked else (30, 30, 38), bay)
            pygame.draw.rect(surf, GOLD if unlocked else EDGE, bay, 2)
            draw_text(surf, f"ROOM {i + 1}", (x, y + 38), GOLD if unlocked else ASH, 18, center=True)
            draw_text(surf, DUNGEON_BOSSES[i].title() if unlocked else "LOCKED", (x, y + 60), WHITE if unlocked else ASH, 15, center=True)

    def draw_top(self, surf, cam):
        draw_text(surf, f"DUNGEON HUB  -  {game.dungeon_progress}/10 ROOMS CLEARED", (480, 96), GOLD, 22, center=True)

    def objective(self):
        if game.dungeon_progress < 10:
            i = game.dungeon_progress
            return f"Talk to {DUNGEON_GUIDES[i]} to enter Room {i + 1}", self.interactables[2 + i].pos
        return "Every room is cleared. Rooms can be replayed for loot.", None


class DungeonRoom(Arena):
    key = "dungeon_room"
    allow_escape = False

    def __init__(self, room):
        super().__init__(R(36, 64, 888, 520))
        self.room = room
        self.title = f"ROOM {room + 1}: {DUNGEON_ROOMS[room][0]}"
        self.accent = GOLD
        self.walls = [R(x * TILE, y * TILE, w * TILE, h * TILE) for x, y, w, h in DUNGEON_ROOMS[room][1]]
        self.walls = [w for w in self.walls if not w.collidepoint(80, 330) and not w.colliderect(R(60, 280, 80, 100))]
        self.cleared = False
        self.chest_open = False
        rng = random.Random(room * 13 + random.randint(0, 999))
        scale = 1.42 ** room
        count = 6 + int(room * 1.4)
        types = ["crawler", "wraith", "brute", "shooter", "mage"]
        if room >= 5:
            types = types + ["guard", "drone"]
        if room >= 7:
            types = types + ["drone", "drone"]
        elites = 0 if room < 2 else 1 + room // 3
        for i in range(count):
            p = V(rng.randint(300, 860), rng.randint(110, 540))
            e = self.add_enemy(Enemy(p, types[(i + room) % len(types)] if room > 2 else types[i % 3], scale, None, aggro=420))
            if i < elites:
                make_elite(e)
        self.boss = self.add_enemy(DungeonBoss(V(740, 330), room))
        self.interactables = [
            Interactable(V(860, 330), "Open the chest", self.open_chest, 60, visible=lambda: self.cleared and not self.chest_open,
                         draw_fn=lambda s, p, it: self.draw_chest(s, p)),
            Interactable(V(70, 330), lambda: "Return to the Dungeon Hub" if self.cleared else "Doors are sealed", self.leave, 56,
                         draw_fn=lambda s, p, it: self.draw_door(s, p)),
        ]

    def spawn(self):
        return V(110, 330)

    def leave(self):
        if not self.cleared:
            game.float_text(game.player.pos, "Defeat every enemy to unseal the doors", RED)
            return
        game.enter_dungeon_hub()

    def update(self, dt):
        super().update(dt)
        if not self.cleared and not any(e.alive for e in self.enemies):
            self.cleared = True
            game.banner("ROOM CLEARED", "A chest appears. The doors unseal.", GREEN)

    def open_chest(self):
        if self.chest_open:
            return
        self.chest_open = True
        tier = self.room + 1
        gold = int(random.randint(30 * tier, 50 * tier) * GOLD_RATE)
        game.player.gold += gold
        game.float_text(V(860, 300), f"+{gold} gold", GOLD, 1.5, 22)
        drops = []
        for unlock, kit in DUNGEON_KITS.items():
            if unlock == tier:
                for entry in kit:
                    if self.room + 1 >= game.dungeon_progress or random.random() < .12:
                        drops.append(kit_item(entry))
        if not drops and random.random() < .5:
            drops.append(potion(2))
        if random.random() < .5:
            game.player.embers += 1 + self.room // 2
        for it in drops:
            game.give_item(it)
        burst(V(860, 330), GOLD, 30, (60, 180), .8, 3)

    def objective(self):
        if not self.cleared:
            return f"Defeat {DUNGEON_BOSSES[self.room].title()} and its guards ({len(self.enemies)} left)", None
        if not self.chest_open:
            return "Open the chest", V(860, 330)
        return "Return to the hub", V(70, 330)

    def draw_ground(self, surf, cam):
        base = mix((52, 50, 58), REALM_COLORS[self.room % 4], .12)
        self.draw_floor(surf, base, mix(base, BLACK, .2), 32)
        self.draw_walls(surf, (36, 36, 44), (100, 90, 80))


    def draw_chest(self, surf, p):
        x, y = ipos(p)
        glow(surf, (x, y), 40, GOLD, 80)
        pygame.draw.rect(surf, (116, 73, 45), (x - 18, y - 10, 36, 22))
        pygame.draw.rect(surf, GOLD, (x - 19, y - 14, 38, 9), 3)
        pygame.draw.rect(surf, GOLD, (x - 3, y - 5, 6, 9))

    def draw_door(self, surf, p):
        x, y = ipos(p)
        c = GREEN if self.cleared else (110, 50, 55)
        pygame.draw.rect(surf, (12, 12, 16), (x - 16, y - 40, 32, 80))
        pygame.draw.rect(surf, c, (x - 16, y - 40, 32, 80), 3)


# ============================================================
# REALM BOSSES (end of each realm's third quest)
# ============================================================

class Crystal:
    """Breakable healing crystal (Emberfang's Sanctum)."""
    is_boss = False

    def __init__(self, pos, color=EMBER):
        self.pos = V(pos)
        self.radius = 16
        self.hp = 70
        self.alive = True
        self.color = color
        self.anim = random.random() * 6
        self.flash = 0

    def take_damage(self, amount, effect=None, knock=None):
        if not self.alive:
            return
        self.hp -= amount
        self.flash = .1
        if self.hp <= 0:
            self.alive = False
            burst(self.pos, GREEN, 20, (50, 150), .6, 3)
            game.float_text(self.pos, "CRYSTAL SHATTERED", GREEN)

    def apply_effect(self, effect, power=1.0):
        pass

    def draw(self, surf, cam):
        if not self.alive:
            return
        self.anim += 1 / 60
        x, y = ipos(self.pos - cam)
        glow(surf, (x, y), 36, self.color, 90)
        pygame.draw.polygon(surf, self.color, [(x, y - 20), (x + 12, y), (x, y + 20), (x - 12, y)])
        pygame.draw.polygon(surf, WHITE if self.flash <= 0 else RED, [(x, y - 10), (x + 5, y), (x, y + 10), (x - 5, y)])
        self.flash = max(0, self.flash - 1 / 60)


class Emberfang(Boss):
    phase_names = ("THE SLEEPER WAKES", "WINGS OF CINDER", "THE MOUNTAIN BURNS")

    def __init__(self, pos, arena):
        super().__init__(pos, "EMBERFANG, THE EMBER DRAGON", 1700, 46, EMBER, 18)
        self.arena = arena
        self.boss_kind = "realm"
        self.rid = EMBER_ID
        self.landing = None

    def damage_mult(self):
        return .15 if any(c.alive for c in self.arena.crystals) else 1.0

    def think(self, dt, scene):
        if any(c.alive for c in self.arena.crystals) and self.timer("heal", dt, 2.4) and self.hp < self.max_hp:
            self.hp = min(self.max_hp, self.hp + 45)
            game.float_text(self.pos, "+45 (crystals)", GREEN, .8)
        if self.landing is not None:
            self.landing[1] -= dt
            if self.landing[1] <= 0:
                self.pos = V(self.landing[0])
                self.landing = None
                game.shake(.3)
            return
        self.chase(dt, scene, 48 + 12 * self.phase, 130)
        if self.timer("volley", dt, max(.6, 1.2 - .17 * (self.phase - 1))):
            base = angle_to(self.pos, game.player.pos)
            for off in ((0,) if self.phase == 1 else (-.16, 0, .16)):
                game.enemy_shot(self.pos, base + off, 230, 16, EMBER, 9, element="fire")
        if self.timer("breath", dt, max(1.6, 3.0 - .4 * self.phase)) and dist(self.pos, game.player.pos) < 300:
            base = angle_to(self.pos, game.player.pos)
            for i in range(9):
                game.enemy_shot(self.pos + from_angle(base, 30), base - .6 + i * .15, 190, 11, ORANGE, 10, effect="burn", element="fire", life=1.8)
        if self.phase >= 2 and self.timer("fly", dt, 7.0):
            target = scene.find_free(game.player.pos + V(random.uniform(-40, 40), random.uniform(-40, 40)), self.radius)
            scene.hazards.append(Hazard(target, 90, 1.1, .3, 28, ORANGE, element="fire", label="LANDING"))
            self.landing = [target, 1.1]
        if self.phase >= 3 and self.timer("meteor", dt, 1.4):
            for _ in range(2):
                p = V(random.randint(100, 860), random.randint(130, 540))
                scene.hazards.append(Hazard(p, 55, 1.0, .3, 22, EMBER, element="fire", effect="burn"))

    def draw_body(self, surf, x, y):
        if self.landing is not None:
            alpha_circle(surf, (x, y), self.radius, EMBER, 60)
            return
        y += int(math.sin(self.anim * 3) * 3)
        flap = math.sin(self.anim * 6) * 10
        pygame.draw.polygon(surf, (190, 76, 36), [(x - 36, y - 12), (x - 90, y - 50 - flap), (x - 50, y), (x - 85, y + 14), (x - 34, y + 10)])
        pygame.draw.polygon(surf, (190, 76, 36), [(x + 36, y - 12), (x + 90, y - 50 - flap), (x + 50, y), (x + 85, y + 14), (x + 34, y + 10)])
        pygame.draw.ellipse(surf, (92, 40, 27), (x - 55, y - 35, 110, 70))
        pygame.draw.ellipse(surf, (150, 61, 31), (x - 46, y - 28, 92, 56))
        pygame.draw.polygon(surf, (220, 200, 160), [(x - 20, y - 30), (x - 30, y - 52), (x - 10, y - 32)])
        pygame.draw.polygon(surf, (220, 200, 160), [(x + 20, y - 30), (x + 30, y - 52), (x + 10, y - 32)])
        pygame.draw.circle(surf, GOLD, (x - 16, y - 10), 5)
        pygame.draw.circle(surf, GOLD, (x + 16, y - 10), 5)
        glow(surf, (x, y + 10), 30, ORANGE, 80)


class FrostheartColossus(Boss):
    phase_names = ("THE GLACIER STIRS", "WALLS OF WINTER", "WHITEOUT")

    def __init__(self, pos, arena):
        super().__init__(pos, "THE FROSTHEART COLOSSUS", 2300, 50, BLUE, 24)
        self.arena = arena
        self.boss_kind = "realm"
        self.rid = FROZEN_ID

    def think(self, dt, scene):
        self.chase(dt, scene, 40 + 8 * self.phase, 110)
        if self.timer("fan", dt, max(.7, 1.3 - .2 * (self.phase - 1))):
            base = angle_to(self.pos, game.player.pos)
            for off in (-.34, -.17, 0, .17, .34):
                game.enemy_shot(self.pos, base + off, 250, 19, ICE, 7, kind="shard")
        if self.timer("ring", dt, 4.2 if self.phase < 3 else 3.0):
            for i in range(12):
                game.enemy_shot(self.pos, i * math.tau / 12 + self.anim * .3, 170, 18, BLUE, 10, effect="slow")
        if self.timer("icefall", dt, 2.4 if self.phase == 1 else 1.6):
            for _ in range(1 + self.phase):
                p = game.player.pos + V(random.uniform(-90, 90), random.uniform(-90, 90))
                scene.hazards.append(Hazard(p, 46, 1.0, .25, 22, ICE, effect="freeze", label="ICE"))
        if self.phase >= 2 and self.timer("walls", dt, 8.0):
            scene.raise_ice_walls()

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 2) * 3)
        pygame.draw.polygon(surf, (52, 91, 122), [(x, y - 62), (x + 46, y - 26), (x + 38, y + 42), (x, y + 60), (x - 38, y + 42), (x - 46, y - 26)])
        pygame.draw.polygon(surf, (125, 205, 235), [(x, y - 48), (x + 28, y - 16), (x + 20, y + 26), (x, y + 40), (x - 20, y + 26), (x - 28, y - 16)], 3)
        pygame.draw.polygon(surf, WHITE, [(x - 26, y - 36), (x - 8, y - 58), (x - 4, y - 32), (x - 18, y - 18)])
        pygame.draw.polygon(surf, WHITE, [(x + 26, y - 36), (x + 8, y - 58), (x + 4, y - 32), (x + 18, y - 18)])
        glow(surf, (x, y + 4), 26, ICE, 110)
        pygame.draw.circle(surf, WHITE, (x - 13, y - 8), 5)
        pygame.draw.circle(surf, WHITE, (x + 13, y - 8), 5)


class SeraphBoss(Boss):
    phase_names = ("JUDGMENT", "THE CATHEDRAL SHATTERS", "FALLEN SKY")

    def __init__(self, pos, arena):
        super().__init__(pos, "THE SERAPH OF THE FALLEN SKY", 3300, 44, GOLD, 26)
        self.arena = arena
        self.boss_kind = "realm"
        self.rid = STARFALL_ID
        self.immune_waves_done = 0
        self.wave = []

    def update(self, dt, scene):
        if self.immune:
            self.anim += dt
            self.wave = [m for m in self.wave if m.alive]
            if not self.wave:
                self.immune = False
                game.banner("VULNERABLE", "The Seraph's light falters", GREEN)
            elif self.timer("immune_lance", dt, 1.8):
                self.lances(scene, 2)
            return
        super().update(dt, scene)
        if self.alive and self.immune_waves_done < 2 and self.ratio() <= (.66 if self.immune_waves_done == 0 else .33):
            self.immune_waves_done += 1
            self.immune = True
            self.pos = V(480, 200)
            positions = [V(260, 260), V(700, 260), V(300, 460), V(660, 460)] + ([V(480, 470)] if self.immune_waves_done == 2 else [])
            for p in positions:
                e = scene.add_enemy(Enemy(p, random.choice(["wraith", "mage", "shooter"]), REALM_DIFFICULTY[STARFALL_ID] * 1.1, GOLD, 900))
                e.drops = False
                self.wave.append(e)
            game.banner("IMMUNE", "Defeat the celestial guardians", GOLD)

    def lances(self, scene, n):
        for _ in range(n):
            x = clamp(game.player.pos.x + random.uniform(-120, 120), 70, 890)
            scene.hazards.append(Hazard(V(x, 75), 0, 1.0, .3, 24, GOLD, "line", end=V(x, 580), width=36))

    def think(self, dt, scene):
        self.chase(dt, scene, 50 + 10 * self.phase, 170)
        if self.timer("spread", dt, max(.55, 1.0 - .15 * (self.phase - 1))):
            base = angle_to(self.pos, game.player.pos)
            for off in (-.24, 0, .24):
                game.enemy_shot(self.pos, base + off, 280, 24, GOLD, 6)
        if self.timer("lance", dt, 2.6 if self.phase < 3 else 1.6):
            self.lances(scene, 3 if self.phase < 3 else 5)
        if self.phase >= 2 and self.timer("halo", dt, 5.0):
            for i in range(16):
                game.enemy_shot(self.pos, i * math.tau / 16, 160, 20, WHITE, 8)

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 2) * 4)
        glow(surf, (x, y), 80, GOLD, 70)
        pygame.draw.polygon(surf, WHITE, [(x - 24, y - 2), (x - 80, y - 32), (x - 62, y + 8), (x - 80, y + 30), (x - 20, y + 16)])
        pygame.draw.polygon(surf, WHITE, [(x + 24, y - 2), (x + 80, y - 32), (x + 62, y + 8), (x + 80, y + 30), (x + 20, y + 16)])
        pygame.draw.polygon(surf, GOLD, [(x, y - 56), (x + 26, y - 28), (x + 34, y + 8), (x + 20, y + 30), (x, y + 46), (x - 20, y + 30), (x - 34, y + 8), (x - 26, y - 28)])
        pygame.draw.circle(surf, WHITE, (x, y - 10), 10)
        pygame.draw.circle(surf, GOLD, (x, y - 66), 16, 3)


class VoidAdmiral(Boss):
    phase_names = ("BOARDING ACTION", "PLATFORM PHASE", "ALL HANDS LOST")

    def __init__(self, pos, arena):
        super().__init__(pos, "THE VOID ADMIRAL", 2800, 42, PURPLE, 26)
        self.arena = arena
        self.boss_kind = "realm"
        self.rid = VOID_ID
        self.beam_x = 480
        self.beam_dir = 1

    def teleport(self, scene):
        for _ in range(20):
            p = game.player.pos + from_angle(random.random() * math.tau, random.uniform(170, 300))
            if not scene.blocked(p, self.radius) and scene.play.inflate(-60, -60).collidepoint(p):
                burst(self.pos, PURPLE, 20, (60, 170), .5, 3)
                self.pos = p
                burst(p, PURPLE, 20, (60, 170), .5, 3)
                game.float_text(p, "VOID SHIFT", PURPLE)
                return

    def think(self, dt, scene):
        if self.phase == 2:
            # Platform phase: the Admiral looms at the top and sweeps the deck with a beam.
            target = V(480 + math.sin(self.anim * .8) * 330, 120)
            self.pos += (target - self.pos) * min(1, dt * 3)
            speed = 240
            self.beam_x += self.beam_dir * speed * dt
            if self.beam_x < 90 or self.beam_x > 870:
                self.beam_dir *= -1
                self.beam_x = clamp(self.beam_x, 90, 870)
            if abs(game.player.pos.x - self.beam_x) < 26 and game.player.pos.y > 150:
                game.player.take_damage(30)
            if self.timer("rain", dt, .65):
                for off in (-.18, 0, .18):
                    game.enemy_shot(self.pos, math.pi / 2 + off + random.uniform(-.1, .1), 250, 22, PURPLE, 8)
            return
        self.chase(dt, scene, 46 + 10 * self.phase, 120)
        if self.timer("tp", dt, 5.0 if self.phase == 1 else 3.5):
            self.teleport(scene)
        if self.timer("radial", dt, max(.6, 1.0 - .15 * (self.phase - 1))):
            for i in range(7):
                game.enemy_shot(self.pos, angle_to(self.pos, game.player.pos) + i * math.tau / 7, 240, 22, PURPLE, 7)
        if self.timer("lance", dt, 3.2 if self.phase == 1 else 2.0):
            base = angle_to(self.pos, game.player.pos)
            for off in (-.5, -.25, 0, .25, .5):
                game.enemy_shot(self.pos, base + off, 300, 24, (200, 120, 255), 9)
        if self.phase >= 3 and self.timer("hole", dt, 4.0):
            p = V(random.randint(150, 810), random.randint(170, 500))
            scene.hazards.append(Hazard(p, 70, 1.0, 2.0, 18, (40, 10, 60), label="RIFT"))

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 2) * 3)
        glow(surf, (x, y), 70, PURPLE, 70)
        pygame.draw.polygon(surf, (27, 22, 50), [(x, y - 64), (x + 39, y - 30), (x + 31, y + 42), (x, y + 57), (x - 31, y + 42), (x - 39, y - 30)])
        pygame.draw.polygon(surf, PURPLE, [(x, y - 49), (x + 24, y - 19), (x + 20, y + 30), (x, y + 44), (x - 20, y + 30), (x - 24, y - 19)], 4)
        pygame.draw.line(surf, BLUE, (x - 20, y - 24), (x + 20, y + 25), 4)
        pygame.draw.line(surf, WHITE, (x + 20, y - 24), (x - 20, y + 25), 2)
        pygame.draw.rect(surf, GOLD, (x - 18, y - 70, 36, 8))


REALM_BOSS_CLASSES = {EMBER_ID: Emberfang, FROZEN_ID: FrostheartColossus, STARFALL_ID: SeraphBoss, VOID_ID: VoidAdmiral}
REALM_BOSS_WALLS = {
    EMBER_ID: [R(240, 170, 40, 110), R(680, 170, 40, 110), R(240, 400, 40, 100), R(680, 400, 40, 100)],
    FROZEN_ID: [R(190, 160, 34, 90), R(736, 160, 34, 90), R(190, 410, 34, 90), R(736, 410, 34, 90)],
    STARFALL_ID: [R(230, 140, 90, 22), R(640, 140, 90, 22), R(230, 480, 90, 22), R(640, 480, 90, 22)],
    VOID_ID: [R(200, 150, 160, 22), R(600, 150, 160, 22), R(200, 470, 160, 22), R(600, 470, 160, 22)],
}


class RealmBossArena(Arena):
    def __init__(self, rid):
        super().__init__(R(40, 70, 880, 515))
        self.rid = rid
        self.key = f"realmboss{rid}"
        self.title = REALM_INFO[rid]["lair"]
        self.accent = REALM_COLORS[rid]
        self.base_walls = [R(w) for w in REALM_BOSS_WALLS[rid]]
        self.walls = list(self.base_walls)
        self.ice_walls = []
        self.ice_wall_timer = 0
        self.crystals = []
        if rid == EMBER_ID:
            self.crystals = [Crystal(p) for p in ((130, 140), (830, 140), (130, 510), (830, 510), (480, 110))]
        self.boss = REALM_BOSS_CLASSES[rid](V(480, 300), self)
        self.enemies = [self.boss]
        self.interactables = [
            Interactable(V(480, 560), lambda: "Leave the chamber" if not self.boss.alive else "Sealed while the boss lives",
                         self.leave, 56, draw_fn=lambda s, p, it: draw_portal(s, p, GREEN if not self.boss.alive else ASH, self.time, "EXIT", 24, not self.boss.alive)),
        ]

    def spawn(self):
        return V(480, 540)

    def leave(self):
        if self.boss.alive:
            game.float_text(game.player.pos, "The exit is sealed while the boss lives", RED)
            return
        game.go_realm(self.rid, at="boss")

    def extra_targets(self):
        return [c for c in self.crystals if c.alive]

    def raise_ice_walls(self):
        self.ice_walls = []
        for _ in range(3):
            for _try in range(10):
                w = R(random.randint(120, 800), random.randint(140, 500), random.choice((26, 140)), 0)
                w.height = 140 if w.width == 26 else 26
                if not w.inflate(60, 60).collidepoint(game.player.pos) and not w.inflate(40, 40).collidepoint(self.boss.pos):
                    self.ice_walls.append(w)
                    break
        self.walls = self.base_walls + self.ice_walls
        self.ice_wall_timer = 5.0
        game.float_text(V(480, 300), "WALLS OF ICE", ICE, 1.2, 22)

    def update(self, dt):
        super().update(dt)
        if self.ice_walls:
            self.ice_wall_timer -= dt
            if self.ice_wall_timer <= 0:
                self.ice_walls = []
                self.walls = list(self.base_walls)
        if self.rid == FROZEN_ID and self.boss.alive and self.boss.phase >= 3:
            game.player.on_ice = True

    def objective(self):
        if self.boss.alive:
            if self.crystals and any(c.alive for c in self.crystals):
                return "Shatter the healing crystals - they shield Emberfang", None
            return f"Defeat {self.boss.name.title()}", None
        return "Victory! Leave through the exit", V(480, 560)

    def draw_ground(self, surf, cam):
        bg = [(58, 25, 20), (24, 44, 70), (44, 40, 80), (12, 12, 30)][self.rid]
        line = [(90, 40, 28), (80, 130, 170), (110, 100, 150), (60, 35, 95)][self.rid]
        self.draw_floor(surf, bg, line)
        cx, cy = 480, 320
        if self.rid == EMBER_ID:
            for i in range(16):
                a = i * math.tau / 16
                pygame.draw.line(surf, (110, 45, 25), (cx, cy), (cx + math.cos(a) * 420, cy + math.sin(a) * 250), 2)
        elif self.rid == STARFALL_ID and self.boss.phase >= 2:
            for y in (145, 260, 390, 505):
                pygame.draw.line(surf, (190, 175, 230), (70, y), (890, y), 2)
        elif self.rid == VOID_ID:
            for rr in (90, 175, 260):
                pygame.draw.circle(surf, (80, 45, 120), (cx, cy), rr, 2)
            if self.boss.alive and self.boss.phase == 2:
                bx = int(self.boss.beam_x)
                alpha_rect(surf, R(bx - 26, 150, 52, 430), PURPLE, 90)
                pygame.draw.line(surf, WHITE, (bx, 150), (bx, 580), 4)
        if self.rid == FROZEN_ID and self.boss.phase >= 3:
            alpha_rect(surf, self.play, (200, 230, 255), 40)
        self.draw_walls(surf, mix(bg, BLACK, .3), self.accent)
        for w in self.ice_walls:
            pygame.draw.rect(surf, (170, 220, 245), w)
            pygame.draw.rect(surf, WHITE, w, 2)
        for c in self.crystals:
            c.draw(surf, cam)



# ============================================================
# OPTIONAL SECRET BOSSES (five phases each)
# ============================================================

class FloorGrid:
    """Arena floor split into cells that can crack, vanish or turn to lava."""
    NORMAL, WARN, GONE = 0, 1, 2

    def __init__(self, play, cell=80):
        self.cells = []
        for y in range(play.top, play.bottom - cell // 2, cell):
            for x in range(play.left, play.right - cell // 2, cell):
                self.cells.append(R(x, y, min(cell, play.right - x), min(cell, play.bottom - y)))
        self.state = [0] * len(self.cells)
        self.timer = [0.0] * len(self.cells)
        self.duration = [0.0] * len(self.cells)

    def index_at(self, p):
        for i, c in enumerate(self.cells):
            if c.collidepoint(p):
                return i
        return -1

    def trigger(self, i, warn=1.2, duration=4.0):
        if 0 <= i < len(self.cells) and self.state[i] == self.NORMAL:
            self.state[i] = self.WARN
            self.timer[i] = warn
            self.duration[i] = duration

    def gone_fraction(self):
        return sum(1 for s in self.state if s != self.NORMAL) / max(1, len(self.cells))

    def random_trigger(self, n, warn, duration, avoid=None, near=None, max_frac=.45):
        candidates = [i for i in range(len(self.cells)) if self.state[i] == self.NORMAL]
        if avoid is not None:
            candidates = [i for i in candidates if not self.cells[i].inflate(-10, -10).collidepoint(avoid)] or candidates
        if near is not None:
            candidates.sort(key=lambda i: dist(self.cells[i].center, near))
            candidates = candidates[:max(n * 3, 6)]
        random.shuffle(candidates)
        for i in candidates[:n]:
            if self.gone_fraction() >= max_frac:
                break
            self.trigger(i, warn, duration)

    def update(self, dt):
        for i in range(len(self.cells)):
            if self.state[i] == self.WARN:
                self.timer[i] -= dt
                if self.timer[i] <= 0:
                    self.state[i] = self.GONE
                    self.timer[i] = self.duration[i]
            elif self.state[i] == self.GONE:
                self.timer[i] -= dt
                if self.timer[i] <= 0:
                    self.state[i] = self.NORMAL

    def is_gone(self, p):
        i = self.index_at(p)
        return i >= 0 and self.state[i] == self.GONE

    def safe_point(self, near):
        best, bd = None, 1e9
        for i, c in enumerate(self.cells):
            if self.state[i] == self.NORMAL:
                d = dist(c.center, near)
                if d < bd:
                    best, bd = V(c.center), d
        return best or V(480, 330)

    def reset(self):
        self.state = [0] * len(self.cells)

    def draw(self, surf, mode, t):
        for i, c in enumerate(self.cells):
            s = self.state[i]
            if s == self.WARN:
                col = ORANGE if mode == "lava" else WHITE
                if int(t * 10) % 2 == 0:
                    pygame.draw.rect(surf, col, c, 2)
                pygame.draw.line(surf, col, c.topleft, c.bottomright, 1)
                pygame.draw.line(surf, col, c.topright, c.bottomleft, 1)
            elif s == self.GONE:
                if mode == "lava":
                    pygame.draw.rect(surf, (180, 60, 20), c)
                    pygame.draw.rect(surf, ORANGE, c, 2)
                else:
                    pygame.draw.rect(surf, (4, 3, 8), c)
                    pygame.draw.rect(surf, PURPLE if mode == "void" else (90, 80, 130), c, 1)


class SecretBoss(Boss):
    thresholds = (.8, .6, .4, .2)
    boss_kind = "secret"

    def __init__(self, arena, rid, name, hp, radius, color, contact):
        super().__init__(V(480, 300), name, hp, radius, color, contact)
        self.arena = arena
        self.rid = rid
        self.boss_kind = "secret"
        self.dmg_scale = SECRET_BOSS_TUNE[rid][1]
        self.vulnerable = True
        self.apply_tune()

    def d(self, base):
        return int(base * self.dmg_scale)

    def on_phase(self, phase):
        if phase == 5:
            game.banner("PHASE V - UNDOCUMENTED", self.phase_names[4], self.color, 3.5)
            if not game.phase5_seen[self.rid]:
                game.phase5_seen[self.rid] = True
            game.shake(.6)
        else:
            super().on_phase(phase)
        self.arena.on_phase(phase)

    def shot(self, origin, angle, speed, base, color=None, radius=8, **kw):
        game.enemy_shot(origin, angle, speed, self.d(base), color or self.color, radius, **kw)


# ------------------------------------------------------------
# THE ASHEN BEHEMOTH (Ember)
# ------------------------------------------------------------

class AshenBehemoth(SecretBoss):
    phase_names = ("THE HUNT", "ERUPTION", "FOUR FLAMES", "INFERNO HUNT", "HEART OF THE MOUNTAIN")

    def __init__(self, arena):
        super().__init__(arena, EMBER_ID, "THE ASHEN BEHEMOTH", 6000, 52, EMBER, 24)
        self.volcanoes = []          # [pos, hazard, spit_timer]
        self.beam_angle = 0.0
        self.beam_on = True
        self.beam_cycle = 0.0
        self.core_open = False

    # --- vulnerability windows ---
    def damage_mult(self):
        if self.phase == 3:
            return 1.0 if not self.beam_on else .25
        if self.phase == 5:
            return 1.5 if self.core_open else .35
        return 1.0

    def add_volcano(self, scene):
        for _ in range(20):
            p = V(random.randint(120, 840), random.randint(140, 520))
            if dist(p, game.player.pos) > 160 and all(dist(p, v[0]) > 170 for v in self.volcanoes):
                break
        if len(self.volcanoes) >= 2:
            oldest = self.volcanoes.pop(0)
            oldest[1].alive = False
            if oldest[1] in scene.hazards:
                scene.hazards.remove(oldest[1])
        hz = Hazard(p, 72, 1.2, 9999, self.d(14), ORANGE, element="fire", effect="burn", tick=.5, label="ERUPTION")
        scene.hazards.append(hz)
        self.volcanoes.append([p, hz, 2.0])
        game.float_text(p, "VOLCANO ERUPTS", ORANGE, 1.2, 20)
        game.shake(.25)

    def update_volcanoes(self, dt, scene):
        for v in self.volcanoes:
            v[2] -= dt
            if v[2] <= 0 and v[1].t > v[1].warn:
                v[2] = 2.2
                off = random.random()
                for i in range(6):
                    self.shot(v[0], off + i * math.tau / 6, 170, 14, ORANGE, 8, element="fire")

    def clear_volcanoes(self, scene, keep=0):
        while len(self.volcanoes) > keep:
            v = self.volcanoes.pop(0)
            if v[1] in scene.hazards:
                scene.hazards.remove(v[1])

    def slam(self, scene, radius=115):
        scene.hazards.append(Hazard(self.pos, radius, .8, .25, self.d(26), EMBER, element="fire", label="SLAM"))
        scene.hazards.append(Hazard(self.pos, radius + 110, 1.2, .25, self.d(18), ORANGE, "ring", inner=radius + 60, element="fire"))

    def think(self, dt, scene):
        ph = self.phase
        if ph in (2, 4):
            self.update_volcanoes(dt, scene)
        if ph == 1:
            self.chase(dt, scene, 85, 60)
            if self.timer("slam", dt, 3.0):
                self.slam(scene)
            if self.timer("volley", dt, 1.6):
                base = angle_to(self.pos, game.player.pos)
                for i in range(5):
                    self.shot(self.pos, base + (i - 2) * .18, 240, 15, EMBER, 8, element="fire")
        elif ph == 2:
            self.chase(dt, scene, 70, 80)
            if self.timer("volcano", dt, 6.0):
                self.add_volcano(scene)
            if self.timer("volley", dt, 1.4):
                base = angle_to(self.pos, game.player.pos)
                for i in range(3):
                    self.shot(self.pos, base + (i - 1) * .2, 250, 16, EMBER, 8, element="fire")
            if self.timer("slam", dt, 4.5):
                self.slam(scene, 100)
        elif ph == 3:
            center = V(480, 330)
            self.pos += (center - self.pos) * min(1, dt * 2.5)
            self.beam_cycle += dt
            if self.beam_on:
                self.beam_angle += .55 * dt
                if self.beam_cycle > 6.0:
                    self.beam_on = False
                    self.beam_cycle = 0
                    game.float_text(self.pos + V(0, -70), "THE FLAMES GUTTER - STRIKE!", GREEN, 1.6, 20)
                elif self.beam_cycle > .8:
                    for k in range(4):
                        a = self.beam_angle + k * math.pi / 2
                        end = self.pos + from_angle(a, 700)
                        if point_segment_distance(game.player.pos, self.pos, end) < 20 + game.player.RADIUS and dist(game.player.pos, self.pos) > 30:
                            game.player.take_damage(self.d(30), "fire")
                            game.player.apply_burn(2)
            else:
                if self.beam_cycle > 2.6:
                    self.beam_on = True
                    self.beam_cycle = 0
            if self.timer("edgefire", dt, 1.2):
                side = random.choice(["l", "r", "t", "b"])
                origin = {"l": V(50, random.randint(100, 560)), "r": V(910, random.randint(100, 560)),
                          "t": V(random.randint(60, 900), 80), "b": V(random.randint(60, 900), 575)}[side]
                self.shot(origin, angle_to(origin, game.player.pos), 230, 15, ORANGE, 9, element="fire")
        elif ph == 4:
            self.chase(dt, scene, 135, 40)
            if self.timer("trail", dt, .35):
                scene.hazards.append(Hazard(self.pos, 36, .3, 3.5, self.d(10), ORANGE, element="fire", effect="burn"))
            if self.timer("ash", dt, 1.2):
                for _ in range(3):
                    p = game.player.pos + V(random.uniform(-150, 150), random.uniform(-150, 150))
                    scene.hazards.append(Hazard(p, 50, .9, .25, self.d(20), (140, 140, 150), label="ASH"))
            if self.timer("volcano", dt, 9.0):
                self.add_volcano(scene)
        else:  # phase 5
            center = V(480, 330)
            self.pos += (center - self.pos) * min(1, dt * 2)
            self.beam_cycle += dt
            if self.core_open and self.beam_cycle > 2.6:
                self.core_open = False
                self.beam_cycle = 0
            elif not self.core_open and self.beam_cycle > 4.5:
                self.core_open = True
                self.beam_cycle = 0
                game.float_text(self.pos + V(0, -80), "THE CORE IS EXPOSED!", GREEN, 1.5, 22)
            if self.timer("collapse", dt, 1.3):
                self.arena.floor.random_trigger(3, 1.4, 9.0, avoid=self.pos, near=game.player.pos, max_frac=.4)
            if self.timer("meteor", dt, .8):
                p = V(random.randint(80, 880), random.randint(110, 560))
                scene.hazards.append(Hazard(p, 58, 1.0, .25, self.d(24), EMBER, element="fire", effect="burn"))
            if self.timer("spiral", dt, .25):
                self.beam_angle += .45
                for k in range(3):
                    self.shot(self.pos, self.beam_angle + k * math.tau / 3, 190, 14, ORANGE, 7, element="fire")

    def draw_body(self, surf, x, y):
        r = self.radius
        y += int(math.sin(self.anim * 3) * 2)
        if self.phase == 3:
            for k in range(4):
                a = self.beam_angle + k * math.pi / 2
                end = V(x, y) + from_angle(a, 700)
                if self.beam_on and self.beam_cycle > .8:
                    pygame.draw.line(surf, ORANGE, (x, y), ipos(end), 40)
                    pygame.draw.line(surf, (255, 230, 150), (x, y), ipos(end), 12)
                elif self.beam_on:
                    pygame.draw.line(surf, ORANGE, (x, y), ipos(end), 2)
        pygame.draw.circle(surf, (60, 40, 36), (x, y), r)
        pygame.draw.circle(surf, (95, 60, 50), (x, y - 8), r - 10)
        for k in range(5):
            a = -math.pi / 2 + (k - 2) * .4
            p1 = V(x, y) + from_angle(a, r - 6)
            p2 = V(x, y) + from_angle(a, r + 22)
            pygame.draw.line(surf, (50, 35, 30), ipos(p1), ipos(p2), 8)
            pygame.draw.circle(surf, ORANGE, ipos(p2), 4)
        core_col = (255, 240, 160) if (self.phase == 5 and self.core_open) or (self.phase == 3 and not self.beam_on) else ORANGE
        glow(surf, (x, y + 6), 34, core_col, 140)
        pygame.draw.circle(surf, core_col, (x, y + 6), 14)
        pygame.draw.rect(surf, GOLD, (x - 18, y - 16, 8, 6))
        pygame.draw.rect(surf, GOLD, (x + 10, y - 16, 8, 6))


# ------------------------------------------------------------
# THE MIRROR WARDEN (Frozen)
# ------------------------------------------------------------

class FalseWarden(Enemy):
    STYLES = {"red": (RED, 900, "rush"), "blue": (BLUE, 800, "magic"), "yellow": (GOLD, 800, "ranged"), "purple": (PURPLE, 1600, "anchor")}

    def __init__(self, pos, gem, scale):
        super().__init__(pos, "guard", 1.0, None, aggro=2000)
        color, hp, style = self.STYLES[gem]
        self.gem = gem
        self.gem_color = color
        self.style = style
        self.max_hp = int(hp * (0.8 + .2 * scale))
        self.hp = self.max_hp
        self.radius = 22
        self.scale = scale
        self.damage = int(14 * scale)
        self.speed = {"rush": 120, "magic": 70, "ranged": 75, "anchor": 45}[style]
        self.drops = False
        self.dash = 0.0
        self.dash_dir = V()
        self.xp = 60

    def update(self, dt, scene):
        self.tick_status(dt)
        if not self.alive or self.freeze > 0:
            return
        p = game.player
        d = dist(self.pos, p.pos)
        to = (p.pos - self.pos).normalize() if d > 1 else V(1, 0)
        sf = self.speed_factor()
        if self.style == "rush":
            if self.dash > 0:
                self.dash -= dt
                self.pos = scene.move(self.pos, self.dash_dir * 430 * dt, self.radius)
            else:
                self.pos = scene.move(self.pos, to * self.speed * sf * dt, self.radius)
                if self.atk_cd <= 0 and d < 300:
                    self.dash = .45
                    self.dash_dir = to
                    self.atk_cd = 2.4
        elif self.style == "magic":
            if d > 260:
                self.pos = scene.move(self.pos, to * self.speed * sf * dt, self.radius)
            if self.atk_cd <= 0:
                self.atk_cd = 1.9
                for off in (-.4, 0, .4):
                    game.enemy_shot(self.pos, angle_to(self.pos, p.pos) + off, 170, int(13 * self.scale), BLUE, 9, homing=1.2, life=3.5)
        elif self.style == "ranged":
            side = V(-to.y, to.x)
            self.pos = scene.move(self.pos, (side * (1 if int(self.anim / 2) % 2 else -1) + (to if d > 320 else -to * .5)) * self.speed * sf * dt, self.radius)
            if self.atk_cd <= 0:
                self.atk_cd = .55
                game.enemy_shot(self.pos, angle_to(self.pos, p.pos), 340, int(10 * self.scale), GOLD, 5, kind="shard")
        else:
            self.pos = scene.move(self.pos, to * self.speed * sf * dt, self.radius)
            if self.atk_cd <= 0:
                self.atk_cd = 3.2
                scene.hazards.append(Hazard(self.pos, 150, .9, .25, int(20 * self.scale), PURPLE, "ring", inner=60))
        if d < self.radius + p.RADIUS + 4 and self.contact_cd <= 0:
            p.take_damage(self.damage)
            self.contact_cd = 1.0

    def draw(self, surf, cam):
        x, y = ipos(self.pos - cam)
        y += int(math.sin(self.anim * 3) * 2)
        pygame.draw.ellipse(surf, (0, 0, 0), (x - 20, y + 18, 40, 10))
        pygame.draw.polygon(surf, (120, 170, 200), [(x, y - 30), (x + 20, y - 8), (x + 15, y + 22), (x - 15, y + 22), (x - 20, y - 8)])
        pygame.draw.polygon(surf, (200, 235, 250), [(x, y - 30), (x + 20, y - 8), (x + 15, y + 22), (x - 15, y + 22), (x - 20, y - 8)], 2)
        glow(surf, (x, y - 6), 20, self.gem_color, 140)
        pygame.draw.polygon(surf, self.gem_color, [(x, y - 14), (x + 6, y - 6), (x, y + 2), (x - 6, y - 6)])
        if self.flash > 0:
            pygame.draw.circle(surf, WHITE, (x, y), 26, 2)
        if self.freeze > 0:
            pygame.draw.circle(surf, ICE, (x, y), 28, 2)
        w = 50
        pygame.draw.rect(surf, (20, 20, 24), (x - w // 2, y - 46, w, 6))
        pygame.draw.rect(surf, self.gem_color, (x - w // 2 + 1, y - 45, int((w - 2) * max(0, self.hp) / self.max_hp), 4))


class MirrorPane:
    """Breakable mirror used by the Mirror Realm phase."""
    is_boss = False

    def __init__(self, pos):
        self.pos = V(pos)
        self.radius = 18
        self.hp = 140
        self.alive = True
        self.flash = 0

    def take_damage(self, amount, effect=None, knock=None):
        if not self.alive:
            return
        self.hp -= amount
        self.flash = .1
        if self.hp <= 0:
            self.alive = False
            burst(self.pos, ICE, 24, (60, 200), .6, 3)
            game.scene.hazards.append(Hazard(self.pos, 46, .2, 3.0, 10, ICE, label=None))

    def apply_effect(self, effect, power=1.0):
        pass

    def draw(self, surf, cam):
        x, y = ipos(self.pos - cam)
        self.flash = max(0, self.flash - 1 / 60)
        pygame.draw.rect(surf, (150, 210, 240), (x - 14, y - 24, 28, 48))
        pygame.draw.rect(surf, WHITE if self.flash <= 0 else RED, (x - 14, y - 24, 28, 48), 2)
        pygame.draw.line(surf, WHITE, (x - 8, y - 16), (x + 4, y - 4), 1)


class MirrorCopy(Enemy):
    """Reflection of the Warden: stands opposite the player and fires."""

    def __init__(self, pos, scale, mirror_axis):
        super().__init__(pos, "mage", 1.0, ICE, aggro=2000)
        self.max_hp = self.hp = int(260 * scale)
        self.radius = 20
        self.axis = mirror_axis
        self.drops = False
        self.scale = scale
        self.xp = 20

    def update(self, dt, scene):
        self.tick_status(dt)
        if not self.alive or self.freeze > 0:
            return
        p = game.player.pos
        c = V(480, 330)
        target = V(2 * c.x - p.x, p.y) if self.axis == "x" else V(p.x, 2 * c.y - p.y) if self.axis == "y" else 2 * c - p
        d = target - self.pos
        if d.length() > 4:
            self.pos = scene.move(self.pos, d.normalize() * min(d.length(), 160 * dt), self.radius)
        if self.atk_cd <= 0:
            self.atk_cd = 1.6
            game.enemy_shot(self.pos, angle_to(self.pos, p), 260, int(12 * self.scale), ICE, 6, kind="shard")

    def draw(self, surf, cam):
        x, y = ipos(self.pos - cam)
        alpha_circle(surf, (x, y), 24, ICE, 90)
        pygame.draw.polygon(surf, (170, 220, 245), [(x, y - 26), (x + 16, y - 6), (x + 12, y + 20), (x - 12, y + 20), (x - 16, y - 6)], 2)
        if self.flash > 0:
            pygame.draw.circle(surf, WHITE, (x, y), 24, 2)


class MirrorWarden(SecretBoss):
    phase_names = ("FOUR REFLECTIONS", "THE TRUE WARDEN - ICE STORM", "MIRROR REALM", "FROZEN ARENA", "SHATTERED REFLECTION")

    def __init__(self, arena):
        super().__init__(arena, FROZEN_ID, "THE MIRROR WARDEN", 6500, 40, ICE, 24)
        self.revealed = False
        self.rise = 0.0
        self.reflections = []
        self.mirrors = []
        self.copies = []
        self.charge = None

    def start_reflections(self, scene):
        for gem, p in (("red", (250, 200)), ("blue", (710, 200)), ("yellow", (250, 470)), ("purple", (710, 470))):
            self.reflections.append(scene.add_enemy(FalseWarden(V(p), gem, self.dmg_scale)))

    def compute_phase(self):
        if not self.revealed:
            return 1
        r = self.ratio()
        return 2 + sum(1 for th in (.75, .5, .25) if r <= th)

    def damage_mult(self):
        if not self.revealed or self.rise > 0:
            return 0.0
        if self.phase == 3 and sum(1 for m in self.mirrors if m.alive) >= 3:
            return .5
        return 1.0

    def take_damage(self, amount, effect=None, knock=None):
        if not self.revealed or self.rise > 0:
            return
        super().take_damage(amount, effect, knock)

    def update(self, dt, scene):
        if not self.revealed:
            self.anim += dt
            if not self.reflections:
                self.start_reflections(scene)
            if all(not r.alive for r in self.reflections):
                self.revealed = True
                self.rise = 2.2
                self.phase = 2
                self.timers.clear()
                game.banner("YOU THOUGHT IT'D BE THAT EASY?", "The true Mirror Warden rises from the ice", ICE, 3.5)
                game.shake(.5)
                self.arena.on_phase(2)
            return
        if self.rise > 0:
            self.rise -= dt
            self.anim += dt
            return
        super().update(dt, scene)

    def teleport(self, scene, near_player=True):
        for _ in range(20):
            p = (game.player.pos + from_angle(random.random() * math.tau, random.uniform(180, 300))) if near_player else V(random.randint(120, 840), random.randint(140, 520))
            if scene.play.inflate(-80, -80).collidepoint(p) and not scene.blocked(p, self.radius):
                burst(self.pos, ICE, 16, (60, 160), .4, 3)
                self.pos = p
                burst(p, ICE, 16, (60, 160), .4, 3)
                return

    def think(self, dt, scene):
        ph = self.phase
        p = game.player
        if self.charge is not None:
            self.charge[1] -= dt
            if self.charge[1] <= 0:
                self.pos = scene.move(self.pos, self.charge[0] * 520 * dt, self.radius)
                if self.charge[1] < -.5:
                    self.charge = None
            return
        if ph == 2:
            self.chase(dt, scene, 60, 220)
            if self.timer("fan", dt, 1.1):
                base = angle_to(self.pos, p.pos)
                for i in range(7):
                    self.shot(self.pos, base + (i - 3) * .14, 270, 15, ICE, 7, kind="shard")
            if self.timer("spikes", dt, 3.2):
                scene.hazards.append(Hazard(p.pos, 60, .9, .25, self.d(20), ICE, effect="freeze", label="SPIKE"))
                scene.hazards.append(Hazard(self.pos, 220, 1.3, .25, self.d(16), BLUE, "ring", inner=170))
            if self.timer("orb", dt, 2.6):
                self.shot(self.pos, angle_to(self.pos, p.pos), 150, 18, BLUE, 12, effect="freeze", homing=1.0, life=4.0)
        elif ph == 3:
            self.mirrors = [m for m in self.mirrors if m.alive]
            if self.timer("mirrors", dt, 10.0):
                for _ in range(6 - len(self.mirrors)):
                    self.mirrors.append(MirrorPane(scene.find_free(V(random.randint(120, 840), random.randint(140, 520)), 20)))
                self.copies = [c for c in self.copies if c.alive]
                for axis in ("x", "y")[:2 - len(self.copies)]:
                    self.copies.append(scene.add_enemy(MirrorCopy(V(480, 330), self.dmg_scale, axis)))
            if self.timer("reflect", dt, 2.2):
                for m in self.mirrors:
                    if m.alive:
                        self.shot(m.pos, angle_to(m.pos, p.pos), 230, 14, ICE, 6, kind="shard")
            if self.timer("hop", dt, 4.0):
                self.teleport(scene)
            if self.timer("fan", dt, 1.8):
                base = angle_to(self.pos, p.pos)
                for i in range(5):
                    self.shot(self.pos, base + (i - 2) * .2, 250, 14, ICE, 7, kind="shard")
        elif ph == 4:
            p.on_ice = True
            if self.timer("walls", dt, 7.0):
                self.arena.raise_ice_walls()
            self.chase(dt, scene, 70, 150)
            if self.timer("charge", dt, 3.0):
                direction = (p.pos - self.pos).normalize() if dist(p.pos, self.pos) > 1 else V(1, 0)
                scene.hazards.append(Hazard(self.pos, 0, .7, .01, 0, RED, "line", end=self.pos + direction * 420, width=self.radius * 2))
                self.charge = [direction, .7]
            if self.timer("ring", dt, 2.4):
                for i in range(14):
                    self.shot(self.pos, i * math.tau / 14 + self.anim, 180, 15, ICE, 8, effect="slow")
        else:
            p.on_ice = True
            self.copies = [c for c in self.copies if c.alive]
            if self.timer("copies", dt, 8.0):
                for axis in ("x", "y", "xy")[:3 - len(self.copies)]:
                    self.copies.append(scene.add_enemy(MirrorCopy(V(480, 330), self.dmg_scale * 1.2, axis)))
            if self.timer("crack", dt, 2.0):
                self.arena.floor.random_trigger(3, 1.2, 5.0, near=p.pos, max_frac=.35)
            if self.timer("blink", dt, random.choice((1.6, 2.4, 3.2))):
                self.teleport(scene, random.random() < .6)
                choice = random.randint(0, 3)
                base = angle_to(self.pos, p.pos)
                if choice == 0:
                    for i in range(9):
                        self.shot(self.pos, base + (i - 4) * .12, 290, 17, ICE, 7, kind="shard")
                elif choice == 1:
                    scene.hazards.append(Hazard(p.pos, 80, .7, .25, self.d(24), ICE, effect="freeze"))
                elif choice == 2:
                    for i in range(16):
                        self.shot(self.pos, i * math.tau / 16, 200, 15, BLUE, 8)
                else:
                    self.shot(self.pos, base, 160, 22, BLUE, 13, homing=1.4, effect="freeze", life=4)

    def extra_targets(self):
        return [m for m in self.mirrors if m.alive]

    def draw(self, surf, cam):
        if not self.revealed:
            x, y = 480, 330
            alpha_circle(surf, (x, y), 46, ICE, 50 + 30 * math.sin(self.anim * 2))
            draw_text(surf, "something waits beneath the ice...", (x, y + 50), mix(ICE, BLACK, .4), 16, center=True)
            return
        for m in self.mirrors:
            if m.alive:
                m.draw(surf, cam)
        if self.rise > 0:
            x, y = ipos(self.pos - cam)
            alpha_circle(surf, (x, y), self.radius * (2.2 - self.rise * .5), ICE, 110)
        super().draw(surf, cam)

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 2) * 3)
        glow(surf, (x, y), 60, ICE, 90)
        pygame.draw.polygon(surf, (90, 150, 190), [(x, y - 50), (x + 32, y - 14), (x + 24, y + 34), (x - 24, y + 34), (x - 32, y - 14)])
        pygame.draw.polygon(surf, WHITE, [(x, y - 50), (x + 32, y - 14), (x + 24, y + 34), (x - 24, y + 34), (x - 32, y - 14)], 3)
        pygame.draw.polygon(surf, ICE, [(x, y - 20), (x + 10, y - 6), (x, y + 8), (x - 10, y - 6)])
        pygame.draw.circle(surf, WHITE, (x, y - 6), 4)
        for k in (-1, 1):
            pygame.draw.polygon(surf, (190, 230, 250), [(x + k * 30, y - 30), (x + k * 50, y - 60), (x + k * 40, y - 20)])


# ------------------------------------------------------------
# THE NULL MAW (Void)
# ------------------------------------------------------------

class NullMaw(SecretBoss):
    phase_names = ("VOID WELLS", "THE VANISHING WORLD", "THE TELEPORTER", "BLACK HOLE COLLAPSE", "EVENT HORIZON")

    def __init__(self, arena):
        super().__init__(arena, VOID_ID, "THE NULL MAW", 8000, 48, PURPLE, 28)
        self.wells = [V(220, 200), V(740, 200), V(220, 470), V(740, 470)]
        self.portals = []        # [pos, life, fire_timer]
        self.holes = []          # [pos, life]
        self.tp_timer = 5.0
        self.spin = 0.0

    def damage_mult(self):
        return .6 if self.phase == 4 else 1.0

    def apply_wells(self, dt, scene, strength=130):
        p = game.player
        for w in self.wells:
            d = w - p.pos
            L = d.length()
            if 10 < L < 210 and not (p.has_relic("nullcompass") and p.dash_time > 0):
                p.external += d.normalize() * strength * (1 - L / 230)
            if L < 28:
                p.take_damage(self.d(14))

    def strategic_spot(self, scene):
        """Pick a teleport destination that makes the next attack awkward: at mid range,
        behind the player's direction of travel, with a clear line of fire."""
        p = game.player
        moving = p.vel.normalize() if p.vel.length() > 20 else V(p.facing)
        best, best_score = None, -1e9
        for _ in range(28):
            cand = p.pos + from_angle(random.random() * math.tau, random.uniform(200, 320))
            if not scene.play.inflate(-70, -70).collidepoint(cand) or scene.blocked(cand, self.radius):
                continue
            if self.arena.floor.is_gone(cand):
                continue
            to_cand = (cand - p.pos).normalize()
            score = -to_cand.dot(moving) * 2.0            # behind the player
            score -= abs(dist(cand, p.pos) - 260) / 100.0  # preferred range
            score += min(dist(cand, self.pos), 400) / 400  # surprising: far from the old spot
            if score > best_score:
                best, best_score = cand, score
        return best

    def teleport_strike(self, scene):
        spot = self.strategic_spot(scene)
        if spot is None:
            return
        burst(self.pos, PURPLE, 24, (60, 200), .5, 3)
        self.pos = spot
        burst(spot, PURPLE, 24, (60, 200), .5, 3)
        game.float_text(spot, "THE NULL MAW SHIFTS", PURPLE)
        p = game.player
        predicted = p.pos + p.vel * .5
        base = angle_to(self.pos, predicted)
        for off in (0, math.pi / 2):
            a = base + off
            scene.hazards.append(Hazard(self.pos - from_angle(a, 600), 0, .65, .25, self.d(30), PURPLE, "line",
                                        end=self.pos + from_angle(a, 600), width=34))
        for i in range(10):
            self.shot(self.pos, i * math.tau / 10 + .3, 200, 16, PURPLE, 8)

    def spawn_hole(self, scene, life=5.0):
        for _ in range(20):
            p = V(random.randint(130, 830), random.randint(150, 510))
            if dist(p, game.player.pos) > 220:
                self.holes.append([p, life])
                game.float_text(p, "BLACK HOLE", PURPLE, 1.2, 20)
                return

    def update_holes(self, dt):
        p = game.player
        for h in self.holes:
            h[1] -= dt
            d = h[0] - p.pos
            L = d.length()
            if L < 260 and L > 0:
                p.external += d.normalize() * 175 * (1 - L / 290) ** .7
            if L < 22 and h[1] > 0:
                h[1] = 0
                p.instant_defeat("Pulled into a black hole")
        self.holes = [h for h in self.holes if h[1] > 0]

    def update_portals(self, dt, scene, rate=1.6):
        for pt in self.portals:
            pt[1] -= dt
            pt[2] -= dt
            if pt[2] <= 0:
                pt[2] = rate
                self.shot(pt[0], angle_to(pt[0], game.player.pos), 240, 16, (200, 120, 255), 8)
        self.portals = [pt for pt in self.portals if pt[1] > 0]

    def think(self, dt, scene):
        ph = self.phase
        p = game.player
        self.spin += dt
        if ph in (1, 5):
            self.apply_wells(dt, scene, 130 if ph == 1 else 100)
        if ph in (2, 5):
            if self.timer("vanish", dt, 2.2 if ph == 2 else 2.8):
                self.arena.floor.random_trigger(4 if ph == 2 else 3, 1.2, 4.0, near=p.pos, max_frac=.4)
            if self.timer("portal", dt, 3.5 if ph == 2 else 4.5):
                self.portals.append([V(random.randint(100, 860), random.randint(120, 540)), 6.0, 1.0])
            self.update_portals(dt, scene)
        if ph in (4, 5):
            if self.timer("hole", dt, 4.0 if ph == 4 else 6.0):
                self.spawn_hole(scene, 5.0 if ph == 4 else 4.0)
        self.update_holes(dt)
        if ph == 1:
            self.chase(dt, scene, 45, 200)
            if self.timer("orbs", dt, 1.5):
                self.shot(self.pos, angle_to(self.pos, p.pos), 170, 18, PURPLE, 11, homing=.9, life=4)
            if self.timer("burst", dt, 2.6):
                for i in range(8):
                    self.shot(self.pos, i * math.tau / 8 + self.spin, 190, 15, PURPLE, 8)
        elif ph == 2:
            self.chase(dt, scene, 50, 200)
            if self.timer("emerge", dt, 6.0) and self.portals:
                self.pos = V(random.choice(self.portals)[0])
                burst(self.pos, PURPLE, 20, (50, 160), .5, 3)
            if self.timer("burst", dt, 1.8):
                for i in range(10):
                    self.shot(self.pos, i * math.tau / 10 + self.spin, 200, 15, PURPLE, 8)
        elif ph == 3:
            if self.timer("tp", dt, 5.0):
                self.teleport_strike(scene)
            if self.timer("aim", dt, 1.0):
                base = angle_to(self.pos, p.pos)
                for off in (-.15, 0, .15):
                    self.shot(self.pos, base + off, 280, 15, PURPLE, 7)
        elif ph == 4:
            self.chase(dt, scene, 40, 220)
            if self.timer("aim", dt, 1.3):
                self.shot(self.pos, angle_to(self.pos, p.pos), 230, 18, PURPLE, 10, homing=.7)
            if self.timer("burst", dt, 3.0):
                for i in range(12):
                    self.shot(self.pos, i * math.tau / 12, 170, 15, PURPLE, 8)
        else:
            if self.timer("tp", dt, 4.0):
                self.teleport_strike(scene)
            if self.timer("spiral", dt, .3):
                for k in range(2):
                    self.shot(self.pos, self.spin * 2.2 + k * math.pi, 190, 14, PURPLE, 7)

    def draw_underlay(self, surf):
        ph = self.phase
        if ph in (1, 5):
            for w in self.wells:
                for k in range(3):
                    rr = int(210 - ((self.time_offset() * 70 + k * 70) % 210))
                    pygame.draw.circle(surf, (70, 35, 105), ipos(w), max(4, rr), 1)
                pygame.draw.circle(surf, (4, 2, 10), ipos(w), 26)
                pygame.draw.circle(surf, PURPLE, ipos(w), 26, 3)
        for pt in self.portals:
            draw_portal(surf, pt[0], (200, 120, 255), self.spin, None, 20)
        for h in self.holes:
            pos = h[0]
            for k in range(4):
                rr = int(260 - ((self.spin * 120 + k * 65) % 260))
                pygame.draw.circle(surf, (60, 20, 90), ipos(pos), max(6, rr), 1)
            pygame.draw.circle(surf, (0, 0, 0), ipos(pos), 34)
            pygame.draw.circle(surf, (255, 200, 255), ipos(pos), 34, 2)
            pygame.draw.circle(surf, RED, ipos(pos), 22, 1)

    def time_offset(self):
        return self.spin

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 2) * 4)
        glow(surf, (x, y), 80, PURPLE, 90)
        pygame.draw.circle(surf, (20, 10, 30), (x, y), self.radius)
        for k in range(10):
            a = self.spin * 1.5 + k * math.tau / 10
            p1 = V(x, y) + from_angle(a, self.radius - 4)
            p2 = V(x, y) + from_angle(a + .25, self.radius + 16)
            pygame.draw.line(surf, PURPLE, ipos(p1), ipos(p2), 4)
        pygame.draw.circle(surf, (0, 0, 0), (x, y), self.radius - 14)
        pygame.draw.circle(surf, (230, 200, 255), (x, y), self.radius - 14, 2)
        for k in range(6):
            a = -self.spin + k * math.tau / 6
            pygame.draw.circle(surf, WHITE, ipos(V(x, y) + from_angle(a, self.radius - 22)), 3)


# ------------------------------------------------------------
# THE ASTRAL CLOCKWORK (Starfall)
# ------------------------------------------------------------

CLOCK_CENTER = V(480, 330)
CLOCK_LAYOUTS = {
    "A": [(-300, -170, 120, 26), (180, -170, 120, 26), (-300, 144, 120, 26), (180, 144, 120, 26)],
    "B": [(-260, -200, 26, 150), (-120, -80, 240, 26), (234, 50, 26, 150), (-120, 54, 26, 140), (94, -194, 26, 140), (-330, 60, 140, 26)],
}


def rotate_rect90(rect_tuple, k):
    """Rotate a rect given relative to the clock centre by k * 90 degrees (discrete)."""
    x, y, w, h = rect_tuple
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    for _ in range(k % 4):
        corners = [(-cy, cx) for cx, cy in corners]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return R(int(CLOCK_CENTER.x + min(xs)), int(CLOCK_CENTER.y + min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))


class AstralClockwork(SecretBoss):
    phase_names = ("CLOCKWORK DUEL", "GEOMETRY SHIFT", "STARFALL", "CLOCKWORK ECLIPSE", "FALLING SKY")

    def __init__(self, arena):
        super().__init__(arena, STARFALL_ID, "THE ASTRAL CLOCKWORK", 9500, 46, GOLD, 26)
        self.hand_angle = 0.0
        self.shift_count = 0
        self.stars = []   # visual falling stars attached to hazards
        self.eclipse = []  # [radius, gap_angle, speed]

    def think(self, dt, scene):
        ph = self.phase
        p = game.player
        arena = self.arena
        self.pos += (CLOCK_CENTER + V(math.sin(self.anim * .5) * 60, math.cos(self.anim * .35) * 30) - self.pos) * min(1, dt * 1.5)
        if ph in (1, 2, 4) and self.timer("tick", dt, 1.0 if ph == 1 else .8):
            # Clock hands tick in discrete steps rather than sweeping continuously.
            self.hand_angle += math.radians(30)
            for k in (0, math.pi):
                a = self.hand_angle + k
                scene.hazards.append(Hazard(self.pos, 0, .45, .5, self.d(20), GOLD, "line", end=self.pos + from_angle(a, 330), width=22))
        if ph >= 2 and ph <= 4:
            period = {2: 6.0, 3: 7.0, 4: 5.0}[ph]
            if self.timer("shift", dt, period):
                self.shift_count += 1
                step = -1 if (ph == 4 and self.shift_count % 3 == 0) else 1
                arena.schedule_rotation(step, 1.5, "REWIND" if step < 0 else "ARENA SHIFT")
        if ph == 1:
            if self.timer("rings", dt, 3.2):
                for i in range(3):
                    scene.hazards.append(Hazard(self.pos, 110 + i * 90, .7 + i * .4, .25, self.d(16), GOLD, "ring", inner=80 + i * 90))
            if self.timer("volley", dt, 1.3):
                base = angle_to(self.pos, p.pos)
                for i in range(4):
                    self.shot(self.pos, base + (i - 1.5) * .17, 260, 15, GOLD, 7)
        elif ph == 2:
            if self.timer("volley", dt, 1.1):
                base = angle_to(self.pos, p.pos)
                for i in range(6):
                    self.shot(self.pos, base + (i - 2.5) * .16, 260, 15, GOLD, 7)
        elif ph == 3:
            if self.timer("star", dt, 1.3):
                for _ in range(2):
                    target = p.pos + V(random.uniform(-160, 160), random.uniform(-120, 120))
                    target.x = clamp(target.x, 70, 890)
                    target.y = clamp(target.y, 100, 560)
                    hz = Hazard(target, 92, 1.5, .3, self.d(34), GOLD, label="STAR")
                    scene.hazards.append(hz)
                    self.stars.append(hz)
            if self.timer("aim", dt, 1.6):
                self.shot(self.pos, angle_to(self.pos, p.pos), 300, 16, WHITE, 8)
        elif ph == 4:
            if self.timer("eclipse", dt, 2.6):
                self.eclipse.append([60.0, random.random() * math.tau, 120.0])
            if self.timer("volley", dt, 1.4):
                for i in range(8):
                    self.shot(self.pos, i * math.tau / 8 + self.anim, 200, 14, GOLD, 7)
        else:
            if self.timer("platforms", dt, 3.0):
                arena.shift_platforms()
            if self.timer("star", dt, .9):
                target = p.pos + V(random.uniform(-200, 200), random.uniform(-140, 140))
                hz = Hazard(target, 80, 1.2, .3, self.d(32), GOLD)
                scene.hazards.append(hz)
                self.stars.append(hz)
            if self.timer("spiral", dt, .22):
                self.hand_angle += .4
                for k in range(3):
                    self.shot(self.pos, self.hand_angle + k * math.tau / 3, 200, 15, GOLD, 7)
        # eclipse rings: expanding annuli with two safe gaps
        for e in self.eclipse:
            e[0] += e[2] * dt
            d = dist(p.pos, CLOCK_CENTER)
            if abs(d - e[0]) < 14:
                a = angle_to(CLOCK_CENTER, p.pos)
                if angle_diff(a, e[1]) > .35 and angle_diff(a, e[1] + math.pi) > .35:
                    p.take_damage(self.d(24))
        self.eclipse = [e for e in self.eclipse if e[0] < 620]
        self.stars = [s for s in self.stars if s.alive]

    def draw_underlay(self, surf):
        for e in self.eclipse:
            r = int(e[0])
            for seg in range(48):
                a0 = seg * math.tau / 48
                mid = a0 + math.tau / 96
                if angle_diff(mid, e[1]) < .35 or angle_diff(mid, e[1] + math.pi) < .35:
                    continue
                p1 = CLOCK_CENTER + from_angle(a0, r)
                p2 = CLOCK_CENTER + from_angle(a0 + math.tau / 48, r)
                pygame.draw.line(surf, GOLD, ipos(p1), ipos(p2), 8)
        for hz in self.stars:
            if hz.t < hz.warn:
                frac = hz.t / hz.warn
                sp = V(hz.pos.x + 200 * (1 - frac), hz.pos.y - 420 * (1 - frac))
                glow(surf, sp, 30, GOLD, 160)
                pygame.draw.circle(surf, WHITE, ipos(sp), 9)
                pygame.draw.line(surf, GOLD, ipos(sp), ipos(sp + V(60, -120)), 3)

    def draw_body(self, surf, x, y):
        glow(surf, (x, y), 70, GOLD, 80)
        pygame.draw.circle(surf, (40, 34, 70), (x, y), self.radius)
        pygame.draw.circle(surf, GOLD, (x, y), self.radius, 4)
        for k in range(12):
            a = k * math.tau / 12
            pygame.draw.line(surf, GOLD, ipos(V(x, y) + from_angle(a, self.radius - 10)), ipos(V(x, y) + from_angle(a, self.radius - 2)), 2)
        pygame.draw.line(surf, WHITE, (x, y), ipos(V(x, y) + from_angle(self.hand_angle, self.radius - 8)), 4)
        pygame.draw.line(surf, WHITE, (x, y), ipos(V(x, y) + from_angle(self.hand_angle / 12, self.radius - 18)), 6)
        pygame.draw.circle(surf, WHITE, (x, y), 6)


# ------------------------------------------------------------
# SECRET BOSS ARENA
# ------------------------------------------------------------

SECRET_BOSS_CLASSES = {EMBER_ID: AshenBehemoth, FROZEN_ID: MirrorWarden, VOID_ID: NullMaw, STARFALL_ID: AstralClockwork}
SECRET_GOLD = {EMBER_ID: 1500, FROZEN_ID: 2000, VOID_ID: 2500, STARFALL_ID: 3000}


class SecretBossArena(Arena):
    def __init__(self, rid):
        super().__init__(R(40, 70, 880, 515))
        self.rid = rid
        self.key = f"secret{rid}"
        self.title = "OPTIONAL BOSS: " + REALM_INFO[rid]["secret_boss"]
        self.accent = REALM_COLORS[rid]
        self.floor = FloorGrid(self.play, 80)
        self.floor_mode = "lava" if rid == EMBER_ID else "void" if rid == VOID_ID else "sky"
        self.ice_walls = []
        self.ice_timer = 0
        self.rotation = 0
        self.pending_rotation = None   # [step, timer, label]
        self.layout = "A"
        self.platforms = None
        self.boss = SECRET_BOSS_CLASSES[rid](self)
        self.enemies = [self.boss]
        self.update_walls()
        self.interactables = [
            Interactable(V(480, 565), lambda: "Leave the arena" if not self.boss.alive else "The way out is sealed",
                         self.leave, 56, draw_fn=lambda s, p, it: draw_portal(s, p, GREEN if not self.boss.alive else ASH, self.time, "EXIT", 22, not self.boss.alive)),
        ]

    def spawn(self):
        return V(480, 540)

    def leave(self):
        if self.boss.alive:
            game.float_text(game.player.pos, "The way out is sealed. Win, or fall.", RED)
            return
        game.go_realm(self.rid, at="secret")

    def extra_targets(self):
        return self.boss.extra_targets() if hasattr(self.boss, "extra_targets") else []

    def targets(self):
        out = []
        for e in self.enemies:
            if not e.alive:
                continue
            if isinstance(e, MirrorWarden) and (not e.revealed or e.rise > 0):
                continue
            out.append(e)
        return out + self.extra_targets()

    # ---- geometry ----
    def update_walls(self):
        walls = []
        if self.rid == STARFALL_ID and self.boss.phase < 5:
            walls = [rotate_rect90(r, self.rotation) for r in CLOCK_LAYOUTS[self.layout]]
        self.walls = walls + self.ice_walls

    def is_solid(self, p):
        return super().is_solid(p)

    def schedule_rotation(self, step, warn, label):
        if self.pending_rotation is None:
            self.pending_rotation = [step, warn, label]
            game.banner(label, "The arena turns 90 degrees", GOLD, 1.4)

    def raise_ice_walls(self):
        self.ice_walls = []
        for _ in range(3):
            for _try in range(12):
                horiz = random.random() < .5
                w = R(random.randint(120, 760), random.randint(140, 480), 150 if horiz else 26, 26 if horiz else 150)
                if not w.inflate(70, 70).collidepoint(game.player.pos) and not w.inflate(50, 50).collidepoint(self.boss.pos):
                    self.ice_walls.append(w)
                    break
        self.ice_timer = 5.0
        self.update_walls()

    def shift_platforms(self):
        # Falling Sky: the floor is open sky except for drifting platforms that jump to new spots.
        if self.platforms is None:
            return
        n = len(self.floor.cells)
        keep = set(random.sample(range(n), max(10, int(n * .5))))
        keep.add(self.floor.index_at(self.boss.pos))
        for i in range(n):
            if i in keep:
                self.floor.state[i] = FloorGrid.NORMAL
            elif self.floor.state[i] == FloorGrid.NORMAL:
                self.floor.trigger(i, 1.2, 99)
        game.float_text(V(480, 120), "THE SKY SHIFTS", GOLD, 1.0, 22)

    def on_phase(self, phase):
        game.clear_enemy_projectiles()
        if self.rid == STARFALL_ID:
            if phase == 2:
                self.layout = "B"
            if phase == 5:
                self.platforms = True
                self.floor.reset()
                self.shift_platforms()
            self.update_walls()
        if self.rid == EMBER_ID and phase == 3 and hasattr(self.boss, "clear_volcanoes"):
            self.boss.clear_volcanoes(self, 0)
        if self.rid == EMBER_ID and phase == 4 and hasattr(self.boss, "clear_volcanoes"):
            self.boss.clear_volcanoes(self, 0)
        if self.rid == VOID_ID and phase in (3, 4):
            self.floor.reset()
            self.boss.portals = []
        if self.rid == FROZEN_ID and phase == 5:
            self.ice_walls = []
            self.update_walls()

    def update(self, dt):
        super().update(dt)
        self.floor.update(dt)
        if self.ice_walls:
            self.ice_timer -= dt
            if self.ice_timer <= 0:
                self.ice_walls = []
                self.update_walls()
        if self.pending_rotation is not None:
            self.pending_rotation[1] -= dt
            if self.pending_rotation[1] <= 0:
                self.rotation = (self.rotation + self.pending_rotation[0]) % 4
                self.pending_rotation = None
                self.update_walls()
                p = game.player
                if self.blocked(p.pos, p.RADIUS):
                    p.pos = self.find_free(p.pos, p.RADIUS)
                game.shake(.3)
        p = game.player
        if self.boss.alive and p.dash_time <= 0 and self.floor.is_gone(p.pos):
            if self.floor_mode == "lava":
                if not p.has_relic("cinderheart"):
                    p.take_damage(self.boss.d(12), "fire")
                    p.apply_burn(2)
            else:
                safe = self.floor.safe_point(p.pos)
                p.pos = V(safe)
                p.take_damage(self.boss.d(24), ignore_invuln=True)
                p.invuln = 1.0
                game.float_text(p.pos, "YOU FELL!", RED, 1.2, 22)
        if not self.boss.alive and self.floor.gone_fraction() > 0:
            self.floor.reset()

    def objective(self):
        b = self.boss
        if not b.alive:
            return "The relic is yours. Leave through the exit.", V(480, 565)
        if isinstance(b, MirrorWarden) and not b.revealed:
            return "Shatter the four false Wardens", None
        if isinstance(b, AshenBehemoth) and b.phase == 3:
            return "Dodge the four flames - strike while they gutter", None
        if isinstance(b, AshenBehemoth) and b.phase == 5:
            return "Survive the collapse - hit the exposed core", None
        if isinstance(b, NullMaw) and b.phase == 4:
            return "Black holes are lethal at the centre - keep moving", None
        return f"Defeat {b.name.title()}", None

    # ---- drawing ----
    def draw_ground(self, surf, cam):
        bg = [(55, 23, 17), (24, 48, 70), (52, 46, 90), (10, 9, 25)][self.rid]
        line = [(85, 38, 26), (70, 120, 160), (100, 90, 150), (40, 26, 70)][self.rid]
        if self.rid == STARFALL_ID and self.boss.phase >= 5:
            surf.fill((6, 6, 18))
            for i in range(60):
                pygame.draw.circle(surf, WHITE, ((i * 137) % 960, (i * 71) % 640), 1)
            for i, c in enumerate(self.floor.cells):
                if self.floor.state[i] != FloorGrid.GONE:
                    pygame.draw.rect(surf, (80, 72, 120), c.inflate(-4, -4))
                    pygame.draw.rect(surf, GOLD, c.inflate(-4, -4), 1)
                    if self.floor.state[i] == FloorGrid.WARN and int(self.time * 10) % 2 == 0:
                        pygame.draw.rect(surf, RED, c.inflate(-4, -4), 2)
        else:
            self.draw_floor(surf, bg, line)
            self.floor.draw(surf, self.floor_mode, self.time)
        if self.rid == FROZEN_ID and self.boss.alive and self.boss.phase >= 4:
            alpha_rect(surf, self.play, (210, 235, 255), 45)
        if self.rid == STARFALL_ID:
            cx, cy = ipos(CLOCK_CENTER)
            pygame.draw.circle(surf, (110, 100, 160), (cx, cy), 230, 1)
            for k in range(12):
                a = k * math.tau / 12 + self.rotation * math.pi / 2
                pygame.draw.line(surf, (120, 108, 170), ipos(CLOCK_CENTER + from_angle(a, 215)), ipos(CLOCK_CENTER + from_angle(a, 240)), 3)
            if self.pending_rotation is not None:
                ghost_rot = (self.rotation + self.pending_rotation[0]) % 4
                for r in CLOCK_LAYOUTS[self.layout]:
                    pygame.draw.rect(surf, RED, rotate_rect90(r, ghost_rot), 2)
                draw_text(surf, f"{self.pending_rotation[2]} IN {self.pending_rotation[1]:.1f}", (480, 100), GOLD, 22, center=True)
        wall_fill = [(70, 35, 28), (140, 190, 220), (110, 100, 160), (40, 30, 70)][self.rid]
        for w in self.walls:
            pygame.draw.rect(surf, wall_fill, w)
            pygame.draw.rect(surf, WHITE if w in self.ice_walls else self.accent, w, 2)
        if hasattr(self.boss, "draw_underlay"):
            self.boss.draw_underlay(surf)



# ============================================================
# TREASURE GROVES (unlocked by a realm's treasure map)
# ============================================================

class TreasureWorld(Arena):
    """Three generated ordering riddles guard the treasure.  Wrong touches wake the grove."""
    allow_escape = True
    ANCHORS = {4: [(260, 320), (700, 320), (260, 460), (700, 460)],
               5: [(210, 320), (480, 300), (750, 320), (300, 460), (660, 460)],
               6: [(210, 310), (480, 295), (750, 310), (210, 460), (480, 470), (750, 460)]}

    def __init__(self, rid):
        super().__init__(R(40, 70, 880, 515))
        self.rid = rid
        self.key = f"treasure{rid}"
        self.title = REALM_INFO[rid]["treasure"]
        self.accent = REALM_COLORS[rid]
        self.state = game.realm_states[rid]
        self.rng = random.Random()
        self.stage = 0
        self.stages = 3
        self.progress = 0
        self.nodes = []
        self.names = []
        self.order = []
        self.clues = []
        self.well = V(120, 320)
        self.interactables = [Interactable(V(480, 560), "Leave the grove", lambda: game.go_realm(rid, at="treasure"), 52,
                                           draw_fn=lambda s, p, it: draw_portal(s, p, GREEN, self.time, "EXIT", 20))]
        self.node_its = []
        for i in range(6):
            it = Interactable(V(0, 0), lambda i=i: f"Touch {self.names[i]}" if i < len(self.names) else "", (lambda i=i: self.activate(i)), 62,
                              visible=(lambda i=i: i < len(self.nodes) and self.stage < self.stages and not self.state.treasure_claimed),
                              draw_fn=(lambda s, p, it, i=i: self.draw_node(s, p, i)))
            self.node_its.append(it)
            self.interactables.append(it)
        self.interactables.append(Interactable(V(480, 150), "Open the treasure", self.claim, 60,
                                               visible=lambda: self.stage >= self.stages and not self.state.treasure_claimed,
                                               draw_fn=lambda s, p, it: self.draw_chest(s, p)))
        self.new_stage()

    def new_stage(self):
        size = ORDER_SIZES[self.rid][min(self.stage, 2)]
        labels = random.sample(ORDER_LABELS[self.rid], size)
        self.clues, self.order_names = gen_ordering_riddle(labels, self.rng)
        spots = list(self.ANCHORS[size])
        self.rng.shuffle(spots)
        self.names = labels
        self.nodes = [V(p) for p in spots]
        for it, p in zip(self.node_its, self.nodes):
            it.pos = V(p)
        self.order = [labels.index(n) for n in self.order_names]
        self.progress = 0

    def spawn(self):
        return V(480, 520)

    def activate(self, i):
        if self.stage >= self.stages or self.progress >= len(self.order):
            return
        if self.order[self.progress] == i:
            self.progress += 1
            burst(self.nodes[i], GOLD, 20, (50, 140), .6, 3)
            game.float_text(self.nodes[i], f"{self.progress}/{len(self.order)}", GREEN)
            if self.progress >= len(self.order):
                game.log_riddle(self.rid, f"{ORDER_INTRO[self.rid]} " + " ".join(self.clues), " > ".join(self.order_names))
                self.stage += 1
                if self.stage >= self.stages:
                    game.banner("THE LAST RIDDLE IS SOLVED", "The treasure rises from the ground", GOLD)
                else:
                    game.banner(f"RIDDLE {self.stage} / {self.stages} SOLVED", "The grove rearranges itself...", GREEN, 2.0)
                    self.new_stage()
        else:
            self.progress = 0
            game.float_text(self.nodes[i], "WRONG - THE GROVE STIRS", RED, 1.4, 20)
            for k in range(2 + self.stage):
                p = self.nodes[i] + from_angle(k * 2.1 + .5, 90)
                e = self.add_enemy(Enemy(p, random.choice(REALM_ENEMY_TYPES[self.rid]), REALM_DIFFICULTY[self.rid] * 1.1, self.accent, 900))
                e.drops = False
                if self.stage >= 2 and k == 0:
                    make_elite(e)

    def claim(self):
        if self.state.treasure_claimed:
            return
        self.state.treasure_claimed = True
        rid = self.rid
        gold = int({EMBER_ID: 450, FROZEN_ID: 650, VOID_ID: 850, STARFALL_ID: 1100}[rid] * GOLD_RATE)
        game.player.gold += gold
        game.player.embers += 3 + PROGRESSION.index(rid)
        relic = REALM_TREASURE_RELIC[rid]
        game.player.gain_relic(relic)
        game.banner("TREASURE CLAIMED", f"+{gold} gold and the relic {RELICS[relic]['name']}", GOLD, 3.0)
        game.autosave()

    def objective(self):
        if self.state.treasure_claimed:
            return "Treasure claimed. Leave the grove.", V(480, 560)
        if self.stage >= self.stages:
            return "Open the treasure", V(480, 150)
        return f"Riddle {self.stage + 1}/{self.stages}: {self.progress}/{len(self.order)} done", None

    def draw_ground(self, surf, cam):
        bg = [(62, 30, 22), (30, 58, 80), (40, 36, 74), (16, 14, 34)][self.rid]
        self.draw_floor(surf, bg, mix(bg, WHITE, .08), 48)
        if self.rid == VOID_ID:
            for k in range(3):
                rr = int(150 - ((self.time * 50 + k * 50) % 150))
                pygame.draw.circle(surf, (90, 50, 130), ipos(self.well), max(4, rr), 1)
            pygame.draw.circle(surf, (5, 3, 10), ipos(self.well), 24)
            pygame.draw.circle(surf, PURPLE, ipos(self.well), 24, 2)

    def draw_top(self, surf, cam):
        if self.state.treasure_claimed or self.stage >= self.stages:
            return
        alpha_rect(surf, R(130, 84, 700, 22 + 20 * (len(self.clues) + 1)), BLACK, 140)
        draw_text(surf, f"RIDDLE {self.stage + 1}/{self.stages}  -  {ORDER_INTRO[self.rid]}", (480, 90), GOLD, 18, center=True)
        for k, line in enumerate(self.clues):
            draw_text(surf, line, (480, 114 + k * 20), WHITE, 17, center=True)

    def draw_node(self, surf, p, i):
        x, y = ipos(p)
        done = i in self.order[:self.progress]
        col = GREEN if done else self.accent
        glow(surf, (x, y), 40, col, 70)
        if self.rid == EMBER_ID:
            s = 16
            pygame.draw.polygon(surf, (150, 110, 50), [(x - s, y + s), (x - s * .6, y - s), (x + s * .6, y - s), (x + s, y + s)])
            pygame.draw.polygon(surf, col, [(x - s, y + s), (x - s * .6, y - s), (x + s * .6, y - s), (x + s, y + s)], 2)
            pygame.draw.circle(surf, GOLD, (x, y + s + 4), 5)
        elif self.rid == FROZEN_ID:
            pygame.draw.rect(surf, (170, 215, 240), (x - 18, y - 26, 36, 52))
            pygame.draw.rect(surf, col, (x - 18, y - 26, 36, 52), 3)
            pygame.draw.line(surf, WHITE, (x - 10, y - 14), (x - 2, y - 22), 2)
        elif self.rid == VOID_ID:
            pygame.draw.rect(surf, (60, 60, 80), (x - 8, y - 22, 16, 38))
            pygame.draw.circle(surf, col, (x, y - 26), 8)
        else:
            pygame.draw.polygon(surf, col, [(x, y - 18), (x + 6, y - 6), (x + 18, y - 6), (x + 8, y + 3), (x + 12, y + 16), (x, y + 8), (x - 12, y + 16), (x - 8, y + 3), (x - 18, y - 6), (x - 6, y - 6)])
        if i < len(self.names):
            draw_text(surf, self.names[i], (x, y + 34), WHITE if not done else GREEN, 16, center=True)

    def draw_chest(self, surf, p):
        x, y = ipos(p)
        glow(surf, (x, y), 60, GOLD, 110)
        pygame.draw.rect(surf, (116, 73, 45), (x - 24, y - 12, 48, 28))
        pygame.draw.rect(surf, GOLD, (x - 25, y - 18, 50, 11), 3)
        pygame.draw.rect(surf, GOLD, (x - 4, y - 6, 8, 12))


# ============================================================
# DISCOVERY WORLDS (one optional activity per realm)
# ============================================================

DISCOVERY_REWARDS = {
    EMBER_ID: ("Forgeheart Greatsword", "greatsword", 28, "burn"),
    FROZEN_ID: ("Glacier Mirror Staff", "staff", 37, "slow"),
    VOID_ID: ("Signal Wraith Bow", "bow", 46, "void"),
    STARFALL_ID: ("Constellation Blade", "sword", 56, "star"),
}


class DiscoveryWorld(Arena):
    allow_escape = True

    def __init__(self, rid):
        super().__init__(R(40, 70, 880, 515))
        self.rid = rid
        self.key = f"discovery{rid}"
        self.title = REALM_INFO[rid]["discovery"]
        self.accent = REALM_COLORS[rid]
        self.state = game.realm_states[rid]
        self.done = False
        self.interactables = [Interactable(V(80, 540), "Leave", lambda: game.go_realm(rid, at="discovery"), 50,
                                           draw_fn=lambda s, p, it: draw_portal(s, p, GREEN, self.time, "EXIT", 20))]

    def finish(self):
        if self.done:
            return
        self.done = True
        st = self.state
        first = st.discovery_clears == 0
        st.discovery_clears += 1
        gold = int(((300 + 200 * PROGRESSION.index(self.rid)) if first else (60 + 30 * PROGRESSION.index(self.rid))) * GOLD_RATE)
        game.player.gold += gold
        game.player.embers += 2 if first else 1
        game.player.gain_xp(120 + 80 * PROGRESSION.index(self.rid))
        if first:
            game.give_item(kit_item(DISCOVERY_REWARDS[self.rid]))
            game.banner(f"{self.title} COMPLETE", f"+{gold} gold and {DISCOVERY_REWARDS[self.rid][0]}", GOLD, 3.0)
        else:
            game.banner(f"{self.title} COMPLETE", f"+{gold} gold", GOLD)
        game.autosave()

    def spawn(self):
        return V(110, 520)


class EmberForgeRun(DiscoveryWorld):
    """Collect six ember cores in the collapsing forge before time runs out."""

    def __init__(self, rid):
        super().__init__(rid)
        self.floor = FloorGrid(self.play, 80)
        self.running = False
        self.clock = 0.0
        self.cores = []
        self.interactables.append(Interactable(V(200, 540), lambda: "Start the Forge Run" if not self.running else "Running!",
                                               self.start, 56, visible=lambda: not self.running and not self.done,
                                               draw_fn=lambda s, p, it: self.draw_bell(s, p)))

    def start(self):
        if self.running or self.done:
            return
        self.running = True
        self.clock = 50.0
        self.cores = [V(x, y) for x, y in ((150, 140), (480, 120), (820, 150), (820, 470), (480, 330), (300, 470))]
        game.banner("FORGE RUN", "Grab all six ember cores!", ORANGE)

    def update(self, dt):
        super().update(dt)
        self.floor.update(dt)
        if not self.running:
            return
        p = game.player
        self.clock -= dt
        if self.timer_tick(dt, "lava", 1.1):
            self.floor.random_trigger(3, 1.0, 3.0, near=p.pos, max_frac=.35)
        if self.timer_tick(dt, "hammer", 1.6):
            self.hazards.append(Hazard(p.pos + V(random.uniform(-40, 40), random.uniform(-40, 40)), 60, .9, .25, 18, (180, 180, 190), label="HAMMER"))
        if self.floor.is_gone(p.pos) and not p.has_relic("cinderheart"):
            p.take_damage(10, "fire")
            p.apply_burn(1.5)
        for c in list(self.cores):
            if dist(c, p.pos) < 30:
                self.cores.remove(c)
                burst(c, ORANGE, 20, (60, 160), .5, 3)
                game.float_text(c, f"CORE {6 - len(self.cores)}/6", ORANGE)
        if not self.cores:
            self.running = False
            self.floor.reset()
            self.hazards = []
            self.finish()
        elif self.clock <= 0:
            self.running = False
            self.floor.reset()
            self.hazards = []
            game.banner("THE FORGE COOLS", "Out of time - ring the bell to try again", RED)

    def timer_tick(self, dt, key, period):
        t = getattr(self, "_t_" + key, period) - dt
        if t <= 0:
            setattr(self, "_t_" + key, period)
            return True
        setattr(self, "_t_" + key, t)
        return False

    def objective(self):
        if self.done:
            return "Forge Run complete. Leave when ready.", V(80, 540)
        if self.running:
            return f"Collect ember cores: {6 - len(self.cores)}/6   {max(0, self.clock):.0f}s", None
        return "Ring the bell to start the Forge Run", V(200, 540)

    def draw_ground(self, surf, cam):
        self.draw_floor(surf, (70, 34, 24), (95, 45, 30))
        self.floor.draw(surf, "lava", self.time)
        for c in self.cores:
            glow(surf, c, 30, ORANGE, 130)
            pygame.draw.polygon(surf, ORANGE, [(c.x, c.y - 12), (c.x + 9, c.y), (c.x, c.y + 12), (c.x - 9, c.y)])

    def draw_bell(self, surf, p):
        x, y = ipos(p)
        pygame.draw.polygon(surf, (150, 110, 50), [(x - 14, y + 10), (x - 9, y - 14), (x + 9, y - 14), (x + 14, y + 10)])
        draw_text(surf, "START", (x, y - 36), ORANGE, 16, center=True)



class FrozenMirrorMaze(DiscoveryWorld):
    """A maze of ice. Three exit mirrors - only the true one shows your reflection."""

    def __init__(self, rid):
        super().__init__(rid)
        cols, rows, cell = 11, 6, 80
        ox, oy = 40, 70
        rng = random.Random()
        visited = [[False] * cols for _ in range(rows)]
        walls_v = [[True] * (cols + 1) for _ in range(rows)]
        walls_h = [[True] * cols for _ in range(rows + 1)]
        stack = [(0, rows - 1)]
        visited[rows - 1][0] = True
        while stack:
            cx, cy = stack[-1]
            options = [(nx, ny) for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1))
                       if 0 <= nx < cols and 0 <= ny < rows and not visited[ny][nx]]
            if not options:
                stack.pop()
                continue
            nx, ny = rng.choice(options)
            if nx != cx:
                walls_v[cy][max(cx, nx)] = False
            else:
                walls_h[max(cy, ny)][cx] = False
            visited[ny][nx] = True
            stack.append((nx, ny))
        # Open a few extra passages so the maze has loops.
        for _ in range(8):
            y, x = rng.randrange(rows), rng.randrange(1, cols)
            walls_v[y][x] = False
        t = 8
        self.walls = []
        for y in range(rows):
            for x in range(1, cols):
                if walls_v[y][x]:
                    self.walls.append(R(ox + x * cell - t // 2, oy + y * cell, t, cell + t // 2))
        for y in range(1, rows):
            for x in range(cols):
                if walls_h[y][x]:
                    self.walls.append(R(ox + x * cell, oy + y * cell - t // 2, cell + t // 2, t))
        exits = [(cols - 1, 0), (cols - 1, rows - 1), (cols // 2, 0)]
        self.true_exit = rng.randrange(3)
        self.exits = [V(ox + ex * cell + cell / 2, oy + ey * cell + cell / 2) for ex, ey in exits]
        # mirror tiles teleport you to the reflected position across the middle of the maze
        self.mirror_tiles = [V(ox + 3 * cell + cell / 2, oy + 2 * cell + cell / 2), V(ox + 7 * cell + cell / 2, oy + 4 * cell + cell / 2)]
        self.mirror_cd = 0
        self.interactables = [self.interactables[0]]
        self.interactables[0].pos = V(ox + cell / 2, oy + (rows - 1) * cell + cell / 2)
        for i, e in enumerate(self.exits):
            self.interactables.append(Interactable(e, "Step into the mirror", (lambda i=i: self.try_exit(i)), 46,
                                                   visible=lambda: not self.done, draw_fn=(lambda s, p, it, i=i: self.draw_exit(s, p, i))))
        for _ in range(4):
            p = V(rng.randint(250, 880), rng.randint(100, 540))
            self.add_enemy(Enemy(p, "wraith", REALM_DIFFICULTY[rid], ICE, aggro=220))

    def spawn(self):
        return V(80, 70 + 5 * 80 + 40)

    def try_exit(self, i):
        if self.done:
            return
        if i == self.true_exit:
            self.finish()
            game.player.pos = V(self.spawn())
        else:
            game.float_text(self.exits[i], "Only cold glass. A false mirror!", RED, 1.6, 20)
            for k in range(2):
                e = self.add_enemy(Enemy(self.exits[i] + from_angle(k * math.pi, 60), "wraith", REALM_DIFFICULTY[self.rid], ICE, 600))
                e.drops = False

    def update(self, dt):
        super().update(dt)
        self.mirror_cd = max(0, self.mirror_cd - dt)
        p = game.player
        for m in self.mirror_tiles:
            if self.mirror_cd <= 0 and dist(p.pos, m) < 22:
                target = V(2 * 480 - m.x, m.y)
                target = self.find_free(target, p.RADIUS)
                burst(p.pos, ICE, 20, (60, 160), .4, 3)
                p.pos = target
                self.mirror_cd = 1.5
                game.float_text(p.pos, "REFLECTED", ICE)

    def objective(self):
        if self.done:
            return "You escaped the maze! Return to the exit.", self.interactables[0].pos
        return "Find the true mirror - only it shows your reflection", None

    def draw_ground(self, surf, cam):
        self.draw_floor(surf, (150, 185, 210), (170, 205, 225), 80)
        for w in self.walls:
            pygame.draw.rect(surf, (90, 140, 180), w)
        for m in self.mirror_tiles:
            pygame.draw.circle(surf, WHITE, ipos(m), 20, 2)
            pygame.draw.circle(surf, (210, 240, 255), ipos(m), 12)
            target = V(2 * 480 - m.x, m.y)
            pygame.draw.circle(surf, WHITE, ipos(target), 8, 1)

    def draw_exit(self, surf, p, i):
        x, y = ipos(p)
        pygame.draw.rect(surf, (200, 235, 250), (x - 18, y - 28, 36, 56))
        pygame.draw.rect(surf, WHITE, (x - 18, y - 28, 36, 56), 3)
        if i == self.true_exit:
            # your reflection, mirrored horizontally, only in the true mirror
            pl = game.player.pos
            offx = clamp((p.x - pl.x) / 40, -10, 10)
            offy = clamp((pl.y - p.y) / 60, -14, 14)
            pygame.draw.rect(surf, (63, 116, 178), (x + offx - 4, y + offy, 8, 9))
            pygame.draw.rect(surf, (226, 177, 132), (x + offx - 3, y + offy - 7, 6, 7))



class VoidSignalHunt(DiscoveryWorld):
    """Hunt three silent beacons in the dark, then face the mini-boss that answers."""

    def __init__(self, rid):
        super().__init__(rid)
        rng = random.Random()
        self.beacons = []
        while len(self.beacons) < 3:
            p = V(rng.randint(120, 860), rng.randint(110, 540))
            if dist(p, self.spawn()) > 250 and all(dist(p, b) > 220 for b in self.beacons):
                self.beacons.append(p)
        self.found = [False] * 3
        self.walls = [R(rng.randint(150, 800), rng.randint(110, 500), rng.choice((30, 120)), 30) for _ in range(9)]
        self.walls = [w for w in self.walls if not any(w.inflate(60, 60).collidepoint(b) for b in self.beacons) and not w.inflate(80, 80).collidepoint(self.spawn())]
        for i in range(3):
            self.interactables.append(Interactable(self.beacons[i], "Tune the beacon", (lambda i=i: self.tune(i)), 50,
                                                   visible=(lambda i=i: not self.found[i]), draw_fn=(lambda s, p, it, i=i: self.draw_beacon(s, p))))
        self.miniboss = None
        self.dark = None
        for _ in range(4):
            self.add_enemy(Enemy(V(rng.randint(300, 860), rng.randint(100, 540)), "wraith", REALM_DIFFICULTY[rid], PURPLE, aggro=200))

    def tune(self, i):
        if self.found[i]:
            return
        self.found[i] = True
        burst(self.beacons[i], PURPLE, 24, (50, 160), .6, 3)
        game.float_text(self.beacons[i], f"SIGNAL {sum(self.found)}/3", PURPLE)
        if all(self.found):
            self.miniboss = self.add_enemy(SignalWraith(V(480, 300)))
            game.banner("SOMETHING ANSWERS", "The Signal Wraith", PURPLE)

    def update(self, dt):
        super().update(dt)
        if self.miniboss is not None and not self.miniboss.alive and not self.done:
            self.finish()

    def signal_strength(self):
        p = game.player.pos
        remaining = [b for b, f in zip(self.beacons, self.found) if not f]
        if not remaining:
            return 0
        d = min(dist(p, b) for b in remaining)
        return clamp(1 - d / 700, 0, 1)

    def objective(self):
        if self.done:
            return "Signal restored. Leave when ready.", V(80, 540)
        if all(self.found):
            return "Defeat the Signal Wraith", None
        return f"Find the silent beacons in the dark ({sum(self.found)}/3)", None

    def draw_ground(self, surf, cam):
        self.draw_floor(surf, (20, 18, 36), (30, 26, 50))
        self.draw_walls(surf, (40, 34, 60), PURPLE)

    def draw_beacon(self, surf, p):
        x, y = ipos(p)
        pygame.draw.rect(surf, (60, 60, 80), (x - 7, y - 22, 14, 36))
        pygame.draw.circle(surf, (120, 70, 170), (x, y - 26), 7)

    def draw_top(self, surf, cam):
        if self.dark is None:
            self.dark = pygame.Surface((WIDTH * 2, HEIGHT * 2), pygame.SRCALPHA)
            self.dark.fill((0, 0, 0, 235))
            for r, a in ((190, 200), (165, 150), (140, 90), (115, 30), (95, 0)):
                pygame.draw.circle(self.dark, (0, 0, 0, a), (WIDTH, HEIGHT), r)
        if not self.done and not (self.miniboss is not None and self.miniboss.alive):
            p = game.player.pos
            surf.blit(self.dark, (int(p.x - WIDTH), int(p.y - HEIGHT)))
        s = self.signal_strength()
        panel(surf, R(330, 92, 300, 30), PURPLE)
        pygame.draw.rect(surf, PURPLE, (334, 96, int(292 * s), 22))
        pulse = (math.sin(self.time * (4 + 16 * s)) + 1) / 2
        draw_text(surf, "SIGNAL STRENGTH", (480, 99), mix(WHITE, PURPLE, pulse * .5), 18, center=True)


class SignalWraith(Boss):
    phase_names = ("STATIC", "FEEDBACK", "WHITE NOISE")

    def __init__(self, pos):
        super().__init__(pos, "THE SIGNAL WRAITH", 1800 * REALM_DIFFICULTY[VOID_ID] / 1.75, 30, PURPLE, 20)
        self.boss_kind = "mini"

    def think(self, dt, scene):
        self.chase(dt, scene, 70 + 15 * self.phase, 150)
        if self.timer("shot", dt, 1.2 - .2 * (self.phase - 1)):
            base = angle_to(self.pos, game.player.pos)
            for off in (-.2, 0, .2):
                game.enemy_shot(self.pos, base + off, 250, 18, PURPLE, 7)
        if self.phase >= 2 and self.timer("blink", dt, 3.5):
            for _ in range(10):
                p = game.player.pos + from_angle(random.random() * math.tau, 200)
                if not scene.blocked(p, self.radius):
                    self.pos = p
                    burst(p, PURPLE, 16, (60, 150), .4, 3)
                    break
        if self.phase >= 3 and self.timer("ring", dt, 2.5):
            for i in range(12):
                game.enemy_shot(self.pos, i * math.tau / 12, 180, 16, (200, 120, 255), 7)

    def draw_body(self, surf, x, y):
        y += int(math.sin(self.anim * 4) * 4)
        glow(surf, (x, y), 50, PURPLE, 100)
        pygame.draw.polygon(surf, (90, 60, 140), [(x, y - 34), (x + 24, y), (x + 16, y + 30), (x, y + 18), (x - 16, y + 30), (x - 24, y)])
        for k in range(3):
            pygame.draw.line(surf, WHITE, (x - 14, y - 8 + k * 6), (x + 14, y - 8 + k * 6 + random.randint(-2, 2)), 1)


class StarfallConstellation(DiscoveryWorld):
    """Memorise a constellation while it shines, then trace it from memory. Three rounds."""

    def __init__(self, rid):
        super().__init__(rid)
        rng = random.Random()
        self.stars = []
        while len(self.stars) < 9:
            p = V(rng.randint(120, 840), rng.randint(130, 500))
            if all(dist(p, s) > 120 for s in self.stars) and dist(p, self.spawn()) > 150:
                self.stars.append(p)
        self.round = 0
        self.sequence = []
        self.progress = 0
        self.show = 0.0
        self.active = False
        self.cd = 0
        self.interactables.append(Interactable(V(200, 540), lambda: "Begin the constellation" if self.round == 0 else "Show the pattern again",
                                               self.begin, 56, visible=lambda: not self.done and self.show <= 0,
                                               draw_fn=lambda s, p, it: draw_portal(s, p, GOLD, self.time, "STAR ALTAR", 18)))

    def begin(self):
        if self.done:
            return
        if self.round == 0:
            self.round = 1
        self.new_round()

    def new_round(self):
        n = 3 + self.round
        self.sequence = random.sample(range(len(self.stars)), n)
        self.progress = 0
        self.show = 1.2 + n * .7
        self.active = False
        game.banner(f"ROUND {self.round} / 3", "Watch the constellation...", GOLD, 1.5)

    def update(self, dt):
        super().update(dt)
        self.cd = max(0, self.cd - dt)
        if self.show > 0:
            self.show -= dt
            if self.show <= 0:
                self.active = True
                game.float_text(game.player.pos, "Your turn - touch the stars in order", GOLD, 1.5)
            return
        if not self.active or self.done or self.cd > 0:
            return
        p = game.player.pos
        for i, s in enumerate(self.stars):
            if dist(p, s) < 26:
                if i == self.sequence[self.progress]:
                    self.progress += 1
                    self.cd = .35
                    burst(s, GOLD, 16, (50, 140), .5, 3)
                    if self.progress >= len(self.sequence):
                        self.active = False
                        if self.round >= 3:
                            self.finish()
                        else:
                            self.round += 1
                            self.new_round()
                    return
                elif i not in self.sequence[:self.progress]:
                    self.hazards.append(Hazard(s, 70, .5, .3, 18 * REALM_DIFFICULTY[self.rid], GOLD))
                    game.float_text(s, "WRONG STAR", RED)
                    self.active = False
                    self.cd = 1.2
                    self.show = 1.5 + len(self.sequence) * .6
                    self.progress = 0
                    return

    def objective(self):
        if self.done:
            return "The constellation is restored. Leave when ready.", V(80, 540)
        if self.round == 0:
            return "Touch the star altar to begin", V(200, 540)
        if self.show > 0:
            return "Memorise the pattern...", None
        return f"Trace the constellation: {self.progress}/{len(self.sequence)}", None

    def draw_ground(self, surf, cam):
        surf.fill((8, 8, 22))
        pygame.draw.rect(surf, (20, 18, 44), self.play)
        for i in range(70):
            pygame.draw.circle(surf, (120, 120, 160), (60 + (i * 137) % 860, 80 + (i * 71) % 500), 1)
        if self.show > 0 and self.sequence:
            total = len(self.sequence)
            shown = min(total, int((1 - self.show / (1.2 + total * .7)) * total * 1.4) + 1)
            pts = [self.stars[i] for i in self.sequence[:shown]]
            if len(pts) > 1:
                pygame.draw.lines(surf, GOLD, False, [ipos(q) for q in pts], 3)
            for k, q in enumerate(pts):
                draw_text(surf, str(k + 1), (q.x, q.y - 32), GOLD, 20, center=True)
        elif self.active:
            pts = [self.stars[i] for i in self.sequence[:self.progress]]
            if len(pts) > 1:
                pygame.draw.lines(surf, GREEN, False, [ipos(q) for q in pts], 2)
        for i, s in enumerate(self.stars):
            lit = (self.show > 0 and i in self.sequence) or (i in self.sequence[:self.progress])
            glow(surf, s, 26 if lit else 16, GOLD if lit else (150, 150, 200), 120)
            pygame.draw.circle(surf, WHITE if lit else (180, 180, 210), ipos(s), 7)



DISCOVERY_CLASSES = {EMBER_ID: EmberForgeRun, FROZEN_ID: FrozenMirrorMaze, VOID_ID: VoidSignalHunt, STARFALL_ID: StarfallConstellation}


# ============================================================
# SOUND (tiny synthesizer - silently disabled if audio is unavailable)
# ============================================================

class Sounds:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.last = {}
        try:
            import array
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            rate = pygame.mixer.get_init()[0]
            channels = pygame.mixer.get_init()[2]

            def tone(freq, dur, vol=.25, slide=0.0, noise=0.0, wave="square"):
                n = int(rate * dur)
                buf = array.array("h")
                phase = 0.0
                rng = random.Random(int(freq * 1000 + dur * 100))
                for i in range(n):
                    t = i / n
                    f = freq + slide * t
                    phase += f / rate
                    if wave == "square":
                        s = 1.0 if (phase % 1) < .5 else -1.0
                    else:
                        s = math.sin(phase * math.tau)
                    if noise:
                        s = s * (1 - noise) + rng.uniform(-1, 1) * noise
                    env = (1 - t) ** 2
                    v = int(s * env * vol * 32767)
                    for _ in range(channels):
                        buf.append(v)
                return pygame.mixer.Sound(buffer=buf.tobytes())

            self.sounds = {
                "swing": tone(220, .07, .10, -80, .6),
                "hit": tone(140, .08, .16, -60, .4),
                "bow": tone(500, .08, .10, 300, 0, "sine"),
                "bolt": tone(700, .1, .10, -300, 0, "sine"),
                "hurt": tone(110, .14, .22, -50, .3),
                "pickup": tone(880, .07, .10, 400, 0, "sine"),
                "level": tone(523, .35, .18, 520, 0, "sine"),
                "dash": tone(300, .08, .08, 300, .5),
                "blink": tone(900, .15, .12, -700, 0, "sine"),
                "menu": tone(660, .04, .08, 0, 0, "sine"),
                "boss": tone(70, .6, .25, -20, .4),
            }
            self.enabled = True
        except Exception:
            self.enabled = False

    def play(self, name):
        if not self.enabled:
            return
        now = pygame.time.get_ticks()
        if now - self.last.get(name, -1000) < 45:
            return
        self.last[name] = now
        snd = self.sounds.get(name)
        if snd:
            try:
                snd.play()
            except Exception:
                pass


# ============================================================
# GAME
# ============================================================

class GameCore:
    def __init__(self):
        self.state = MENU
        self.menu_index = 0
        self.player = None
        self.boss_ctx = None
        self.scene = None
        self.cam = V()
        self.particles = []
        self.texts = []
        self.projectiles = []
        self.loot = []
        self.banners = []
        self.flash_rings = []
        self.shake_time = 0.0
        self.fade = 0.0
        self.time = 0.0
        self.god_mode = False
        self.death_reason = ""
        self.dialogue = None
        self.shop = None
        self.book = None
        self.arcade = None
        self.drag = None
        self.toast = None
        self.error_times = []
        self.sfx = Sounds()
        self.menu_embers = [[random.randrange(WIDTH), random.randrange(HEIGHT), random.uniform(10, 45)] for _ in range(80)]
        self.reset_progress()

    # ------------------------------------------------------------------
    # setup / persistence of progress
    # ------------------------------------------------------------------
    def reset_progress(self):
        self.player = Player()
        self.realm_states = {rid: RealmState(rid) for rid in range(4)}
        self.home_status = {rid: None for rid in range(4)}
        self.dungeon_progress = 0
        self.phase5_seen = [False] * 4
        self.arcade_best = 0
        self.arcade_medals = []
        self.victory_seen = False
        self.riddle_log = []
        self.boss_deaths = {}
        self.journal_page = 0
        self.last_hub = ("home", None)
        self.home = None
        self.realm_scenes = {}
        self.scene = None

    def new_game(self):
        self.reset_progress()
        self.home = HomeWorld()
        self.change_scene(self.home, self.home.spawn())
        self.state = PLAYING
        self.dialog([("MIRA", "You made it through the ashfall. Welcome to the village."),
                     ("MIRA", "Four realms broke away from this world - Ember, Frozen, Void and Starfall. Each one is ruled by something terrible."),
                     ("MIRA", "Come talk to me at the Ember Gate on the west road when you're ready. Bram, Pip and Wren can outfit you first."),
                     ("TIP", "WASD to move, mouse to aim, Left Click to attack, Shift to dash, E to talk. Press J any time for your quest journal.")])

    # ------------------------------------------------------------------
    # small effect helpers
    # ------------------------------------------------------------------
    def sound(self, name):
        self.sfx.play(name)

    def float_text(self, pos, text, color=WHITE, life=1.0, size=18):
        if len(self.texts) < 120:
            self.texts.append(FloatText(pos, text, color, life, size))

    def banner(self, title, subtitle="", color=GOLD, time=2.4):
        self.banners = [[title, subtitle, color, time, time]]

    def shake(self, t):
        self.shake_time = max(self.shake_time, t)

    def flash_ring(self, pos, radius, color):
        self.flash_rings.append([V(pos), radius, color, .35])

    def notify(self, text, color=WHITE):
        self.toast = [text, color, 3.0]

    def mouse_world(self):
        return V(pygame.mouse.get_pos()) + self.cam

    def enemy_shot(self, pos, angle, speed, damage, color=EMBER, radius=7, **kw):
        if len(self.projectiles) > 450:
            return
        ctx = getattr(self, "boss_ctx", None)
        if ctx is not None:
            damage = max(1, int(damage * ctx.dmg_mult))
            speed *= ctx.spd_mult
        self.projectiles.append(Projectile(pos, from_angle(angle, speed), damage, "enemy", radius, color,
                                           kw.pop("life", 3.0), kw.pop("effect", None), 0, kw.pop("element", None),
                                           kw.pop("kind", "orb"), kw.pop("homing", 0.0), kw.pop("bounces", 0)))

    def player_shot(self, proj):
        self.projectiles.append(proj)

    def clear_projectiles(self):
        self.projectiles = []

    def clear_enemy_projectiles(self):
        self.projectiles = [p for p in self.projectiles if p.owner == "player"]

    def give_item(self, item):
        if self.player.inv.add(item):
            self.float_text(self.player.pos + V(0, -30), f"Got {item.name}", item.color, 1.6)
            return True
        self.player.gold += item.value // 5
        self.float_text(self.player.pos + V(0, -30), f"Bag full - sold {item.name} for {item.value // 5}g", GOLD, 2.0)
        return False

    # ------------------------------------------------------------------
    # scenes / travel
    # ------------------------------------------------------------------
    def change_scene(self, scene, pos=None):
        if self.scene is not None and self.scene is not scene:
            try:
                self.scene.on_exit()
            except Exception:
                log_error("scene exit")
        self.scene = scene
        scene.on_enter()
        p = self.player
        p.pos = scene.find_free(V(pos) if pos is not None else scene.spawn(), p.RADIUS)
        p.vel = V()
        p.dash_time = 0
        p.bow_charge = None
        p.swing = 0
        p.invuln = max(p.invuln, 1.0)
        self.projectiles = []
        self.loot = []
        self.particles = []
        self.texts = []
        self.flash_rings = []
        self.fade = 1.0
        self.snap_camera()
        if scene.hub:
            if isinstance(scene, RealmWorld):
                self.last_hub = ("realm", scene.rid)
            elif isinstance(scene, HomeWorld):
                self.last_hub = ("home", None)

    def snap_camera(self):
        if self.scene.fixed_camera:
            self.cam = V()
        else:
            self.cam = V(clamp(self.player.pos.x - WIDTH / 2, 0, max(0, self.scene.width - WIDTH)),
                         clamp(self.player.pos.y - HEIGHT / 2, 0, max(0, self.scene.height - HEIGHT)))

    def get_home(self):
        if self.home is None:
            self.home = HomeWorld()
        return self.home

    def get_realm(self, rid):
        if rid not in self.realm_scenes:
            self.realm_scenes[rid] = RealmWorld(rid)
        return self.realm_scenes[rid]

    def go_home(self, from_rid=None):
        home = self.get_home()
        if from_rid is None and isinstance(self.scene, RealmWorld):
            from_rid = self.scene.rid
        pos = None
        if from_rid is not None:
            gx, gy = home.gates[from_rid]
            pos = home.tile_center(gx + (2 if gx < 36 else -2 if gx > 36 else 0), gy + (2 if gy < 26 else -2 if gy > 26 else 0)) + V(0, 30)
        elif isinstance(self.scene, (DungeonHub, DungeonRoom)):
            pos = home.tile_center(36, 22)
        self.change_scene(home, pos)
        self.autosave()

    def go_realm(self, rid, at="spawn"):
        realm = self.get_realm(rid)
        tc = realm.tile_center
        if at == "boss":
            pos = tc(*realm.boss_door) + V(0, 40)
        elif at == "secret":
            pos = tc(*realm.secret_gate_tile) + V(-50, 40)
        elif at == "treasure":
            pos = tc(*realm.treasure_tile) + V(0, 50)
        elif at == "discovery":
            pos = tc(*realm.discovery_tile) + V(50, 0)
        elif isinstance(at, tuple) and at[0] == "door":
            pos = tc(*realm.doors[at[1]]) + V(0, 46)
        else:
            pos = realm.spawn()
        self.change_scene(realm, pos)

    def travel_to_realm(self, rid):
        self.go_realm(rid)
        st = self.realm_states[rid]
        if not st.lines[0].started:
            self.banner(REALM_NAMES[rid], self.danger_text(REALM_RECOMMENDED_LEVEL[rid]), REALM_COLORS[rid], 3.4)

    def enter_quest_building(self, rid, i):
        line = self.realm_states[rid].lines[i]
        if line.complete:
            self.dialog([(line.area, "It's quiet inside now. Your work here is done.")])
            return
        if not line.started:
            self.dialog([(line.area, f"The doors are barred. Talk to {line.giver} first.")])
            return
        self.change_scene(QuestInterior(rid, i))
        self.banner(line.area, line.title, REALM_COLORS[rid])

    def leave_interior(self):
        sc = self.scene
        if isinstance(sc, QuestInterior):
            self.go_realm(sc.rid, at=("door", sc.index))

    def enter_dungeon_hub(self):
        self.change_scene(DungeonHub())

    def talk_dungeon_guide(self, i):
        name = DUNGEON_GUIDES[i]
        if i > self.dungeon_progress:
            self.dialog([(name.upper(), f"Room {i + 1} is sealed. Clear Room {self.dungeon_progress + 1} first.")])
            return
        boss = DUNGEON_BOSSES[i].title()
        tag = "Cleared - you can fight here again for loot." if i < self.dungeon_progress else "Nobody has cleared it yet."
        self.dialog([(name.upper(), f"Room {i + 1}: {DUNGEON_ROOMS[i][0].title()}. {boss} waits inside. {tag}")],
                    choices=[(f"Enter Room {i + 1}", lambda: self.change_scene(DungeonRoom(i))), ("Not yet", None)])

    def try_realm_boss(self, rid):
        st = self.realm_states[rid]
        info = REALM_INFO[rid]
        if not st.boss_unlocked():
            self.dialog([(info["lair"], f"The gate is sealed. Complete {st.lines[2].title} to break the seals.")])
            return
        text = f"{info['boss'].title()} waits beyond this gate." + (" You have beaten it before - it will fight again for a smaller reward." if st.boss_defeated else "")
        lines = [(info["lair"], text), (info["lair"], self.danger_text(REALM_RECOMMENDED_LEVEL[rid] + 1))]
        self.dialog(lines, choices=self.boss_choices(rid, "realm", lambda: self.change_scene(RealmBossArena(rid))))

    def try_secret_boss(self, rid):
        st = self.realm_states[rid]
        info = REALM_INFO[rid]
        if st.side != "complete":
            self.dialog([("HIDDEN GATE", "The gate is sealed by an old seal. Someone in this realm's hidden corner might know how to open it.")])
            return
        if st.secret_defeated:
            self.dialog([("HIDDEN GATE", f"{info['secret_boss'].title()} has been conquered. Its echo still waits inside for anyone wanting a rematch.")],
                        choices=[("Rematch (reduced gold)", lambda: self.change_scene(SecretBossArena(rid))), ("Leave", None)])
            return
        self.dialog([("HIDDEN GATE", f"Beyond this gate: {info['secret_boss'].title()}. One of the deadliest things in Ashfall."),
                     ("HIDDEN GATE", f"{info['adventurer']} nearby keeps a field journal about it. Read it before you go in."),
                     ("HIDDEN GATE", self.danger_text(REALM_RECOMMENDED_LEVEL[rid] + 6 + 2 * PROGRESSION.index(rid)))],
                    choices=self.boss_choices(rid, "secret", lambda: self.change_scene(SecretBossArena(rid))))

    def danger_text(self, rec):
        lv = self.player.level
        d = lv - rec
        word = "LETHAL" if d <= -5 else "VERY DANGEROUS" if d <= -2 else "DANGEROUS" if d < 0 else "FAIR" if d <= 3 else "COMFORTABLE"
        return f"Recommended level {rec}+. You are level {lv}: {word}."

    def boss_choices(self, rid, kind, enter):
        ch = [("Enter", enter)]
        if self.boss_deaths.get((kind, rid), 0) >= 2:
            def aided():
                self.player.buffs["aid"] = 1200
                self.notify("Keeper's aid: -20% damage taken, +10% damage dealt.", GREEN)
                enter()
            ch.append(("Enter with aid", aided))
        ch.append(("Not yet", None))
        return ch

    def try_treasure(self, rid):
        if TREASURE_MAPS[rid] not in self.player.treasure_maps:
            self.dialog([("TREASURE GATE", "A gate without a key. It seems to want a map - one only this realm's secret merchant would have.")])
            return
        self.change_scene(TreasureWorld(rid))

    def enter_discovery(self, rid):
        self.change_scene(DISCOVERY_CLASSES[rid](rid))
        self.banner(REALM_INFO[rid]["discovery"], "Optional discovery world", REALM_COLORS[rid])

    # ------------------------------------------------------------------
    # home quest progression
    # ------------------------------------------------------------------
    def home_quest_status(self, rid):
        st = self.home_status.get(rid)
        if st:
            return st
        idx = PROGRESSION.index(rid)
        if all(self.home_status.get(prev) == "done" for prev in PROGRESSION[:idx]):
            return "available"
        return "locked"

    def giver_marker(self, rid):
        s = self.home_quest_status(rid)
        return {"available": ("!", GOLD), "ready": ("?", GREEN), "active": ("...", WHITE)}.get(s)

    def talk_quest_giver(self, rid):
        info = REALM_INFO[rid]
        name = info["giver"].upper()
        status = self.home_quest_status(rid)
        travel = ("Travel to the " + REALM_NAMES[rid].title(), lambda: self.travel_to_realm(rid))
        if status == "locked":
            prev = PROGRESSION[PROGRESSION.index(rid) - 1]
            self.dialog([(name, f"I can't open the {REALM_SHORT[rid]} gate yet - it would tear you apart."),
                         (name, f"Finish {REALM_INFO[prev]['title']} for {REALM_INFO[prev]['giver']} first.")])
        elif status == "available":
            lines = {
                EMBER_ID: ["The Ember Realm is a volcano that never stopped erupting. Raiders, cultists - and above them all, Emberfang.",
                           "Sera will meet you at the gate. Three quests stand between you and the Dragon's Sanctum."],
                FROZEN_ID: ["The Frozen Realm is a land of archives, monasteries and mirrors under endless snow.",
                            "Nivi guides travellers there. Something called the Frostheart sleeps beneath the Frost Throne."],
                VOID_ID: ["The Void is what's left of an old station - broken machines, bent gravity and a growing singularity.",
                          "Vex will meet you on the dock. The Void Admiral commands whatever is still alive in there."],
                STARFALL_ID: ["Starfall is the sky itself - cloud gardens, glass cathedrals and stars that fell and kept burning.",
                              "Astra waits at the cloud gate. The Seraph of the Fallen Sky judges anyone who climbs that high."],
            }[rid]
            self.dialog([(name, f"{info['title']}.")] + [(name, l) for l in lines] +
                        [(name, f"(Recommended level: {REALM_RECOMMENDED_LEVEL[rid]}+ - you are level {self.player.level}.)")],
                        choices=[travel, ("Not yet", None)], on_choice_start=lambda: self.home_status.__setitem__(rid, "active"))
        elif status == "active":
            self.dialog([(name, "The expedition is still underway. Your progress in the realm is safe.")], choices=[travel, ("Stay here", None)])
        elif status == "ready":
            reward = info["reward"]
            self.player.gold += reward
            self.player.gain_xp(150 + 100 * PROGRESSION.index(rid))
            kit = [e for e in REALM_KITS[rid] if e[1] != "armor"]
            self.give_item(kit_item(random.choice(kit)))
            self.home_status[rid] = "done"
            nxt = PROGRESSION.index(rid) + 1
            follow = f"{REALM_INFO[PROGRESSION[nxt]]['giver']} is ready to open the next gate." if nxt < 4 else "That was the last of the four realm tyrants."
            self.dialog([(name, f"You did it. {info['boss'].title()} is gone."), (name, f"Take this: {reward} gold and gear from the realm's forges."),
                         (name, follow), (name, "I can still send you back whenever you like, and I'll trade realm gear with you.")],
                        on_close=self.check_victory)
            self.autosave()
        else:
            self.dialog([(name, f"The {REALM_SHORT[rid]} Realm owes you. Where to?")],
                        choices=[travel, ("Browse realm gear", lambda: self.open_realm_shop(rid)), ("Nothing", None)])

    def check_victory(self):
        if not self.victory_seen and all(self.home_status.get(r) == "done" for r in range(4)):
            self.victory_seen = True
            self.state = VICTORY
            self.autosave()

    # ------------------------------------------------------------------
    # realm NPCs
    # ------------------------------------------------------------------
    def realm_giver_marker(self, rid, i):
        st = self.realm_states[rid]
        line = st.lines[i]
        if not line.started and (i == 0 or st.lines[i - 1].complete):
            return ("!", GOLD)
        if line.started and not line.complete:
            return ("...", WHITE)
        return None

    def talk_realm_giver(self, rid, i):
        st = self.realm_states[rid]
        line = st.lines[i]
        name = line.giver.upper()
        if line.complete:
            nxt = st.next_line_to_start()
            if i == 2:
                msg = f"The way to the {REALM_INFO[rid]['lair'].title()} is open." if not st.boss_defeated else "The realm can breathe again. Thank you."
            elif nxt:
                msg = f"{nxt.giver} needs you next for {nxt.title}."
            else:
                msg = "Thank you, traveller."
            self.dialog([(name, f"{line.title} is done."), (name, msg)])
        elif line.started:
            self.dialog([(name, f"Current step: {line.task_label}."), (name, f"Head into {line.area.title()} - the doors are just beside me.")])
        elif i == 0 or st.lines[i - 1].complete:
            line.started = True
            intro = {
                (EMBER_ID, 0): "Our caravan never reached the Cinder Outpost. Raiders, probably. Find out what happened.",
                (EMBER_ID, 1): "Someone is supplying the dragon cult from my own quarry. The ledger in the foundry will name them.",
                (EMBER_ID, 2): "The Dragon Crag is sealed by three wardstones. Break them and Emberfang's Sanctum opens.",
                (FROZEN_ID, 0): "The Frost Codex is locked in the Archive. We need its route through the blizzard.",
                (FROZEN_ID, 1): "The Aurora Relay in the mage tower can cut through the whiteout. Repair it.",
                (FROZEN_ID, 2): "The Frost Throne is bound by ancient seals. Break them, and the Colossus wakes.",
                (STARFALL_ID, 0): "The Cloud Garden choir fell silent. Its hymn fragments still glow somewhere.",
                (STARFALL_ID, 1): "The Glass Cathedral holds the Sun Relic. It is guarded, so be quiet about it.",
                (STARFALL_ID, 2): "Three celestial seals stand before Seraph's Gate. Light them all.",
                (VOID_ID, 0): "There's a signal looping from the Derelict Dock. Find out who's sending it.",
                (VOID_ID, 1): "We sabotage the Reactor Ring or the Admiral's shield never falls. You'll need the access card.",
                (VOID_ID, 2): "The Singularity Spire is the Admiral's door. Stabilise it and walk through.",
            }[(rid, i)]
            self.dialog([(name, f"QUEST: {line.title}"), (name, intro), (name, line.tasks[0][2]),
                         ("TIP", f"Enter {line.area.title()} through the door beside {line.giver}.")])
            self.autosave()
        else:
            prev = st.lines[i - 1]
            self.dialog([(name, f"You're not ready for this yet. Help {prev.giver} with {prev.title} first.")])

    def talk_world_guide(self, rid):
        info = REALM_INFO[rid]
        speaker = info["world_guide"].upper()
        st = self.realm_states[rid]
        mech = {
            EMBER_ID: "Vents flare every few seconds and lava burns anyone without fire protection. Watch the glow.",
            FROZEN_ID: "Frozen lakes are slippery - you'll keep sliding after you stop pressing a key.",
            VOID_ID: "Gravity wells drag you in. Walk against the pull, or dash out of it.",
            STARFALL_ID: "Star gates light up one at a time. Pass through the lit one to refresh your dash and heal.",
        }[rid]
        text, _ = self.scene.objective() if isinstance(self.scene, RealmWorld) else ("", None)
        pages = [(speaker, f"Welcome to the {REALM_NAMES[rid].title()}. {st.completed()}/3 story quests complete."),
                 (speaker, mech), (speaker, f"Right now: {text}")]
        if st.side == "hidden":
            pages.append((speaker, MERCHANT_HINTS[rid]))
        pages.append((speaker, f"The portal in the south-west leads to {info['discovery'].title()} - a challenge with its own reward."))
        self.dialog(pages)

    def merchant_marker(self, rid):
        st = self.realm_states[rid]
        return {"return": ("?", GREEN)}.get(st.side)

    def talk_secret_merchant(self, rid):
        st = self.realm_states[rid]
        info = REALM_INFO[rid]
        name = info["merchant"].upper()
        if st.side == "hidden":
            self.dialog([(name, "Well. Nobody finds this corner by accident."), (name, f"{info['side']}: {info['side_desc']}"),
                         (name, "Do this for me and I'll give you something no map shop sells.")],
                        choices=[("Accept the side quest", lambda: self.start_side(rid)), ("Maybe later", None)])
        elif st.side == "active":
            self.dialog([(name, f"Found {sum(st.side_found)} of 3 so far. They're marked for you now - follow the golden glow.")])
        elif st.side == "return":
            st.side = "complete"
            mp = TREASURE_MAPS[rid]
            if mp not in self.player.treasure_maps:
                self.player.treasure_maps.append(mp)
            self.player.gain_xp(150 + 60 * PROGRESSION.index(rid))
            self.player.gold += int((150 + 100 * PROGRESSION.index(rid)) * GOLD_RATE)
            self.dialog([(name, "All three. I knew you were the one."), (name, f"Take the {mp}. It opens the treasure gate in the north."),
                         (name, f"And the hidden gate beside it is unsealed now. {info['secret_boss'].title()} lives there - read {info['adventurer']}'s journal first."),
                         (name, "My shop is open to you from now on.")])
            self.banner("TREASURE MAP FOUND", f"{mp} - and the optional boss gate is open", GOLD, 3.0)
            self.autosave()
        else:
            self.open_secret_shop(rid)

    # ------------------------------------------------------------------
    # BOUNTIES (side quests) and riddles
    # ------------------------------------------------------------------
    def renown(self):
        return renown_points()

    def log_riddle(self, rid, text, answer):
        for r in self.riddle_log:
            if r[1] == text:
                return
        self.riddle_log.append([rid, text, answer])
        self.riddle_log = self.riddle_log[-24:]

    def bounty_status_text(self, rid, q):
        st = self.realm_states[rid]
        b = st.bstate(q["id"])
        if b["s"] == 2:
            return "[x] " + q["name"]
        if b["s"] == 1:
            return "[>] " + q["name"] + " " + self.bounty_progress_text(q, b)
        if st.completed() < q["req"]:
            return f"[-] {q['name']} (finish {q['req']} main quest{'s' if q['req'] > 1 else ''})"
        return "[ ] " + q["name"]

    def bounty_progress_text(self, q, b):
        if q["kind"] in ("survey", "cache"):
            return f"({sum(b['hit'])}/3)"
        if q["kind"] == "riddle":
            return f"({b['p']}/3)"
        return f"({b['p']}/{q['n']})"

    def open_board(self, rid):
        st = self.realm_states[rid]
        qs = SIDE_QUESTS[rid]
        lines = [("BOUNTY BOARD", f"{REALM_NAMES[rid].title()} bounties. Renown {self.renown()} (+2 max HP per bounty done). Three active at most.")]
        names = [self.bounty_status_text(rid, q) for q in qs]
        lines.append(("BOUNTIES", "   ".join(names[:4])))
        lines.append(("BOUNTIES", "   ".join(names[4:])))
        avail = [q for q in qs if st.bstate(q["id"])["s"] == 0 and st.completed() >= q["req"]]
        act = len(st.active_bounties())
        if not avail:
            lines.append(("BOUNTY BOARD", "Nothing new is posted. Finish main quests to unlock more."))
            self.dialog(lines)
            return
        lines.append(("BOUNTY BOARD", "Take a bounty?" if act < 3 else "You are already on three bounties. Finish one first."))
        choices = []
        if act < 3:
            for q in avail[:4]:
                nm = q["name"] if len(q["name"]) <= 22 else q["name"][:21] + ".."
                choices.append((nm, (lambda q=q: self.accept_bounty(rid, q["id"]))))
            choices.append(("Leave", None))
        else:
            choices = [("Leave", None)]
        self.dialog(lines, choices=choices)

    def accept_bounty(self, rid, qid):
        _, q = BOUNTY_BY_ID[qid]
        st = self.realm_states[rid]
        b = st.bstate(qid)
        if b["s"] != 0 or len(st.active_bounties()) >= 3:
            return
        b["s"] = 1
        b["p"] = 0
        b["hit"] = [False, False, False]
        self.banner("BOUNTY ACCEPTED", q["name"], GOLD)
        self.dialog([("BOUNTY", q["text"])])
        self.autosave()

    def complete_bounty(self, rid, qid):
        _, q = BOUNTY_BY_ID[qid]
        st = self.realm_states[rid]
        b = st.bstate(qid)
        if b["s"] == 2:
            return
        b["s"] = 2
        qi = SIDE_QUESTS[rid].index(q)
        prog = PROGRESSION.index(rid)
        xp = 110 + 60 * prog + 25 * qi
        gold = int((140 + 70 * prog + 30 * qi) * GOLD_RATE)
        embers = 1 + (1 if qi >= 3 else 0)
        p = self.player
        p.gain_xp(xp)
        p.gold += gold
        p.embers += embers
        if q["kind"] in ("wanted", "camp", "riddle", "elite"):
            self.give_item(potion(2))
        self.banner("BOUNTY COMPLETE", f"{q['name']}  +{xp} xp  +{gold} gold  +{embers} ember  (renown {self.renown()})", GOLD, 3.2)
        p.hp = min(p.max_hp, p.hp + 2)
        self.autosave()

    def bounty_kill(self, enemy):
        sc = self.scene
        if not isinstance(sc, RealmWorld):
            return
        st = self.realm_states[sc.rid]
        for q in st.active_bounties():
            b = st.bstate(q["id"])
            hit = False
            if q["kind"] == "slay" and enemy.kind in q["enemy"]:
                hit = True
            elif q["kind"] == "elite" and enemy.affix:
                hit = True
            if hit:
                b["p"] += 1
                self.float_text(enemy.pos + V(0, -30), f"{q['name']}: {b['p']}/{q['n']}", GOLD, 1.4, 16)
                if b["p"] >= q["n"]:
                    self.complete_bounty(sc.rid, q["id"])

    def bounty_tick(self, sc, dt):
        rid = sc.rid
        st = self.realm_states[rid]
        if not hasattr(sc, "wanted_ref"):
            sc.wanted_ref = {}
            sc.camp_ref = {}
        p = self.player
        diff = REALM_DIFFICULTY[rid]
        for q in st.active_bounties():
            qid = q["id"]
            b = st.bstate(qid)
            kind = q["kind"]
            if kind == "wanted":
                e = sc.wanted_ref.get(qid)
                if e is None or not e.alive:
                    pt = sc.random_far_point(700)
                    e = sc.add_enemy(Enemy(pt, random.choice(q["enemy"]), diff * 1.3, sc.accent, 520))
                    e.on_death = (lambda en, qid=qid: self.complete_bounty(rid, qid))
                    make_elite(e)
                    e.max_hp = int(e.max_hp * 1.7)
                    e.hp = e.max_hp
                    e.name_tag = q["target"]
                    e.radius = max(e.radius, 18)
                    sc.wanted_ref[qid] = e
            elif kind == "camp":
                center = sc.bounty_pts[qid][0]
                ref = sc.camp_ref.get(qid)
                if ref is None and dist(p.pos, center) < 650:
                    ref = []
                    n = 6 + 2 * PROGRESSION.index(rid)
                    for k in range(n):
                        pos = center + from_angle(k * math.tau / n, random.uniform(40, 110))
                        e = sc.add_enemy(Enemy(pos, q["enemy"][k % len(q["enemy"])], diff * 1.1, sc.accent, 380))
                        e.home = V(center)
                        if k == 0:
                            make_elite(e)
                        ref.append(e)
                    sc.camp_ref[qid] = ref
                    self.float_text(p.pos + V(0, -50), "Camp spotted!", RED, 1.6, 20)
                elif ref is not None and not any(e.alive for e in ref):
                    self.complete_bounty(rid, qid)
            elif kind == "survey":
                for k, pt in enumerate(sc.bounty_pts[qid]):
                    if not b["hit"][k] and dist(p.pos, pt) < 80:
                        b["hit"][k] = True
                        b["p"] = sum(b["hit"])
                        burst(pt, GOLD, 16, (40, 120), .6, 3)
                        self.float_text(pt, f"{q['name']}: {b['p']}/3", GOLD, 1.4, 18)
                        if b["p"] >= 3:
                            self.complete_bounty(rid, qid)

    def dig_cache(self, rid, qid, k):
        st = self.realm_states[rid]
        b = st.bstate(qid)
        if b["s"] != 1 or b["hit"][k]:
            return
        b["hit"][k] = True
        b["p"] = sum(b["hit"])
        burst(self.player.pos, GOLD, 18, (40, 120), .6, 3)
        self.sound("pickup")
        self.float_text(self.player.pos + V(0, -30), f"Dug up {b['p']}/3", GOLD, 1.4, 18)
        if random.random() < .4 and isinstance(self.scene, RealmWorld):
            for i in range(2 + PROGRESSION.index(rid) // 2):
                e = self.scene.add_enemy(Enemy(self.player.pos + from_angle(i * 2.4, 130), random.choice(REALM_ENEMY_TYPES[rid]), REALM_DIFFICULTY[rid], REALM_COLORS[rid], 900))
                e.provoked = True
            self.float_text(self.player.pos + V(0, -55), "Someone was watching!", RED)
        if b["p"] >= 3:
            self.complete_bounty(rid, qid)

    def bounty_objective(self, sc):
        st = self.realm_states[sc.rid]
        act = st.active_bounties()
        if not act:
            return None
        q = act[0]
        b = st.bstate(q["id"])
        label = f"Bounty - {q['name']} {self.bounty_progress_text(q, b)}"
        kind = q["kind"]
        pos = None
        if kind in ("survey", "cache"):
            for k, pt in enumerate(sc.bounty_pts[q["id"]]):
                if not b["hit"][k]:
                    pos = pt
                    break
        elif kind == "camp":
            pos = sc.bounty_pts[q["id"]][0]
        elif kind == "wanted":
            e = getattr(sc, "wanted_ref", {}).get(q["id"])
            pos = V(e.pos) if e is not None and e.alive else None
        elif kind == "riddle":
            pos = sc.tile_center(*sc.keeper_tile)
        return label, pos

    def talk_keeper(self, rid):
        st = self.realm_states[rid]
        q = SIDE_QUESTS[rid][6]
        b = st.bstate(q["id"])
        name = KEEPERS[rid].upper()
        if b["s"] == 0:
            self.dialog([(name, "I trade in riddles, not coin."), (name, "Pin my bounty from the board and I will test you. Three riddles, all answered correctly, in a row.")])
        elif b["s"] == 1:
            self.dialog([(name, "Three riddles. A wrong answer wakes the wilds and you start again.")],
                        choices=[("Ask me", lambda: self.start_riddles(rid, True)), ("Not now", None)])
        else:
            self.dialog([(name, "You have beaten me once. Want a harder-feeling one for the pleasure of it? (+small xp)")],
                        choices=[("One more", lambda: self.start_riddles(rid, False)), ("No thanks", None)])

    def start_riddles(self, rid, for_bounty):
        qs = random.sample(RIDDLE_BANK[rid], 3 if for_bounty else 1)
        self.ask_riddle(rid, qs, 0, for_bounty)

    def ask_riddle(self, rid, qs, k, for_bounty):
        text, opts, ans = qs[k]
        order = list(range(len(opts)))
        random.shuffle(order)
        name = KEEPERS[rid].upper()
        body = "   ".join(f"{i + 1}) {opts[o]}" for i, o in enumerate(order))
        choices = []
        for i, o in enumerate(order):
            label = opts[o] if len(opts[o]) <= 22 else opts[o][:20] + ".."
            choices.append((label, (lambda o=o: self.answer_riddle(rid, qs, k, o == ans, for_bounty))))
        self.dialog([(name, f"Riddle {k + 1}/{len(qs)}: {text}"), (name, body)], choices=choices)

    def answer_riddle(self, rid, qs, k, ok, for_bounty):
        name = KEEPERS[rid].upper()
        st = self.realm_states[rid]
        q = SIDE_QUESTS[rid][6]
        b = st.bstate(q["id"])
        text, opts, ans = qs[k]
        if ok:
            self.log_riddle(rid, text, opts[ans])
            self.sound("pickup")
            if for_bounty:
                b["p"] = k + 1
            if k + 1 < len(qs):
                self.dialog([(name, "Correct. Again...")], on_close=lambda: self.ask_riddle(rid, qs, k + 1, for_bounty))
            else:
                if for_bounty:
                    self.dialog([(name, "Three for three. Impressive.")], on_close=lambda: self.complete_bounty(rid, q["id"]))
                else:
                    self.player.gain_xp(20 + 10 * PROGRESSION.index(rid))
                    self.dialog([(name, "Correct. Your mind is sharper than your blade.")])
        else:
            if for_bounty:
                b["p"] = 0
            self.dialog([(name, f"Wrong. The answer was: {opts[ans]}."), (name, "The wilds answer for me.")])
            if isinstance(self.scene, RealmWorld):
                for i in range(2 + PROGRESSION.index(rid) // 2):
                    e = self.scene.add_enemy(Enemy(self.player.pos + from_angle(i * 2.5 + 1, 150), random.choice(REALM_ENEMY_TYPES[rid]), REALM_DIFFICULTY[rid], REALM_COLORS[rid], 900))
                    e.provoked = True

    def start_side(self, rid):
        st = self.realm_states[rid]
        if st.side == "hidden":
            st.side = "active"
            self.banner("SIDE QUEST", REALM_INFO[rid]["side"], GOLD)

    def find_side_mark(self, rid, j):
        st = self.realm_states[rid]
        if st.side != "active" or st.side_found[j]:
            return
        st.side_found[j] = True
        n = sum(st.side_found)
        self.float_text(self.player.pos + V(0, -30), f"{REALM_INFO[rid]['side']}: {n}/3", GOLD, 1.8)
        burst(self.player.pos, GOLD, 24, (60, 160), .6, 3)
        if n >= 2 and isinstance(self.scene, RealmWorld):
            for k in range(2 + PROGRESSION.index(rid) // 2):
                e = self.scene.add_enemy(Enemy(self.player.pos + from_angle(k * 2.4, 140), random.choice(REALM_ENEMY_TYPES[rid]),
                                               REALM_DIFFICULTY[rid] * 1.1, REALM_COLORS[rid], 900))
                e.provoked = True
            self.float_text(self.player.pos + V(0, -55), "Guardians appear!", RED)
        if n >= 3:
            st.side = "return"
            self.banner("SIDE QUEST", f"Return to the {REALM_INFO[rid]['merchant']}", GOLD)

    def open_boss_journal(self, rid):
        info = REALM_INFO[rid]
        name = info["secret_boss"]
        pages = JOURNALS[rid]
        book = [(f"{info['adventurer']}'s Field Journal", JOURNAL_INTROS[rid])]
        for i, text in enumerate(pages):
            book.append((f"{name.title()} - Phase {['I', 'II', 'III', 'IV'][i]}", text))
        book.append(("Phase V - Unknown", PHASE5_UNKNOWN[rid]))
        if self.phase5_seen[rid]:
            book.append(("Your own notes", PHASE5_NOTES[rid]))
        self.book = {"pages": book, "page": 0, "color": REALM_COLORS[rid]}
        self.state = BOOK

    # ------------------------------------------------------------------
    # home NPCs
    # ------------------------------------------------------------------
    def talk_vale(self):
        tips = ["Every realm hides a merchant in its north-west corner, behind a ring of rock. Look for the one narrow gap.",
                "Those merchants know where the treasure maps are. Treasure groves hold relics - and relics change how you fight.",
                "Four relics are guarded by optional bosses behind hidden gates. Adventurers camp outside them; their journals are worth reading.",
                "Nobody has ever written down a fifth phase. If you see one, you'll be the first.",
                "The Null Compass turns a dash into a blink. The Cinderheart sets your blade on fire. Just stories... probably.",
                f"Dungeon progress: {self.dungeon_progress}/10 rooms. The guides in the hub open each room in turn."]
        self.dialog([("VALE", "Maps! Rumours! Unreliable directions!")] + [("VALE", t) for t in random.sample(tips, 3)])

    def talk_milo(self):
        best = f"Your best score: {self.arcade_best}." if self.arcade_best else "You haven't played yet!"
        self.dialog([("MILO", "Welcome to the arcade! Free to play, no gold needed - ever. Just skill."),
                     ("MILO", "Ember Gallery: click the glowing lanterns before they fade, avoid the ash skulls. 30 seconds."),
                     ("MILO", f"Bronze 15+, Silver 25+, Gold 35+. Every medal has a fixed prize. {best}")],
                    choices=[("Play Ember Gallery", self.start_arcade), ("Maybe later", None)])

    def start_arcade(self):
        self.arcade = {"time": 30.0, "score": 0, "targets": [], "spawn": 0.0, "done": False, "result": None, "hits": 0, "misses": 0}
        self.state = ARCADE

    def finish_arcade(self):
        a = self.arcade
        a["done"] = True
        score = a["score"]
        self.arcade_best = max(self.arcade_best, score)
        medal = "gold" if score >= 35 else "silver" if score >= 25 else "bronze" if score >= 15 else None
        reward = []
        if medal:
            gold = {"bronze": 10, "silver": 20, "gold": 35}[medal]
            self.player.gold += gold
            reward.append(f"+{gold} gold")
            if medal in ("silver", "gold"):
                self.player.inv.add(potion())
                reward.append("+1 potion")
            if medal == "gold" and "arcadestar" not in self.player.relics_owned:
                self.player.gain_relic("arcadestar")
                reward.append("Relic: Arcade Star Pin!")
            if medal not in self.arcade_medals:
                self.arcade_medals.append(medal)
        a["result"] = (medal, reward)

    # ------------------------------------------------------------------
    # shops
    # ------------------------------------------------------------------
    def open_shop(self, title, entries, accent=GOLD):
        self.shop = {"title": title, "entries": entries, "sel": 0, "mode": "buy", "accent": accent, "scroll": 0}
        self.state = SHOP

    @staticmethod
    def entry(item, price, currency="gold"):
        return {"item": item, "price": price, "currency": currency}

    def open_bram(self):
        e = self.entry
        entries = [e(Item("Iron Sword", "sword", 14), 260), e(Item("Iron Greatsword", "greatsword", 15), 360),
                   e(Item("Ashwood Bow", "bow", 13), 240), e(Item("Apprentice Staff", "staff", 13), 240),
                   e(Item("Iron Mail", "armor", 12), 300), e(Item("Steel Plate", "armor", 18), 700),
                   {"service": "reforge", "name": "Reforge selected weapon (+3 power)", "desc": "Hold the weapon in your hotbar first."},
                   {"service": "reforge_armor", "name": "Reforge worn armor (+3 defense)", "desc": "Strengthens your equipped armor."}]
        self.open_shop("BRAM'S FORGE", entries, EMBER)

    def open_pip(self):
        e = self.entry
        self.open_shop("PIP'S HERBS", [e(potion(), 55), e(potion(3), 150), e(potion(), 3, "embers")], GREEN)

    def open_wren(self):
        e = self.entry
        foods = [Item("Ember Stew", "food", 0, "regen", 1, 40), Item("Hunter's Pie", "food", 0, "might", 1, 60),
                 Item("Frostberry Tart", "food", 0, "swift", 1, 50), Item("Hearty Roast", "food", 0, "hearty", 1, 70)]
        self.open_shop("WREN'S KITCHEN", [e(f, int(f.value * 2.2)) for f in foods], ORANGE)

    def open_realm_shop(self, rid):
        e = self.entry
        entries = [e(kit_item(k), max(300, k[2] * 40)) for k in REALM_KITS[rid]] + [e(potion(), 60)]
        self.open_shop(f"{REALM_NAMES[rid]} SHOP", entries, REALM_COLORS[rid])

    def open_secret_shop(self, rid):
        e = self.entry
        entries = [e(Item(n, k, p, eff), price) for n, k, p, eff, price in SECRET_MERCHANT_STOCK[rid]] + [e(potion(2), 110)]
        self.open_shop(f"{REALM_INFO[rid]['merchant'].upper()}'S WARES", entries, PURPLE)

    def open_dungeon_shop(self):
        e = self.entry
        entries = []
        for unlock, kit in DUNGEON_KITS.items():
            if self.dungeon_progress >= unlock:
                entries += [e(kit_item(k), k[2] * 34) for k in kit]
        entries.append(e(potion(), 55))
        if len(entries) == 1:
            self.dialog([("QUARTERMASTER", "Clear Room 2 and I'll have Graveborn gear for you. Until then, potions only.")],
                        on_close=lambda: self.open_shop("DUNGEON ARMORY", entries, PURPLE))
            return
        self.open_shop("DUNGEON ARMORY", entries, PURPLE)

    def reforge_cost(self, item):
        return 140 + item.power * 20, 2 + item.power // 15

    def shop_buy(self, index):
        shop = self.shop
        entries = shop["entries"]
        if not 0 <= index < len(entries):
            return
        ent = entries[index]
        p = self.player
        if ent.get("service"):
            target = p.weapon() if ent["service"] == "reforge" else p.inv.armor
            if target is None:
                self.notify("Select a weapon in your hotbar first." if ent["service"] == "reforge" else "You aren't wearing armor.", RED)
                return
            gold, embers = self.reforge_cost(target)
            if p.gold < gold or p.embers < embers:
                self.notify(f"Need {gold} gold and {embers} embers.", RED)
                return
            if target.power >= 70:
                self.notify("Bram: 'That's as good as metal gets.'", ASH)
                return
            p.gold -= gold
            p.embers -= embers
            target.power += 3
            target.value = target.default_value()
            self.notify(f"{target.name} reforged to {target.power}!", GREEN)
            self.sound("level")
            return
        item = ent["item"]
        price = ent["price"]
        cur = ent.get("currency", "gold")
        have = p.gold if cur == "gold" else p.embers
        if have < price:
            self.notify(f"Not enough {cur}.", RED)
            return
        if not p.inv.add(item.copy()):
            self.notify("Your bag is full.", RED)
            return
        if cur == "gold":
            p.gold -= price
        else:
            p.embers -= price
        self.notify(f"Bought {item.name}" + (f" x{item.stack}" if item.stack > 1 else ""), GREEN)
        self.sound("pickup")

    def shop_sell(self, slot):
        p = self.player
        item = p.inv.slots[slot] if 0 <= slot < Inventory.SIZE else None
        if item is None:
            return
        price = max(1, int(item.value * .18))
        if item.stack > 1:
            item.stack -= 1
        else:
            p.inv.slots[slot] = None
        p.gold += price
        self.notify(f"Sold {item.name} for {price}g", GOLD)
        self.sound("pickup")

    # ------------------------------------------------------------------
    # dialogue
    # ------------------------------------------------------------------
    def dialog(self, lines, on_close=None, choices=None, on_choice_start=None):
        lines = [l for l in lines if l and l[1]]
        if not lines:
            return
        self.dialogue = {"lines": lines, "index": 0, "on_close": on_close, "choices": choices, "sel": 0, "on_choice_start": on_choice_start}
        self.state = DIALOGUE

    def dialog_advance(self, choice=None):
        d = self.dialogue
        if d is None:
            self.state = PLAYING
            return
        last = d["index"] >= len(d["lines"]) - 1
        if not last:
            d["index"] += 1
            return
        if d["choices"] and choice is None:
            choice = d["sel"]
        self.dialogue = None
        self.state = PLAYING
        if d["choices"]:
            label, action = d["choices"][int(clamp(choice, 0, len(d["choices"]) - 1))]
            if action is not None:
                if d.get("on_choice_start"):
                    d["on_choice_start"]()
                action()
        if d["on_close"]:
            d["on_close"]()

    # ------------------------------------------------------------------
    # combat events
    # ------------------------------------------------------------------
    def on_enemy_killed(self, enemy):
        if enemy.is_boss:
            return
        self.player.gain_xp(enemy.xp)
        self.bounty_kill(enemy)
        if not enemy.drops:
            return
        mult = (1.08 if self.player.has_relic("bellchime") else 1.0) * GOLD_RATE
        scale = getattr(enemy, "scale", 1.0)
        gold = int(round(random.randint(3, 9) * (1 + .6 * (scale - 1)) * mult * (2.5 if enemy.affix else 1)))
        if gold > 0 and random.random() < .8:
            self.loot.append(Loot(enemy.pos, "gold", max(1, gold)))
        r = random.random()
        if r < .06:
            self.loot.append(Loot(enemy.pos, "potion"))
        elif r < .12:
            self.loot.append(Loot(enemy.pos, "ember", 1))
        elif r < .22:
            self.loot.append(Loot(enemy.pos, "heart"))

    def on_boss_defeated(self, boss):
        kind = getattr(boss, "boss_kind", "")
        p = self.player
        self.sound("boss")
        if kind == "realm":
            rid = boss.rid
            st = self.realm_states[rid]
            first = not st.boss_defeated
            self.boss_deaths.pop(("realm", rid), None)
            st.boss_defeated = True
            gold = int(((600 + 450 * PROGRESSION.index(rid)) if first else 150 + 50 * PROGRESSION.index(rid)) * GOLD_RATE)
            p.gold += gold
            p.gain_xp((500 + 250 * PROGRESSION.index(rid)) if first else 150)
            p.embers += 3
            if first:
                armor = [k for k in REALM_KITS[rid] if k[1] == "armor"][0]
                self.give_item(kit_item(armor))
                if self.home_status.get(rid) != "done":
                    self.home_status[rid] = "ready"
                self.banner(f"{boss.name} DEFEATED", f"+{gold} gold - return home to {REALM_INFO[rid]['giver']}", GOLD, 4.0)
            else:
                self.banner(f"{boss.name} DEFEATED", f"+{gold} gold", GOLD, 3.0)
            self.autosave()
        elif kind == "secret":
            rid = boss.rid
            st = self.realm_states[rid]
            first = not st.secret_defeated
            self.boss_deaths.pop(("secret", rid), None)
            st.secret_defeated = True
            gold = int((SECRET_GOLD[rid] if first else SECRET_GOLD[rid] // 4) * GOLD_RATE)
            p.gold += gold
            p.gain_xp(900 + 300 * PROGRESSION.index(rid) if first else 250)
            relic = REALM_MAJOR_RELIC[rid]
            got = p.gain_relic(relic)
            if got:
                self.banner(f"{boss.name} DEFEATED", f"RELIC: {RELICS[relic]['name']}   +{gold} gold", GOLD, 5.0)
                self.dialog([("RELIC", f"You claimed the {RELICS[relic]['name']}!"), ("RELIC", RELICS[relic]["desc"]),
                             ("TIP", "Relics live in the four relic slots of your inventory (I). Click a relic to equip or unequip it.")])
            else:
                self.banner(f"{boss.name} DEFEATED", f"+{gold} gold", GOLD, 3.0)
            self.autosave()
        elif kind == "dungeon":
            first = boss.room >= self.dungeon_progress
            self.dungeon_progress = max(self.dungeon_progress, boss.room + 1)
            p.gain_xp((200 + boss.room * 90) if first else 60 + boss.room * 20)
            p.gold += int(((100 + boss.room * 60) if first else 30 + boss.room * 10) * GOLD_RATE)
            self.banner(f"{boss.name} DEFEATED", "Next room unlocked!" if first and boss.room < 9 else "Room cleared", GOLD, 3.0)
            self.autosave()
        elif kind == "mini":
            p.gain_xp(300)

    def on_player_death(self):
        if self.state == DEAD:
            return
        if not self.death_reason:
            self.death_reason = "The ash remembers."
        sc = self.scene
        if isinstance(sc, (RealmBossArena, SecretBossArena)):
            key = ("secret" if isinstance(sc, SecretBossArena) else "realm", sc.rid)
            self.boss_deaths[key] = self.boss_deaths.get(key, 0) + 1
            self.last_boss_death = key
        else:
            self.last_boss_death = None
        self.state = DEAD
        self.player.bow_charge = None

    def respawn(self):
        p = self.player
        lost = int(p.gold * .25)
        p.gold -= lost
        p.hp = p.max_hp
        p.burn = p.freeze = p.slow = 0
        p.invuln = 2.0
        p.buffs = {}
        self.death_reason = ""
        sc = self.scene
        self.state = PLAYING
        rid = getattr(sc, "rid", None)
        if isinstance(sc, (DungeonHub, DungeonRoom)):
            self.enter_dungeon_hub()
        elif isinstance(sc, (RealmBossArena, SecretBossArena)):
            self.go_realm(rid, at="secret" if isinstance(sc, SecretBossArena) else "boss")
            n = self.boss_deaths.get(("secret" if isinstance(sc, SecretBossArena) else "realm", rid), 0)
            if n >= 2:
                self.notify("You may accept the Keeper's aid at the gate (defeated twice).", GREEN)
        elif rid is not None and not isinstance(sc, HomeWorld):
            self.go_realm(rid)
        else:
            self.change_scene(self.get_home(), self.get_home().spawn())
        if lost:
            self.notify(f"You lost {lost} gold.", GOLD)

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def nearest_interactable(self, extra=0):
        best, bd = None, 1e9
        p = self.player.pos
        for it in self.scene.interactables:
            if not it.is_visible():
                continue
            d = dist(p, it.pos)
            if d < it.radius + extra and d < bd:
                best, bd = it, d
        return best

    def interact(self):
        it = self.nearest_interactable()
        if it is not None and it.action:
            it.action()

    def click_interact(self, world_pos):
        p = self.player.pos
        for it in self.scene.interactables:
            if it.is_visible() and dist(world_pos, it.pos) < 36 and dist(p, it.pos) < it.radius + 50:
                if it.action:
                    it.action()
                return True
        return False


MERCHANT_HINTS = {
    EMBER_ID: "They say the old forge-hermit still hides where the north-west rocks stand too neatly in a circle. Some stone there is only a memory of stone - lean on the side that faces the heart of the realm.",
    FROZEN_ID: "A scribe is rumoured to wait in the far west, inside a ring of ice. Part of that wall is only a reflection. Walk at it from the side that looks toward the middle of the world.",
    VOID_ID: "A trader hides in a silent pocket on the west edge of the station, behind a hologram of a wall. It faces the core. Walk into it.",
    STARFALL_ID: "The cartographer keeps a ring of cloud-stone on the far eastern shelf. One stretch of it is painted on. Look for the side turned to the centre of the sky.",
}

JOURNAL_INTROS = {
    EMBER_ID: "I'm Kael. They call me Ashbound because I keep walking back into the fire. Everything below is what we learned about the Ashen Behemoth - paid for in burns.",
    FROZEN_ID: "Seren the Mirrorwalker. I have crossed every frozen lake in this realm, and only one of them looked back at me. These are my notes on the Mirror Warden.",
    VOID_ID: "Veyra, Voidrunner. If you are reading this, you found the gate. These are the notes of six crews who went after the Null Maw. Four came back.",
    STARFALL_ID: "Orin, Star-Seeker. I have charted every star that fell on this realm except one: the machine at the heart of the sky. Here is what I know of the Astral Clockwork.",
}
JOURNALS = {
    EMBER_ID: ["The hunt. It closes distance, slams the ground and throws fire in fans. Keep moving - a ring of flame always follows the slam.",
               "The Eruption. Volcanoes burst from the arena and leave lasting lava. Never more than two at once: when a third wakes, the oldest dies. They spit fire, so don't hug them.",
               "Four Flames. It plants itself in the centre and four great beams wheel around it. Fire comes from the walls too. When the flames gutter, its core is open - that is the only time it really bleeds.",
               "Inferno Hunt. It chases you down, leaving lava where it walks, while ash bursts rain on your position. It stops giving you comfortable space."],
    FROZEN_ID: ["Four reflections guard the arena, each with a gem. Red rushes you. Blue throws seeking magic. Yellow fires from range without pause. Purple is slow, but it barely notices your blows. None of them is the true Warden.",
                "When the reflections fall, the real Warden rises from the ice and asks: 'You thought it'd be that easy?' Then the ice storm: shard fans, spikes under your feet, freezing orbs.",
                "The Mirror Realm. Mirrors fill the chamber and every one of them fires at you. Copies of the Warden mirror your movements. Break the mirrors - while three stand, it shrugs off half your damage.",
                "The Frozen Arena. The floor turns to ice and you slide. Walls of ice rise and fall. It charges in straight lines - watch for the red line and step aside early."],
    VOID_ID: ["Void Wells. Four wells drag you towards their centre. Touching a core hurts. The Maw floats between them throwing seeking orbs.",
              "The Vanishing World. Floor sections crack, warn and disappear. Fall through and you'll be thrown back onto solid ground, hurt. Portals open and fire from places the Maw is not.",
              "The Teleporter. Every five seconds it vanishes and reappears somewhere chosen - behind you, at the worst range - and cuts two lines of void through where you're about to be.",
              "Black Hole Collapse. Singularities appear and pull at everything. The pull can be outrun. The centre cannot. Anyone pulled all the way in is simply gone."],
    STARFALL_ID: ["The Clockwork Duel. Its hands tick around the arena - step, step, step - never sweeping, always jumping. Rings of light pulse outwards. Count the ticks.",
                  "Geometry Shift. Barriers appear and the whole arena turns ninety degrees at a time. It warns you first - the red outlines show where the walls will land.",
                  "Starfall. Huge stars fall where you are standing. The circle tells you where; the star tells you when.",
                  "Clockwork Eclipse. Giant golden rings expand from the centre with two gaps. Find the gap. The arena keeps turning, and sometimes it rewinds."],
}
PHASE5_UNKNOWN = {
    EMBER_ID: "PHASE V - UNKNOWN. Every expedition that reached the fourth phase turned back, fell, or lost the trail. I have never seen what comes next. If you discover it, write it here.",
    FROZEN_ID: "PHASE V - UNKNOWN. The Warden's light-blue core was still glowing when the last survivor escaped. Nobody knows what happens after the frozen arena breaks apart.",
    VOID_ID: "PHASE V - UNKNOWN. The maps call it Event Horizon, but no surviving explorer has confirmed what that name means. The final chamber is still a blank page.",
    STARFALL_ID: "PHASE V - UNKNOWN. The final page only says FALLING SKY. No adventurer has returned with a complete description of what the Clockwork becomes.",
}
PHASE5_NOTES = {
    EMBER_ID: "HEART OF THE MOUNTAIN. (written in your hand) The arena collapses into lava, cell by cell. Meteors fall. It stands still at the centre - and every few seconds its core splits open. That is the moment.",
    FROZEN_ID: "SHATTERED REFLECTION. (written in your hand) The floor breaks into pits, three copies mirror every step you take, and the Warden blinks between attacks from every earlier phase. Unpredictable - but never unfair.",
    VOID_ID: "EVENT HORIZON. (written in your hand) Everything at once: wells, vanishing floor, portals, black holes and teleport strikes. There is very little safe ground. Keep moving and never stop reading the floor.",
    STARFALL_ID: "FALLING SKY. (written in your hand) The arena's floor falls away into open sky. Only drifting platforms remain, and they jump every few seconds. Stars fall, and the Clockwork spirals its light at you.",
}


# ============================================================
# GAME: update, drawing, UI, input, saving
# ============================================================

INV_PANEL = R(70, 36, 820, 568)
INV_SLOT = 58
INV_GAP = 8
INV_ORIGIN = (100, 128)
ARMOR_RECT = R(730, 128, 64, 64)
RELIC_SLOT_RECTS = [R(100 + i * 74, 362, 62, 62) for i in range(4)]
HOTBAR_SLOT = 50
HOTBAR_X = (WIDTH - 9 * (HOTBAR_SLOT + 4)) // 2
HOTBAR_Y = HEIGHT - 58


def inv_slot_rect(i):
    col, row = i % 9, i // 9
    y = INV_ORIGIN[1] + row * (INV_SLOT + INV_GAP) + (10 if row > 0 else 0)
    return R(INV_ORIGIN[0] + col * (INV_SLOT + INV_GAP), y, INV_SLOT, INV_SLOT)


def owned_relic_rect(i):
    return R(420 + (i % 7) * 58, 362 + (i // 7) * 58, 50, 50)


class Game(GameCore):
    def __init__(self):
        super().__init__()
        self.lmb_attack = False
        self.menu_confirm = False
        self.show_help = False
        self.pause_index = 0
        self.has_save = os.path.exists(SAVE_FILE) or os.path.exists(LEGACY_SAVE_FILE)

    # ==================================================================
    # SAVE / LOAD
    # ==================================================================
    def save_data(self):
        p = self.player
        loc = {"scene": self.last_hub[0], "rid": self.last_hub[1], "pos": None}
        if self.scene is not None and self.scene.hub and isinstance(self.scene, (HomeWorld, RealmWorld)):
            loc["pos"] = [p.pos.x, p.pos.y]
        return {
            "version": SAVE_VERSION,
            "player": {"level": p.level, "xp": p.xp, "base_max_hp": p.base_max_hp, "hp": p.hp, "gold": p.gold, "embers": p.embers,
                       "inventory": [it.to_dict() if it else None for it in p.inv.slots], "selected": p.inv.selected,
                       "armor": p.inv.armor.to_dict() if p.inv.armor else None, "relics_owned": list(p.relics_owned),
                       "relic_slots": list(p.relic_slots), "treasure_maps": list(p.treasure_maps)},
            "home_status": {str(k): v for k, v in self.home_status.items()},
            "realms": {str(k): st.to_dict() for k, st in self.realm_states.items()},
            "dungeon_progress": self.dungeon_progress,
            "phase5_seen": list(self.phase5_seen),
            "arcade_best": self.arcade_best,
            "arcade_medals": list(self.arcade_medals),
            "victory_seen": self.victory_seen,
            "riddle_log": [list(r) for r in self.riddle_log],
            "location": loc,
        }

    def write_save(self, quiet=False):
        if self.player is None or self.scene is None:
            return False
        try:
            data = self.save_data()
            tmp = SAVE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, SAVE_FILE)
            self.has_save = True
            if not quiet:
                self.notify("Game saved.", GREEN)
            return True
        except Exception:
            log_error("save")
            self.notify("Could not save the game (see ashfall_errors.log).", RED)
            return False

    def autosave(self):
        if self.state in (PLAYING, DIALOGUE, SHOP, INVENTORY, BOOK, JOURNAL, VICTORY):
            self.write_save(quiet=True)

    def load_game(self):
        path = SAVE_FILE if os.path.exists(SAVE_FILE) else None
        if path is None:
            if os.path.exists(LEGACY_SAVE_FILE):
                return self.import_legacy()
            self.notify("No save file found.", RED)
            return False
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.apply_save(data)
            self.notify("Game loaded.", GREEN)
            return True
        except Exception:
            log_error("load")
            try:
                os.replace(path, path + ".corrupt")
            except Exception:
                pass
            self.notify("Save file was damaged (kept as .corrupt) - starting fresh.", RED)
            self.new_game()
            return False

    def apply_save(self, data):
        self.reset_progress()
        pd = data.get("player", {}) or {}
        p = self.player
        p.level = max(1, int(pd.get("level", 1)))
        p.xp = max(0, int(pd.get("xp", 0)))
        p.base_max_hp = max(100, int(pd.get("base_max_hp", 120 + 12 * (p.level - 1))))
        p.gold = max(0, int(pd.get("gold", 0)))
        p.embers = max(0, int(pd.get("embers", 0)))
        inv = pd.get("inventory")
        if isinstance(inv, list):
            p.inv.slots = [Item.from_dict(d) if d else None for d in (inv + [None] * Inventory.SIZE)[:Inventory.SIZE]]
        p.inv.select(int(pd.get("selected", 0) or 0))
        p.inv.armor = Item.from_dict(pd.get("armor")) if pd.get("armor") else None
        if p.inv.armor is not None and p.inv.armor.kind != "armor":
            p.inv.add(p.inv.armor)
            p.inv.armor = None
        p.relics_owned = [r for r in pd.get("relics_owned", []) if r in RELICS]
        slots = [r if r in p.relics_owned else None for r in (list(pd.get("relic_slots", [])) + [None] * 4)[:4]]
        seen = set()
        for i, r in enumerate(slots):
            if r in seen:
                slots[i] = None
            elif r:
                seen.add(r)
        p.relic_slots = slots
        p.treasure_maps = [m for m in pd.get("treasure_maps", []) if m in TREASURE_MAPS.values()]
        p.hp = clamp(float(pd.get("hp", p.max_hp)), 1, p.max_hp)
        hs = data.get("home_status", {}) or {}
        for rid in range(4):
            v = hs.get(str(rid))
            self.home_status[rid] = v if v in ("active", "ready", "done") else None
        realms = data.get("realms", {}) or {}
        for rid in range(4):
            self.realm_states[rid].load(realms.get(str(rid)))
        self.dungeon_progress = int(clamp(int(data.get("dungeon_progress", 0) or 0), 0, 10))
        p5 = list(data.get("phase5_seen", [])) + [False] * 4
        self.phase5_seen = [bool(x) for x in p5[:4]]
        self.arcade_best = int(data.get("arcade_best", 0) or 0)
        self.arcade_medals = [m for m in data.get("arcade_medals", []) if m in ("bronze", "silver", "gold")]
        self.victory_seen = bool(data.get("victory_seen", False))
        self.riddle_log = []
        for r in (data.get("riddle_log", []) or [])[-24:]:
            if isinstance(r, (list, tuple)) and len(r) == 3 and isinstance(r[1], str) and isinstance(r[2], str):
                self.riddle_log.append([int(r[0]) if str(r[0]).isdigit() else 0, r[1], r[2]])
        self.home = HomeWorld()
        loc = data.get("location", {}) or {}
        pos = loc.get("pos")
        pos = V(pos) if isinstance(pos, list) and len(pos) == 2 else None
        rid = loc.get("rid")
        if loc.get("scene") == "realm" and rid in (0, 1, 2, 3) and self.home_quest_status(rid) in ("active", "ready", "done"):
            realm = self.get_realm(rid)
            self.change_scene(realm, pos if pos is not None else realm.spawn())
        else:
            self.change_scene(self.home, pos if pos is not None else self.home.spawn())
        self.state = PLAYING

    def import_legacy(self):
        """Best-effort import of a save from the previous version of Ashfall."""
        try:
            with open(LEGACY_SAVE_FILE, "r", encoding="utf-8") as fh:
                old = json.load(fh)
            self.new_game()
            self.dialogue = None
            self.state = PLAYING
            p = self.player
            p.level = max(1, int(old.get("level", 1)))
            p.base_max_hp = 120 + 12 * (p.level - 1)
            p.hp = p.max_hp
            p.gold = int(old.get("gold", 0))
            p.embers = int(old.get("embers", 0))
            items = [Item.from_dict(d) for d in old.get("inventory", []) if d]
            if items:
                p.inv.slots = [None] * Inventory.SIZE
                for it in items:
                    if it:
                        p.inv.add(it)
            name_to_key = {v["name"]: k for k, v in RELICS.items()}
            for name in old.get("relics", []):
                if name in name_to_key:
                    p.gain_relic(name_to_key[name])
            p.treasure_maps = [m for m in old.get("treasure_maps", []) if m in TREASURE_MAPS.values()]
            mapping = {"ember": EMBER_ID, "frost": FROZEN_ID, "heaven": STARFALL_ID, "space": VOID_ID}
            for key, rid in mapping.items():
                v = (old.get("quest_progress") or {}).get(key, False)
                if v is True or v == "ready":
                    st = self.realm_states[rid]
                    for line in st.lines:
                        line.started = line.complete = True
                        line.step = len(line.tasks)
                    st.boss_defeated = True
                    self.home_status[rid] = "done" if v is True else "ready"
                elif v == "active":
                    self.home_status[rid] = "active"
            self.dungeon_progress = int(clamp(int(old.get("dungeon_room_progress", 0) or 0), 0, 10))
            self.write_save(quiet=True)
            self.notify("Imported your save from the previous version.", GREEN)
            return True
        except Exception:
            log_error("legacy import")
            self.new_game()
            return False

    # ==================================================================
    # UPDATE
    # ==================================================================
    def update(self, dt):
        self.time += dt
        if self.toast:
            self.toast[2] -= dt
            if self.toast[2] <= 0:
                self.toast = None
        if self.state == MENU:
            for e in self.menu_embers:
                e[1] -= e[2] * dt
                if e[1] < -5:
                    e[0], e[1] = random.randrange(WIDTH), HEIGHT + 5
            return
        if self.state == ARCADE:
            self.update_arcade(dt)
            return
        for b in self.banners:
            b[3] -= dt
        self.banners = [b for b in self.banners if b[3] > 0]
        self.fade = max(0, self.fade - dt * 2.5)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.texts = [t for t in self.texts if t.update(dt)]
        if self.state != PLAYING:
            return
        scene = self.scene
        p = self.player
        if self.lmb_attack and pygame.mouse.get_pressed()[0]:
            sel = p.selected()
            if sel is None or sel.kind in ("sword", "greatsword", "staff"):
                p.use_primary()
        p.update(dt, scene)
        if self.state != PLAYING:
            return
        scene.update(dt)
        self.projectiles = [pr for pr in self.projectiles if pr.update(dt, scene)]
        self.loot = [l for l in self.loot if l.update(dt)]
        self.flash_rings = [[a, b, c, t - dt] for a, b, c, t in self.flash_rings if t - dt > 0]
        self.shake_time = max(0, self.shake_time - dt)
        if not scene.fixed_camera:
            target = V(clamp(p.pos.x - WIDTH / 2, 0, max(0, scene.width - WIDTH)),
                       clamp(p.pos.y - HEIGHT / 2, 0, max(0, scene.height - HEIGHT)))
            self.cam += (target - self.cam) * min(1, dt * 8)
        else:
            self.cam = V()

    def update_arcade(self, dt):
        a = self.arcade
        if a is None:
            self.state = PLAYING
            return
        if a["done"]:
            return
        a["time"] -= dt
        a["spawn"] -= dt
        if a["spawn"] <= 0:
            a["spawn"] = max(.32, .7 - (30 - a["time"]) * .012)
            bad = random.random() < .22
            life = random.uniform(1.0, 1.6) * (1 - (30 - a["time"]) * .012)
            a["targets"].append({"pos": V(random.randint(170, 790), random.randint(150, 500)), "life": life, "max": life, "bad": bad})
        for t in a["targets"]:
            t["life"] -= dt
            if t["life"] <= 0 and not t["bad"]:
                a["misses"] += 1
        a["targets"] = [t for t in a["targets"] if t["life"] > 0]
        if a["time"] <= 0:
            a["targets"] = []
            self.finish_arcade()

    def arcade_click(self, pos):
        a = self.arcade
        if a is None:
            return
        if a["done"]:
            self.arcade = None
            self.state = PLAYING
            return
        for t in reversed(a["targets"]):
            r = 10 + 18 * t["life"] / t["max"]
            if dist(pos, t["pos"]) < r + 4:
                a["targets"].remove(t)
                if t["bad"]:
                    a["score"] = max(0, a["score"] - 2)
                else:
                    a["score"] += 1
                    a["hits"] += 1
                self.sound("pickup")
                return

    # ==================================================================
    # DRAW
    # ==================================================================
    def draw(self, surf):
        if self.state == MENU:
            self.draw_menu(surf)
            return
        scene = self.scene
        cam = V(self.cam)
        if self.shake_time > 0:
            cam += V(random.uniform(-5, 5), random.uniform(-5, 5)) * min(1, self.shake_time * 4)
        scene.draw_ground(surf, cam)
        scene.draw_hazards(surf, cam)
        scene.draw_objects(surf, cam)
        for l in self.loot:
            l.draw(surf, cam)
        for e in sorted(scene.enemies, key=lambda e: e.pos.y):
            if e.alive:
                e.draw(surf, cam)
        for pr in self.projectiles:
            pr.draw(surf, cam)
        self.player.draw(surf, cam)
        for pt in self.particles:
            pt.draw(surf, cam)
        for pos, radius, color, t in self.flash_rings:
            pygame.draw.circle(surf, color, ipos(pos - cam), int(radius * (1 - t / .35) + 10), 3)
        scene.draw_top(surf, cam)
        for t in self.texts:
            t.draw(surf, cam)
        if self.state in (PLAYING, DEAD):
            self.draw_prompt(surf, cam)
        self.draw_hud(surf)
        if self.fade > 0:
            alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, int(255 * self.fade))
        st = self.state
        if st == DIALOGUE:
            self.draw_dialogue(surf)
        elif st == SHOP:
            self.draw_shop(surf)
        elif st == INVENTORY:
            self.draw_inventory(surf)
        elif st == BOOK:
            self.draw_book(surf)
        elif st == JOURNAL:
            self.draw_journal(surf)
        elif st == PAUSE:
            self.draw_pause(surf)
        elif st == DEAD:
            self.draw_dead(surf)
        elif st == VICTORY:
            self.draw_victory(surf)
        elif st == ARCADE:
            self.draw_arcade(surf)
        if self.show_help:
            self.draw_help(surf)
        if self.toast:
            text, color, t = self.toast
            img_w = get_font(20).size(text)[0]
            rr = R(WIDTH // 2 - img_w // 2 - 14, 132, img_w + 28, 30)
            panel(surf, rr, color)
            draw_text(surf, text, (WIDTH // 2, 138), color, 20, center=True)

    # ------------------------------------------------------------------
    def draw_prompt(self, surf, cam):
        it = self.nearest_interactable()
        if it is None:
            return
        label = it.get_label()
        if not label:
            return
        text = f"[E] {label}"
        w = get_font(18).size(text)[0] + 16
        p = it.pos - cam
        rr = R(int(p.x - w / 2), int(p.y - 92), w, 24)
        rr.x = clamp(rr.x, 4, WIDTH - w - 4)
        rr.y = clamp(rr.y, 90, HEIGHT - 90)
        panel(surf, rr, GOLD, (14, 14, 20), 220)
        draw_text(surf, text, (rr.centerx, rr.y + 4), GOLD, 18, center=True)

    def draw_hud(self, surf):
        p = self.player
        # vitals
        panel(surf, R(10, 8, 258, 78), EDGE, UI_BG, 200)
        draw_text(surf, f"LV {p.level}", (20, 14), GOLD, 22)
        hp_frac = clamp(p.hp / p.max_hp, 0, 1)
        pygame.draw.rect(surf, (40, 30, 34), (74, 16, 184, 16))
        pygame.draw.rect(surf, RED if hp_frac > .3 else (255, 60, 60), (75, 17, int(182 * hp_frac), 14))
        draw_text(surf, f"{int(math.ceil(p.hp))} / {p.max_hp}", (166, 17), WHITE, 16, center=True)
        need = xp_needed(p.level)
        pygame.draw.rect(surf, (30, 32, 44), (74, 37, 184, 6))
        pygame.draw.rect(surf, BLUE, (75, 38, int(182 * clamp(p.xp / need, 0, 1)), 4))
        draw_text(surf, f"{p.gold}g", (20, 50), GOLD, 20)
        draw_text(surf, f"{p.embers} ember", (100, 50), EMBER, 20)
        draw_text(surf, f"{p.inv.count(kind='potion')} pot", (190, 50), GREEN, 20)
        bx = 20
        for name, t in p.buffs.items():
            draw_text(surf, f"{name} {int(t)}s", (bx, 70), ORANGE, 15)
            bx += 62
        # objective
        text, target = self.scene.objective()
        title = self.scene.title
        if isinstance(self.scene, (HomeWorld, RealmWorld)) and REALM_NAMES.count(title):
            dgr = self.player.level - REALM_RECOMMENDED_LEVEL[self.scene.rid]
            tag = "LETHAL" if dgr <= -5 else "HARD" if dgr < 0 else "FAIR" if dgr <= 3 else "EASY"
            title = f"{title}  x{REALM_DIFFICULTY[self.scene.rid]:g} {tag}"
        panel(surf, R(WIDTH - 360, 8, 350, 64), self.scene.accent, UI_BG, 200)
        draw_text(surf, title[:44], (WIDTH - 350, 13), self.scene.accent, 18)
        lines = wrap_text(text or "", 17, 330)[:2]
        for i, line in enumerate(lines):
            draw_text(surf, line, (WIDTH - 350, 33 + i * 17), WHITE, 17)
        if target is not None:
            self.draw_compass(surf, target)
        if isinstance(self.scene, RealmWorld):
            st_ = self.realm_states[self.scene.rid]
            for k, q in enumerate(st_.active_bounties()[:3]):
                draw_text(surf, f"Bounty: {q['name']} {self.bounty_progress_text(q, st_.bstate(q['id']))}", (WIDTH - 350, 78 + k * 16), (210, 190, 120), 14)
        # boss bar
        boss = None
        for e in self.scene.enemies:
            if e.alive and e.is_boss and getattr(e, "intro", 0) <= 0:
                if not (isinstance(e, MirrorWarden) and not e.revealed):
                    boss = e
                    break
        if isinstance(self.scene, SecretBossArena) and isinstance(self.scene.boss, MirrorWarden) and not self.scene.boss.revealed:
            refl = [r for r in self.scene.boss.reflections if r.alive]
            draw_text(surf, f"FALSE WARDENS REMAINING: {len(refl)}", (WIDTH // 2, HEIGHT - 128), ICE, 20, center=True)
        if boss is not None:
            w = 520
            x = WIDTH // 2 - w // 2
            by = HEIGHT - 118
            label = boss.name
            if boss.phase > 1 or getattr(boss, "phase_names", ()):
                names = getattr(boss, "phase_names", ())
                label += f"   -   PHASE {boss.phase}" + (f": {names[boss.phase - 1]}" if boss.phase - 1 < len(names) else "")
            draw_text(surf, label, (WIDTH // 2, by - 20), boss.color, 19, center=True)
            pygame.draw.rect(surf, (20, 18, 24), (x, by, w, 12))
            pygame.draw.rect(surf, boss.color if not boss.immune else ASH, (x + 2, by + 2, int((w - 4) * boss.ratio()), 8))
            pygame.draw.rect(surf, WHITE, (x, by, w, 12), 1)
            ths = (.75, .5, .25) if isinstance(boss, MirrorWarden) else boss.thresholds
            for th in ths:
                pygame.draw.line(surf, WHITE, (x + int(w * th), by - 2), (x + int(w * th), by + 14), 1)
        # hotbar
        for i in range(9):
            r = R(HOTBAR_X + i * (HOTBAR_SLOT + 4), HOTBAR_Y, HOTBAR_SLOT, HOTBAR_SLOT)
            panel(surf, r, GOLD if i == p.inv.selected else EDGE, UI_BG, 220, 2 if i != p.inv.selected else 3)
            item = p.inv.slots[i]
            if item:
                draw_item_icon(surf, item, r.inflate(-8, -8))
                if item.stack > 1:
                    draw_text(surf, str(item.stack), (r.right - 4, r.bottom - 17), WHITE, 16, right=True)
            draw_text(surf, str(i + 1), (r.x + 3, r.y + 1), ASH, 14)
        sel = p.selected()
        if sel:
            draw_text(surf, f"{sel.name}  -  {sel.stat_line()}", (WIDTH // 2, HOTBAR_Y - 20), sel.color, 17, center=True)
        # relic slots + cooldowns
        rx = HOTBAR_X + 9 * (HOTBAR_SLOT + 4) + 10
        for i, key in enumerate(p.relic_slots):
            r = R(rx + i * 34, HOTBAR_Y + 10, 30, 30)
            panel(surf, r, RELICS[key]["color"] if key else EDGE, UI_BG, 200, 1)
            if key:
                draw_relic_icon(surf, key, r)
        if p.has_relic("mirrorstep"):
            r = R(rx, HOTBAR_Y - 22, 136, 16)
            pygame.draw.rect(surf, (30, 34, 44), r)
            frac = 1 - p.nova_cd / 12.0
            pygame.draw.rect(surf, ICE if p.nova_cd <= 0 else (90, 120, 140), (r.x, r.y, int(r.width * frac), r.height))
            draw_text(surf, "R: FROST NOVA" if p.nova_cd <= 0 else f"NOVA {p.nova_cd:.0f}s", (r.centerx, r.y + 1), BLACK if p.nova_cd <= 0 else WHITE, 15, center=True, shadow=False)
        dash_r = R(HOTBAR_X - 56, HOTBAR_Y + 10, 46, 30)
        panel(surf, dash_r, PURPLE if p.has_relic("nullcompass") else BLUE, UI_BG, 200, 1)
        frac = 1 - p.dash_cd / .9 if p.dash_cd > 0 else 1
        pygame.draw.rect(surf, PURPLE if p.has_relic("nullcompass") else BLUE, (dash_r.x + 2, dash_r.bottom - 6, int((dash_r.width - 4) * clamp(frac, 0, 1)), 4))
        draw_text(surf, "BLINK" if p.has_relic("nullcompass") else "DASH", (dash_r.centerx, dash_r.y + 4), WHITE, 15, center=True)
        # banner
        if self.banners:
            title, sub, color, t, total = self.banners[0]
            a = clamp(min(t, total - t) * 3, 0, 1)
            if a > 0:
                y = 168
                alpha_rect(surf, R(0, y - 10, WIDTH, 84), BLACK, int(150 * a))
                draw_text(surf, title, (WIDTH // 2, y), mix(BLACK, color, a), 44, center=True)
                if sub:
                    draw_text(surf, sub, (WIDTH // 2, y + 44), mix(BLACK, WHITE, a), 22, center=True)
        # low health vignette
        if hp_frac < .3 and self.state == PLAYING:
            a = int(70 * (1 - hp_frac / .3) * (0.6 + 0.4 * math.sin(self.time * 6)))
            for k in range(4):
                alpha_rect(surf, R(0, 0, WIDTH, 18 + k * 8), (160, 0, 0), a // 3)
                alpha_rect(surf, R(0, HEIGHT - 18 - k * 8, WIDTH, 18 + k * 8), (160, 0, 0), a // 3)

    def draw_compass(self, surf, target):
        sp = V(target) - self.cam
        if 30 < sp.x < WIDTH - 30 and 100 < sp.y < HEIGHT - 80:
            pulse = 4 + math.sin(self.time * 5) * 3
            pygame.draw.polygon(surf, GOLD, [(sp.x, sp.y - 46 - pulse), (sp.x - 8, sp.y - 60 - pulse), (sp.x + 8, sp.y - 60 - pulse)])
            return
        center = V(WIDTH / 2, HEIGHT / 2)
        d = sp - center
        if d.length() == 0:
            return
        d = d.normalize()
        edge = V(clamp(center.x + d.x * 600, 40, WIDTH - 40), clamp(center.y + d.y * 400, 110, HEIGHT - 90))
        a = math.atan2(d.y, d.x)
        pts = [edge + from_angle(a, 18), edge + from_angle(a + 2.5, 12), edge + from_angle(a - 2.5, 12)]
        pygame.draw.polygon(surf, GOLD, [ipos(q) for q in pts])
        pygame.draw.polygon(surf, BLACK, [ipos(q) for q in pts], 2)
        meters = int(dist(self.player.pos, target) / TILE)
        draw_text(surf, f"{meters}m", (edge.x, edge.y + 14), GOLD, 15, center=True)

    # ------------------------------------------------------------------
    def draw_dialogue(self, surf):
        d = self.dialogue
        if d is None:
            return
        speaker, text = d["lines"][d["index"]]
        box = R(50, HEIGHT - 196, WIDTH - 100, 140)
        panel(surf, box, GOLD, (10, 11, 16), 240, 2)
        draw_text(surf, speaker, (box.x + 20, box.y + 12), GOLD, 24)
        for i, line in enumerate(wrap_text(text, 22, box.width - 40)[:4]):
            draw_text(surf, line, (box.x + 20, box.y + 42 + i * 22), WHITE, 22)
        last = d["index"] >= len(d["lines"]) - 1
        if last and d["choices"]:
            n = len(d["choices"])
            for i, (label, _) in enumerate(d["choices"]):
                r = R(box.right - 300, box.y - 40 * (n - i) - 6, 290, 34)
                sel = i == d["sel"]
                panel(surf, r, GOLD if sel else EDGE, (24, 26, 36) if not sel else (50, 44, 30), 240)
                draw_text(surf, f"{i + 1}. {label}", (r.x + 12, r.y + 8), GOLD if sel else WHITE, 20)
            draw_text(surf, "1-4 / arrows + E or click to choose", (box.right - 20, box.bottom - 22), ASH, 16, right=True)
        else:
            draw_text(surf, f"E / Space / Click  continue  ({d['index'] + 1}/{len(d['lines'])})", (box.right - 20, box.bottom - 22), ASH, 16, right=True)

    def dialogue_choice_rects(self):
        d = self.dialogue
        if not d or not d["choices"]:
            return []
        box = R(50, HEIGHT - 196, WIDTH - 100, 140)
        n = len(d["choices"])
        return [R(box.right - 300, box.y - 40 * (n - i) - 6, 290, 34) for i in range(n)]

    # ------------------------------------------------------------------
    def draw_book(self, surf):
        b = self.book
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 170)
        book = R(110, 70, 740, 500)
        pygame.draw.rect(surf, (90, 60, 40), book.inflate(16, 16))
        pygame.draw.rect(surf, PARCHMENT, book)
        pygame.draw.line(surf, (170, 150, 110), (book.centerx, book.top + 10), (book.centerx, book.bottom - 10), 2)
        pages = b["pages"]
        i = b["page"]
        for side, idx in ((0, i), (1, i + 1)):
            if idx >= len(pages):
                continue
            title, text = pages[idx]
            x = book.x + 30 + side * 370
            draw_text(surf, title, (x, book.y + 26), INK if "UNKNOWN" not in text[:16] else (150, 30, 30), 22, shadow=False)
            pygame.draw.line(surf, (170, 150, 110), (x, book.y + 52), (x + 320, book.y + 52), 1)
            for k, line in enumerate(wrap_text(text, 20, 320)[:17]):
                draw_text(surf, line, (x, book.y + 66 + k * 22), INK, 20, shadow=False)
            draw_text(surf, str(idx + 1), (x + 160, book.bottom - 30), (130, 110, 80), 18, center=True, shadow=False)
        draw_text(surf, "Left/Right or A/D: turn pages      ESC/E: close", (WIDTH // 2, 588), WHITE, 18, center=True)

    # ------------------------------------------------------------------
    def draw_inventory(self, surf):
        p = self.player
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 160)
        panel(surf, INV_PANEL, GOLD, UI_BG, 245, 3)
        draw_text(surf, "INVENTORY", (100, 50), GOLD, 40)
        draw_text(surf, "Drag to move  |  Right-click: equip / use  |  Click a relic to equip it  |  I or ESC: close", (100, 88), ASH, 16)
        draw_text(surf, "HOTBAR", (100, 112), ASH, 15)
        mouse = pygame.mouse.get_pos()
        hover = None
        for i in range(Inventory.SIZE):
            r = inv_slot_rect(i)
            sel = i == p.inv.selected
            panel(surf, r, GOLD if sel else EDGE, UI_BG2, 255, 3 if sel else 1)
            item = p.inv.slots[i]
            if item and not (self.drag and self.drag[0] == "slot" and self.drag[1] == i):
                draw_item_icon(surf, item, r.inflate(-10, -10))
                if item.stack > 1:
                    draw_text(surf, str(item.stack), (r.right - 4, r.bottom - 17), WHITE, 16, right=True)
                pygame.draw.rect(surf, item.color, r, 1)
            if r.collidepoint(mouse) and item:
                hover = ("item", item)
        # armor
        panel(surf, ARMOR_RECT, GOLD, UI_BG2, 255)
        draw_text(surf, "ARMOR", (ARMOR_RECT.centerx, ARMOR_RECT.y - 18), GOLD, 16, center=True)
        if p.inv.armor and not (self.drag and self.drag[0] == "armor"):
            draw_item_icon(surf, p.inv.armor, ARMOR_RECT.inflate(-10, -10))
            if ARMOR_RECT.collidepoint(mouse):
                hover = ("item", p.inv.armor)
        weapon = p.weapon()
        stats = [f"Health  {int(p.hp)}/{p.max_hp}", f"Defense  {p.armor_value}", f"Damage x{p.damage_mult():.2f}",
                 f"Speed  {int(p.move_speed())}", f"Weapon  {weapon.name if weapon else 'none'}"]
        for k, s in enumerate(stats):
            draw_text(surf, s, (712, 206 + k * 20), WHITE, 17)
        # relics
        draw_text(surf, "RELIC SLOTS (4)", (100, 340), GOLD, 18)
        for i, r in enumerate(RELIC_SLOT_RECTS):
            key = p.relic_slots[i]
            panel(surf, r, RELICS[key]["color"] if key else EDGE, UI_BG2, 255, 2)
            if key:
                draw_relic_icon(surf, key, r)
                if r.collidepoint(mouse):
                    hover = ("relic", key)
            else:
                draw_text(surf, "empty", (r.centerx, r.centery - 8), ASH, 15, center=True)
        draw_text(surf, f"RELICS OWNED ({len(p.relics_owned)}/{len(RELICS)})", (420, 340), GOLD, 18)
        for i, key in enumerate(p.relics_owned):
            r = owned_relic_rect(i)
            on = key in p.relic_slots
            panel(surf, r, GREEN if on else EDGE, UI_BG2, 255, 2)
            draw_relic_icon(surf, key, r, dim=not on)
            if r.collidepoint(mouse):
                hover = ("relic", key)
        if not p.relics_owned:
            draw_text(surf, "None yet. Optional bosses and treasure groves hold relics.", (420, 372), ASH, 16)
        if p.treasure_maps:
            draw_text(surf, "Maps: " + ", ".join(p.treasure_maps), (100, 440), GOLD, 16)
        # detail panel
        box = R(100, 470, 760, 120)
        panel(surf, box, EDGE, (16, 18, 24), 255)
        if hover:
            kind, obj = hover
            if kind == "item":
                draw_text(surf, obj.name, (box.x + 14, box.y + 10), obj.color, 24)
                draw_text(surf, obj.stat_line(), (box.x + 14, box.y + 38), WHITE, 18)
                extra = []
                if obj.is_weapon and obj.effect:
                    extra.append(f"Effect: {EFFECT_NAMES.get(obj.effect, obj.effect)}")
                if obj.is_weapon:
                    extra.append(self.relic_note(obj))
                if obj.desc:
                    extra.append(obj.desc)
                extra.append(f"Sells for {max(1, int(obj.value * .4))}g")
                for k, line in enumerate([e for e in extra if e][:3]):
                    draw_text(surf, line, (box.x + 14, box.y + 62 + k * 18), ASH, 17)
            else:
                data = RELICS[obj]
                draw_text(surf, data["name"] + ("  (MAJOR RELIC)" if data["major"] else ""), (box.x + 14, box.y + 10), data["color"], 24)
                for k, line in enumerate(wrap_text(data["desc"], 18, 730)[:3]):
                    draw_text(surf, line, (box.x + 14, box.y + 40 + k * 20), WHITE, 18)
                draw_text(surf, f"Source: {data['source']}   -   {'EQUIPPED' if obj in p.relic_slots else 'not equipped'}", (box.x + 14, box.y + 98), ASH, 16)
        else:
            draw_text(surf, "Hover over an item or relic to see details.", (box.x + 14, box.y + 14), ASH, 18)
        if self.drag:
            item = p.inv.slots[self.drag[1]] if self.drag[0] == "slot" else p.inv.armor
            if item:
                draw_item_icon(surf, item, R(mouse[0] - 24, mouse[1] - 24, 48, 48))

    def relic_note(self, item):
        p = self.player
        notes = []
        if item.kind in ("sword", "greatsword") and p.has_relic("cinderheart"):
            notes.append("Cinderheart: blazing, burning strikes")
        if item.kind == "staff" and p.has_relic("mirrorstep"):
            notes.append("Mirrorstep: Frost Nova (R)")
        if item.kind in ("bow", "staff") and p.has_relic("starlens"):
            notes.append("Star Lens: golden piercing shots")
        return "  |  ".join(notes)

    # ------------------------------------------------------------------
    def shop_row_rects(self):
        return [R(100, 140 + i * 52, 760, 46) for i in range(8)]

    def draw_shop(self, surf):
        s = self.shop
        p = self.player
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 160)
        panel(surf, INV_PANEL, s["accent"], UI_BG, 245, 3)
        draw_text(surf, s["title"], (WIDTH // 2, 48), s["accent"], 38, center=True)
        draw_text(surf, f"Gold {p.gold}    Embers {p.embers}", (WIDTH // 2, 84), GOLD, 20, center=True)
        for k, (mode, label) in enumerate((("buy", "BUY"), ("sell", "SELL"))):
            r = R(100 + k * 110, 100, 100, 30)
            panel(surf, r, s["accent"] if s["mode"] == mode else EDGE, (40, 40, 52) if s["mode"] == mode else UI_BG2)
            draw_text(surf, label, (r.centerx, r.y + 6), WHITE, 20, center=True)
        draw_text(surf, "TAB: switch buy/sell   ESC: close", (860, 108), ASH, 16, right=True)
        mouse = pygame.mouse.get_pos()
        if s["mode"] == "buy":
            entries = s["entries"]
            s["sel"] = int(clamp(s["sel"], 0, max(0, len(entries) - 1)))
            if s["sel"] < s["scroll"]:
                s["scroll"] = s["sel"]
            if s["sel"] >= s["scroll"] + 8:
                s["scroll"] = s["sel"] - 7
            for row, r in enumerate(self.shop_row_rects()):
                idx = s["scroll"] + row
                if idx >= len(entries):
                    break
                ent = entries[idx]
                sel = idx == s["sel"]
                panel(surf, r, s["accent"] if sel else EDGE, (40, 40, 52) if sel else UI_BG2, 255)
                if ent.get("service"):
                    target = p.weapon() if ent["service"] == "reforge" else p.inv.armor
                    draw_text(surf, ent["name"], (r.x + 56, r.y + 5), ORANGE, 20)
                    if target:
                        g, e = self.reforge_cost(target)
                        draw_text(surf, f"{target.name}: {target.power} -> {target.power + 3}", (r.x + 56, r.y + 25), WHITE, 16)
                        ok = p.gold >= g and p.embers >= e
                        draw_text(surf, f"{g}g + {e} ember", (r.right - 12, r.y + 14), GOLD if ok else RED, 20, right=True)
                    else:
                        draw_text(surf, ent["desc"], (r.x + 56, r.y + 25), ASH, 16)
                    pygame.draw.circle(surf, ORANGE, (r.x + 26, r.centery), 12, 3)
                    continue
                item = ent["item"]
                draw_item_icon(surf, item, R(r.x + 4, r.y + 2, 42, 42))
                name = item.name + (f" x{item.stack}" if item.stack > 1 else "")
                draw_text(surf, name, (r.x + 56, r.y + 5), item.color, 20)
                line = item.stat_line()
                if item.is_weapon or item.kind == "armor":
                    cur = p.weapon() if item.is_weapon else p.inv.armor
                    if cur and (cur.kind == item.kind or item.kind == "armor"):
                        diff = item.power - cur.power
                        line += f"   ({'+' if diff >= 0 else ''}{diff} vs equipped)"
                    if item.effect and item.is_weapon:
                        line += f"   {EFFECT_NAMES.get(item.effect, '')}"
                draw_text(surf, line, (r.x + 56, r.y + 25), ASH, 16)
                cur = ent.get("currency", "gold")
                afford = (p.gold if cur == "gold" else p.embers) >= ent["price"]
                draw_text(surf, f"{ent['price']} {'g' if cur == 'gold' else 'ember'}", (r.right - 12, r.y + 14), (GOLD if cur == "gold" else EMBER) if afford else RED, 20, right=True)
            if len(entries) > 8:
                draw_text(surf, f"{s['scroll'] + 1}-{min(len(entries), s['scroll'] + 8)} of {len(entries)} (scroll)", (WIDTH // 2, 562), ASH, 16, center=True)
            draw_text(surf, "Up/Down select   Enter or click: buy", (WIDTH // 2, 584), ASH, 16, center=True)
        else:
            draw_text(surf, "Click an item to sell one. Equipped armor can't be sold.", (100, 144), ASH, 17)
            for i in range(Inventory.SIZE):
                r = inv_slot_rect(i).move(0, 50)
                item = p.inv.slots[i]
                panel(surf, r, EDGE, UI_BG2, 255, 1)
                if item:
                    draw_item_icon(surf, item, r.inflate(-10, -10))
                    if item.stack > 1:
                        draw_text(surf, str(item.stack), (r.right - 4, r.bottom - 17), WHITE, 16, right=True)
                    if r.collidepoint(mouse):
                        pygame.draw.rect(surf, GOLD, r, 2)
                        draw_text(surf, f"{item.name} - sells for {max(1, int(item.value * .4))}g", (WIDTH // 2, 430), item.color, 20, center=True)

    # ------------------------------------------------------------------
    def draw_journal2(self, surf):
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 170)
        panel(surf, INV_PANEL, GOLD, UI_BG, 245, 3)
        draw_text(surf, "BOUNTIES & RIDDLES", (WIDTH // 2, 48), GOLD, 38, center=True)
        y = 92
        draw_text(surf, f"BOUNTIES   (renown {self.renown()}, +{2 * self.renown()} max HP)", (100, y), GOLD, 19)
        y += 22
        for rid in PROGRESSION:
            st = self.realm_states[rid]
            if self.home_quest_status(rid) in ("locked", "available"):
                draw_text(surf, f"{REALM_SHORT[rid]}: ???", (110, y), ASH, 15)
                y += 19
                continue
            done = sum(1 for q in SIDE_QUESTS[rid] if st.bstate(q["id"])["s"] == 2)
            act = [f"{q['name']} {self.bounty_progress_text(q, st.bstate(q['id']))}" for q in st.active_bounties()]
            draw_text(surf, f"{REALM_SHORT[rid]}: {done}/{len(SIDE_QUESTS[rid])} done" + (("   active: " + "; ".join(act))[:88] if act else ""), (110, y), WHITE, 15)
            y += 19
        y += 8
        draw_text(surf, f"RIDDLE LOG   ({len(self.riddle_log)} solved)", (100, y), GOLD, 19)
        y += 22
        if not self.riddle_log:
            draw_text(surf, "Solve riddles in the treasure groves or for the realm keepers to record them here.", (110, y), ASH, 15)
        for r in self.riddle_log[-9:][::-1]:
            line = f"{REALM_SHORT[r[0]] if 0 <= r[0] < 4 else '?'}: {r[2]}"
            draw_text(surf, line[:100], (110, y), (200, 220, 200), 15)
            y += 19
        draw_text(surf, "TAB / click: other page      J or ESC to close", (WIDTH // 2, 580), ASH, 17, center=True)

    def draw_journal(self, surf):
        if self.journal_page == 1:
            self.draw_journal2(surf)
            return
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 170)
        panel(surf, INV_PANEL, GOLD, UI_BG, 245, 3)
        draw_text(surf, "QUEST JOURNAL", (WIDTH // 2, 48), GOLD, 38, center=True)
        y = 96
        draw_text(surf, "MAIN EXPEDITIONS", (100, y), GOLD, 20)
        y += 24
        for rid in PROGRESSION:
            info = REALM_INFO[rid]
            st = self.realm_states[rid]
            status = self.home_quest_status(rid)
            label = {"locked": "locked", "available": f"talk to {info['giver']}", "active": "in progress",
                     "ready": f"return to {info['giver']}", "done": "complete"}[status]
            col = ASH if status == "locked" else GREEN if status == "done" else WHITE
            draw_text(surf, f"{info['title']} ({REALM_SHORT[rid]})  -  {label}", (110, y), col, 18)
            qs = "   ".join(f"{'[x]' if l.complete else '[>]' if l.started else '[ ]'} {l.title}" for l in st.lines)
            draw_text(surf, qs + (f"   [{'x' if st.boss_defeated else ' '}] {info['boss'].title()}" if status != "locked" else ""), (126, y + 18), ASH if status == "locked" else (200, 200, 200), 15)
            y += 42
        y += 4
        draw_text(surf, "SECRETS", (100, y), GOLD, 20)
        y += 24
        for rid in PROGRESSION:
            info = REALM_INFO[rid]
            st = self.realm_states[rid]
            if self.home_quest_status(rid) in ("locked", "available"):
                draw_text(surf, f"{REALM_SHORT[rid]}: ???", (110, y), ASH, 17)
            else:
                side = {"hidden": "undiscovered", "active": f"{sum(st.side_found)}/3", "return": "return to merchant", "complete": "complete"}[st.side]
                parts = [f"Side quest: {side}",
                         f"Treasure: {'claimed' if st.treasure_claimed else ('map found' if TREASURE_MAPS[rid] in self.player.treasure_maps else '?')}",
                         f"{info['secret_boss'].title()}: {'defeated' if st.secret_defeated else '?'}",
                         f"{info['discovery'].title()}: {'cleared x' + str(st.discovery_clears) if st.discovery_clears else '-'}"]
                draw_text(surf, f"{REALM_SHORT[rid]}:  " + "   |   ".join(parts), (110, y), WHITE, 16)
            y += 22
        y += 10
        draw_text(surf, f"DUNGEON: {self.dungeon_progress}/10 rooms cleared", (100, y), GOLD, 20)
        draw_text(surf, f"RELICS: {len(self.player.relics_owned)}/{len(RELICS)}      ARCADE BEST: {self.arcade_best}", (500, y), GOLD, 20)
        draw_text(surf, "TAB / click: bounties & riddles      J or ESC to close", (WIDTH // 2, 580), ASH, 17, center=True)

    # ------------------------------------------------------------------
    @property
    def PAUSE_OPTIONS(self):
        opts = ["Resume", "Save game", "Load game", "Controls", "Quit to title"]
        if self.scene is not None and not self.scene.hub:
            opts.insert(1, "Retreat (leave this area)")
        return opts

    def pause_rects(self):
        return [R(WIDTH // 2 - 160, 220 + i * 52, 320, 42) for i in range(len(self.PAUSE_OPTIONS))]

    def draw_pause(self, surf):
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 180)
        draw_text(surf, "PAUSED", (WIDTH // 2, 150), GOLD, 64, center=True)
        self.pause_index = int(clamp(self.pause_index, 0, len(self.PAUSE_OPTIONS) - 1))
        for i, (r, label) in enumerate(zip(self.pause_rects(), self.PAUSE_OPTIONS)):
            sel = i == self.pause_index
            panel(surf, r, GOLD if sel else EDGE, (50, 44, 30) if sel else UI_BG2)
            draw_text(surf, label, (r.centerx, r.y + 11), GOLD if sel else WHITE, 24, center=True)

    def pause_choose(self, i):
        options = self.PAUSE_OPTIONS
        if not 0 <= i < len(options):
            return
        option = options[i]
        if option == "Resume":
            self.state = PLAYING
        elif option.startswith("Retreat"):
            self.state = PLAYING
            sc = self.scene
            rid = getattr(sc, "rid", None)
            if isinstance(sc, QuestInterior):
                self.leave_interior()
            elif isinstance(sc, DungeonRoom):
                self.enter_dungeon_hub()
            elif rid is not None:
                self.go_realm(rid)
            else:
                self.change_scene(self.get_home(), self.get_home().spawn())
            self.notify("You retreated to safety.", ASH)
        elif option == "Save game":
            self.write_save()
            self.state = PLAYING
        elif option == "Load game":
            self.load_game()
        elif option == "Controls":
            self.show_help = True
        else:
            self.autosave_on_quit()
            self.state = MENU
            self.menu_index = 0

    def autosave_on_quit(self):
        if self.scene is not None:
            prev = self.state
            self.state = PLAYING
            self.write_save(quiet=True)
            self.state = prev

    def draw_help(self, surf):
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 200)
        box = R(150, 70, 660, 500)
        panel(surf, box, GOLD, UI_BG, 250, 3)
        draw_text(surf, "CONTROLS", (WIDTH // 2, 86), GOLD, 36, center=True)
        rows = [("WASD / Arrows", "Move"), ("Mouse", "Aim"), ("Left click (hold)", "Use selected item: attack, cast, drink"),
                ("Right click (hold)", "Quick-draw your bow, release to fire"), ("Shift / Space", "Dash (Blink with the Null Compass)"),
                ("R", "Relic ability: Frost Nova (Mirrorstep Charm + staff)"), ("E", "Interact / talk / enter"), ("Q", "Drink a potion"),
                ("1-9 / mouse wheel", "Choose hotbar slot"), ("I / Tab", "Inventory, armor and relic slots"), ("J", "Quest journal"),
                ("F5 / F9", "Quick save / quick load"), ("ESC", "Pause / close menus")]
        for i, (k, v) in enumerate(rows):
            draw_text(surf, k, (190, 140 + i * 30), GOLD, 20)
            draw_text(surf, v, (390, 140 + i * 30), WHITE, 20)
        draw_text(surf, "Press any key or click to close", (WIDTH // 2, 540), ASH, 18, center=True)

    def draw_dead(self, surf):
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), (30, 0, 0), 190)
        draw_text(surf, "YOU FELL", (WIDTH // 2, 200), RED, 72, center=True)
        draw_text(surf, self.death_reason or "The ash remembers.", (WIDTH // 2, 280), WHITE, 24, center=True)
        draw_text(surf, "ENTER / click: rise again (lose 25% of your gold)", (WIDTH // 2, 340), GOLD, 22, center=True)
        draw_text(surf, "ESC: return to title", (WIDTH // 2, 372), ASH, 20, center=True)

    def draw_victory(self, surf):
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 200)
        draw_text(surf, "ASHFALL RESTORED", (WIDTH // 2, 150), GOLD, 64, center=True)
        draw_text(surf, "Emberfang, the Frostheart Colossus, the Void Admiral and the Seraph have fallen.", (WIDTH // 2, 236), WHITE, 22, center=True)
        secrets = sum(1 for st in self.realm_states.values() if st.secret_defeated)
        draw_text(surf, f"Level {self.player.level}   -   Optional bosses defeated: {secrets}/4   -   Dungeon: {self.dungeon_progress}/10   -   Relics: {len(self.player.relics_owned)}/{len(RELICS)}",
                  (WIDTH // 2, 280), GREEN, 20, center=True)
        if secrets < 4:
            draw_text(surf, "But not every secret has been found. The undocumented fifth phases are still waiting...", (WIDTH // 2, 330), PURPLE, 20, center=True)
        draw_text(surf, "ENTER: keep exploring", (WIDTH // 2, 400), ASH, 22, center=True)

    # ------------------------------------------------------------------
    def draw_arcade(self, surf):
        a = self.arcade
        if a is None:
            return
        alpha_rect(surf, R(0, 0, WIDTH, HEIGHT), BLACK, 190)
        box = R(130, 80, 700, 480)
        pygame.draw.rect(surf, (24, 12, 36), box)
        pygame.draw.rect(surf, GOLD, box, 4)
        draw_text(surf, "MILO'S EMBER GALLERY", (WIDTH // 2, 92), GOLD, 30, center=True)
        draw_text(surf, f"SCORE {a['score']}", (160, 124), WHITE, 24)
        draw_text(surf, f"TIME {max(0, a['time']):.1f}", (800, 124), WHITE, 24, right=True)
        if not a["done"]:
            for t in a["targets"]:
                r = 10 + 18 * t["life"] / t["max"]
                if t["bad"]:
                    pygame.draw.circle(surf, (90, 90, 100), ipos(t["pos"]), int(r))
                    pygame.draw.circle(surf, BLACK, ipos(t["pos"] + V(-5, -3)), 3)
                    pygame.draw.circle(surf, BLACK, ipos(t["pos"] + V(5, -3)), 3)
                else:
                    glow(surf, t["pos"], r * 2, ORANGE, 120)
                    pygame.draw.circle(surf, ORANGE, ipos(t["pos"]), int(r))
                    pygame.draw.circle(surf, (255, 230, 150), ipos(t["pos"]), int(r * .45))
            draw_text(surf, "Click lanterns (+1). Avoid ash skulls (-2). No wagers, just skill.", (WIDTH // 2, 528), ASH, 17, center=True)
        else:
            medal, reward = a["result"]
            col = {"gold": GOLD, "silver": (200, 200, 220), "bronze": (200, 130, 70)}.get(medal, ASH)
            draw_text(surf, f"{(medal or 'no').upper()} MEDAL", (WIDTH // 2, 240), col, 56, center=True)
            draw_text(surf, f"Score {a['score']}   (best {self.arcade_best})", (WIDTH // 2, 310), WHITE, 24, center=True)
            draw_text(surf, "   ".join(reward) if reward else "Reach 15 points for a bronze medal. Try again!", (WIDTH // 2, 350), GREEN if reward else ASH, 22, center=True)
            draw_text(surf, "Click or press Enter to leave", (WIDTH // 2, 470), ASH, 20, center=True)

    # ------------------------------------------------------------------
    MENU_OPTIONS = ["New Game", "Continue", "Controls", "Quit"]

    def menu_rects(self):
        return [R(WIDTH // 2 - 130, 320 + i * 50, 260, 40) for i in range(len(self.MENU_OPTIONS))]

    def draw_menu(self, surf):
        surf.fill((9, 10, 14))
        for e in self.menu_embers:
            pygame.draw.rect(surf, EMBER, (int(e[0]), int(e[1]), 2, 2))
        pygame.draw.circle(surf, (46, 42, 55), (WIDTH // 2, 150), 74)
        pygame.draw.circle(surf, (9, 10, 14), (WIDTH // 2 + 25, 130), 63)
        draw_text(surf, "ASHFALL", (WIDTH // 2, 95), WHITE, 110, center=True)
        draw_text(surf, "A shattered world. Four realms. Secrets nobody has written down.", (WIDTH // 2, 200), ASH, 22, center=True)
        if self.menu_confirm:
            draw_text(surf, "Start a new game? Your existing save will be replaced at the first autosave.", (WIDTH // 2, 262), RED, 20, center=True)
            draw_text(surf, "ENTER / Y: yes        ESC / N: no", (WIDTH // 2, 290), WHITE, 20, center=True)
        for i, (r, label) in enumerate(zip(self.menu_rects(), self.MENU_OPTIONS)):
            sel = i == self.menu_index
            disabled = label == "Continue" and not self.has_save
            panel(surf, r, GOLD if sel else EDGE, (50, 44, 30) if sel else UI_BG2)
            draw_text(surf, label, (r.centerx, r.y + 10), ASH if disabled else (GOLD if sel else WHITE), 26, center=True)
        draw_text(surf, "Arrows/mouse to choose, Enter to select", (WIDTH // 2, 560), (90, 94, 104), 18, center=True)
        if self.toast:
            draw_text(surf, self.toast[0], (WIDTH // 2, 600), self.toast[1], 20, center=True)

    def menu_choose(self, i):
        label = self.MENU_OPTIONS[i]
        if label == "New Game":
            if self.has_save and not self.menu_confirm:
                self.menu_confirm = True
                return
            self.menu_confirm = False
            self.new_game()
        elif label == "Continue":
            if self.has_save:
                self.load_game()
        elif label == "Controls":
            self.show_help = True
        else:
            raise SystemExit

    # ==================================================================
    # INPUT
    # ==================================================================
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self.handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.handle_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.handle_mouse_up(event)
        elif event.type == pygame.MOUSEWHEEL:
            if self.state == PLAYING:
                self.player.inv.select((self.player.inv.selected - event.y) % 9)
            elif self.state == SHOP and self.shop and self.shop["mode"] == "buy":
                self.shop["sel"] = int(clamp(self.shop["sel"] - event.y, 0, max(0, len(self.shop["entries"]) - 1)))
            elif self.state == BOOK and self.book:
                self.turn_page(-event.y)

    def turn_page(self, direction):
        b = self.book
        b["page"] = int(clamp(b["page"] + 2 * (1 if direction > 0 else -1), 0, max(0, (len(b["pages"]) - 1) // 2 * 2)))

    def handle_key(self, key):
        if self.show_help:
            self.show_help = False
            return
        st = self.state
        if st == MENU:
            if self.menu_confirm:
                if key in (pygame.K_RETURN, pygame.K_y, pygame.K_SPACE):
                    self.menu_choose(0)
                elif key in (pygame.K_ESCAPE, pygame.K_n):
                    self.menu_confirm = False
                return
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(self.MENU_OPTIONS)
                self.sound("menu")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(self.MENU_OPTIONS)
                self.sound("menu")
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self.menu_choose(self.menu_index)
            return
        if st == DIALOGUE:
            d = self.dialogue
            if d is None:
                self.state = PLAYING
                return
            last = d["index"] >= len(d["lines"]) - 1
            if last and d["choices"]:
                n = len(d["choices"])
                if key in (pygame.K_UP, pygame.K_w):
                    d["sel"] = (d["sel"] - 1) % n
                elif key in (pygame.K_DOWN, pygame.K_s):
                    d["sel"] = (d["sel"] + 1) % n
                elif pygame.K_1 <= key <= pygame.K_9 and key - pygame.K_1 < n:
                    self.dialog_advance(key - pygame.K_1)
                elif key in (pygame.K_e, pygame.K_SPACE, pygame.K_RETURN):
                    self.dialog_advance()
                elif key == pygame.K_ESCAPE:
                    self.dialog_advance(n - 1)
                return
            if key in (pygame.K_e, pygame.K_SPACE, pygame.K_RETURN):
                self.dialog_advance()
            elif key == pygame.K_ESCAPE:
                d["index"] = len(d["lines"]) - 1
                if not d["choices"]:
                    self.dialog_advance()
            return
        if st == SHOP:
            s = self.shop
            if key in (pygame.K_ESCAPE, pygame.K_e):
                self.state = PLAYING
                self.shop = None
            elif key == pygame.K_TAB:
                s["mode"] = "sell" if s["mode"] == "buy" else "buy"
            elif s["mode"] == "buy":
                if key in (pygame.K_UP, pygame.K_w):
                    s["sel"] = max(0, s["sel"] - 1)
                elif key in (pygame.K_DOWN, pygame.K_s):
                    s["sel"] = min(len(s["entries"]) - 1, s["sel"] + 1)
                elif key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.shop_buy(s["sel"])
            return
        if st == INVENTORY:
            if key in (pygame.K_ESCAPE, pygame.K_i, pygame.K_TAB):
                self.state = PLAYING
                self.drag = None
            elif pygame.K_1 <= key <= pygame.K_9:
                self.player.inv.select(key - pygame.K_1)
            return
        if st == BOOK:
            if key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN):
                self.state = PLAYING
                self.book = None
            elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_SPACE):
                self.turn_page(1)
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.turn_page(-1)
            return
        if st == JOURNAL:
            if key in (pygame.K_ESCAPE, pygame.K_j, pygame.K_e):
                self.state = PLAYING
            elif key in (pygame.K_TAB, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
                self.journal_page = 1 - self.journal_page
            return
        if st == ARCADE:
            a = self.arcade
            if a and a["done"] and key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_e, pygame.K_SPACE):
                self.arcade = None
                self.state = PLAYING
            elif a and not a["done"] and key == pygame.K_ESCAPE:
                a["time"] = 0
            return
        if st == DEAD:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.respawn()
            elif key == pygame.K_ESCAPE:
                self.respawn()
                self.autosave_on_quit()
                self.state = MENU
            return
        if st == VICTORY:
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.state = PLAYING
            return
        if st == PAUSE:
            if key == pygame.K_ESCAPE:
                self.state = PLAYING
            elif key in (pygame.K_UP, pygame.K_w):
                self.pause_index = (self.pause_index - 1) % len(self.PAUSE_OPTIONS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.pause_index = (self.pause_index + 1) % len(self.PAUSE_OPTIONS)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self.pause_choose(self.pause_index)
            elif key == pygame.K_F5:
                self.write_save()
            elif key == pygame.K_F9:
                self.load_game()
            return
        # ---- PLAYING ----
        p = self.player
        if key == pygame.K_ESCAPE:
            self.state = PAUSE
            self.pause_index = 0
            self.lmb_attack = False
        elif key in (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_SPACE):
            p.dash(self.scene)
        elif key == pygame.K_e:
            self.interact()
        elif key == pygame.K_q:
            p.drink_potion()
        elif key == pygame.K_r:
            p.relic_ability()
        elif key in (pygame.K_i, pygame.K_TAB):
            self.state = INVENTORY
            self.lmb_attack = False
            p.bow_charge = None
        elif key == pygame.K_j:
            self.state = JOURNAL
            self.lmb_attack = False
        elif pygame.K_1 <= key <= pygame.K_9:
            p.inv.select(key - pygame.K_1)
            p.bow_charge = None
        elif key == pygame.K_F5:
            self.write_save()
        elif key == pygame.K_F9:
            self.load_game()
        elif key == pygame.K_F12 and os.environ.get("ASHFALL_DEBUG"):
            self.god_mode = not self.god_mode
            self.notify(f"God mode {'on' if self.god_mode else 'off'}", PURPLE)

    def handle_mouse_down(self, event):
        if self.show_help:
            self.show_help = False
            return
        pos = event.pos
        st = self.state
        if st == MENU:
            if event.button == 1:
                if self.menu_confirm:
                    self.menu_choose(0)
                    return
                for i, r in enumerate(self.menu_rects()):
                    if r.collidepoint(pos):
                        self.menu_index = i
                        self.menu_choose(i)
            return
        if st == PAUSE:
            if event.button == 1:
                for i, r in enumerate(self.pause_rects()):
                    if r.collidepoint(pos):
                        self.pause_choose(i)
            return
        if st == DIALOGUE:
            if event.button == 1:
                rects = self.dialogue_choice_rects()
                d = self.dialogue
                if d and d["index"] >= len(d["lines"]) - 1 and rects:
                    for i, r in enumerate(rects):
                        if r.collidepoint(pos):
                            self.dialog_advance(i)
                            return
                    return
                self.dialog_advance()
            return
        if st == ARCADE:
            if event.button == 1:
                self.arcade_click(V(pos))
            return
        if st == DEAD:
            if event.button == 1:
                self.respawn()
            return
        if st == VICTORY:
            if event.button == 1:
                self.state = PLAYING
            return
        if st == BOOK:
            if event.button == 1:
                self.turn_page(1 if pos[0] > WIDTH // 2 else -1)
            elif event.button == 3:
                self.state = PLAYING
            return
        if st == JOURNAL:
            if event.button == 1:
                self.journal_page = 1 - self.journal_page
            elif event.button == 3:
                self.state = PLAYING
            return
        if st == SHOP:
            self.shop_click(event)
            return
        if st == INVENTORY:
            self.inventory_click(event)
            return
        if st != PLAYING:
            return
        if event.button == 1:
            if self.click_interact(self.mouse_world()):
                return
            self.lmb_attack = True
            self.player.use_primary()
        elif event.button == 3:
            self.player.quick_bow()

    def handle_mouse_up(self, event):
        if self.state == INVENTORY and event.button == 1 and self.drag:
            self.inventory_drop(event.pos)
            return
        if event.button == 1:
            self.lmb_attack = False
            if self.state == PLAYING:
                self.player.release_bow()
        elif event.button == 3 and self.state == PLAYING:
            self.player.release_bow()

    def shop_click(self, event):
        s = self.shop
        pos = event.pos
        if event.button != 1:
            return
        if not INV_PANEL.collidepoint(pos):
            self.state = PLAYING
            self.shop = None
            return
        for k, mode in enumerate(("buy", "sell")):
            if R(100 + k * 110, 100, 100, 30).collidepoint(pos):
                s["mode"] = mode
                return
        if s["mode"] == "buy":
            for row, r in enumerate(self.shop_row_rects()):
                idx = s["scroll"] + row
                if idx < len(s["entries"]) and r.collidepoint(pos):
                    s["sel"] = idx
                    self.shop_buy(idx)
                    return
        else:
            for i in range(Inventory.SIZE):
                if inv_slot_rect(i).move(0, 50).collidepoint(pos):
                    self.shop_sell(i)
                    return

    def inventory_click(self, event):
        p = self.player
        pos = event.pos
        for i in range(Inventory.SIZE):
            r = inv_slot_rect(i)
            if r.collidepoint(pos):
                item = p.inv.slots[i]
                if event.button == 1 and item:
                    self.drag = ("slot", i)
                    if i < 9:
                        p.inv.select(i)
                elif event.button == 3 and item:
                    self.inventory_quick_use(i)
                return
        if ARMOR_RECT.collidepoint(pos) and p.inv.armor:
            if event.button == 1:
                self.drag = ("armor", 0)
            elif event.button == 3:
                if p.inv.add(p.inv.armor):
                    p.inv.armor = None
            return
        for i, r in enumerate(RELIC_SLOT_RECTS):
            if r.collidepoint(pos) and p.relic_slots[i]:
                p.toggle_relic(p.relic_slots[i])
                return
        for i, key in enumerate(p.relics_owned):
            if owned_relic_rect(i).collidepoint(pos):
                p.toggle_relic(key)
                return
        if event.button == 1 and not INV_PANEL.collidepoint(pos):
            self.state = PLAYING

    def inventory_quick_use(self, i):
        p = self.player
        item = p.inv.slots[i]
        if item is None:
            return
        if item.kind == "armor":
            p.inv.slots[i], p.inv.armor = p.inv.armor, item
            self.notify(f"Equipped {item.name}", GREEN)
        elif item.kind in ("potion", "food"):
            p.consume(item)
        elif item.is_weapon:
            sel = p.inv.selected
            if i != sel:
                p.inv.slots[i], p.inv.slots[sel] = p.inv.slots[sel], p.inv.slots[i]
                self.notify(f"{item.name} moved to hotbar slot {sel + 1}", GREEN)

    def inventory_drop(self, pos):
        p = self.player
        kind, idx = self.drag
        self.drag = None
        if kind == "slot":
            item = p.inv.slots[idx]
            if item is None:
                return
            if ARMOR_RECT.collidepoint(pos):
                if item.kind == "armor":
                    p.inv.slots[idx], p.inv.armor = p.inv.armor, item
                    self.notify(f"Equipped {item.name}", GREEN)
                else:
                    self.notify("Only armor fits there.", RED)
                return
            for j in range(Inventory.SIZE):
                if inv_slot_rect(j).collidepoint(pos) and j != idx:
                    a, b = p.inv.slots[idx], p.inv.slots[j]
                    if b and a and a.name == b.name and a.kind == b.kind and a.kind in STACKABLE:
                        b.stack += a.stack
                        p.inv.slots[idx] = None
                    else:
                        p.inv.slots[idx], p.inv.slots[j] = b, a
                    return
        elif kind == "armor" and p.inv.armor:
            for j in range(Inventory.SIZE):
                if inv_slot_rect(j).collidepoint(pos):
                    other = p.inv.slots[j]
                    if other is None or other.kind == "armor":
                        p.inv.slots[j], p.inv.armor = p.inv.armor, other
                    else:
                        self.notify("Only armor can be swapped into the armor slot.", RED)
                    return


# ============================================================
# MAIN LOOP
# ============================================================

game = None
screen = None


def init_display():
    global screen
    pygame.init()
    flags = pygame.SCALED if hasattr(pygame, "SCALED") else 0
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    except Exception:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ASHFALL")
    return screen


def recover_from_error(context):
    """Log an unexpected error and put the game back into a safe state instead of crashing."""
    log_error(context)
    now = pygame.time.get_ticks()
    game.error_times = [t for t in game.error_times if now - t < 3000] + [now]
    try:
        game.projectiles = []
        if game.scene is not None:
            game.scene.hazards = []
        if game.dialogue is None and game.state == DIALOGUE:
            game.state = PLAYING
        if len(game.error_times) >= 4 and game.player is not None:
            game.error_times = []
            game.dialogue = None
            game.shop = None
            game.state = PLAYING
            game.change_scene(game.get_home(), game.get_home().spawn())
            game.notify("Something went wrong - you were returned home safely. (logged)", RED)
        else:
            game.notify("Recovered from an error (details in ashfall_errors.log)", RED)
    except Exception:
        log_error("recovery")
        game.state = MENU


async def main():
    global game
    init_display()
    clock = pygame.time.Clock()
    game = Game()
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            try:
                game.handle_event(event)
            except SystemExit:
                running = False
            except Exception:
                recover_from_error("input")
        try:
            game.update(dt)
        except SystemExit:
            running = False
        except Exception:
            recover_from_error("update")
        try:
            game.draw(screen)
        except Exception:
            recover_from_error("draw")
            screen.fill(BLACK)
        pygame.display.flip()
        # Required by pygbag/pygame-wasm to return control to the browser.
        await asyncio.sleep(0)
    if game.state not in (MENU,) and game.scene is not None:
        game.autosave_on_quit()


if __name__ == "__main__":
    asyncio.run(main())
