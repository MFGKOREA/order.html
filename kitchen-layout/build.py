#!/usr/bin/env python3
"""Build the kitchen layout planner.

1. analysis/scale_fit.py + analysis/trace.py turn floorplan.jpg pixel boxes into a mm layout (trace.json).
2. The layout, the dimension check and floorplan.jpg are embedded into template.html.

Writes index.html (open directly in a browser) and, optionally, the page body for a claude.ai Artifact:
    python3 build.py [artifact_out]
"""
import base64, json, pathlib, subprocess, sys

here = pathlib.Path(__file__).resolve().parent
ana = here / "analysis"
subprocess.run([sys.executable, "trace.py"], cwd=ana, check=True)
trace = json.loads((ana / "trace.json").read_text(encoding="utf-8"))
scale = json.loads((ana / "scale.json").read_text(encoding="utf-8"))
trace["dims"] = [{k: r[k] for k in ("label", "label_mm", "drawn_mm", "diff_mm")} for r in scale["x"] + scale["y"]]

tpl = (here / "template.html").read_text(encoding="utf-8")
uri = "data:image/jpeg;base64," + base64.b64encode((here / "floorplan.jpg").read_bytes()).decode()
page = tpl.replace("__FLOORPLAN_DATA_URI__", uri).replace("__TRACE_JSON__", json.dumps(trace, ensure_ascii=False, separators=(",", ":")))
(here / "index.html").write_text(page, encoding="utf-8")

if len(sys.argv) > 1:
    body = page.split("<!--wrap-end-->", 1)[1]
    body = body.replace("</head>\n<body>\n", "", 1)
    body = body.rsplit("</body>", 1)[0].lstrip()
    pathlib.Path(sys.argv[1]).write_text(body, encoding="utf-8")
print("built", here / "index.html")
