"""Instrument layouts observed in NTE; no Windows input on import."""
from dataclasses import dataclass
from .keyboard import KEYS, PianoKey, note_name


@dataclass(frozen=True)
class Instrument:
    id: str
    title: str
    low: int
    high: int
    keys: dict

    @property
    def range_label(self):
        return f"{note_name(self.low)}–{note_name(self.high)}"


SHIFT = PianoKey("左 Shift", 0xA0, 0x2A)
# Each octave has seven natural keys. Shift raises that natural by one semitone.
PIANO_ROWS = [
    (48, "ZXCVBNM", [0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32]),
    (60, "ASDFGHJ", [0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24]),
    (72, "QWERTYU", [0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16]),
]
PIANO_KEYS = {}
for start, labels, scans in PIANO_ROWS:
    for offset, label, scan in zip((0, 2, 4, 5, 7, 9, 11), labels, scans):
        PIANO_KEYS[note_name(start + offset)] = PianoKey(label, ord(label), scan)
        if offset in (0, 2, 5, 7, 9):
            PIANO_KEYS[note_name(start + offset + 1)] = PianoKey("Shift + " + label, ord(label), scan, True)

INSTRUMENTS = {
    "guitar": Instrument("guitar", "吉他 · 钢琴模式", 52, 87, KEYS),
    "piano": Instrument("piano", "钢琴 · Shift 黑键", 48, 83, PIANO_KEYS),
}


def get_instrument(value="guitar"):
    try:
        return INSTRUMENTS[value]
    except (KeyError, TypeError):
        raise ValueError("乐器类型无效，请选择 guitar 或 piano。") from None


def score_instrument(score):
    return get_instrument(score.get("instrument", "guitar"))
