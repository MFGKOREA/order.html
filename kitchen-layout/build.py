#!/usr/bin/env python3
"""Build the kitchen layout planner.

Embeds floorplan.jpg into template.html and writes:
  index.html            standalone page (open directly in a browser)
  <artifact_out>        optional: page body only, for publishing as a claude.ai Artifact
Usage: python3 build.py [artifact_out]
"""
import base64, pathlib, sys

here = pathlib.Path(__file__).resolve().parent
tpl = (here / "template.html").read_text(encoding="utf-8")
uri = "data:image/jpeg;base64," + base64.b64encode((here / "floorplan.jpg").read_bytes()).decode()
page = tpl.replace("__FLOORPLAN_DATA_URI__", uri)
(here / "index.html").write_text(page, encoding="utf-8")

if len(sys.argv) > 1:
    body = page.split("<!--wrap-end-->", 1)[1]
    body = body.replace("</head>\n<body>\n", "", 1)
    body = body.rsplit("</body>", 1)[0].lstrip()
    pathlib.Path(sys.argv[1]).write_text(body, encoding="utf-8")
print("built", here / "index.html")
