"""Regenerate docs/demo.gif: drive the app headlessly and save one SVG frame per step.

Usage: uv run python docs/make-demo-gif.py <data-dir> <frames-dir>
Then: rsvg-convert each frame to PNG (add xml:space="preserve" to <text>) and
assemble with Pillow using the hold times in frames.txt. Needs book 31100 cached.
"""
import asyncio, os, sys
from pathlib import Path

DATA = Path(sys.argv[1]); OUT = Path(sys.argv[2])
os.environ["GUTENBERG_TUI_DATA"] = str(DATA)
from gutenberg_tui.app import GutenbergApp

app = GutenbergApp(db_path=DATA / "catalog.db")
app.shelf.remove(31100)  # start from a clean shelf
frames: list[tuple[str, float]] = []

def snap(hold: float) -> None:
    n = len(frames)
    path = OUT / f"{n:03d}.svg"
    path.write_text(app.export_screenshot(title="gutenberg-tui"))
    frames.append((path.name, hold))

async def main() -> None:
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3); snap(1.2)
        for ch in "jane austen":
            await pilot.press(ch); await pilot.pause(0.25); snap(0.12)
        snap(1.0)
        await pilot.press("down"); await pilot.pause(0.2); snap(0.8)
        await pilot.press("enter"); await pilot.pause(1.5); snap(1.6)
        for _ in range(3):
            await pilot.press("space"); await pilot.pause(0.1); snap(0.5)
        await pilot.press("slash"); await pilot.pause(0.2); snap(0.6)
        for ch in "Mr. Darcy":
            await pilot.press(ch); await pilot.pause(0.05)
        snap(0.8)
        await pilot.press("enter"); await pilot.pause(0.5); snap(1.8)
        await pilot.press("n"); await pilot.pause(0.3); snap(1.2)
        await pilot.press("a"); await pilot.pause(0.4); snap(1.6)
        await pilot.press("escape"); await pilot.pause(0.5); snap(0.8)
        await pilot.press("s"); await pilot.pause(0.5); snap(1.8)
        await pilot.press("escape"); await pilot.pause(0.3)
        await pilot.press("b"); await pilot.pause(0.8); snap(1.2)
        await pilot.press("down", "down"); await pilot.pause(0.5); snap(1.4)
        await pilot.press("t"); await pilot.pause(0.6); snap(1.6)
    (OUT / "frames.txt").write_text("".join(f"{name} {hold}\n" for name, hold in frames))
    print(len(frames), "frames")

asyncio.run(main())
