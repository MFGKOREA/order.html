# How the drawing was measured

The plan is measured from the image with code, not by eye. `../build.py` runs all of this.

| Step | File | What it does |
|---|---|---|
| 1 | `lines.py` | Finds every long horizontal and vertical ink line in `floorplan.jpg` (pixel positions). |
| 2 | `scale_fit.py` | Fits mm-per-pixel separately for X and Y from the 12 dimension labels on the drawing. Prints how far each label disagrees with the fit. |
| 3 | `trace.py` | Lists each wall, door and piece of equipment as a pixel box, converts it to mm, and writes `trace.json`. It also writes `trace-check.png` with the boxes drawn over the drawing. |

## Scale

- X: **15.19 mm/px**. Y: **32.98 mm/px**. The image is squashed vertically by 2.17×.
- Inner room: **10,640 × 8,210 mm**. The first hand trace used 10,200 × 8,250, so it was 440 mm too narrow.
- All 12 labelled dimensions agree with the fit within ±30 mm, which is about one pixel.
- Three labels first came out about 120 mm off: 890, 910, and the 900 aisle on the right. In each case the wrong edge line had been picked:
  - The bottom counter front is the y=231 line. The y=227 line is an edge band.
  - The cooking line front is the x=661 line. The x=653 line is the gas rail.
- Use the fitted figures, not the raw pixels.

## Findings (default layout, minimum aisle 800 mm)

The 분석 tab in the planner computes these live.

1. **Two burners have no hood drawn.**
   - 가스렌지 on the bottom counter, x ≈ 2.9 m.
   - 가스렌지 5구, x ≈ 8.1 m.
   - Check whether a hood exists on site or the units are electric warmers.
2. **The walk-in chiller door swings into the end of the top counter.** Check the door hand and width on site.
3. **Working space in front of units is under 800 mm in these places:**
   - Bottom-right corner below the griddle: 170 mm. This is a blind corner.
   - Wall shelf, top left: 650 mm.
   - Shelf to the partition: 700 mm (labelled 709).
   - Island to the partition equipment: 790 mm (labelled 800).
4. **Walking routes.** These are A* paths on a 100 mm grid around equipment, assuming a person 300 mm wide.
   - Entrance → walk-in: 8.9 m
   - Walk-in → prep sink: 7.9 m
   - Prep → cooking line: 4.0 m
   - Cooking line → dishwasher: **12.3 m**, 1.5× the straight-line distance. The dishwasher is on the opposite wall from the cooking line.
   - The route back to the dishwasher crosses the walk-in → prep route once. That is where clean ingredients and used tools meet.

Names marked (확인) in the layout are best guesses from the drawing symbols.
