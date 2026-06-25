import json
import sys
import tkinter as tk
from pathlib import Path


def state_path(id: str) -> Path:
    return Path.home() / ".trafficlight" / f"{id}.json"


COLORS = {"red": "#e53935", "yellow": "#f5c518", "green": "#28c93f"}
INACTIVE = "#2d2d2d"
BG = "#1a1a2e"
RADIUS = 20
GAP = 14
PADDING = 30
CANVAS_W = RADIUS * 2 + PADDING * 2
CANVAS_H = RADIUS * 6 + GAP * 2 + PADDING * 2


def draw_light(canvas: tk.Canvas, cx: int, cy: int, color: str) -> None:
    if color != INACTIVE:
        canvas.create_oval(cx-RADIUS-6, cy-RADIUS-6, cx+RADIUS+6, cy+RADIUS+6,
                           fill=color, outline="", stipple="gray25")
        canvas.create_oval(cx-RADIUS-3, cy-RADIUS-3, cx+RADIUS+3, cy+RADIUS+3,
                           fill=color, outline="", stipple="gray50")
    canvas.create_oval(cx-RADIUS, cy-RADIUS, cx+RADIUS, cy+RADIUS,
                       fill=color, outline="#111111", width=2)


class TrafficLight:
    def __init__(self, root: tk.Tk, id: str) -> None:
        self.root = root
        self.id = id
        self.current_color = "green"

        root.title(f"TL {id}")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"{CANVAS_W}x{CANVAS_H}+{sw - CANVAS_W - 10}+10")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._render("green")
        self._poll()

    def _render(self, color: str) -> None:
        self.canvas.delete("all")
        cx = CANVAS_W // 2
        for i, name in enumerate(["red", "yellow", "green"]):
            cy = PADDING + RADIUS + i * (RADIUS * 2 + GAP)
            draw_light(self.canvas, cx, cy, COLORS[name] if color == name else INACTIVE)
        self.current_color = color

    def _poll(self) -> None:
        try:
            p = state_path(self.id)
            if p.exists():
                data = json.loads(p.read_text())
                if data.get("command") == "exit":
                    self._cleanup()
                    return
                color = data.get("color", self.current_color)
                if color != self.current_color:
                    self._render(color)
        except Exception:
            pass
        self.root.after(100, self._poll)

    def _cleanup(self) -> None:
        try:
            state_path(self.id).unlink(missing_ok=True)
        except OSError:
            pass
        self.root.destroy()

    def _on_close(self) -> None:
        self._cleanup()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: window.py <id>", file=sys.stderr)
        sys.exit(1)
    id = sys.argv[1]
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"Error: tkinter unavailable — {e}", file=sys.stderr)
        sys.exit(1)
    TrafficLight(root, id)
    root.mainloop()


if __name__ == "__main__":
    main()
