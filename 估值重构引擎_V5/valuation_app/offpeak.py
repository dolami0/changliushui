"""DeepSeek 峰谷定价避峰工具

高峰时段（北京时间 9:00-12:00、14:00-18:00）价格为空闲时段的 2 倍。
天机峰管线需要实时性不避峰；其余管线（主估值/万业谱/望气）只在空闲时段运行。
"""

from datetime import datetime, timedelta, timezone

# 高峰时段（北京时间）
_PEAK_RANGES_BJ = [(9, 12), (14, 18)]


def is_peak_bj(dt_utc: datetime | None = None) -> bool:
    """当前（或给定 UTC 时间）是否处于北京时间高峰时段。"""
    dt = dt_utc if dt_utc is not None else datetime.now(timezone.utc)
    bj = dt + timedelta(hours=8)
    minutes = bj.hour * 60 + bj.minute
    for start_h, end_h in _PEAK_RANGES_BJ:
        if start_h * 60 <= minutes < end_h * 60:
            return True
    return False


def seconds_until_offpeak(dt_utc: datetime | None = None) -> float:
    """距离下一个空闲时段开始的秒数。已处于空闲时段时返回 0。"""
    dt = dt_utc if dt_utc is not None else datetime.now(timezone.utc)
    if not is_peak_bj(dt):
        return 0.0

    bj = dt + timedelta(hours=8)
    minutes_now = bj.hour * 60 + bj.minute
    # 找到下一个时段边界
    for start_h, end_h in _PEAK_RANGES_BJ:
        if start_h * 60 <= minutes_now < end_h * 60:
            return (end_h * 60 - minutes_now) * 60.0
    return 0.0
