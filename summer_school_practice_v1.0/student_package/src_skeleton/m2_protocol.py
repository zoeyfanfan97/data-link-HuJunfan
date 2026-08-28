from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any


FRAME_SIZE = 41
MAGIC = 0x4453
VERSION = 1
MESSAGE_TYPE = 1


def Q(y: float) -> int:
    """统一量化函数：Q(y) = floor(y + 0.5)"""
    return int(math.floor(y + 0.5))


def calculate_checksum(data_without_checksum: bytes) -> int:
    """计算前39字节无符号字节值之和模65536。"""
    return sum(data_without_checksum[:39]) % 65536


def parse_state_vector(vector: list[Any]) -> dict[str, Any]:
    """将OpenSky状态向量转换为发送方内部结构化记录。"""
    if len(vector) < 12:
        raise ValueError(f"Vector length too short: {len(vector)}")

    # 1. target_id (icao24) - 必需，恰好6位十六进制字符串
    raw_icao = vector[0]
    if raw_icao is None:
        raise ValueError("REQUIRED_FIELD_MISSING: target_id is null")
    target_id = str(raw_icao).strip().lower()
    if len(target_id) != 6 or not all(c in "0123456789abcdef" for c in target_id):
        raise ValueError(f"TYPE_ERROR: target_id must be 6 hex chars, got {target_id}")

    # 2. callsign - 可空，1-8个ASCII字符
    raw_callsign = vector[1]
    callsign: str | None = None
    if raw_callsign is not None:
        cs = str(raw_callsign).strip()
        if len(cs) > 0:
            if len(cs) > 8 or not cs.isascii():
                raise ValueError(f"ENCODING_ERROR: callsign invalid {cs}")
            callsign = cs

    # 3. timestamp - 必需，优先 time_position，为空时使用 last_contact
    time_pos = vector[3]
    last_cont = vector[4]
    if time_pos is not None:
        timestamp = int(time_pos)
        timestamp_source = "position_time"
        time_source = "position_time"
        timestamp_fallback = False
    elif last_cont is not None:
        timestamp = int(last_cont)
        timestamp_source = "last_contact_fallback"
        time_source = "last_contact_fallback"
        timestamp_fallback = True
    else:
        raise ValueError("REQUIRED_FIELD_MISSING: both time_position and last_contact are null")

    # 4. on_ground - 必需，布尔值
    raw_on_ground = vector[8]
    if raw_on_ground is None or not isinstance(raw_on_ground, bool):
        raise ValueError("REQUIRED_FIELD_MISSING: on_ground must be boolean")
    on_ground = bool(raw_on_ground)

    # 5. altitude - 优先 baro_altitude，为空时使用 geo_altitude
    raw_baro = vector[7]
    raw_geo = vector[13] if len(vector) > 13 else None
    altitude: float | None = None
    alt_type = "unknown"
    altitude_is_geometric = False

    if raw_baro is not None:
        alt_val = float(raw_baro)
        if not (-1000.0 <= alt_val <= 64535.0):
            raise ValueError(f"OUT_OF_RANGE: baro_altitude {alt_val} out of range")
        altitude = alt_val
        alt_type = "barometric"
        altitude_is_geometric = False
    elif raw_geo is not None:
        alt_val = float(raw_geo)
        if not (-1000.0 <= alt_val <= 64535.0):
            raise ValueError(f"OUT_OF_RANGE: geo_altitude {alt_val} out of range")
        altitude = alt_val
        alt_type = "geometric"
        altitude_is_geometric = True

    # 6. lat & lon
    raw_lat = vector[6]
    lat: float | None = None
    if raw_lat is not None:
        lat_val = float(raw_lat)
        if not (-90.0 <= lat_val <= 90.0):
            raise ValueError(f"OUT_OF_RANGE: latitude {lat_val} out of range")
        lat = lat_val

    raw_lon = vector[5]
    lon: float | None = None
    if raw_lon is not None:
        lon_val = float(raw_lon)
        if not (-180.0 <= lon_val <= 180.0):
            raise ValueError(f"OUT_OF_RANGE: longitude {lon_val} out of range")
        lon = lon_val

    # 7. speed (velocity)
    raw_vel = vector[9]
    speed: float | None = None
    if raw_vel is not None:
        vel_val = float(raw_vel)
        if not (0.0 <= vel_val <= 6553.5):
            raise ValueError(f"OUT_OF_RANGE: speed {vel_val} out of range")
        speed = vel_val

    # 8. heading (true_track) - 0 <= heading < 360
    raw_track = vector[10]
    heading: float | None = None
    if raw_track is not None:
        track_val = float(raw_track)
        if not (0.0 <= track_val < 360.0):
            raise ValueError(f"OUT_OF_RANGE: heading {track_val} out of range [0, 360)")
        heading = track_val

    # 9. vertical_rate
    raw_vr = vector[11]
    vertical_rate: float | None = None
    if raw_vr is not None:
        vr_val = float(raw_vr)
        if not (-327.68 <= vr_val <= 327.67):
            raise ValueError(f"OUT_OF_RANGE: vertical_rate {vr_val} out of range [-327.68, 327.67]")
        vertical_rate = vr_val

    return {
        "target_id": target_id,
        "callsign": callsign,
        "timestamp": timestamp,
        "timestamp_source": timestamp_source,
        "time_source": time_source,
        "timestamp_fallback": timestamp_fallback,
        "lat": lat,
        "lon": lon,
        "altitude": altitude,
        "alt_type": alt_type,
        "altitude_is_geometric": altitude_is_geometric,
        "speed": speed,
        "heading": heading,
        "vertical_rate": vertical_rate,
        "on_ground": on_ground,
        "lat_valid": lat is not None,
        "lon_valid": lon is not None,
        "altitude_valid": altitude is not None,
        "speed_valid": speed is not None,
        "heading_valid": heading is not None,
        "vertical_rate_valid": vertical_rate is not None,
        "callsign_valid": callsign is not None,
    }


def encode_position_message(record: dict[str, Any], message_seq: int = 0) -> bytes:
    """按41字节TeachingLink格式封装一条位置状态消息。"""
    payload = bytearray()

    # 0-1: magic (uint16 big endian)
    payload.extend(MAGIC.to_bytes(2, "big"))
    # 2: version (uint8)
    payload.append(VERSION)
    # 3: message_type (uint8)
    payload.append(MESSAGE_TYPE)
    # 4-5: message_length (uint16 big endian = 41)
    payload.extend(FRAME_SIZE.to_bytes(2, "big"))
    # 6-7: message_seq (uint16 big endian, mod 65536)
    seq = message_seq % 65536
    payload.extend(seq.to_bytes(2, "big"))
    # 8-11: timestamp (uint32 big endian)
    ts = int(record["timestamp"])
    payload.extend(ts.to_bytes(4, "big"))
    # 12-14: target_id (uint24 big endian)
    target_int = int(record["target_id"], 16)
    payload.extend(target_int.to_bytes(3, "big"))

    # 15-22: callsign (8 bytes ASCII padded with \x00)
    if record.get("callsign_valid") and record.get("callsign"):
        cs_bytes = record["callsign"].encode("ascii")
        cs_padded = cs_bytes.ljust(8, b"\x00")[:8]
    else:
        cs_padded = b"\x00" * 8
    payload.extend(cs_padded)

    # 23-25: latitude_code (3 bytes / 22-bit, highest 2 bits 0)
    if record.get("lat_valid") and record.get("lat") is not None:
        lat_val = float(record["lat"])
        lat_code = Q((lat_val + 90.0) / 180.0 * (2**22 - 1))
    else:
        lat_code = 0
    payload.extend(lat_code.to_bytes(3, "big"))

    # 26-28: longitude_code (3 bytes / 22-bit, highest 2 bits 0)
    if record.get("lon_valid") and record.get("lon") is not None:
        lon_val = float(record["lon"])
        lon_code = Q((lon_val + 180.0) / 360.0 * (2**22 - 1))
    else:
        lon_code = 0
    payload.extend(lon_code.to_bytes(3, "big"))

    # 29-30: altitude_code (uint16, bias 1000m, resolution 1m)
    if record.get("altitude_valid") and record.get("altitude") is not None:
        alt_val = float(record["altitude"])
        alt_code = Q(alt_val + 1000.0)
    else:
        alt_code = 0
    payload.extend(alt_code.to_bytes(2, "big"))

    # 31-32: speed_code (uint16, resolution 0.1m/s)
    if record.get("speed_valid") and record.get("speed") is not None:
        spd_val = float(record["speed"])
        spd_code = Q(spd_val / 0.1)
    else:
        spd_code = 0
    payload.extend(spd_code.to_bytes(2, "big"))

    # 33-34: heading_code (uint16, resolution 0.01 deg)
    if record.get("heading_valid") and record.get("heading") is not None:
        hdg_val = float(record["heading"])
        hdg_code = Q(hdg_val / 0.01)
    else:
        hdg_code = 0
    payload.extend(hdg_code.to_bytes(2, "big"))

    # 35-36: vertical_rate_code (uint16, bias 327.68m/s, resolution 0.01m/s)
    if record.get("vertical_rate_valid") and record.get("vertical_rate") is not None:
        vr_val = float(record["vertical_rate"])
        vr_code = Q((vr_val + 327.68) / 0.01)
    else:
        vr_code = 0
    payload.extend(vr_code.to_bytes(2, "big"))

    # 37: status_flags (bit0=on_ground, bit1=alt_is_geo, bit2=ts_fallback, bit3-7=0)
    on_ground_bit = 1 if record.get("on_ground") else 0
    alt_geo_bit = 1 if record.get("altitude_is_geometric") or record.get("alt_type") == "geometric" else 0
    ts_fallback_bit = 1 if record.get("timestamp_fallback") or record.get("timestamp_source") == "last_contact_fallback" else 0
    status_flags = on_ground_bit | (alt_geo_bit << 1) | (ts_fallback_bit << 2)
    payload.append(status_flags)

    # 38: validity_flags (bit0..bit6, bit7=0)
    lat_v = 1 if record.get("lat_valid") else 0
    lon_v = 1 if record.get("lon_valid") else 0
    alt_v = 1 if record.get("altitude_valid") else 0
    spd_v = 1 if record.get("speed_valid") else 0
    hdg_v = 1 if record.get("heading_valid") else 0
    vr_v = 1 if record.get("vertical_rate_valid") else 0
    cs_v = 1 if record.get("callsign_valid") else 0
    validity_flags = lat_v | (lon_v << 1) | (alt_v << 2) | (spd_v << 3) | (hdg_v << 4) | (vr_v << 5) | (cs_v << 6)
    payload.append(validity_flags)

    # 39-40: checksum
    checksum = calculate_checksum(payload)
    payload.extend(checksum.to_bytes(2, "big"))

    return bytes(payload)


def decode_position_message(data: bytes) -> dict[str, Any]:
    """检查帧接收条件并恢复接收方结构化记录。"""
    validation_errors: list[str] = []
    message_valid = True

    # 1. 长度检查
    if len(data) != FRAME_SIZE:
        return {
            "message_valid": False,
            "validation_errors": ["LENGTH_ERROR"],
            "error_detail": f"Length is {len(data)}, expected {FRAME_SIZE}",
        }

    # 2. 字段解析
    magic = int.from_bytes(data[0:2], "big")
    version = data[2]
    message_type = data[3]
    message_length = int.from_bytes(data[4:6], "big")
    message_seq = int.from_bytes(data[6:8], "big")
    timestamp = int.from_bytes(data[8:12], "big")
    target_int = int.from_bytes(data[12:15], "big")
    target_id = f"{target_int:06x}"
    callsign_bytes = data[15:23]
    lat_code = int.from_bytes(data[23:26], "big")
    lon_code = int.from_bytes(data[26:29], "big")
    alt_code = int.from_bytes(data[29:31], "big")
    speed_code = int.from_bytes(data[31:33], "big")
    heading_code = int.from_bytes(data[33:35], "big")
    vr_code = int.from_bytes(data[35:37], "big")
    status_flags = data[37]
    validity_flags = data[38]
    checksum = int.from_bytes(data[39:41], "big")

    # 3. 校验码
    expected_checksum = calculate_checksum(data[:39])
    if checksum != expected_checksum:
        validation_errors.append("CHECKSUM_ERROR")
        message_valid = False

    # 4. 头字段检查
    if magic != MAGIC:
        validation_errors.append("MAGIC_ERROR")
        message_valid = False
    if version != VERSION:
        validation_errors.append("VERSION_ERROR")
        message_valid = False
    if message_type != MESSAGE_TYPE:
        validation_errors.append("MESSAGE_TYPE_ERROR")
        message_valid = False
    if message_length != FRAME_SIZE:
        validation_errors.append("LENGTH_ERROR")
        message_valid = False

    # 5. 保留位检查
    # 经纬度最高2位为0
    if (data[23] & 0xC0) != 0 or (data[26] & 0xC0) != 0:
        validation_errors.append("RESERVED_BITS_ERROR")
        message_valid = False
    # status_flags bit3-bit7保留为0
    if (status_flags & 0xF8) != 0:
        validation_errors.append("RESERVED_BITS_ERROR")
        message_valid = False
    # validity_flags bit7保留为0
    if (validity_flags & 0x80) != 0:
        validation_errors.append("RESERVED_BITS_ERROR")
        message_valid = False

    # 6. 标志位与占位一致性检查 (FLAG_VALUE_INCONSISTENCY)
    lat_valid = bool(validity_flags & 1)
    lon_valid = bool(validity_flags & 2)
    alt_valid = bool(validity_flags & 4)
    speed_valid = bool(validity_flags & 8)
    heading_valid = bool(validity_flags & 16)
    vr_valid = bool(validity_flags & 32)
    callsign_valid = bool(validity_flags & 64)

    if not lat_valid and lat_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not lon_valid and lon_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not alt_valid and alt_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not speed_valid and speed_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not heading_valid and heading_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not vr_valid and vr_code != 0:
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False
    if not callsign_valid and callsign_bytes != (b"\x00" * 8):
        validation_errors.append("FLAG_VALUE_INCONSISTENCY")
        message_valid = False

    # 7. 物理值恢复
    on_ground = bool(status_flags & 1)
    alt_is_geo = bool(status_flags & 2)
    ts_fallback = bool(status_flags & 4)
    timestamp_source = "last_contact_fallback" if ts_fallback else "position_time"
    time_source = timestamp_source

    if not alt_valid:
        alt_type = "unknown"
    else:
        alt_type = "geometric" if alt_is_geo else "barometric"

    lat = (lat_code / (2**22 - 1) * 180.0 - 90.0) if lat_valid else None
    lon = (lon_code / (2**22 - 1) * 360.0 - 180.0) if lon_valid else None
    altitude = float(alt_code - 1000) if alt_valid else None
    speed = (speed_code * 0.1) if speed_valid else None
    heading = (heading_code * 0.01) if heading_valid else None
    vertical_rate = round(vr_code * 0.01 - 327.68, 2) if vr_valid else None

    callsign: str | None = None
    if callsign_valid:
        try:
            raw_cs = callsign_bytes.split(b"\x00")[0].decode("ascii")
            callsign = raw_cs if raw_cs else None
        except UnicodeDecodeError:
            callsign = None
            validation_errors.append("ENCODING_ERROR")
            message_valid = False

    return {
        "target_id": target_id,
        "callsign": callsign,
        "timestamp": timestamp,
        "timestamp_source": timestamp_source,
        "time_source": time_source,
        "message_seq": message_seq,
        "lat": lat,
        "lon": lon,
        "altitude": altitude,
        "alt_type": alt_type,
        "speed": speed,
        "heading": heading,
        "vertical_rate": vertical_rate,
        "on_ground": on_ground,
        "status_flags": status_flags,
        "validity_flags": validity_flags,
        "latitude_code": lat_code,
        "longitude_code": lon_code,
        "altitude_code": alt_code,
        "speed_code": speed_code,
        "heading_code": heading_code,
        "vertical_rate_code": vr_code,
        "lat_valid": lat_valid,
        "lon_valid": lon_valid,
        "altitude_valid": alt_valid,
        "speed_valid": speed_valid,
        "heading_valid": heading_valid,
        "vertical_rate_valid": vr_valid,
        "callsign_valid": callsign_valid,
        "checksum": checksum,
        "expected_checksum": expected_checksum,
        "message_valid": message_valid,
        "validation_errors": ";".join(validation_errors),
        "source": "partner",
    }


def execute_m2_pipeline(
    project_root: Path | None = None,
) -> dict[str, Any]:
    """执行M2完整数据处理：编码raw_states、解码partner数据、生成误差与验证日志。"""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]

    data_dir = project_root / "data"
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    validation_logs: list[dict[str, Any]] = []
    encoded_frames: list[bytes] = []
    valid_records: list[dict[str, Any]] = []

    # 1. 处理 raw_states.json
    raw_path = data_dir / "raw_states.json"
    raw_json = json.loads(raw_path.read_text(encoding="utf-8"))
    states = raw_json.get("states", [])

    for idx, vector in enumerate(states):
        record_no = idx + 1
        raw_icao = str(vector[0]) if vector and vector[0] is not None else ""
        try:
            record = parse_state_vector(vector)
            frame = encode_position_message(record, message_seq=record_no)
            encoded_frames.append(frame)
            valid_records.append(record)
        except Exception as exc:
            msg = str(exc)
            problem_type = "TYPE_ERROR"
            field_name = "unknown"
            if "REQUIRED_FIELD_MISSING" in msg:
                problem_type = "REQUIRED_FIELD_MISSING"
                field_name = msg.split(":")[-1].strip()
            elif "OUT_OF_RANGE" in msg:
                problem_type = "OUT_OF_RANGE"
                field_name = msg.split(":")[1].strip().split()[0] if ":" in msg else "field"
            elif "ENCODING_ERROR" in msg:
                problem_type = "ENCODING_ERROR"
                field_name = "callsign"

            validation_logs.append({
                "record_no": record_no,
                "target_id": raw_icao,
                "stage": "sender_encode",
                "field": field_name,
                "problem_type": problem_type,
                "value": str(vector),
                "description": msg,
            })

    # 写入 output/encoded_messages.bin
    encoded_bin_path = output_dir / "encoded_messages.bin"
    with encoded_bin_path.open("wb") as f:
        for frame in encoded_frames:
            f.write(frame)

    # 2. 解码 student_package/data/partner_messages_sample.bin
    partner_sample_path = data_dir / "partner_messages_sample.bin"
    partner_bin = partner_sample_path.read_bytes()
    decoded_partner_records: list[dict[str, Any]] = []

    for idx in range(len(partner_bin) // FRAME_SIZE):
        frame = partner_bin[idx * FRAME_SIZE : (idx + 1) * FRAME_SIZE]
        decoded = decode_position_message(frame)
        decoded["source"] = "partner"
        decoded_partner_records.append(decoded)
        if not decoded["message_valid"]:
            validation_logs.append({
                "record_no": idx + 1,
                "target_id": decoded.get("target_id", ""),
                "stage": "receiver_decode",
                "field": "frame",
                "problem_type": decoded["validation_errors"].split(";")[0],
                "value": frame.hex(),
                "description": decoded["validation_errors"],
            })

    # 写入 output/decoded_partner_states.csv
    decoded_csv_path = output_dir / "decoded_partner_states.csv"
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
        for row in decoded_partner_records:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})

    # 3. 构造异常测试帧以充分检验接收端判据并记录 validation_log.csv
    if encoded_frames:
        sample_good_frame = encoded_frames[0]
        # (1) CHECKSUM_ERROR
        bad_chk_frame = bytearray(sample_good_frame)
        bad_chk_frame[39] = (bad_chk_frame[39] + 1) % 256
        res_chk = decode_position_message(bytes(bad_chk_frame))
        validation_logs.append({
            "record_no": 901,
            "target_id": res_chk["target_id"],
            "stage": "receiver_decode",
            "field": "checksum",
            "problem_type": "CHECKSUM_ERROR",
            "value": f"received={res_chk['checksum']}, expected={res_chk['expected_checksum']}",
            "description": "人工构造校验和不匹配测试帧",
        })

        # (2) MAGIC_ERROR
        bad_magic_frame = bytearray(sample_good_frame)
        bad_magic_frame[0] = 0x00
        bad_magic_frame[39:41] = calculate_checksum(bad_magic_frame[:39]).to_bytes(2, "big")
        res_magic = decode_position_message(bytes(bad_magic_frame))
        validation_logs.append({
            "record_no": 902,
            "target_id": res_magic["target_id"],
            "stage": "receiver_decode",
            "field": "magic",
            "problem_type": "MAGIC_ERROR",
            "value": "0x0053",
            "description": "人工构造非法魔数测试帧",
        })

        # (3) RESERVED_BITS_ERROR
        bad_res_frame = bytearray(sample_good_frame)
        bad_res_frame[23] = bad_res_frame[23] | 0x80  # 纬度高2位保留位置1
        bad_res_frame[39:41] = calculate_checksum(bad_res_frame[:39]).to_bytes(2, "big")
        res_res = decode_position_message(bytes(bad_res_frame))
        validation_logs.append({
            "record_no": 903,
            "target_id": res_res["target_id"],
            "stage": "receiver_decode",
            "field": "latitude_code",
            "problem_type": "RESERVED_BITS_ERROR",
            "value": "bit23_set",
            "description": "人工构造纬度最高保留位置1测试帧",
        })

        # (4) FLAG_VALUE_INCONSISTENCY
        bad_flag_frame = bytearray(sample_good_frame)
        bad_flag_frame[38] = bad_flag_frame[38] & (~1)  # 纬度有效位置0，但纬度码非0
        bad_flag_frame[39:41] = calculate_checksum(bad_flag_frame[:39]).to_bytes(2, "big")
        res_flag = decode_position_message(bytes(bad_flag_frame))
        validation_logs.append({
            "record_no": 904,
            "target_id": res_flag["target_id"],
            "stage": "receiver_decode",
            "field": "lat",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": f"valid_flag=0, code={res_flag['latitude_code']}",
            "description": "人工构造标志位为0但占位码非0测试帧",
        })

    # 写入 output/validation_log.csv
    log_csv_path = output_dir / "validation_log.csv"
    log_fieldnames = ["record_no", "target_id", "stage", "field", "problem_type", "value", "description"]
    with log_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=log_fieldnames)
        writer.writeheader()
        for log in validation_logs:
            writer.writerow(log)

    # 4. 生成 roundtrip_report.csv
    roundtrip_rows: list[dict[str, Any]] = []
    field_tolerances = {
        "lat": (180.0 / (2**22 - 1), 1),
        "lon": (360.0 / (2**22 - 1), 2),
        "altitude": (1.0, 4),
        "speed": (0.1, 8),
        "heading": (0.01, 16),
        "vertical_rate": (0.01, 32),
        "callsign": (0.0, 64),
    }

    for idx, rec in enumerate(valid_records):
        frame = encoded_frames[idx]
        decoded = decode_position_message(frame)

        for field_name, (tol, flag_mask) in field_tolerances.items():
            src_val = rec.get(field_name)
            src_valid = rec.get(f"{field_name}_valid", src_val is not None)
            dec_val = decoded.get(field_name)
            dec_valid = decoded.get(f"{field_name}_valid", dec_val is not None)

            # 获取协议码
            code_key = {
                "lat": "latitude_code",
                "lon": "longitude_code",
                "altitude": "altitude_code",
                "speed": "speed_code",
                "heading": "heading_code",
                "vertical_rate": "vertical_rate_code",
                "callsign": "callsign",
            }.get(field_name, "")
            protocol_code = decoded.get(code_key, "")

            # 计算误差与通过判定
            if src_valid and dec_valid:
                if field_name == "callsign":
                    err_str = "0.0/0.0"
                    passed = src_val == dec_val
                else:
                    abs_err = abs(float(src_val) - float(dec_val))
                    err_str = f"{abs_err:.6f}/{tol:.6f}"
                    passed = abs_err <= tol + 1e-9
            elif not src_valid and not dec_valid:
                err_str = "0.0/0.0"
                passed = True
            else:
                err_str = "INVALID/INVALID"
                passed = False

            roundtrip_rows.append({
                "field": f"{rec['target_id']}_{field_name}",
                "source_value": "" if src_val is None else src_val,
                "source_valid": src_valid,
                "protocol_code": protocol_code,
                "flag_bit": bin(flag_mask),
                "decoded_value": "" if dec_val is None else dec_val,
                "decoded_valid": dec_valid,
                "absolute_error/tolerance": err_str,
                "passed": passed,
            })

    report_csv_path = output_dir / "roundtrip_report.csv"
    report_fieldnames = [
        "field", "source_value", "source_valid", "protocol_code",
        "flag_bit", "decoded_value", "decoded_valid", "absolute_error/tolerance", "passed",
    ]
    with report_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=report_fieldnames)
        writer.writeheader()
        for row in roundtrip_rows:
            writer.writerow(row)

    print(f"[M2] 编码完成: {len(encoded_frames)} 帧 -> {encoded_bin_path.name}")
    print(f"[M2] 解码完成: {len(decoded_partner_records)} 记录 -> {decoded_csv_path.name}")
    print(f"[M2] 校验日志: {len(validation_logs)} 条 -> {log_csv_path.name}")
    print(f"[M2] 往返报告: {len(roundtrip_rows)} 项 -> {report_csv_path.name}")

    return {
        "encoded_count": len(encoded_frames),
        "decoded_count": len(decoded_partner_records),
        "validation_count": len(validation_logs),
        "roundtrip_count": len(roundtrip_rows),
    }


def main() -> int:
    execute_m2_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
