from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# 兼容包内与直接运行导入
try:
    from m2_protocol import FRAME_SIZE, decode_position_message, encode_position_message, parse_state_vector
except ImportError:
    from student_package.src_skeleton.m2_protocol import (
        FRAME_SIZE,
        decode_position_message,
        encode_position_message,
        parse_state_vector,
    )


def decode_message_stream(data: bytes, frame_size: int = FRAME_SIZE) -> list[dict[str, Any]]:
    """按固定帧长批量解码；记录并忽略不完整尾帧。"""
    records: list[dict[str, Any]] = []
    total_len = len(data)
    num_frames = total_len // frame_size
    residual = total_len % frame_size

    if residual != 0:
        print(f"[WARN] 消息流尾部存在 {residual} 字节残余（非完整帧），已自动忽略。")

    for i in range(num_frames):
        chunk = data[i * frame_size : (i + 1) * frame_size]
        decoded = decode_position_message(chunk)
        decoded["source"] = "partner_stream"
        records.append(decoded)

    return records


def save_records_to_sqlite(records: list[dict[str, Any]], db_path: str) -> None:
    """选做：保存接收记录，None必须写为NULL。"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS state_record")
    cursor.execute("""
    CREATE TABLE state_record (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT,
        callsign TEXT NULL,
        timestamp INTEGER,
        timestamp_source TEXT,
        message_seq INTEGER,
        lat REAL NULL,
        lon REAL NULL,
        altitude REAL NULL,
        alt_type TEXT NULL,
        speed REAL NULL,
        heading REAL NULL,
        vertical_rate REAL NULL,
        on_ground INTEGER,
        status_flags INTEGER,
        validity_flags INTEGER,
        message_valid INTEGER,
        source TEXT
    );
    """)

    insert_sql = """
    INSERT INTO state_record (
        target_id, callsign, timestamp, timestamp_source, message_seq,
        lat, lon, altitude, alt_type, speed, heading, vertical_rate,
        on_ground, status_flags, validity_flags, message_valid, source
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    rows_to_insert = []
    for rec in records:
        rows_to_insert.append((
            rec.get("target_id"),
            rec.get("callsign"),
            rec.get("timestamp"),
            rec.get("timestamp_source") or rec.get("time_source"),
            rec.get("message_seq"),
            rec.get("lat"),
            rec.get("lon"),
            rec.get("altitude"),
            rec.get("alt_type"),
            rec.get("speed"),
            rec.get("heading"),
            rec.get("vertical_rate"),
            1 if rec.get("on_ground") else 0,
            rec.get("status_flags"),
            rec.get("validity_flags"),
            1 if rec.get("message_valid") else 0,
            rec.get("source", "partner"),
        ))

    cursor.executemany(insert_sql, rows_to_insert)
    conn.commit()

    # 简单自查查询
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT target_id) FROM state_record WHERE message_valid = 1")
    count, distinct_targets = cursor.fetchone()
    conn.close()
    print(f"[SQLite] 成功保存 {len(records)} 条记录到 {db_path}，有效记录数={count}，目标数={distinct_targets}")


def build_tracks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅使用可接受记录，按target_id分组并按timestamp排序，生成从1开始的track_sequence_no。"""
    # 筛选可接受记录：message_valid=True 且必需字段可用
    valid_records = [
        r for r in records
        if r.get("message_valid") and r.get("target_id") and r.get("timestamp") is not None
    ]

    # 按 target_id 分组
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in valid_records:
        tid = r["target_id"]
        grouped.setdefault(tid, []).append(r)

    track_rows: list[dict[str, Any]] = []
    # 保持 target_id 顺序有序
    for tid in sorted(grouped.keys()):
        # 组内按 timestamp 升序（时间相同时按 message_seq 排序）
        points = sorted(grouped[tid], key=lambda x: (x["timestamp"], x.get("message_seq", 0)))
        for seq_no, pt in enumerate(points, start=1):
            track_rows.append({
                "target_id": tid,
                "timestamp": pt["timestamp"],
                "message_seq": pt.get("message_seq", 0),
                "track_sequence_no": seq_no,
                "lat": pt.get("lat"),
                "lon": pt.get("lon"),
                "altitude": pt.get("altitude"),
                "speed": pt.get("speed"),
                "heading": pt.get("heading"),
            })

    return track_rows


def build_current_situation(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每个目标保留时间最新的可接受记录；可选字段缺失仍可入选。"""
    valid_records = [
        r for r in records
        if r.get("message_valid") and r.get("target_id") and r.get("timestamp") is not None
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in valid_records:
        tid = r["target_id"]
        grouped.setdefault(tid, []).append(r)

    situation_rows: list[dict[str, Any]] = []
    for tid in sorted(grouped.keys()):
        points = grouped[tid]
        track_length = len(points)
        # 选择时间最新的记录（时间相同时选 message_seq 最大的）
        latest = max(points, key=lambda x: (x["timestamp"], x.get("message_seq", 0)))

        situation_rows.append({
            "target_id": tid,
            "callsign": latest.get("callsign"),
            "latest_time": latest["timestamp"],
            "lat": latest.get("lat"),
            "lon": latest.get("lon"),
            "altitude": latest.get("altitude"),
            "speed": latest.get("speed"),
            "heading": latest.get("heading"),
            "vertical_rate": latest.get("vertical_rate"),
            "on_ground": latest.get("on_ground", False),
            "track_length": track_length,
            "alt_type": latest.get("alt_type", "unknown"),
            "time_source": latest.get("time_source") or latest.get("timestamp_source", "position_time"),
            "message_valid": latest.get("message_valid", True),
        })

    return situation_rows


def execute_m3_pipeline(
    project_root: Path | None = None,
) -> dict[str, Any]:
    """执行M3批量解码、航迹关联、当前态势提取与SQLite入库。"""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    data_dir = project_root / "data"
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 读取并批量解码 partner_messages_multitime.bin
    bin_path = data_dir / "partner_messages_multitime.bin"
    raw_bytes = bin_path.read_bytes()
    decoded_records = decode_message_stream(raw_bytes, frame_size=FRAME_SIZE)

    # 2. 输出 output/decoded_multitime.csv
    decoded_csv_path = output_dir / "decoded_multitime.csv"
    fieldnames = [
        "target_id", "callsign", "timestamp", "timestamp_source", "time_source",
        "message_seq", "lat", "lon", "altitude", "alt_type", "speed", "heading",
        "vertical_rate", "on_ground", "status_flags", "validity_flags",
        "latitude_code", "longitude_code", "altitude_code", "speed_code",
        "heading_code", "vertical_rate_code", "lat_valid", "lon_valid",
        "altitude_valid", "speed_valid", "heading_valid", "vertical_rate_valid",
        "callsign_valid", "checksum", "expected_checksum", "message_valid",
        "validation_errors", "source",
    ]
    with decoded_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in decoded_records:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})

    # 3. 关联构建航迹表 track_table.csv
    track_rows = build_tracks(decoded_records)
    track_csv_path = output_dir / "track_table.csv"
    track_fieldnames = [
        "target_id", "timestamp", "message_seq", "track_sequence_no",
        "lat", "lon", "altitude", "speed", "heading",
    ]
    with track_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=track_fieldnames)
        writer.writeheader()
        for row in track_rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in track_fieldnames})

    # 4. 生成当前态势表 current_situation.csv
    situation_rows = build_current_situation(decoded_records)
    sit_csv_path = output_dir / "current_situation.csv"
    sit_fieldnames = [
        "target_id", "callsign", "latest_time", "lat", "lon", "altitude",
        "speed", "heading", "vertical_rate", "on_ground", "track_length",
        "alt_type", "time_source", "message_valid",
    ]
    with sit_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sit_fieldnames)
        writer.writeheader()
        for row in situation_rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in sit_fieldnames})

    # 5. 选做：持久化至 SQLite 数据库 output/states.db
    db_path = str(output_dir / "states.db")
    save_records_to_sqlite(decoded_records, db_path)

    print(f"[M3] 批量解码: {len(decoded_records)} 帧 -> {decoded_csv_path.name}")
    print(f"[M3] 航迹构建: {len(track_rows)} 点 -> {track_csv_path.name}")
    print(f"[M3] 当前态势: {len(situation_rows)} 目标 -> {sit_csv_path.name}")

    return {
        "decoded_count": len(decoded_records),
        "track_points": len(track_rows),
        "situation_targets": len(situation_rows),
    }


def validate_opensky_real_data(project_root: Path | None = None) -> dict[str, Any]:
    """验证 OpenSky 真实快照数据的解析、编码、解码与航迹生成。"""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    real_data_dir = project_root / "data" / "opensky_real"
    if not real_data_dir.exists():
        print("[M3 Real] 未找到 opensky_real 目录，跳过真实数据验证。")
        return {}

    real_bin = real_data_dir / "opensky_real_messages.bin"
    if real_bin.exists():
        data = real_bin.read_bytes()
        frames = decode_message_stream(data)
        tracks = build_tracks(frames)
        situation = build_current_situation(frames)
        print(f"[M3 Real] 成功验证真实快照: {len(frames)} 帧, {len(tracks)} 航迹点, {len(situation)} 活跃目标。")
        return {
            "real_frames": len(frames),
            "real_tracks": len(tracks),
            "real_targets": len(situation),
        }
    return {}


def main() -> int:
    execute_m3_pipeline()
    validate_opensky_real_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
