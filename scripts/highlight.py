"""Button-highlighting logic for the novice's Blender session.

Imported by novice_start.py. Importing has no side effects: call start() to patch the UI,
feed it speech with handle_text(kind, text), call update() regularly from a timer, and call stop() to undo everything.
"""
import bpy, sys, re, time, functools

NS = bpy.app.driver_namespace

# ---------------- config ----------------
LAST_N_WORDS = 4
HIGHLIGHT_SECONDS = 5.0
TICK_DELAY = 0.2                    # seconds between flash toggles
REG_TTL = 1.0                       # seconds a button stays "visible" after its last draw
HIGHLIGHT = (0x7D / 255, 0xE7 / 255, 0x9E / 255, 1.0)

# Reset preferences (uncomment to reset to default preferences in case autosave breaks it)
# bpy.ops.preferences.reset_default_theme()
# bpy.ops.wm.save_userpref()

LEAF = {"operator", "prop", "prop_enum", "menu", "operator_menu_enum", "prop_menu_enum"}
CONTAINER = {"row", "column", "box", "split", "column_flow", "grid_flow"}

EXCLUDE_CLASSES = set()             # class names whose draw() must not be patched (e.g. our own panel)

PHASE = {"on": False}
REG = {}                            # (class, index) -> (name, label, last_seen)
TARGETS = set()                     # keys currently highlighted
STATE = {"until": 0.0, "label": None, "last_toggle": 0.0}


def log(msg):
    out = sys.__stdout__ or sys.stdout
    if out:
        out.write(msg + "\n")
        out.flush()
    try:
        bpy.context.workspace.status_text_set(msg[:120])
    except Exception:
        pass


# ---------------- Error color ----------------
def find_error_owner():
    ui = bpy.context.preferences.themes[0].user_interface
    for owner in (getattr(ui, "wcol_state", None), ui):
        if owner is not None and hasattr(owner, "error"):
            return owner
    return None


def set_highlight_color():
    owner = find_error_owner()
    if owner is None:
        log("[probe] could not find the theme's Error color")
        return
    cur = tuple(owner.error)
    if all(abs(a - b) < 1e-3 for a, b in zip(cur, HIGHLIGHT)):
        log("[probe] Error color is already the highlight color; not saving it as the original")
        return
    NS.setdefault("ui_probe_error_orig", cur)
    owner.error = HIGHLIGHT


def restore_highlight_color():
    orig = NS.pop("ui_probe_error_orig", None)
    owner = find_error_owner()
    if orig is not None and owner is not None:
        owner.error = orig


# ---------------- cleanup of draw patches ----------------
def unwrap_all_draws():
    for base in (bpy.types.Panel, bpy.types.Header, bpy.types.Menu):
        for cls in base.__subclasses__():
            d = cls.__dict__.get("draw")
            if d is None or not hasattr(d, "_probe_orig"):
                continue
            while hasattr(d, "_probe_orig"):
                d = d._probe_orig
            cls.draw = d


# ---------------- matcher (swap this out to change matching) ----------------
def norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def match(spoken, entries):
    """spoken: str. entries: {key: (name, label)}. Returns (set_of_keys, matched_label)."""
    text = f" {norm(spoken)} "
    best, keys, best_label = 0, set(), None
    for key, (name, label) in entries.items():
        lab = norm(label)
        if not lab or f" {lab} " not in text:
            continue
        if len(lab) > best:
            best, keys, best_label = len(lab), {key}, lab
        elif len(lab) == best:
            keys.add(key)
    return keys, best_label


def handle_text(kind, text):
    """kind: 'partial' | 'final'. text: what the expert said."""
    words = text.split()[-LAST_N_WORDS:]
    entries = {k: (v[0], v[1]) for k, v in REG.items()}
    keys, label = match(" ".join(words), entries)
    if keys and label != STATE["label"]:
        STATE["label"] = label
        TARGETS.clear()
        TARGETS.update(keys)
        STATE["until"] = time.time() + HIGHLIGHT_SECONDS
        PHASE["on"] = True
        log(f"[probe] heard '{label}' -> highlighting {len(keys)} button(s)")
        redraw_all()
    if kind == "final":
        STATE["label"] = None


# ---------------- layout proxy ----------------
def button_name(kind, a, k):
    if kind in ("operator", "operator_menu_enum", "menu"):
        n = a[0] if a else k.get("operator", k.get("menu"))
    else:
        n = a[1] if len(a) > 1 else k.get("property")
    return str(n)


def button_label(kind, a, k):
    text = k.get("text")
    if text is None and kind in ("prop", "prop_enum", "operator_menu_enum") and len(a) > 2 \
            and isinstance(a[2], str):
        text = a[2]
    if text:
        return text
    try:
        if kind in ("operator", "operator_menu_enum"):
            mod, fn = (a[0] if a else k["operator"]).split(".", 1)
            return getattr(getattr(bpy.ops, mod), fn).get_rna_type().name
        if kind == "menu":
            return getattr(bpy.types, a[0] if a else k["menu"]).bl_label
        if kind in ("prop", "prop_enum", "prop_menu_enum"):
            prop = a[1] if len(a) > 1 else k["property"]
            return a[0].bl_rna.properties[prop].name
    except Exception:
        pass
    return ""


class LayoutProxy:
    def __init__(self, real, ctx):
        object.__setattr__(self, "_l", real)
        object.__setattr__(self, "_ctx", ctx)

    def __getattr__(self, name):
        attr = getattr(self._l, name)
        ctx = self._ctx
        if name in CONTAINER:
            return lambda *a, **k: LayoutProxy(attr(*a, **k), ctx)
        if name in LEAF:
            def call(*a, **k):
                idx = ctx["i"]
                ctx["i"] += 1
                key = (ctx["cls"], idx)
                REG[key] = (button_name(name, a, k), button_label(name, a, k), time.time())
                if key in TARGETS:
                    sub = self._l.row(align=True)
                    sub.alert = PHASE["on"]
                    return getattr(sub, name)(*a, **k)
                return attr(*a, **k)
            return call
        return attr

    def __setattr__(self, name, value):
        setattr(self._l, name, value)


class SelfProxy:
    def __init__(self, real, ctx):
        self._r = real
        self.layout = LayoutProxy(real.layout, ctx)

    def __getattr__(self, n):
        return getattr(self._r, n)


def patch_ui():
    for base in (bpy.types.Panel, bpy.types.Header, bpy.types.Menu):
        for cls in base.__subclasses__():
            if cls.__name__ in EXCLUDE_CLASSES:
                continue
            orig = cls.__dict__.get("draw")
            if orig is None or hasattr(orig, "_probe_orig"):
                continue

            def make(orig, cname):
                @functools.wraps(orig)
                def draw(self, context):
                    orig(SelfProxy(self, {"cls": cname, "i": 0}), context)
                draw._probe_orig = orig
                return draw

            cls.draw = make(orig, cls.__name__)


def redraw_all():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except Exception:
        pass


# ---------------- lifecycle ----------------
def update():
    """Call frequently from a timer. Flashes the highlight and expires stale state every TICK_DELAY seconds."""
    now = time.time()
    if now - STATE["last_toggle"] < TICK_DELAY:
        return
    STATE["last_toggle"] = now
    PHASE["on"] = not PHASE["on"]
    for k in [k for k, v in REG.items() if now - v[2] > REG_TTL]:
        del REG[k]
    if TARGETS and now > STATE["until"]:
        TARGETS.clear()
    redraw_all()


def start():
    unwrap_all_draws()              # drop patches left by an earlier copy of this module
    set_highlight_color()
    patch_ui()
    log("[probe] highlighting started")


def stop():
    TARGETS.clear()
    REG.clear()
    STATE["label"] = None
    PHASE["on"] = False
    unwrap_all_draws()
    restore_highlight_color()
    try:
        bpy.context.workspace.status_text_set(None)
    except Exception:
        pass
    redraw_all()
