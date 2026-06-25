import json
import sys
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


IMGS_DIR = Path(__file__).parent
TRANSP   = "#010101"


def state_path(id: str) -> Path:
    return Path.home() / ".trafficlight" / f"{id}.json"


def load_images() -> dict:
    imgs = {}
    for name in ("red", "yellow", "green"):
        p = IMGS_DIR / f"{name}.png"
        img = Image.open(p).convert("RGBA")
        # заменяем прозрачные пиксели на TRANSP чтобы окно было прозрачным там
        r, g, b = int(TRANSP[1:3], 16), int(TRANSP[3:5], 16), int(TRANSP[5:7], 16)
        bg = Image.new("RGBA", img.size, (r, g, b, 255))
        bg.paste(img, mask=img.split()[3])
        imgs[name] = ImageTk.PhotoImage(bg)
    return imgs


class TrafficLight:
    def __init__(self, root: tk.Tk, id: str) -> None:
        self.root = root
        self.id = id
        self.current_color = "green"
        self._drag_x = 0
        self._drag_y = 0

        self.images = load_images()
        w = self.images["green"].width()
        h = self.images["green"].height()

        root.overrideredirect(True)
        root.configure(bg=TRANSP)
        root.wm_attributes("-transparentcolor", TRANSP)
        root.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(root, width=w, height=h,
                                bg=TRANSP, highlightthickness=0)
        self.canvas.pack()
        self._img_item = self.canvas.create_image(0, 0, anchor="nw",
                                                  image=self.images["green"])

        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>",     self._drag_move)
        self.canvas.bind("<Button-3>",      lambda e: self._on_close())

        root.update_idletasks()
        sw = root.winfo_screenwidth()
        root.geometry(f"{w}x{h}+{sw - w - 10}+10")
        self._poll()

    def _drag_start(self, e: tk.Event) -> None:
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_move(self, e: tk.Event) -> None:
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _render(self, color: str) -> None:
        self.canvas.itemconfig(self._img_item, image=self.images[color])
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
