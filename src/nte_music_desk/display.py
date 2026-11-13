"""System DPI and compact window sizing for the Tk desktop."""
import ctypes
from ctypes import wintypes
import sys


def enable_system_dpi_awareness():
    """For source launches, opt in before Tk creates any windows."""
    if sys.platform == 'win32':
        ctypes.windll.user32.SetProcessDPIAware()


def pixels(widget, size):
    """Convert a layout distance at 96 DPI to a Tk pixel distance."""
    return round(size * widget.winfo_fpixels('1i') / 96)


def available_window_size(widget):
    """Leave room for window decorations within the desktop work area."""
    width, height = widget.winfo_screenwidth(), widget.winfo_screenheight()
    if sys.platform == 'win32':
        area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0):  # SPI_GETWORKAREA
            width, height = area.right - area.left, area.bottom - area.top
    return max(1, width - 32), max(1, height - 64)


def set_main_window_size(root):
    """Open at the existing minimum layout size, fitted to the work area."""
    width, height = available_window_size(root)
    dpi = round(root.winfo_fpixels('1i'))
    scale = min(dpi / 96, width / 1000, height / 700)
    root.tk.call('tk', 'scaling', scale * 96 / 72)
    width, height = round(1000 * scale), round(700 * scale)
    root.minsize(width, height)
    root.geometry(f'{width}x{height}')
