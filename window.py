import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidgetAction,
    QWidget, QHBoxLayout, QSlider, QLabel as QLbl,
)

try:
    import psutil as _psutil
except ImportError:
    _psutil = None

STATE_DIR = Path.home() / ".trafficlight"

INVERT = {"red": "green", "green": "red", "yellow": "yellow"}

_user32   = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_dwmapi   = ctypes.windll.dwmapi


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags",               ctypes.c_ulong),
        ("rcDestination",         _RECT),
        ("rcSource",              _RECT),
        ("opacity",               ctypes.c_ubyte),
        ("fVisible",              ctypes.c_int),
        ("fSourceClientAreaOnly", ctypes.c_int),
    ]


_DWM_TNP_RECTDESTINATION      = 0x00000001
_DWM_TNP_VISIBLE              = 0x00000008
_DWM_TNP_OPACITY              = 0x00000004
_DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010

_dwmapi.DwmRegisterThumbnail.argtypes = [
    wt.HWND, wt.HWND, ctypes.POINTER(ctypes.c_void_p)
]
_dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
_dwmapi.DwmUpdateThumbnailProperties.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_DWM_THUMBNAIL_PROPERTIES)
]
_dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long
_dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.c_void_p]
_dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long

_user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(_RECT)]
_user32.GetWindowRect.restype  = ctypes.c_int
_user32.IsIconic.argtypes      = [wt.HWND]
_user32.IsIconic.restype       = ctypes.c_int
_user32.IsWindow.argtypes      = [wt.HWND]
_user32.IsWindow.restype       = ctypes.c_int


def state_path(id: str) -> Path:
    return STATE_DIR / f"{id}.json"


# ── focus helpers ──────────────────────────────────────────────────────────────

_TERMINAL_PROCS = {
    "windowsterminal.exe", "wt.exe", "conhost.exe",
    "alacritty.exe", "wezterm.exe", "mintty.exe", "hyper.exe",
}
_CLAUDE_TITLE_HINTS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏✳⠂")
_SKIP_PROCS = {
    "explorer.exe", "svchost.exe", "wmiprvse.exe", "wmiapsrv.exe",
    "services.exe", "lsass.exe", "csrss.exe", "winlogon.exe",
    "taskhostw.exe", "runtimebroker.exe",
}


def _bring_hwnd_to_front(hwnd: int) -> None:
    fg_hwnd = _user32.GetForegroundWindow()
    fg_tid  = _user32.GetWindowThreadProcessId(fg_hwnd, None)
    my_tid  = _kernel32.GetCurrentThreadId()
    tgt_tid = _user32.GetWindowThreadProcessId(hwnd, None)
    _user32.AttachThreadInput(my_tid, fg_tid, True)
    _user32.AttachThreadInput(my_tid, tgt_tid, True)
    _user32.ShowWindow(hwnd, 9)
    _user32.BringWindowToTop(hwnd)
    _user32.SetForegroundWindow(hwnd)
    _user32.AttachThreadInput(my_tid, tgt_tid, False)
    _user32.AttachThreadInput(my_tid, fg_tid, False)
    _user32.SwitchToThisWindow(hwnd, True)


def _enum_visible_windows() -> list[tuple[int, int, str]]:
    results: list[tuple[int, int, str]] = []
    buf = ctypes.create_unicode_buffer(256)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    @EnumWindowsProc
    def _cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        dpid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dpid))
        _user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if title:
            results.append((hwnd, dpid.value, title))
        return True

    _user32.EnumWindows(_cb, 0)
    return results


def _find_pid_hwnd(pid: int) -> int | None:
    """Resolve the most likely terminal window HWND for the given Claude PID.

    Walks the ancestor chain, collects every visible window that belongs to
    a non-skip ancestor (or to a conhost child of one), and scores them by
    how strongly they look like THIS Claude's window — preferring titles
    that contain the Claude process's cwd basename and/or Claude's spinner
    glyphs. Falls back to any visible terminal-process window with the same
    scoring if the ancestor chain yields nothing.
    """
    windows = _enum_visible_windows()
    pid_to_entries: dict[int, list[tuple[int, str]]] = {}
    for hwnd, wpid, title in windows:
        pid_to_entries.setdefault(wpid, []).append((hwnd, title))

    if not _psutil:
        return None

    # Cwd basename of the Claude process — the strongest per-session signal,
    # because terminals (PowerShell/WT/Claude itself) bake it into the title.
    cwd_hint = ""
    try:
        cwd = _psutil.Process(pid).cwd()
        if cwd:
            cwd_hint = Path(cwd).name.lower()
    except Exception:
        pass

    ancestor_chain: list[int] = []
    try:
        proc = _psutil.Process(pid)
        ancestor_chain.append(proc.pid)
        for _ in range(12):
            try:
                parent = proc.parent()
                if parent is None or parent.pid <= 4:
                    break
                ancestor_chain.append(parent.pid)
                proc = parent
            except Exception:
                try:
                    ancestor_chain.append(proc.ppid())
                except Exception:
                    pass
                break
    except Exception:
        pass

    def _has_claude_glyph(title: str) -> bool:
        return any(c in title for c in _CLAUDE_TITLE_HINTS)

    def _score(title: str) -> int:
        t = title.lower()
        s = 0
        if cwd_hint and cwd_hint in t:
            s += 100
        if _has_claude_glyph(title):
            s += 10
        return s

    def _pick(entries: list[tuple[int, str]]) -> int | None:
        if not entries:
            return None
        ranked = sorted(entries, key=lambda e: _score(e[1]), reverse=True)
        return ranked[0][0]

    # Collect every candidate (hwnd, title) reachable from the ancestor chain —
    # both ancestors themselves and any conhost children they own.
    candidates: list[tuple[int, str]] = []
    seen_hwnds: set[int] = set()

    def _push(entries):
        for hwnd, title in entries:
            if hwnd not in seen_hwnds:
                seen_hwnds.add(hwnd)
                candidates.append((hwnd, title))

    for apid in ancestor_chain:
        try:
            name = _psutil.Process(apid).name().lower()
        except Exception:
            name = ""
        if name in _SKIP_PROCS:
            continue
        if apid in pid_to_entries:
            _push(pid_to_entries[apid])
        try:
            for child in _psutil.Process(apid).children():
                if child.name().lower() == "conhost.exe" and child.pid in pid_to_entries:
                    _push(pid_to_entries[child.pid])
        except Exception:
            pass

    best = _pick(candidates)
    if best is not None:
        return best

    term_pids: set[int] = set()
    try:
        for p in _psutil.process_iter(["pid", "name"]):
            if (p.info["name"] or "").lower() in _TERMINAL_PROCS:
                term_pids.add(p.info["pid"])
    except Exception:
        pass

    term_candidates = [
        (hwnd, title) for hwnd, wpid, title in windows if wpid in term_pids
    ]
    return _pick(term_candidates)


def _focus_pid_window(pid: int) -> bool:
    hwnd = _find_pid_hwnd(pid)
    if hwnd:
        _bring_hwnd_to_front(hwnd)
        return True
    return False


# ── hover preview window ───────────────────────────────────────────────────────

class PreviewWindow(QWidget):
    """Live DWM thumbnail of the target Claude console — at its real size & position."""

    PAD        = 8
    FALLBACK_W = 800
    FALLBACK_H = 500

    def __init__(self, light_widget: "TrafficLight", source_hwnd: int) -> None:
        super().__init__()
        self._source_hwnd = source_hwnd
        self._thumb: ctypes.c_void_p | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen().geometry()

        rect = _RECT()
        have_rect = (
            _user32.GetWindowRect(source_hwnd, ctypes.byref(rect))
            and not _user32.IsIconic(source_hwnd)
            and rect.right - rect.left > 0
            and rect.bottom - rect.top > 0
            and rect.left > -10000  # minimized windows report ~-32000
        )

        dpr = self.devicePixelRatioF() or 1.0
        if have_rect:
            inner_w = max(int((rect.right - rect.left) / dpr), 80)
            inner_h = max(int((rect.bottom - rect.top) / dpr), 60)
            src_x   = int(rect.left / dpr)
            src_y   = int(rect.top  / dpr)
        else:
            inner_w, inner_h = self.FALLBACK_W, self.FALLBACK_H
            src_x = src_y = None

        # cap to screen so we never overflow even for huge windows
        inner_w = min(inner_w, screen.width()  - self.PAD * 2)
        inner_h = min(inner_h, screen.height() - self.PAD * 2)

        self._inner = (inner_w, inner_h)
        total_w = inner_w + self.PAD * 2
        total_h = inner_h + self.PAD * 2
        self.setFixedSize(total_w, total_h)

        if src_x is not None:
            x = src_x - self.PAD
            y = src_y - self.PAD
        else:
            lp = light_widget.pos()
            x = lp.x() - total_w - 8
            y = lp.y()

        x = max(0, min(x, screen.width()  - total_w))
        y = max(0, min(y, screen.height() - total_h))
        self.move(x, y)

        self.show()
        QTimer.singleShot(0, self._register_thumbnail)

    def _register_thumbnail(self) -> None:
        try:
            dest_hwnd = wt.HWND(int(self.winId()))
        except Exception:
            return

        thumb = ctypes.c_void_p()
        hr = _dwmapi.DwmRegisterThumbnail(
            dest_hwnd, wt.HWND(self._source_hwnd), ctypes.byref(thumb)
        )
        if hr != 0 or not thumb.value:
            return
        self._thumb = thumb

        inner_w, inner_h = self._inner
        props = _DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = (
            _DWM_TNP_RECTDESTINATION
            | _DWM_TNP_VISIBLE
            | _DWM_TNP_OPACITY
            | _DWM_TNP_SOURCECLIENTAREAONLY
        )
        props.rcDestination = _RECT(
            self.PAD, self.PAD, self.PAD + inner_w, self.PAD + inner_h
        )
        props.opacity = 255
        props.fVisible = 1
        props.fSourceClientAreaOnly = 0
        _dwmapi.DwmUpdateThumbnailProperties(self._thumb, ctypes.byref(props))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        p.fillPath(path, QColor(22, 22, 28, 235))
        p.setPen(QPen(QColor(80, 80, 95), 1))
        p.drawPath(path)
        p.end()

    def closeEvent(self, event):
        if self._thumb:
            try:
                _dwmapi.DwmUnregisterThumbnail(self._thumb)
            except Exception:
                pass
            self._thumb = None
        super().closeEvent(event)


# ── chart window ───────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


class ChartWindow(QWidget):
    W, H   = 400, 240
    PAD    = dict(l=48, r=16, t=36, b=48)

    def __init__(self, tl: "TrafficLight") -> None:
        super().__init__()
        self._tl = tl

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        # position to the left of the traffic light
        tl_pos = tl.pos()
        self.move(max(0, tl_pos.x() - self.W - 8), tl_pos.y())

        self._drag_pos = QPoint()

        self._tick = QTimer(self)
        self._tick.timeout.connect(self.update)
        self._tick.start(1000)

        self.show()

    def _series(self):
        """Return (times[], cum_red[], cum_green[]) relative to session start."""
        history = self._tl._history
        now = time.time()
        t0 = history[0][0]

        times   = [0.0]
        cum_red = [0.0]
        cum_grn = [0.0]
        cr = cg = 0.0

        events = history + [(now, None)]
        for i in range(len(events) - 1):
            t_start, color = events[i]
            t_end           = events[i + 1][0]
            dt = t_end - t_start
            if color == "red":
                cr += dt
            elif color == "green":
                cg += dt
            times.append(t_end - t0)
            cum_red.append(cr)
            cum_grn.append(cg)

        return times, cum_red, cum_grn

    def paintEvent(self, _):
        times, cum_red, cum_grn = self._series()
        total_t  = times[-1] if times else 1
        max_y    = max(cum_red[-1], cum_grn[-1], 1)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── background ──────────────────────────────────────────────
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.W, self.H), 12, 12)
        p.fillPath(path, QColor(22, 22, 28, 235))
        p.setPen(QPen(QColor(60, 60, 70), 1))
        p.drawPath(path)

        pl = self.PAD["l"]
        pr = self.W - self.PAD["r"]
        pt = self.PAD["t"]
        pb = self.H - self.PAD["b"]
        cw = pr - pl
        ch = pb - pt

        def tx(t):  return pl + t / total_t * cw
        def ty(v):  return pb - v / max_y * ch

        # ── grid ────────────────────────────────────────────────────
        grid_pen = QPen(QColor(50, 50, 60), 1, Qt.PenStyle.DashLine)
        p.setPen(grid_pen)
        for i in range(1, 5):
            y = pt + ch * i / 4
            p.drawLine(int(pl), int(y), int(pr), int(y))
        for i in range(1, 5):
            x = pl + cw * i / 4
            p.drawLine(int(x), int(pt), int(x), int(pb))

        # ── axes ────────────────────────────────────────────────────
        axis_pen = QPen(QColor(80, 80, 95), 1)
        p.setPen(axis_pen)
        p.drawLine(pl, pt, pl, pb)
        p.drawLine(pl, pb, pr, pb)

        # Y axis labels
        lbl_font = QFont("Segoe UI", 8)
        p.setFont(lbl_font)
        p.setPen(QColor(120, 120, 140))
        for i in range(5):
            v = max_y * i / 4
            y = ty(v)
            p.drawText(2, int(y) + 4, pl - 6, 12,
                       Qt.AlignmentFlag.AlignRight, _fmt_time(v))

        # X axis labels
        for i in range(5):
            t = total_t * i / 4
            x = tx(t)
            p.drawText(int(x) - 20, pb + 4, 40, 14,
                       Qt.AlignmentFlag.AlignHCenter, _fmt_time(t))

        # ── filled areas ────────────────────────────────────────────
        def draw_area(values, fill_color, line_color):
            if len(times) < 2:
                return
            area = QPainterPath()
            area.moveTo(tx(times[0]), pb)
            for t, v in zip(times, values):
                area.lineTo(tx(t), ty(v))
            area.lineTo(tx(times[-1]), pb)
            area.closeSubpath()
            p.fillPath(area, QColor(*fill_color, 40))

            line = QPainterPath()
            line.moveTo(tx(times[0]), ty(values[0]))
            for t, v in zip(times[1:], values[1:]):
                line.lineTo(tx(t), ty(v))
            p.setPen(QPen(QColor(*line_color), 2))
            p.drawPath(line)

        draw_area(cum_red, (220, 60,  60),  (220, 60,  60))
        draw_area(cum_grn, (60,  200, 80),  (60,  200, 80))

        # ── title ───────────────────────────────────────────────────
        p.setPen(QColor(190, 190, 210))
        title_font = QFont("Segoe UI", 9)
        title_font.setBold(True)
        p.setFont(title_font)
        p.drawText(pl, 4, cw, pt - 4,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "Session stats")

        # close button
        p.setPen(QColor(120, 120, 140))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(self.W - 24, 4, 20, pt - 4,
                   Qt.AlignmentFlag.AlignCenter, "✕")

        # ── stats bar ───────────────────────────────────────────────
        stat_font = QFont("Segoe UI", 9)
        p.setFont(stat_font)
        bar_y = pb + 28

        p.setPen(QColor(220, 80, 80))
        p.drawText(pl, bar_y, 120, 14, Qt.AlignmentFlag.AlignLeft,
                   f"● Red: {_fmt_time(cum_red[-1])}")

        p.setPen(QColor(80, 200, 100))
        p.drawText(pl + 120, bar_y, 120, 14, Qt.AlignmentFlag.AlignLeft,
                   f"● Green: {_fmt_time(cum_grn[-1])}")

        p.setPen(QColor(160, 160, 180))
        p.drawText(pl + 248, bar_y, 120, 14, Qt.AlignmentFlag.AlignLeft,
                   f"Total: {_fmt_time(total_t)}")

        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # close if clicking the ✕ area
            if e.position().x() > self.W - 28 and e.position().y() < 28:
                self.close()
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()


# ── opacity slider widget ──────────────────────────────────────────────────────

class _OpacityWidget(QWidget):
    def __init__(self, initial: int, on_change) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        lbl = QLbl("Прозрачность")
        lbl.setStyleSheet("color:#ddd; font-size:12px;")
        layout.addWidget(lbl)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(20, 100)
        self.slider.setValue(initial)
        self.slider.setFixedWidth(120)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height:4px; background:#555; border-radius:2px; }
            QSlider::handle:horizontal {
                background:#aaa; width:14px; height:14px; margin:-5px 0;
                border-radius:7px;
            }
            QSlider::sub-page:horizontal { background:#888; border-radius:2px; }
        """)
        self.slider.valueChanged.connect(on_change)
        layout.addWidget(self.slider)

        self.val_lbl = QLbl(f"{initial}%")
        self.val_lbl.setStyleSheet("color:#aaa; font-size:11px;")
        self.val_lbl.setFixedWidth(34)
        layout.addWidget(self.val_lbl)

        self.slider.valueChanged.connect(lambda v: self.val_lbl.setText(f"{v}%"))


# ── main widget ────────────────────────────────────────────────────────────────

class TrafficLight(QLabel):
    def __init__(self, id: str, watch_pid: int | None = None, terminal_hwnd: int | None = None) -> None:
        super().__init__()
        self.id            = id
        self.watch_pid     = watch_pid
        self.terminal_hwnd = terminal_hwnd
        self.current_color = "green"
        self._drag_pos     = QPoint()
        self._press_pos    = QPoint()
        self._was_dragged  = False
        self._inverted     = False
        self._opacity      = 100
        self._auto_focus   = False
        self._chart_win: ChartWindow | None = None
        self._preview_win: PreviewWindow | None = None

        # Snapshot the watched Claude process so a PID reuse later doesn't
        # keep us alive forever after the real Claude has exited.
        self._watch_proc = None
        self._watch_ctime: float | None = None
        if self.watch_pid and _psutil:
            try:
                self._watch_proc  = _psutil.Process(self.watch_pid)
                self._watch_ctime = self._watch_proc.create_time()
            except (_psutil.NoSuchProcess, _psutil.AccessDenied, OSError):
                self._watch_proc = None

        # time tracking
        _now = time.time()
        self._history: list[tuple[float, str]] = [(_now, "green")]

        imgs_dir = Path(__file__).parent
        self.pixmaps = {
            name: QPixmap(str(imgs_dir / f"{name}.png")).scaledToWidth(
                111, Qt.TransformationMode.SmoothTransformation
            )
            for name in ("red", "yellow", "green")
        }

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._set_color("green")

        screen = QApplication.primaryScreen().geometry()
        pm     = self.pixmaps["green"]
        self.move(screen.width() - pm.width() - 10, 10)
        self.show()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(100)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._show_preview)

    def _displayed(self, color: str) -> str:
        return INVERT[color] if self._inverted else color

    def _resolve_hwnd(self) -> int | None:
        """HWND of the terminal hosting this Claude — snapshot first, fallback to heuristic."""
        if self.terminal_hwnd and _user32.IsWindow(self.terminal_hwnd):
            return self.terminal_hwnd
        if self.watch_pid:
            return _find_pid_hwnd(self.watch_pid)
        return None

    def _set_color(self, color: str) -> None:
        prev = self.current_color
        pm = self.pixmaps[self._displayed(color)]
        self.setPixmap(pm)
        self.resize(pm.size())
        self.current_color = color

        if color != prev:
            self._history.append((time.time(), color))
            if color == "green" and self._auto_focus:
                hwnd = self._resolve_hwnd()
                if hwnd:
                    _bring_hwnd_to_front(hwnd)

    def _watch_dead(self) -> bool:
        """True iff the original Claude process is gone (and not a PID reuse)."""
        if not self._watch_proc:
            return False
        try:
            if not self._watch_proc.is_running():
                return True
            if self._watch_ctime is not None and self._watch_proc.create_time() != self._watch_ctime:
                return True
        except (_psutil.NoSuchProcess, _psutil.AccessDenied, OSError):
            return True
        return False

    def _shutdown(self, drop_state: bool = True) -> None:
        if drop_state:
            try:
                state_path(self.id).unlink(missing_ok=True)
            except OSError:
                pass
        if self._chart_win:
            try:
                self._chart_win.close()
            except Exception:
                pass
            self._chart_win = None
        self._hide_preview()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _poll(self) -> None:
        try:
            if self._watch_dead():
                self._shutdown(drop_state=True)
                return
            p = state_path(self.id)
            if not p.exists():
                self._shutdown(drop_state=False)
                return
            data = json.loads(p.read_text())
            if data.get("command") == "exit":
                self._shutdown(drop_state=True)
                return
            color = data.get("color", self.current_color)
            if color != self.current_color:
                self._set_color(color)
        except Exception:
            pass

    def _show_menu(self, global_pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background:#2b2b2b; border:1px solid #444;
                border-radius:6px; padding:4px 0;
            }
            QMenu::item { color:#ddd; padding:6px 20px; font-size:13px; }
            QMenu::item:selected { background:#3d3d3d; }
            QMenu::item:checked { color:#8cf; }
            QMenu::separator { height:1px; background:#444; margin:3px 8px; }
        """)

        ow = _OpacityWidget(self._opacity, self._on_opacity)
        ow.setStyleSheet("background:#2b2b2b;")
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(ow)
        menu.addAction(wa)

        menu.addSeparator()

        inv_action = menu.addAction("Инверсия")
        inv_action.setCheckable(True)
        inv_action.setChecked(self._inverted)
        inv_action.triggered.connect(self._toggle_invert)

        focus_action = menu.addAction("Авто-фокус на зелёный")
        focus_action.setCheckable(True)
        focus_action.setChecked(self._auto_focus)
        focus_action.triggered.connect(lambda checked: setattr(self, "_auto_focus", checked))

        menu.addSeparator()

        menu.addAction("График").triggered.connect(self._show_chart)

        menu.addSeparator()

        menu.addAction("Закрыть").triggered.connect(self._do_close)

        menu.exec(global_pos)

    def _show_chart(self) -> None:
        if self._chart_win and not self._chart_win.isHidden():
            self._chart_win.close()
            self._chart_win = None
        else:
            self._chart_win = ChartWindow(self)

    def _on_opacity(self, value: int) -> None:
        self._opacity = value
        self.setWindowOpacity(value / 100)

    def _toggle_invert(self, checked: bool) -> None:
        self._inverted = checked
        self._set_color(self.current_color)

    def _do_close(self) -> None:
        self._shutdown(drop_state=True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos    = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos   = e.globalPosition().toPoint()
            self._was_dragged = False
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            cur = e.globalPosition().toPoint()
            if not self._was_dragged:
                d = cur - self._press_pos
                if abs(d.x()) + abs(d.y()) <= 4:
                    return
                self._was_dragged = True
                self._hide_preview()
                self._preview_timer.stop()
            self.move(cur - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self._was_dragged:
            self._hide_preview()
            self._preview_timer.stop()
            hwnd = self._resolve_hwnd()
            if hwnd:
                _bring_hwnd_to_front(hwnd)

    def enterEvent(self, event):
        if self.watch_pid or self.terminal_hwnd:
            self._preview_timer.start(120)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._preview_timer.stop()
        self._hide_preview()
        super().leaveEvent(event)

    def _show_preview(self) -> None:
        if self._preview_win:
            return
        hwnd = self._resolve_hwnd()
        if not hwnd:
            return
        self._preview_win = PreviewWindow(self, hwnd)

    def _hide_preview(self) -> None:
        if self._preview_win:
            try:
                self._preview_win.close()
            except Exception:
                pass
            self._preview_win = None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("id")
    parser.add_argument("--watch-pid", type=int, default=None)
    parser.add_argument("--terminal-hwnd", type=int, default=None)
    args, remaining = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + remaining)
    app.setQuitOnLastWindowClosed(True)
    _win = TrafficLight(args.id, watch_pid=args.watch_pid, terminal_hwnd=args.terminal_hwnd)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
