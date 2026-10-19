import queue
from pathlib import Path

import bpy

from .transcription import Transcriber

MODEL_NAME = "vosk-model-small-en-us-0.15"

transcriber = None


def pump():
    """Print pending transcription events on Blender's main thread."""
    if transcriber is None:
        return None
    try:
        while True:
            kind, text = transcriber.events.get_nowait()
            print(f"[{kind}] {text}")
    except queue.Empty:
        pass
    return 0.1


class EXPERT_OT_start(bpy.types.Operator):
    bl_idname = "expert.start"
    bl_label = "Start Transcription"

    def execute(self, context):
        """Load the model, start the transcriber and register the pump timer."""
        global transcriber
        if transcriber is not None:
            return {"CANCELLED"}
        model_path = Path(bpy.utils.extension_path_user(__package__, create=True)) / MODEL_NAME
        if not model_path.exists():
            self.report({"ERROR"}, f"Model not found: {model_path}")
            return {"CANCELLED"}
        transcriber = Transcriber(model_path)
        transcriber.start()
        if not bpy.app.timers.is_registered(pump):
            bpy.app.timers.register(pump, persistent=True)
        return {"FINISHED"}


class EXPERT_OT_stop(bpy.types.Operator):
    bl_idname = "expert.stop"
    bl_label = "Stop Transcription"

    def execute(self, context):
        """Stop the transcriber; the pump timer unregisters itself."""
        global transcriber
        if transcriber is None:
            return {"CANCELLED"}
        transcriber.stop()
        transcriber = None
        return {"FINISHED"}


class EXPERT_PT_panel(bpy.types.Panel):
    bl_label = "Expert"
    bl_idname = "EXPERT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Expert"

    def draw(self, context):
        """Draw the start and stop buttons."""
        col = self.layout.column()
        col.operator("expert.start")
        col.operator("expert.stop")


classes = (EXPERT_OT_start, EXPERT_OT_stop, EXPERT_PT_panel)


def register():
    """Register operators and panel."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Stop any running transcriber and unregister operators and panel."""
    global transcriber
    if transcriber is not None:
        transcriber.stop()
        transcriber = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
