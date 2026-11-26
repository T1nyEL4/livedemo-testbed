# Tissot T-Complication Squelette

Open `model.blend` in Blender for the editable source, or import `model.glb` in a glTF-compatible viewer. Both contain individually named components. `parts.json` describes their functions, modeled relationships and evidence. `PLAN.md` describes the source photos, manual and modeling assumptions. `REVIEW.md` records validation.

## Interactive viewer

Start a local file server in this folder.

```sh
python3 -m http.server 8786 --bind 127.0.0.1
```

Open [the viewer](http://127.0.0.1:8786/index.html) in your browser. Play **How it works** for the walkthrough or select **Run Cycle · 60× watch time** for one small-seconds revolution per playback second at viewer speed 1×. Select **Manual Winding** to see the crown, winding gears, and ratchet turn from the back. **Take apart** and **Part separation** control the illustrative display. Select a component to inspect it with transparent context, isolation or an uncapped section preview.

## Rebuild

With the adjacent copy of the Mechanical Explorer skill and Blender 4.5 available, run from this folder.

```sh
bash '../mechanical-darkmode/scripts/blender.sh' -b --python build.py
```

The script recreates the Blender model and metadata. Run the skill checker and exporter against the rebuilt revision to refresh the GLB. See `REVIEW.md` for the current export status and render locations.
