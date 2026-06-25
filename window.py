import json
import sys
import tkinter as tk
from pathlib import Path


def state_path(id: str) -> Path:
    return Path.home() / ".trafficlight" / f"{id}.json"


# (active, dim) — dim — тёмная версия цвета, не серая
LIGHT_COLORS = {
    "red":    ("#e53935", "#3d1212"),
    "yellow": ("#f5c518", "#2d2200"),
    "green":  ("#28c93f", "#0d2e18"),
}
BG      = "#1a1a2e"
TRANSP  = "#010101"   # ключ прозрачности (не используется в дизайне)
RADIUS  = 22
GAP     = 16
PADDING = 28
CORNER  = 16
CANVAS_W = RADIUS * 2 + PADDING * 2
CANVAS_H = RADIUS * 6 + GAP * 2 + PADDING * 2


def draw_rounded_bg(canvas: tk.Canvas, w: int, h: int, r: int, color: str) -> None:
    kw = dict(fill=color, outline=color)
    canvas.create_arc(0,     0,     2*r, 2*r, start=90,  extent=90, style="pieslice", **kw)
    canvas.create_arc(w-2*r, 0,     w,   2*r, start=0,   extent=90, style="pieslice", **kw)
    canvas.create_arc(0,     h-2*r, 2*r, h,   start=180, extent=90, style="pieslice", **kw)
    canvas.create_arc(w-2*r, h-2*r, w,   h,   start=270, extent=90, style="pieslice", **kw)
    canvas.create_rectangle(r,   0,   w-r, h,   **kw)
    canvas.create_rectangle(0,   r,   w,   h-r, **kw)


class TrafficLight:
    def __init__(self, root: tk.Tk, id: str) -> None:
        self.root = root
        self.id = id
        self.current_color = "green"
        self._drag_x = 0
        self._drag_y = 0

        root.overrideredirect(True)
        root.configure(bg=TRANSP)
        root.wm_attributes("-transparentcolor", TRANSP)
        root.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(root, width=CANVAS_W, height=CANVAS_H,
                                bg=TRANSP, highlightthickness=0)
        self.canvas.pack()

        # перетаскивание
        self.canvas.bind("<ButtonPress-1>",   self._drag_start)
        self.canvas.bind("<B1-Motion>",        self._drag_move)
        # правый клик — закрыть
        self.canvas.bind("<Button-3>",         lambda e: self._on_close())

        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"{CANVAS_W}x{CANVAS_H}+{sw - CANVAS_W - 10}+10")
        self._render("green")
        self._poll()

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event: tk.Event) -> None:
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _render(self, color: str) -> None:
        self.canvas.delete("all")
        draw_rounded_bg(self.canvas, CANVAS_W, CANVAS_H, CORNER, BG)
        cx = CANVAS_W // 2
        for i, name in enumerate(["red", "yellow", "green"]):
            cy = PADDING + RADIUS + i * (RADIUS * 2 + GAP)
            active, dim = LIGHT_COLORS[name]
            self.canvas.create_oval(
                cx - RADIUS, cy - RADIUS, cx + RADIUS, cy + RADIUS,
                fill=active if color == name else dim,
                outline="", width=0,
            )
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
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    TrafficLight(root, id)
    root.mainloop()


if __name__ == "__main__":
    main()
