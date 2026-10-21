"""Novice side: load this into the .blend's Text Editor (ideally via Open, as an external file).

Running it adds a "Novice" tab to the 3D Viewport sidebar (N) with Start / Stop buttons. Start resolves the scripts folder,
opens a socket server for the expert's helper, and highlights the button matching what the expert says.
Nothing needs to be typed into the Python console.

Optional environment variables (set before launching Blender):
  EXPERT_HOST  address to listen on (default 127.0.0.1; use 0.0.0.0 to accept connections from the LAN)
  EXPERT_PORT  port (default 65432)
  EXPERT_SCRIPTS_DIR  explicit scripts folder, if automatic resolution fails
"""
import bpy, json, os, sys
from pathlib import Path
from bpy.app.handlers import persistent

NS = bpy.app.driver_namespace
POLL_INTERVAL = 0.05                # seconds between socket polls

S = {"running": False, "srv": None, "hl": None, "buffer": b"", "got_data": False, "connected": False}


# ---------------- path resolution ----------------
REQUIRED_FILES = ("highlight.py", "connection_server.py")


def resolve_scripts_dir():
    """Find the folder holding highlight.py and connection_server.py. Raises RuntimeError listing what was tried."""
    def candidates():
        if bpy.data.filepath:                                   # <project>/blender/x.blend -> <project>/scripts
            yield Path(bpy.data.filepath).resolve().parent.parent / "scripts"
        for text in bpy.data.texts:                             # externally linked text blocks
            if text.filepath:
                yield Path(bpy.path.abspath(text.filepath)).resolve().parent
        if globals().get("__file__"):
            yield Path(__file__).resolve().parent
        if os.environ.get("EXPERT_SCRIPTS_DIR"):
            yield Path(os.environ["EXPERT_SCRIPTS_DIR"])

    tried = []
    for path in candidates():
        if all((path / f).is_file() for f in REQUIRED_FILES):
            return path
        tried.append(str(path))
    raise RuntimeError(
        "Could not find the scripts folder. Save the .blend inside <project>/blender/ next to <project>/scripts/, "
        "or set EXPERT_SCRIPTS_DIR. Tried: " + (", ".join(tried) or "nothing"))


# ---------------- session ----------------
def on_bytes(msg):
    if msg:
        S["buffer"] += msg
        S["got_data"] = True


def drain_lines(hl):
    while b"\n" in S["buffer"]:
        line, S["buffer"] = S["buffer"].split(b"\n", 1)
        if not line.strip():
            continue
        try:
            data = json.loads(line.decode("utf-8"))
            kind, text = data["kind"], data["text"]
        except (ValueError, KeyError, TypeError):
            hl.log("[novice] ignoring malformed message")
            continue
        try:
            hl.handle_text(kind, text)
        except Exception as e:
            hl.log(f"[novice] highlight error: {e!r}")


def tick():
    srv, hl = S["srv"], S["hl"]
    if srv is None:
        return None
    for _ in range(16):                                         # drain whatever has arrived
        S["got_data"] = False
        srv.server_execution_loop()
        if srv.server_execution_state != 1 or not S["got_data"]:
            break
    drain_lines(hl)

    state = srv.server_execution_state
    if state not in (0, 1):
        hl.log(f"[novice] server error (state {state}); stopping")
        stop_session(unregister_timer=False)
        return None
    connected = state == 1
    if connected != S["connected"]:
        S["connected"] = connected
        if connected:
            hl.log("[novice] expert connected")
        else:
            S["buffer"] = b""
            hl.log("[novice] expert disconnected, waiting for reconnect")
    hl.update()
    return POLL_INTERVAL


def stop_session(unregister_timer=True):
    if unregister_timer and bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for fn in (S["hl"] and S["hl"].stop, S["srv"] and S["srv"].server_close):
        if fn:
            try:
                fn()
            except Exception as e:
                print(f"[novice] cleanup error: {e!r}")
    S.update(running=False, srv=None, hl=None, buffer=b"", got_data=False, connected=False)


class NOVICE_OT_start(bpy.types.Operator):
    bl_idname = "novice.start"
    bl_label = "Start"
    bl_description = "Listen for the expert's voice and highlight matching buttons"

    def execute(self, context):
        if S["running"]:
            return {"CANCELLED"}
        try:
            scripts = resolve_scripts_dir()
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            for name in ("connection_server", "highlight"):     # always run the current files on disk
                sys.modules.pop(name, None)
            import connection_server as srv
            import highlight as hl

            srv.HOST = os.environ.get("EXPERT_HOST", srv.HOST)
            srv.PORT = int(os.environ.get("EXPERT_PORT", srv.PORT))
            S["srv"], S["hl"] = srv, hl
            srv.server_process_message_callbacks.add(on_bytes)
            srv.server_start()
            hl.EXCLUDE_CLASSES.add(NOVICE_PT_panel.__name__)
            hl.start()
            bpy.app.timers.register(tick, first_interval=0.0)
            S["running"] = True
            hl.log(f"[novice] listening on {srv.HOST}:{srv.PORT}")
        except Exception as e:
            stop_session()
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        return {"FINISHED"}


class NOVICE_OT_stop(bpy.types.Operator):
    bl_idname = "novice.stop"
    bl_label = "Stop"

    def execute(self, context):
        stop_session()
        return {"FINISHED"}


class NOVICE_PT_panel(bpy.types.Panel):
    bl_label = "Novice"
    bl_idname = "NOVICE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Novice"

    def draw(self, context):
        col = self.layout.column()
        if S["running"]:
            srv = S["srv"]
            col.label(text="Expert connected" if S["connected"] else "Waiting for expert...",
                      icon="CHECKMARK" if S["connected"] else "TIME")
            col.label(text=f"{srv.HOST}:{srv.PORT}")
            col.operator("novice.stop")
        else:
            col.operator("novice.start")


CLASSES = (NOVICE_OT_start, NOVICE_OT_stop, NOVICE_PT_panel)


@persistent
def on_load_pre(*_):
    """Loading another file: release the port, and remove this one-shot handler (the script re-registers on load)."""
    stop_session()
    if on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(on_load_pre)


def cleanup():
    stop_session()
    if on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(on_load_pre)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    NS.pop("novice_cleanup", None)


# ---------------- (re)load ----------------
# Re-running this script tears down the previous copy first, so the port, timer and UI patches never pile up.
_previous = NS.pop("novice_cleanup", None)
if _previous:
    try:
        _previous()
    except Exception as _e:
        print(f"[novice] previous cleanup failed: {_e!r}")
for _name in ("NOVICE_PT_panel", "NOVICE_OT_stop", "NOVICE_OT_start"):   # classes left by a copy whose hook was lost
    _old = getattr(bpy.types, _name, None)
    if _old is not None:
        try:
            bpy.utils.unregister_class(_old)
        except Exception:
            pass

for _cls in CLASSES:
    bpy.utils.register_class(_cls)
bpy.app.handlers.load_pre.append(on_load_pre)
NS["novice_cleanup"] = cleanup
