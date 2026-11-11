"""Trace the supplied floor plan into a millimetre layout.

Every item is a pixel box (x0, x1, y0, y1) read from the line detector
(lines.py) and gridded zooms of floorplan.jpg, converted with the per-axis
scale fitted in scale_fit.py. Writes trace.json (used by ../build.py) and
trace-check.png (traced boxes drawn over the drawing, for eyeballing).

Origin: inner face of the left wall (x=13px) and top wall (y=4px).
"""
import json, pathlib
from scale_fit import sx, sy

HERE = pathlib.Path(__file__).resolve().parent
OX, OY = 13, 4            # inner wall faces, px
RIGHT, BOTTOM = 713, 253  # inner wall faces, px


def mm_x(px): return round((px - OX) * sx / 10) * 10
def mm_y(py): return round((py - OY) * sy / 10) * 10


ITEMS = []


def add(type_, name, x0, x1, y0, y1, rot=0, **extra):
    x, y = mm_x(x0), mm_y(y0)
    ITEMS.append({"type": type_, "name": name, "x": x, "y": y, "w": mm_x(x1) - x, "h": mm_y(y1) - y, "rot": rot, **extra})


def door(name, side, a0, a1, wall, width=None, inward=1, flip=False):
    """A hinged door in a wall. side: 'top'|'bottom'|'left'|'right' = which edge of the swing box sits on the wall.
    a0..a1: opening along the wall (px). wall: wall face the opening sits on (px). Swing radius = opening width (mm)."""
    if side in ("top", "bottom"):
        x, w = mm_x(a0), mm_x(a1) - mm_x(a0)
        if width: w = width
        y = mm_y(wall) if side == "top" else mm_y(wall) - w
        ITEMS.append({"type": "door", "name": name, "x": x, "y": y, "w": w, "h": w, "rot": 0 if side == "top" else 180, **({"flip": True} if flip else {})})
    else:
        y, h = mm_y(a0), mm_y(a1) - mm_y(a0)
        if width: h = width
        x = mm_x(wall) if side == "left" else mm_x(wall) - h
        ITEMS.append({"type": "door", "name": name, "x": x, "y": y, "w": h, "h": h, "rot": 270 if side == "left" else 90, **({"flip": True} if flip else {})})


# ---- structure -------------------------------------------------------------
add("wall", "벽", 120, 130, 51, 149)            # staff room, left (door below)
add("wall", "벽", 296, 306, 51, 178)            # staff room, right
add("wall", "벽", 120, 306, 173, 178)           # staff room, bottom
add("wall", "벽", 120, 135, 51, 55)             # staff room, top (three pieces between two doors)
add("wall", "벽", 180, 245, 51, 55)
add("wall", "벽", 290, 306, 51, 55)
add("wall", "칸막이", 130, 296, 104, 108)       # lockers | break room
add("wall", "칸막이", 207, 217, 55, 104)        # between changing rooms
add("wall", "파티션", 381, 390, 91, 203)
add("wall", "파티션", 381, 450, 200, 203)
add("wall", "벽 (출입구 옆)", 120, 130, 226, 253)  # stub between entrance 1 and bottom counter
add("column", "기둥·설비", 13, 62, 211, 253)

# ---- doors -----------------------------------------------------------------
door("휴게실 문", "left", 149, 173, 130)
door("탈의실 문", "top", 135, 180, 55)
door("탈의실 문", "top", 245, 290, 55, flip=True)
door("출입구", "bottom", 62, 120, BOTTOM)
door("출입구", "bottom", 370, 424, BOTTOM, flip=True)
door("냉장실 문", "right", 23, 47, 425)         # walk-in chiller, opens outward (left)
door("냉동실 문", "right", 22, 46, 603)         # freezer, opens into the chiller

# ---- zones -----------------------------------------------------------------
add("zone", "탈의실 1", 130, 207, 55, 104)
add("zone", "탈의실 2", 217, 296, 55, 104)
add("zone", "휴게실", 130, 296, 108, 173)

# ---- walk-ins --------------------------------------------------------------
add("walkin", "워크인 냉장실", 425, 598, OY, 65)
add("walkin", "워크인 냉동실", 603, 708, OY, 65)

# ---- left wall line: front faces right (rot 270), front edge x=62 ----------
add("shelf", "벽선반", OX, 42, OY, 65, 270)
add("sink", "1조 싱크대", OX, 62, 65, 85, 270, n=1)
add("worktable", "세척 투입대", OX, 62, 85, 100, 270)
add("dishwasher", "식기세척기", OX, 62, 100, 117, 270)
add("worktable", "작업대", OX, 62, 117, 133, 270)
add("dishwasher", "세척 장비 (확인)", OX, 62, 133, 147, 270)
add("hood", "후드 (세척)", OX, 87, 86, 147)
add("worktable", "작업대", OX, 62, 147, 177, 270)
add("sink", "싱크대 (원형)", OX, 62, 177, 192, 270, n=1)
add("worktable", "작업대", OX, 62, 192, 211, 270)

# ---- top wall line: front faces down, front edge y=24.5 ---------------------
for x0, x1, t, nm in [(85, 145, "fridgeTable", "테이블 냉장고"), (145, 205, "worktable", "작업대"), (205, 284, "worktable", "작업대"),
                      (284, 330, "sink", "1조 싱크대"), (330, 412, "worktable", "작업대")]:
    add(t, nm, x0, x1, OY, 24.5, 0, **({"n": 1} if t == "sink" else {}))

# ---- staff room --------------------------------------------------------------
add("locker", "락커", 130, 207, 90, 104, 180)
add("locker", "락커", 217, 296, 90, 104, 180)
add("table", "테이블", 258, 296, 108, 167, 90)
add("chair", "의자", 222, 242, 113, 130, 270)
add("chair", "의자", 222, 242, 143, 160, 270)
add("shelf", "선반", 306, 335, 63, 175, 270)

# ---- counter under the staff room: front faces down, front edge y=203 ------
for x0, x1, t, nm in [(120, 170, "sink", "1조 싱크대"), (170, 240, "worktable", "작업대"), (240, 268, "kettle", "전기밥솥 (확인)"),
                      (268, 330, "fridgeTable", "테이블 냉장고"), (330, 381, "worktable", "작업대")]:
    add(t, nm, x0, x1, 178, 203, 0, **({"n": 1} if t == "sink" else {}))

# ---- behind the partition: front faces right, front edge x=450 --------------
add("handsink", "손세척대", 390, 412, 101, 115, 270)
add("oven", "가열 장비 (확인)", 390, 450, 128, 172, 270)
add("hood", "후드", 393, 482, 122, 172)
add("worktable", "작업대", 390, 450, 174, 200, 270)

# ---- island: two back-to-back halves -----------------------------------------
add("fridgeTable", "아일랜드 냉장작업대", 502, 552, 85, 204, 90)
add("fridgeTable", "아일랜드 냉장작업대", 552, 602, 85, 204, 270)

# ---- right wall cooking line: front faces left, front edge x=661 -------------
add("worktable", "작업대", 661, RIGHT, 75, 99, 90)
add("range", "가스렌지 (다구)", 661, RIGHT, 99, 178, 90, n=14)
add("worktable", "작업대", 661, RIGHT, 178, 187, 90)
add("griddle", "그리들 (확인)", 661, RIGHT, 187, 226, 90)
add("hood", "후드 (조리)", 634, RIGHT, 71, 175)
add("hood", "후드 (조리)", 634, RIGHT, 175, 234)

# ---- bottom wall line: front faces up, front edge y=231 ----------------------
for x0, x1, t, nm, n in [(130, 172, "icemaker", "제빙기", 0), (172, 206, "fridge", "냉장고", 1), (206, 230, "range", "가스렌지", 2),
                         (230, 284, "worktable", "작업대", 0), (284, 316, "handsink", "손세척대", 0), (316, 358, "sink", "1조 싱크대", 1),
                         (358, 370, "worktable", "작업대", 0),
                         (425, 482, "worktable", "작업대", 0), (482, 545, "sink", "1조 싱크대", 1), (545, 610, "range", "가스렌지 5구", 5),
                         (610, 661, "worktable", "작업대", 0), (661, 690, "handsink", "손세척대", 0), (690, RIGHT, "worktable", "작업대", 0)]:
    add(t, nm, x0, x1, 231, BOTTOM, 180, **({"n": n} if n else {}))

ROOM = {"w": mm_x(RIGHT), "h": mm_y(BOTTOM)}
UNDER = {"show": True, "opacity": 0.35, "x": round(-OX * sx), "y": round(-OY * sy), "w": round(714 * sx), "h": round(263 * sy), "custom": False}

if __name__ == "__main__":
    out = {"room": ROOM, "under": UNDER, "scale": {"sx": round(sx, 3), "sy": round(sy, 3)}, "items": ITEMS}
    (HERE / "trace.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"room {ROOM['w']} x {ROOM['h']} mm, {len(ITEMS)} items -> trace.json")
    try:
        import cv2
        k = 4
        img = cv2.resize(cv2.imread(str(HERE.parent / "floorplan.jpg")), None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        col = {"wall": (60, 60, 60), "door": (120, 120, 120), "zone": (60, 140, 200), "hood": (190, 80, 150)}
        for it in ITEMS:
            px0 = (it["x"] / sx + OX) * k; py0 = (it["y"] / sy + OY) * k
            px1 = ((it["x"] + it["w"]) / sx + OX) * k; py1 = ((it["y"] + it["h"]) / sy + OY) * k
            cv2.rectangle(img, (int(px0), int(py0)), (int(px1), int(py1)), col.get(it["type"], (40, 120, 255)), 2)
        cv2.imwrite(str(HERE / "trace-check.png"), img)
        print("wrote trace-check.png")
    except ImportError:
        pass
