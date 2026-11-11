# Kitchen Layout Planner (주방 배치 플래너)

An editable floor plan of the kitchen, traced from `floorplan.jpg`.
Open `index.html` in a browser. No install needed.

- Room: 10,640 × 8,210 mm (inner), measured by code from the drawing. See `analysis/README.md` for how the scale was fitted and what the analysis found.
- Drag to move. Edges snap to other equipment and to the grid. Handles resize. `R` rotates, `Ctrl+D` duplicates, `Delete` removes, `Ctrl+Z` undoes.
- The thick line on each piece marks its working front. Dashed boxes are ceiling hoods.
- Red areas mark overlaps. Orange dimensions mark aisles narrower than the minimum set in 설정·저장 (default 800 mm).
- The 분석 tab checks working space in front of each unit, hood coverage of burners, door swings, and walking distances between stations (A* pathfinding). It also lists the drawing-dimension check.
- **3D** (toolbar 2D/3D, or keys `2`/`3`): the same layout in three.js (loaded from cdnjs on first use). Drag to orbit, right-drag or Shift-drag to pan, wheel or pinch to zoom, click to select. Walls are cut at 1.1 m with dark cut faces so the inside stays visible ("벽 실제 높이" shows full height). Edits made in 2D or in the properties panel rebuild the scene.
- **동선 쇼** (in 3D): a 13.8 s loop that draws the four measured walking routes in turn, rolls each distance in the caption, lights the stove when the cooking leg arrives, and ends on the longest leg and the point where it crosses the prep route. Reduced-motion users get the finished frame.
- The equipment list groups items by name and size and exports to CSV. Layouts export to PNG and JSON. Named versions (A안, B안…) are kept in the browser.
- 설정·저장 → "두 점으로 축척 맞추기" re-calibrates the underlay from any known dimension line. You can also swap in a different drawing image.

## Editing

`template.html` is the page source. `analysis/trace.py` produces the default layout. `build.py` runs the trace, embeds it with `floorplan.jpg`, and writes `index.html`:

```
python3 build.py
```
