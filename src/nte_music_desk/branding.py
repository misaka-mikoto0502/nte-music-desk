"""The full Chinese wordmark as one bundled, transparent image."""
import tkinter as tk
from PIL import Image, ImageTk

from .appearance import COLORS


class DeskWordmark(tk.Label):
    """Scale the seven-character artwork together, preserving its proportions."""
    def __init__(self, parent, image_path):
        try:
            with Image.open(image_path) as original:
                artwork = original.convert('RGBA')
            bounds = artwork.getchannel('A').getbbox()
            if bounds is None:
                raise ValueError('The wordmark is empty')
            artwork = artwork.crop(bounds)
            artwork.thumbnail((176, 100), Image.Resampling.LANCZOS)
            self.artwork = ImageTk.PhotoImage(artwork, master=parent)
            super().__init__(parent, image=self.artwork, width=176, height=100,
                bg=COLORS['paper'], borderwidth=0, padx=0, pady=0, takefocus=False)
        except (OSError, ValueError):
            super().__init__(parent, text='异环演奏\n工具台', font=('Microsoft YaHei UI', 19, 'bold'),
                bg=COLORS['paper'], fg=COLORS['ink'], borderwidth=0, padx=0, pady=8, takefocus=False)
