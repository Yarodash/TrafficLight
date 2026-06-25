import json
import sys
import tkinter as tk
from pathlib import Path


def state_path(id: str) -> Path:
    return Path.home() / ".trafficlight" / f"{id}.json"


# (active_bright, active_glow, dim)
LIGHT_COLORS = {
    "red":    ("#ff3d3d", "#c0001a", "#3d1212"),
    "yellow": ("#ffe033", "#b87800", "#2d2200"),
    "green":  ("#2dff5a", "#007a28", "#0d2e18"),
}
SOCKET   = "#0d0d1a"   # гнездо лампочки
BG       = "#1e1e32"
BG_EDGE  = "#14142a"   # чуть темнее для глубины корпуса
TRANSP   = "#010101"
RADIUS   = 22
GAP      = 18
PADDING  = 30
CORNER   = 18
CANVAS_W = RADIUS * 2 + PADDING * 2
CANVAS_H = RADIUS * 6 + GAP * 2 + PADDING * 2


def draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int,
                      r: int, color: str, outline: str = "") -> None:
    kw = dict(fill=color, outline=outline or color)
    canvas.create_arc(x1,       y1,       x1+2*r, y1+2*r, start=90,  extent=90, style="pieslice", **kw)
    canvas.create_arc(x2-2*r,   y1,       x2,     y1+2*r, start=0,   extent=90, style="pieslice", **kw)
    canvas.create_arc(x1,       y2-2*r,   x1+2*r, y2,     start=180, extent=90, style="pieslice", **kw)
    canvas.create_arc(x2-2*r,   y2-2*r,   x2,     y2,     start=270, extent=90, style="pieslice", **kw)
    canvas.create_rectangle(x1+r, y1, x2-r, y2, **kw)
    canvas.create_rectangle(x1, y1+r, x2, y2-r, **kw)


def draw_light(canvas: tk.Canvas, cx: int, cy: int, name: str, active: bool) -> None:
    bright, glow, dim = LIGHT_COLORS[name]
    R = RADIUS

    # гнездо (углублённый ободок вокруг лампы)
    canvas.create_oval(cx-R-5, cy-R-5, cx+R+5, cy+R+5, fill=SOCKET, outline="")

    if active:
        # внешнее свечение — чуть больше, основной цвет (имитация ореола)
        canvas.create_oval(cx-R-2, cy-R-2, cx+R+2, cy+R+2, fill=glow, outline="")
        # основная лампочка
        canvas.create_oval(cx-R, cy-R, cx+R, cy+R, fill=bright, outline="")
        # блик — маленький светлый эллипс в левом верхнем углу
        hx, hy, hr = cx - R//3, cy - R//3, R//4
        canvas.create_oval(hx-hr, hy-hr//2, hx+hr, hy+hr//2,
                           fill="#ffffff", outline="", stipple="gray50")
    else:
        canvas.create_oval(cx-R, cy-R, cx+R, cy+R, fill=dim, outline="")


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

        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>",     self._drag_move)
        self.canvas.bind("<Button-3>",      lambda e: self._on_close())

        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"{CANVAS_W}x{CANVAS_H}+{sw - CANVAS_W - 10}+10")
        self._render("green")
        self._poll()

    def _drag_start(self, e: tk.Event) -> None:
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_move(self, e: tk.Event) -> None:
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _render(self, color: str) -> None:
        c = self.canvas
        c.delete("all")

        # тень корпуса (3 слоя offset)
        for i, shade in enumerate(("#0a0a14", "#0d0d1c", "#111126")):
            o = 4 - i
            draw_rounded_rect(c, o, o, CANVAS_W+o, CANVAS_H+o, CORNER, shade)

        # основной корпус
        draw_rounded_rect(c, 0, 0, CANVAS_W, CANVAS_H, CORNER, BG)

        # тонкая светлая полоска сверху — имитация объёма
        draw_rounded_rect(c, 2, 2, CANVAS_W-2, CANVAS_H//3, CORNER, BG_EDGE)

        # лампочки
        cx = CANVAS_W // 2
        for i, name in enumerate(["red", "yellow", "green"]):
            cy = PADDING + RADIUS + i * (RADIUS * 2 + GAP)
            draw_light(c, cx, cy, name, color == name)

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
