"""Shared scrolling surface for the workbench's content pages."""
import tkinter as tk
from tkinter import ttk

from .appearance import COLORS as C
from .scrolling import SceneScrollCanvas


def watch_scene_scroll(canvas, body, item, callback):
    backdrop = getattr(canvas.winfo_toplevel(), '_workspace_backdrop', None)
    if backdrop is not None:
        backdrop.watch_scroll(canvas, body, item, callback)
    else:
        canvas.configure(yscrollcommand=callback)


class ScrollArea(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C['bg'])
        self.canvas = SceneScrollCanvas(self, bg=C['bg'], highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                            style='Desk.Vertical.TScrollbar')
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=C['bg'])
        item = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        watch_scene_scroll(self.canvas, self.body, item, bar.set)
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(item, width=event.width))
