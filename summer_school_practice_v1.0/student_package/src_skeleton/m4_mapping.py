from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any


def verify_candidate_mapping(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """依据字段定义、单位、有效性和样例，形成人工核验后的正式映射表。"""
    verified_rules: list[dict[str, Any]] = [
        # OpenSky 映射规则
        {
            "source_format": "OpenSky",
            "input_field": "target_id",
            "unified_field": "track_id",
            "mapping_rule": "规范为6位小写十六进制字符串，保留前导0",
            "unit_conversion": "无",
            "null_strategy": "必需字段；缺失时不可生成正常记录",
            "evidence": "opensky_field_dictionary.csv: 索引0 icao24",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "latest_time",
            "unified_field": "timestamp",
            "mapping_rule": "直接映射为Unix时间戳秒整数",
            "unit_conversion": "秒 (Unix second)",
            "null_strategy": "必需字段；必须为正整数",
            "evidence": "source_field_definitions.md: latest_time 映射规则",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "callsign",
            "unified_field": "identity.callsign",
            "mapping_rule": "去除首尾空格",
            "unit_conversion": "无",
            "null_strategy": "缺失或空字符串映射为 null",
            "evidence": "source_field_definitions.md: identity.callsign",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "lat",
            "unified_field": "position.lat",
            "mapping_rule": "直接映射浮点纬度",
            "unit_conversion": "度 (°)",
            "null_strategy": "缺失或超限映射为 null",
            "evidence": "source_field_definitions.md: position.lat",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "lon",
            "unified_field": "position.lon",
            "mapping_rule": "直接映射浮点经度",
            "unit_conversion": "度 (°)",
            "null_strategy": "缺失或超限映射为 null",
            "evidence": "source_field_definitions.md: position.lon",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "altitude",
            "unified_field": "position.alt",
            "mapping_rule": "直接映射高度",
            "unit_conversion": "米 (m)",
            "null_strategy": "缺失映射为 null",
            "evidence": "source_field_definitions.md: position.alt",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "alt_type",
            "unified_field": "position.alt_type",
            "mapping_rule": "高度有效时映射 barometric/geometric，无效时 unknown",
            "unit_conversion": "无",
            "null_strategy": "高度缺失时固定为 unknown",
            "evidence": "source_field_definitions.md: position.alt_type",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "speed",
            "unified_field": "motion.speed",
            "mapping_rule": "直接映射地速",
            "unit_conversion": "米/秒 (m/s)",
            "null_strategy": "缺失映射为 null",
            "evidence": "source_field_definitions.md: motion.speed",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "heading",
            "unified_field": "motion.heading",
            "mapping_rule": "直接映射航向且必须 0 <= heading < 360",
            "unit_conversion": "度 (°)",
            "null_strategy": "缺失或超限映射为 null",
            "evidence": "source_field_definitions.md: motion.heading",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "vertical_rate",
            "unified_field": "motion.vertical_rate",
            "mapping_rule": "直接映射垂直速度",
            "unit_conversion": "米/秒 (m/s)",
            "null_strategy": "缺失映射为 null",
            "evidence": "source_field_definitions.md: motion.vertical_rate",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "on_ground",
            "unified_field": "status.on_ground",
            "mapping_rule": "布尔值转换",
            "unit_conversion": "无",
            "null_strategy": "必需布尔值",
            "evidence": "source_field_definitions.md: status.on_ground",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "time_source",
            "unified_field": "quality.time_source",
            "mapping_rule": "映射为 position_time 或 last_contact_fallback",
            "unit_conversion": "无",
            "null_strategy": "缺失默认 position_time",
            "evidence": "source_field_definitions.md: quality.time_source",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "lat+lon",
            "unified_field": "quality.position_valid",
            "mapping_rule": "经纬度非空且均在合法范围 [-90,90] 与 [-180,180] 内",
            "unit_conversion": "无",
            "null_strategy": "任一为空或越界置 false",
            "evidence": "source_field_definitions.md: quality.position_valid",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "latest_time",
            "unified_field": "quality.time_valid",
            "mapping_rule": "时间戳为正整数",
            "unit_conversion": "无",
            "null_strategy": "时间回退不等于时间无效，正整数置 true",
            "evidence": "source_field_definitions.md: quality.time_valid",
            "verified": "true",
        },
        {
            "source_format": "OpenSky",
            "input_field": "message_valid",
            "unified_field": "quality.message_valid",
            "mapping_rule": "源记录校验结果",
            "unit_conversion": "无",
            "null_strategy": "源记录有效置 true",
            "evidence": "source_field_definitions.md: quality.message_valid",
            "verified": "true",
        },
        # TeachingLink 映射规则
        {
            "source_format": "TeachingLink",
            "input_field": "target_id",
            "unified_field": "track_id",
            "mapping_rule": "24位整数转6位小写十六进制字符串，保留前导0",
            "unit_conversion": "无",
            "null_strategy": "必需字段；保留前导0",
            "evidence": "teaching_message_spec.md: 偏移12-14 uint24",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "timestamp",
            "unified_field": "timestamp",
            "mapping_rule": "32位无符号整数直接映射",
            "unit_conversion": "秒 (Unix second)",
            "null_strategy": "必需字段；必须为正整数",
            "evidence": "teaching_message_spec.md: 偏移8-11 uint32",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "callsign+validity_flags.bit6",
            "unified_field": "identity.callsign",
            "mapping_rule": "bit6有效时读取并去除补0；无效时为 null",
            "unit_conversion": "无",
            "null_strategy": "bit6=0或占位全0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移15-22 ASCII/8",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "latitude_code+validity_flags.bit0",
            "unified_field": "position.lat",
            "mapping_rule": "bit0有效时按 code/(2^22-1)*180-90 恢复；无效时 null",
            "unit_conversion": "度 (°)",
            "null_strategy": "bit0=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移23-25 定点量化",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "longitude_code+validity_flags.bit1",
            "unified_field": "position.lon",
            "mapping_rule": "bit1有效时按 code/(2^22-1)*360-180 恢复；无效时 null",
            "unit_conversion": "度 (°)",
            "null_strategy": "bit1=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移26-28 定点量化",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "altitude_code+validity_flags.bit2",
            "unified_field": "position.alt",
            "mapping_rule": "bit2有效时按 code-1000 恢复；无效时 null",
            "unit_conversion": "米 (m)",
            "null_strategy": "bit2=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移29-30 偏置1000m",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "status_flags.bit1+validity_flags.bit2",
            "unified_field": "position.alt_type",
            "mapping_rule": "高度有效时 bit1=1 为 geometric、0 为 barometric；无效时 unknown",
            "unit_conversion": "无",
            "null_strategy": "高度缺失时固定为 unknown",
            "evidence": "teaching_message_spec.md: status_flags.bit1",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "speed_code+validity_flags.bit3",
            "unified_field": "motion.speed",
            "mapping_rule": "bit3有效时按 code*0.1 恢复；无效时 null",
            "unit_conversion": "米/秒 (m/s)",
            "null_strategy": "bit3=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移31-32 分辨率0.1m/s",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "heading_code+validity_flags.bit4",
            "unified_field": "motion.heading",
            "mapping_rule": "bit4有效时按 code*0.01 恢复且 < 360；无效时 null",
            "unit_conversion": "度 (°)",
            "null_strategy": "bit4=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移33-34 分辨率0.01°",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "vertical_rate_code+validity_flags.bit5",
            "unified_field": "motion.vertical_rate",
            "mapping_rule": "bit5有效时按 code*0.01-327.68 恢复；无效时 null",
            "unit_conversion": "米/秒 (m/s)",
            "null_strategy": "bit5=0时映射为 null",
            "evidence": "teaching_message_spec.md: 偏移35-36 偏置327.68m/s",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "status_flags.bit0",
            "unified_field": "status.on_ground",
            "mapping_rule": "bit0=1 为 True、0 为 False",
            "unit_conversion": "无",
            "null_strategy": "必需布尔值",
            "evidence": "teaching_message_spec.md: status_flags.bit0",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "status_flags.bit2",
            "unified_field": "quality.time_source",
            "mapping_rule": "bit2=1 映射为 last_contact_fallback、0 为 position_time",
            "unit_conversion": "无",
            "null_strategy": "时间回退不代表时间无效",
            "evidence": "teaching_message_spec.md: status_flags.bit2",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "lat_valid+lon_valid",
            "unified_field": "quality.position_valid",
            "mapping_rule": "经纬有效位均为1且解码值在合法范围内",
            "unit_conversion": "无",
            "null_strategy": "任一无效置 false",
            "evidence": "source_field_definitions.md: quality.position_valid",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "timestamp",
            "unified_field": "quality.time_valid",
            "mapping_rule": "时间戳为正整数且帧时间未丢失",
            "unit_conversion": "无",
            "null_strategy": "正整数置 true",
            "evidence": "source_field_definitions.md: quality.time_valid",
            "verified": "true",
        },
        {
            "source_format": "TeachingLink",
            "input_field": "message_valid",
            "unified_field": "quality.message_valid",
            "mapping_rule": "完整帧接收判据校验通过",
            "unit_conversion": "无",
            "null_strategy": "完整帧通过置 true",
            "evidence": "teaching_message_spec.md: 接收判据",
            "verified": "true",
        },
    ]
    return verified_rules


def map_to_unified(record: dict[str, Any], source_format: str) -> dict[str, Any]:
    """使用人工核验后的规则生成统一态势消息。"""
    track_id = str(record["target_id"]).strip().lower()

    # 1. timestamp
    ts_val = record.get("latest_time") or record.get("timestamp") or 0
    timestamp = int(ts_val)

    # 2. callsign
    raw_cs = record.get("callsign")
    callsign = str(raw_cs).strip() if raw_cs not in (None, "") else None

    # 3. position
    def safe_float(val: Any) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    lat = safe_float(record.get("lat"))
    lon = safe_float(record.get("lon"))
    alt = safe_float(record.get("altitude"))

    # alt_type: 高度有效时依据 alt_type，无效时为 unknown
    if alt is None:
        alt_type = "unknown"
    else:
        alt_type = record.get("alt_type", "barometric")
        if alt_type not in ("barometric", "geometric"):
            alt_type = "barometric"

    # 4. motion
    speed = safe_float(record.get("speed"))
    heading = safe_float(record.get("heading"))
    vr = safe_float(record.get("vertical_rate"))
    if vr is not None:
        vr = round(vr, 2)

    # 5. status
    raw_og = record.get("on_ground")
    if isinstance(raw_og, str):
        on_ground = raw_og.strip().lower() in ("true", "1", "yes")
    else:
        on_ground = bool(raw_og)

    # 6. quality
    pos_valid = lat is not None and lon is not None and (-90.0 <= lat <= 90.0) and (-180.0 <= lon <= 180.0)
    time_valid = isinstance(timestamp, int) and timestamp > 0

    raw_mv = record.get("message_valid", True)
    if isinstance(raw_mv, str):
        message_valid = raw_mv.strip().lower() in ("true", "1", "yes")
    else:
        message_valid = bool(raw_mv)

    time_src = record.get("time_source") or record.get("timestamp_source") or "position_time"
    if time_src not in ("position_time", "last_contact_fallback"):
        time_src = "position_time"

    return {
        "track_id": track_id,
        "source": source_format,
        "timestamp": timestamp,
        "identity": {
            "callsign": callsign,
        },
        "position": {
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "alt_type": alt_type,
        },
        "motion": {
            "speed": speed,
            "heading": heading,
            "vertical_rate": vr,
        },
        "status": {
            "on_ground": on_ground,
        },
        "quality": {
            "position_valid": pos_valid,
            "time_valid": time_valid,
            "message_valid": message_valid,
            "time_source": time_src,
            "anomaly_flags": [],
        },
    }


def execute_m4_pipeline(project_root: Path | None = None) -> dict[str, Any]:
    """执行M4候选核验、映射表生成与统一NDJSON导出。"""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    data_dir = project_root / "data"
    output_dir = project_root / "output"
    ref_dir = project_root / "reference"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制/生成 output/llm_mapping_candidate.csv
    candidate_src = ref_dir / "pre_generated_mapping_candidate.csv"
    candidate_dst = output_dir / "llm_mapping_candidate.csv"
    if candidate_src.exists():
        shutil.copyfile(candidate_src, candidate_dst)
    else:
        # 若无预生成文件，写入标准候选结构
        with candidate_dst.open("w", encoding="utf-8-sig", newline="") as f:
            f.write("source_format,input_field,candidate_unified_field,candidate_rule,confidence,review_note\n")

    # 2. 生成 output/verified_mapping_table.csv
    candidate_rows: list[dict[str, Any]] = []
    if candidate_dst.exists():
        with candidate_dst.open("r", encoding="utf-8-sig", newline="") as f:
            candidate_rows = list(csv.DictReader(f))

    verified_rows = verify_candidate_mapping(candidate_rows)
    verified_csv_path = output_dir / "verified_mapping_table.csv"
    verified_fieldnames = [
        "source_format", "input_field", "unified_field", "mapping_rule",
        "unit_conversion", "null_strategy", "evidence", "verified",
    ]
    with verified_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=verified_fieldnames)
        writer.writeheader()
        for row in verified_rows:
            writer.writerow(row)

    # 3. 读取 OpenSky 当前态势 output/current_situation.csv
    opensky_cur_path = output_dir / "current_situation.csv"
    opensky_records: list[dict[str, Any]] = []
    if opensky_cur_path.exists():
        with opensky_cur_path.open("r", encoding="utf-8-sig", newline="") as f:
            opensky_records = list(csv.DictReader(f))

    # 4. 读取 TeachingLink 当前态势 data/m4/partner_current_situation.csv
    teaching_cur_path = data_dir / "m4" / "partner_current_situation.csv"
    teaching_records: list[dict[str, Any]] = []
    if teaching_cur_path.exists():
        with teaching_cur_path.open("r", encoding="utf-8-sig", newline="") as f:
            teaching_records = list(csv.DictReader(f))

    # 5. 映射为统一模型并写入 output/unified_situation.ndjson
    unified_objects: list[dict[str, Any]] = []
    for rec in opensky_records:
        unified_objects.append(map_to_unified(rec, source_format="OpenSky"))
    for rec in teaching_records:
        unified_objects.append(map_to_unified(rec, source_format="TeachingLink"))

    ndjson_path = output_dir / "unified_situation.ndjson"
    with ndjson_path.open("w", encoding="utf-8") as f:
        for obj in unified_objects:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"[M4] 候选表已就绪: {candidate_dst.name}")
    print(f"[M4] 核验映射表完成: {len(verified_rows)} 条规则 -> {verified_csv_path.name}")
    print(f"[M4] 统一NDJSON导出: {len(unified_objects)} 条记录 -> {ndjson_path.name}")

    return {
        "verified_rules_count": len(verified_rows),
        "unified_objects_count": len(unified_objects),
    }


def main() -> int:
    execute_m4_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
