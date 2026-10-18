"""Time entry parsing shared by audition and arrangement settings."""
import math


def parse_time(value):
    try:
        parts = str(value).strip().split(":")
        if len(parts) == 1:
            result = float(parts[0])
        elif len(parts) == 2 and parts[0].isdigit():
            seconds = float(parts[1])
            if not 0 <= seconds < 60:
                raise ValueError
            result = int(parts[0]) * 60 + seconds
        else:
            raise ValueError
        if not math.isfinite(result) or not 0 <= result <= 7200:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise ValueError("片段时间请输入秒数或 分:秒，例如 35、1:20.5（最多 2 小时）。") from None
