"""Original geometric Chinese lettering, drawn with the desk's own paints."""
import tkinter as tk

from .appearance import COLORS


class DeskWordmark(tk.Canvas):
    """A font-independent 异环 wordmark; the subtitle stays native text."""
    def __init__(self, parent):
        super().__init__(parent, width=168, height=100, bg=COLORS['paper'],
                         highlightthickness=0, borderwidth=0, takefocus=False)
        # Open terminals and shared stroke widths connect the two characters.
        strokes = (
            ((10, 8, 53, 8, 53, 25, 14, 25), 'ink'),
            ((14, 8, 14, 34, 19, 39, 49, 39, 55, 33), 'ink'),
            ((7, 49, 61, 49), 'teal'),
            ((25, 43, 25, 54, 20, 63, 10, 68), 'ink'),
            ((45, 43, 45, 68), 'ink'),
            ((85, 10, 108, 10), 'ink'),
            ((87, 32, 107, 32), 'ink'),
            ((83, 58, 109, 52), 'ink'),
            ((97, 10, 97, 55), 'ink'),
            ((119, 10, 158, 10), 'teal'),
            ((144, 10, 138, 27, 119, 46), 'ink'),
            ((139, 27, 139, 68), 'ink'),
            ((148, 33, 159, 46), 'ink'),
        )
        for points, paint in strokes:
            self.create_line(*points, fill=COLORS[paint], width=4.5,
                             capstyle=tk.ROUND, joinstyle=tk.ROUND)
        self.create_text(7, 84, text='演 奏 工 作 台', anchor='nw',
                         fill=COLORS['ink'], font=('Microsoft YaHei UI', 9))
