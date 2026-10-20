import bpy, sys, re, time, queue, functools

NS = bpy.app.driver_namespace

# ---------------- config ----------------
TRANSCRIBER_DIR = r"C:\Users\xSkul\OneDrive\Documents\Projects\CPSC581\cpsc581p2\scripts"
MODEL_PATH = r"C:\Users\xSkul\OneDrive\Documents\Projects\CPSC581\cpsc581p2\model"
EXTRA_SITE_PACKAGES = None
LAST_N_WORDS = 4
HIGHLIGHT_SECONDS = 5.0
TICK_DELAY = 0.2
REG_TTL = 1.0                       # seconds a button stays "visible" after its last draw
HIGHLIGHT = (0x7D / 255, 0xE7 / 255, 0x9E / 255, 1.0)

# Reset preferences (uncomment to reset to default preferences in case autosave breaks it)
# bpy.ops.preferences.reset_default_theme()
# bpy.ops.wm.save_userpref()

LEAF = {"operator", "prop", "prop_enum", "menu", "operator_menu_enum", "prop_menu_enum"}
CONTAINER = {"row", "column", "box", "split", "column_flow", "grid_flow"}

PHASE = {"on": False}
REG = {}                            # (class, index) -> (name, label, last_seen)
TARGETS = set()                     # keys currently highlighted
STATE = {"until": 0.0, "label": None, "tr": None}


def log(msg):
    sys.__stdout__.write(msg + "\n")
    sys.__stdout__.flush()
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


# ---------------- cleanup of earlier runs ----------------
def unwrap_all_draws():
    for base in (bpy.types.Panel, bpy.types.Header, bpy.types.Menu):
        for cls in base.__subclasses__():
            d = cls.__dict__.get("draw")
            if d is None or not hasattr(d, "_probe_orig"):
                continue
            while hasattr(d, "_probe_orig"):
                d = d._probe_orig
            cls.draw = d


if "ui_probe_stop" in NS:
    try:
        NS["ui_probe_stop"]()
    except Exception as e:
        log(f"[probe] previous stop failed: {e}")
unwrap_all_draws()


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
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


# ---------------- transcriber ----------------
def start_transcriber():
    if EXTRA_SITE_PACKAGES and EXTRA_SITE_PACKAGES not in sys.path:
        sys.path.append(EXTRA_SITE_PACKAGES)
    if TRANSCRIBER_DIR not in sys.path:
        sys.path.append(TRANSCRIBER_DIR)
    try:
        from transcription import Transcriber
        tr = Transcriber(MODEL_PATH)
        tr.start()
        STATE["tr"] = tr
        log("[probe] transcriber started")
    except Exception as e:
        log(f"[probe] transcriber failed: {e!r} (is vosk/sounddevice installed in Blender's Python?)")


# ---------------- timer ----------------
def tick():
    now = time.time()
    PHASE["on"] = not PHASE["on"]

    tr = STATE["tr"]
    if tr:
        while True:
            try:
                kind, text = tr.events.get_nowait()
            except queue.Empty:
                break
            handle_text(kind, text)

    for k in [k for k, v in REG.items() if now - v[2] > REG_TTL]:
        del REG[k]
    if TARGETS and now > STATE["until"]:
        TARGETS.clear()

    redraw_all()
    return TICK_DELAY


def stop():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    if STATE["tr"]:
        STATE["tr"].stop()
        STATE["tr"] = None
    TARGETS.clear()
    unwrap_all_draws()
    restore_highlight_color()
    try:
        bpy.context.workspace.status_text_set(None)
    except Exception:
        pass
    redraw_all()
    NS.pop("ui_probe_stop", None)


def start():
    NS["ui_probe_stop"] = stop
    try:
        set_highlight_color()
        patch_ui()
        start_transcriber()
        bpy.app.timers.register(tick, first_interval=0.0)
        log("[probe] started")
    except Exception:
        stop()
        raise


start()