<h1>Blender Render View.</h1>
(This is a beta an may be unstable, do not use in production.)

External render window similar to classic IPR (maya, 3dsmax, C4D ..).
This open an external UI and stream a rendered viewport matching the render resolution.
Open Render view in render drop down or with default shortcut: CTRL ALT R

Demo Here :
https://www.youtube.com/watch?v=g3SEom4mJ3s
   
<h2>Currently working features :</h2>

- Save current render to png

- Add Snapshot (unlimited)

- Snapshot compare A & B (right click on a snapshot to set A or B)

- Snapshot compare to live view (set only A or B)

- Zoom to fit image to window

- Zoom to 1:1 ratio

- Render region (using native blender render region)

<h2>How to use:</h2>

1. Download code as zip or download release here :
https://github.com/Eisteed/blender-render-view/releases/

2. Open blender -> Edit -> Preferences -> Get Extensions -> top right down arrow -> Install from disk

3. Select downloaded zip file

4. Wait a bit for it to install, restart blender.

5. Open Render view from render -> Render View (IPR) or with CTRL-ALT-R 

6. Enjoy it for a few minutes then send me a pull request for a bug/crash you found :)

<h3>Todos:</h3>

- File path to save snapshots (re open them after restarting blender)

- Button to start / pause / reload render

- AOVs dropdown

- Toggle realtime / freeze tesselation

- And other usefull stuff (my main reference is redshift renderview)
