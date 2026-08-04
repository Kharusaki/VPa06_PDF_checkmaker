#!/usr/bin/env python3
"""Download Roboto Regular and Bold from Google Fonts."""
import urllib.request
import re

css_url = "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
css = urllib.request.urlopen(req).read().decode("utf-8")

urls = re.findall(r"url\((https://fonts.gstatic.com[^)]+)\)", css)
print(f"Found {len(urls)} font URLs")

for i, url in enumerate(urls):
    if i == 0:
        fname = "Roboto-Regular.ttf"
    else:
        fname = "Roboto-Bold.ttf"
    print(f"Downloading {fname}...")
    req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req2).read()
    with open(f"templates/{fname}", "wb") as f:
        f.write(data)
    print(f"OK: {fname} ({len(data)} bytes)")

print("Done")
