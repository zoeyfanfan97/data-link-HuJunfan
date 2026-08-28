from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


BATCH_TIME = 1710000120


def check_record(record: dict[str, Any], batch_time: int = BATCH_TIME) -> list[dict[str, Any]]:
    """检查单条记录的位置缺失、时间延迟和航向越界。"""
    alerts: list[dict[str, Any]] = []
    tid = str(record.get("target_id", "")).strip().lower()
    ts_val = record.get("timestamp") or record.get("latest_time")
    ts = int(ts_val) if ts_val not in (None, "") else 0

    # 1. R1: POSITION_MISSING (HIGH) - lat 或 lon 为空
    raw_lat = record.get("lat")
    raw_lon = record.get("lon")
    lat_is_none = raw_lat is None or str(raw_lat).strip() == ""
    lon_is_none = raw_lon is None or str(raw_lon).strip() == ""

    if lat_is_none or lon_is_none:
        missing_fields = []
        if lat_is_none:
            missing_fields.append("lat")
        if lon_is_none:
            missing_fields.append("lon")
        alerts.append({
            "alert_time": batch_time,
            "target_id": tid,
            "alert_type": "POSITION_MISSING",
            "severity": "HIGH",
            "field": "+".join(missing_fields),
            "description": f"位置字段缺失：{'+'.join(missing_fields)} 为空",
        })

    # 2. R2: DATA_DELAYED (MEDIUM) - batch_time - record_time > 60 秒
    if ts > 0 and (batch_time - ts) > 60:
        delay_sec = batch_time - ts
        alerts.append({
            "alert_time": batch_time,
            "target_id": tid,
            "alert_type": "DATA_DELAYED",
            "severity": "MEDIUM",
            "field": "timestamp",
            "description": f"数据延迟 {delay_sec} 秒，超过 60 秒阈值",
        })

    # 3. R4: HEADING_OUT_OF_RANGE (MEDIUM) - 非空且 <0 或 >=360
    raw_hdg = record.get("heading")
    if raw_hdg not in (None, ""):
        try:
            hdg = float(raw_hdg)
            if hdg < 0.0 or hdg >= 360.0:
                alerts.append({
                    "alert_time": batch_time,
                    "target_id": tid,
                    "alert_type": "HEADING_OUT_OF_RANGE",
                    "severity": "MEDIUM",
                    "field": "heading",
                    "description": f"航向角 {hdg}° 越界，要求 0 <= heading < 360",
                })
        except (ValueError, TypeError):
            alerts.append({
                "alert_time": batch_time,
                "target_id": tid,
                "alert_type": "HEADING_OUT_OF_RANGE",
                "severity": "MEDIUM",
                "field": "heading",
                "description": f"航向角格式非法：{raw_hdg}",
            })

    return alerts


def check_duplicates(records: list[dict[str, Any]], batch_time: int = BATCH_TIME) -> list[dict[str, Any]]:
    """使用 target_id + timestamp 联合键检查重复。"""
    key_counts: dict[tuple[str, int], int] = {}
    for r in records:
        tid = str(r.get("target_id", "")).strip().lower()
        ts_val = r.get("timestamp") or r.get("latest_time")
        ts = int(ts_val) if ts_val not in (None, "") else 0
        key = (tid, ts)
        key_counts[key] = key_counts.get(key, 0) + 1

    duplicate_alerts: list[dict[str, Any]] = []
    # 针对重复的每个记录实例生成告警
    for r in records:
        tid = str(r.get("target_id", "")).strip().lower()
        ts_val = r.get("timestamp") or r.get("latest_time")
        ts = int(ts_val) if ts_val not in (None, "") else 0
        key = (tid, ts)
        if key_counts.get(key, 0) > 1:
            duplicate_alerts.append({
                "alert_time": batch_time,
                "target_id": tid,
                "alert_type": "DUPLICATE_RECORD",
                "severity": "MEDIUM",
                "field": "target_id+timestamp",
                "description": f"发现重复记录：目标 {tid} 在时间戳 {ts} 出现 {key_counts[key]} 次",
            })

    return duplicate_alerts


def build_quality_situation(
    records: list[dict[str, Any]],
    record_alerts_map: list[list[dict[str, Any]]],
    batch_time: int = BATCH_TIME,
) -> list[dict[str, Any]]:
    """按 HIGH > MEDIUM > NONE 合成质量态势。"""
    key_counts: dict[tuple[str, int], int] = {}
    for r in records:
        tid = str(r.get("target_id", "")).strip().lower()
        ts_val = r.get("timestamp") or r.get("latest_time")
        ts = int(ts_val) if ts_val not in (None, "") else 0
        key = (tid, ts)
        key_counts[key] = key_counts.get(key, 0) + 1

    situation_rows: list[dict[str, Any]] = []
    for idx, rec in enumerate(records):
        tid = str(rec.get("target_id", "")).strip().lower()
        ts_val = rec.get("timestamp") or rec.get("latest_time")
        ts = int(ts_val) if ts_val not in (None, "") else 0

        raw_lat = rec.get("lat")
        raw_lon = rec.get("lon")
        lat_none = raw_lat is None or str(raw_lat).strip() == ""
        lon_none = raw_lon is None or str(raw_lon).strip() == ""
        pos_valid = (not lat_none) and (not lon_none)

        delayed = (batch_time - ts) > 60 if ts > 0 else False
        duplicate_detected = key_counts.get((tid, ts), 0) > 1

        raw_hdg = rec.get("heading")
        if raw_hdg in (None, ""):
            heading_valid = True
        else:
            try:
                hdg = float(raw_hdg)
                heading_valid = 0.0 <= hdg < 360.0
            except (ValueError, TypeError):
                heading_valid = False

        raw_mv = rec.get("message_valid", True)
        if isinstance(raw_mv, str):
            message_valid = raw_mv.strip().lower() in ("true", "1", "yes")
        else:
            message_valid = bool(raw_mv)

        alerts = record_alerts_map[idx]
        severities = {a["severity"] for a in alerts}
        if "HIGH" in severities:
            anomaly_level = "HIGH"
            display_status = "ERROR"
        elif "MEDIUM" in severities:
            anomaly_level = "MEDIUM"
            display_status = "WARNING"
        else:
            anomaly_level = "NONE"
            display_status = "NORMAL"

        situation_rows.append({
            "target_id": tid,
            "timestamp": ts,
            "position_valid": pos_valid,
            "delayed": delayed,
            "duplicate_detected": duplicate_detected,
            "heading_valid": heading_valid,
            "message_valid": message_valid,
            "anomaly_level": anomaly_level,
            "display_status": display_status,
        })

    return situation_rows


def execute_m5_pipeline(project_root: Path | None = None) -> dict[str, Any]:
    """执行M5一致性规则检查，生成告警日志与质量态势表。"""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    data_dir = project_root / "data"
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cases_path = data_dir / "m5" / "anomaly_cases.csv"
    with cases_path.open("r", encoding="utf-8-sig", newline="") as f:
        cases = list(csv.DictReader(f))

    # 计算联合键频次
    key_counts: dict[tuple[str, int], int] = {}
    for r in cases:
        tid = str(r["target_id"]).strip().lower()
        ts = int(r["timestamp"])
        key = (tid, ts)
        key_counts[key] = key_counts.get(key, 0) + 1

    all_alerts: list[dict[str, Any]] = []
    record_alerts_map: list[list[dict[str, Any]]] = []

    for idx, r in enumerate(cases):
        tid = str(r["target_id"]).strip().lower()
        ts = int(r["timestamp"])
        rec_alerts = check_record(r, batch_time=BATCH_TIME)

        # 联合键重复检查
        if key_counts.get((tid, ts), 0) > 1:
            rec_alerts.append({
                "alert_time": BATCH_TIME,
                "target_id": tid,
                "alert_type": "DUPLICATE_RECORD",
                "severity": "MEDIUM",
                "field": "target_id+timestamp",
                "description": f"发现重复记录：目标 {tid} 在时间戳 {ts} 出现 {key_counts[(tid, ts)]} 次",
            })

        record_alerts_map.append(rec_alerts)
        all_alerts.extend(rec_alerts)

    # 1. 输出 output/alert_log.csv
    alert_csv_path = output_dir / "alert_log.csv"
    alert_fieldnames = ["alert_time", "target_id", "alert_type", "severity", "field", "description"]
    with alert_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=alert_fieldnames)
        writer.writeheader()
        for alert in all_alerts:
            writer.writerow(alert)

    # 2. 输出 output/quality_situation.csv
    quality_rows = build_quality_situation(cases, record_alerts_map, batch_time=BATCH_TIME)
    quality_csv_path = output_dir / "quality_situation.csv"
    quality_fieldnames = [
        "target_id", "timestamp", "position_valid", "delayed",
        "duplicate_detected", "heading_valid", "message_valid",
        "anomaly_level", "display_status",
    ]
    with quality_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=quality_fieldnames)
        writer.writeheader()
        for row in quality_rows:
            writer.writerow(row)

    print(f"[M5] 检查完成: {len(cases)} 条用例 -> 生成 {len(all_alerts)} 条告警 -> {alert_csv_path.name}")
    print(f"[M5] 质量态势生成: {len(quality_rows)} 条记录 -> {quality_csv_path.name}")

    return {
        "case_count": len(cases),
        "alert_count": len(all_alerts),
        "quality_rows": len(quality_rows),
    }


def main() -> int:
    execute_m5_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
