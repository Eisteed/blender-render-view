Blender Render View.
(This is beta an may be unstable.)

External render window similar to classic IPR (redshift, vray, arnol).
This open an external UI and stream a rendered viewport matching the render resolution.

Open Render view in render drop down or with default shortcut: CTRL ALT R

Currently working features :
- Save current render to png
- Add Snapshot (unlimited)
- Snapshot compare A & B (right click on a snapshot to set A or B)
- Snapshot compare to live view (set only A or B)
- Zoom to fit image to window
- Zoom to 1:1 ratio
- Render region (using native blender render region)

Todos:
- File path to save snapshots (re open them after restarting blender)
- Button to start / pause / reload render
- AOVs dropdown
- Toggle realtime / freeze tesselation
- And other usefull stuff (my main reference is redshift renderview)