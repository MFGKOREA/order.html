"""Fit the drawing's mm-per-pixel scale on each axis from its labelled dimensions.

The supplied image is squashed vertically, so X and Y need separate scales.
Each measurement is a labelled dimension and the pixel positions of the two
lines it spans, read from the line detector (lines.py) and the gridded zooms.
Prints the fitted scales and how far each label disagrees with the fit.
"""
import json, statistics as st

X = [  # (what, px_from, px_to, label_mm)
    ("섬 작업대 폭 1,500",            502, 602, 1500),
    ("왼쪽 통로 900",                 62, 120, 900),
    ("선반~파티션 통로 709",          334.5, 381, 709),
    ("파티션 장비~섬 통로 800",       450, 502, 800),
    ("섬~조리라인 통로 900",          602, 661, 900),  # front = x661 line; x653 is the gas rail
]
Y = [
    ("워크인 깊이 2,050",             3.5, 65, 2050),
    ("워크인~파티션 870",             65, 91.5, 870),
    ("워크인~섬 690",                 65, 85, 690),
    ("섬 작업대 길이 3,910",          85, 204, 3910),
    ("섬~아래 작업대 890",            204, 231, 890),  # front = y231 line; y227 is the back edge band
    ("위 작업대~휴게실 벽 900",       24.5, 51.5, 900),
    ("휴게실 작업대~아래 작업대 910", 203, 231, 910),
]

def fit(rows):
    # robust: median of per-label ratios, then least squares on the labels within 6% of it
    ratios = [mm / (b - a) for _, a, b, mm in rows]
    med = st.median(ratios)
    keep = [r for r, k in zip(rows, ratios) if abs(k / med - 1) < 0.06]
    s = sum(mm * (b - a) for _, a, b, mm in keep) / sum((b - a) ** 2 for _, a, b, mm in keep)
    out = []
    for name, a, b, mm in rows:
        meas = (b - a) * s
        out.append({"label": name, "px": round(b - a, 1), "label_mm": mm, "drawn_mm": round(meas), "diff_mm": round(meas - mm), "used": (name, a, b, mm) in keep})
    return s, out

sx, rx = fit(X); sy, ry = fit(Y)
if __name__ == "__main__":
    print(f"X scale {sx:.3f} mm/px   Y scale {sy:.3f} mm/px   (aspect squash {sy/sx:.2f}x)")
    for axis, rows in (("X", rx), ("Y", ry)):
        for r in rows:
            flag = "" if abs(r["diff_mm"]) <= 60 else "  <-- 도면 치수와 그림이 맞지 않음"
            print(f"  {axis} {r['label']:<24} {r['px']:>6}px  표기 {r['label_mm']:>5}  그림 {r['drawn_mm']:>5}  차이 {r['diff_mm']:+5}{'' if r['used'] else ' (fit 제외)'}{flag}")
    json.dump({"sx": sx, "sy": sy, "x": rx, "y": ry}, open("scale.json", "w"), ensure_ascii=False, indent=1)
