"""Find long straight lines in the floor plan image (pixel coordinates)."""
import cv2, numpy as np, sys, json
img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else '../floorplan.jpg')
g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
bw = (g < 140).astype(np.uint8)                     # dark ink
H, W = bw.shape
def runs(mask, axis, minlen):
    """Return (pos, start, end) of runs of ink of length>=minlen along rows (axis=1) or cols (axis=0)."""
    out = []
    m = mask if axis == 1 else mask.T
    for i, row in enumerate(m):
        d = np.diff(np.concatenate([[0], row, [0]]))
        st, en = np.where(d == 1)[0], np.where(d == -1)[0]
        for a, b in zip(st, en):
            if b - a >= minlen: out.append((i, int(a), int(b)))
    return out
h = runs(bw, 1, 40); v = runs(bw, 0, 25)
print('image', W, H)
print('H lines (y, x0-x1) len>=40:')
for y, a, b in sorted(h): print(f'  y={y:3d}  x {a:3d}-{b:3d}  ({b-a})')
print('V lines (x, y0-y1) len>=25:')
for x, a, b in sorted(v): print(f'  x={x:3d}  y {a:3d}-{b:3d}  ({b-a})')
