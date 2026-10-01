"""基于 vendored chan.py 的单级别缠论分析。"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
_VENDOR = Path(__file__).resolve().parents[3] / "packages" / "chan_py"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from Chan import CChan
from ChanConfig import CChanConfig
from Common.CEnum import AUTYPE, DATA_FIELD, KL_TYPE
from Common.CTime import CTime
from KLine.KLine_Unit import CKLine_Unit


def _value(bar, name):
    if isinstance(bar, dict):
        return bar[name]
    return getattr(bar, name)


def _time(value: str) -> CTime:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M" if len(value) > 10 else "%Y-%m-%d")
    return CTime(parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, auto=False)


def _units(bars, level):
    kl_type = KL_TYPE.K_DAY if level == "day" else KL_TYPE.K_30M
    result = []
    for bar in bars:
        o, c = float(_value(bar, "open")), float(_value(bar, "close"))
        h, low = float(_value(bar, "high")), float(_value(bar, "low"))
        # chan.py 要求 low <= open/close <= high;来源资料偶有不一致(如还原权息只调了收盘),收敛到合法区间
        h, low = max(h, o, c, low), min(low, o, c, h)
        result.append(CKLine_Unit({
            DATA_FIELD.FIELD_TIME: _time(_value(bar, "date")),
            DATA_FIELD.FIELD_OPEN: o,
            DATA_FIELD.FIELD_HIGH: h,
            DATA_FIELD.FIELD_LOW: low,
            DATA_FIELD.FIELD_CLOSE: c,
            DATA_FIELD.FIELD_VOLUME: float(_value(bar, "volume") or 0),
        }))
        result[-1].kl_type = kl_type
    return kl_type, result


def _date(klu):
    return klu.time.to_str().replace("/", "-")


def _line(item):
    return {
        "begin_time": _date(item.get_begin_klu()),
        "begin_val": round(float(item.get_begin_val()), 2),
        "end_time": _date(item.get_end_klu()),
        "end_val": round(float(item.get_end_val()), 2),
        "dir": item.dir.name.lower(),
        "sure": bool(item.is_sure),
    }


def analyze_level(bars, level):
    """分析一个级别，数据不足或 chan.py 出错时返回 None。"""
    if level not in ("day", "30m") or len(bars or []) < 30:
        logger.warning("缠论分析数据不足: level=%s", level)
        return None
    try:
        kl_type, units = _units(bars, level)
        config = CChanConfig({"print_warning": False, "trigger_step": True})
        chan = CChan(code="custom", data_src="custom:none.none", lv_list=[kl_type],
                     config=config, autype=AUTYPE.QFQ)
        chan.trigger_load({kl_type: units})
        data = chan[kl_type]
        bi = [_line(item) for item in data.bi_list]
        seg = [_line(item) for item in data.seg_list]
        zs = [{"begin_time": _date(item.begin), "end_time": _date(item.end),
               "zd": round(float(item.low), 2), "zg": round(float(item.high), 2), "sure": bool(item.is_sure)}
              for item in data.zs_list]
        bsp = [{"time": _date(item.klu), "price": round(float(item.klu.close), 2),
                "is_buy": bool(item.is_buy), "type": item.type2str(),
                "sure": bool(item.bi.is_sure)} for item in data.bs_point_lst.getSortedBspList()]
        last_close = round(float(_value(bars[-1], "close")), 2)
        return {"level": level, "bi": bi, "seg": seg, "zs": zs, "bsp": bsp,
                "last_close": last_close, "position": position_vs_zs(last_close, zs)}
    except Exception as exc:
        logger.warning("缠论分析失败: level=%s error=%s", level, exc)
        return None


_POSITION_ZH = {"above": "在中枢上方", "inside": "在中枢内", "below": "在中枢下方", "none": "无中枢"}
_POSITION_EN = {"above": "price above pivot", "inside": "price inside pivot",
                "below": "price below pivot", "none": "no pivot"}


def position_vs_zs(price, zs_list):
    if not zs_list:
        return "none"
    zs = zs_list[-1]
    if price < zs["zd"]:
        return "below"
    if price > zs["zg"]:
        return "above"
    return "inside"


def interval_nesting(day, m30, *, since_date):
    result = {"confirmed": False, "direction": None, "day_bsp": None, "m30_bsp": None}
    if not day or not m30:
        return result
    day_points = [p for p in day.get("bsp", []) if p["time"] >= since_date]
    if not day_points:
        return result
    day_point = day_points[-1]
    m30_points = [p for p in m30.get("bsp", []) if p["sure"] and p["time"][:10] >= since_date
                  and p["is_buy"] == day_point["is_buy"]]
    if not m30_points:
        return result
    result.update(confirmed=True, direction="buy" if day_point["is_buy"] else "sell",
                  day_bsp=day_point, m30_bsp=m30_points[-1])
    return result


def analyze_chan(day_bars, m30_bars):
    day = analyze_level(day_bars, "day")
    m30 = analyze_level(m30_bars, "30m") if m30_bars else None
    since_date = _value(day_bars[-10], "date") if len(day_bars) >= 10 else ""
    return {"day": day, "m30": m30,
            "nesting": interval_nesting(day, m30, since_date=since_date)}


def format_chan_summary(result, language):
    if not result or (not result.get("day") and not result.get("m30")):
        return ""
    day = result.get("day")
    m30 = result.get("m30")
    nesting = result.get("nesting") or {}
    if language == "en-US":
        parts = ["Chan structure:"]
        for label, item in (("day", day), ("30m", m30)):
            if item:
                last = item["bi"][-1] if item["bi"] else None
                pivot = item["zs"][-1] if item["zs"] else None
                parts.append(f"{label} last stroke: {last['dir'] if last else 'none'} "
                             f"({'sure' if last and last['sure'] else 'uncertain'}); "
                             f"pivot {pivot['zd']}-{pivot['zg']} ({_POSITION_EN.get(item['position'], item['position'])})" if pivot else
                             f"{label} last stroke: {last['dir'] if last else 'none'}")
                points = item["bsp"][-2:]
                if points:
                    parts.append("  recent points: " + ", ".join(
                        f"{p['type']} {'buy' if p['is_buy'] else 'sell'} {p['time']} "
                        f"({'sure' if p['sure'] else 'uncertain'})" for p in points
                    ))
        if nesting.get("confirmed"):
            parts.append(f"interval nesting: confirmed {nesting['direction']}")
        else:
            parts.append("interval nesting: not confirmed")
        return "\n".join(parts)
    from src.platform.language import localize_text
    parts = ["缠论结构："]
    for label, item in (("日线", day), ("30分钟", m30)):
        if item:
            last = item["bi"][-1] if item["bi"] else None
            pivot = item["zs"][-1] if item["zs"] else None
            direction = {"up": "向上", "down": "向下"}.get(last["dir"], "未知") if last else "未知"
            certainty = "确定" if last and last["sure"] else "未确定"
            text = f"{label}最后一笔：{direction}（{certainty}）"
            if pivot:
                text += f"；最后中枢 {pivot['zd']}-{pivot['zg']}，现价{_POSITION_ZH.get(item['position'], item['position'])}"
            parts.append(text)
            points = item["bsp"][-2:]
            if points:
                parts.append("最近买卖点：" + "、".join(
                    f"{p['type']}{'买' if p['is_buy'] else '卖'} {p['time']}"
                    f"（{'确定' if p['sure'] else '未确定'}）" for p in points
                ))
    if nesting.get("confirmed"):
        parts.append(f"区间套：确认{('买入' if nesting['direction'] == 'buy' else '卖出')}方向")
    else:
        parts.append("区间套：未确认")
    return localize_text("\n".join(parts), language) or ""
