import subprocess
from pathlib import Path
import os

desktop = Path.home() / "Desktop"
if not desktop.is_dir():
    print("No Desktop")
else:
    items = list(desktop.iterdir())
    for item in items:
        try:
            stat = item.stat()
            res = subprocess.run(["gio", "info", "-a", "metadata::*", str(item)], capture_output=True, text=True)
            pos = "no position"
            for line in res.stdout.splitlines():
                if "icon-position:" in line:
                    pos = line.rsplit(":", 1)[-1].strip()
            print(f"{item.name}: atime={stat.st_atime} mtime={stat.st_mtime} pos={pos}")
        except Exception as e:
            print(f"Error on {item}: {e}")
