#!/usr/bin/env python3
"""Kiểm tra chất lượng CSV công việc (task_id, owner, hours) và tính tải công việc theo người.

Cách chạy (cwd là workspace):
    python skills/csv-quality/scripts/check_csv.py --input data/workload.csv --max-hours 8

Exit 0: phân tích thành công, kể cả khi dữ liệu có lỗi chất lượng hoặc có người quá tải.
Exit 1 (hoặc khác 0): file không tồn tại/không đọc được, thiếu cột bắt buộc, lỗi parse CSV,
hoặc thiếu tham số CLI/giá trị tham số không hợp lệ; thông báo ra stderr.
Script chỉ đọc, không sửa CSV đầu vào.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys

REQUIRED_COLUMNS = ("task_id", "owner", "hours")
REASON_ORDER = [
    "wrong_field_count",
    "missing_task_id",
    "duplicate_id",
    "missing_owner",
    "invalid_hours",
]


class InputError(Exception):
    pass


def parse_hours(raw: str | None) -> float | None:
    """Số giờ hợp lệ: số hữu hạn, không âm. Trả None nếu không hợp lệ."""
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _clean_number(val: float) -> int | float:
    return int(val) if val.is_integer() else round(val, 4)


def analyze(path: str, max_hours: float) -> dict:
    try:
        handle = open(path, encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"Không đọc được file {path}: {exc.strerror or exc}") from exc
    with handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader, None)
            if header is None:
                raise InputError(f"File {path} rỗng, không có header.")
            columns = [c.strip() for c in header]
            missing = [c for c in REQUIRED_COLUMNS if c not in columns]
            if missing:
                raise InputError(f"Thiếu cột bắt buộc: {', '.join(missing)}. Header hiện có: {', '.join(columns)}")
            index = {name: columns.index(name) for name in REQUIRED_COLUMNS}

            row_count = 0
            missing_owner = 0
            invalid_hours = 0
            first_seen: dict[str, int] = {}
            duplicate_ids: list[str] = []
            issues: list[dict] = []

            # Thống kê tải công việc theo người
            seen_task_ids: set[str] = set()
            hours_by_owner: dict[str, float] = {}
            excluded_rows: list[dict] = []

            for row in reader:
                line = reader.line_num
                if not any(cell.strip() for cell in row):
                    continue  # bỏ qua dòng trống
                row_count += 1

                def cell(name: str) -> str:
                    position = index[name]
                    return row[position].strip() if position < len(row) else ""

                task_id, owner, hours = cell("task_id"), cell("owner"), cell("hours")

                # 1. Thống kê chất lượng cũ (trên toàn bộ dòng dữ liệu)
                if len(row) != len(columns):
                    issues.append({
                        "line": line, "column": None, "type": "wrong_field_count", "task_id": task_id or None,
                        "message": f"Có {len(row)} trường, header có {len(columns)} cột."
                    })
                if not task_id:
                    issues.append({
                        "line": line, "column": "task_id", "type": "missing_task_id", "task_id": None,
                        "message": "task_id trống."
                    })
                elif task_id in first_seen:
                    if task_id not in duplicate_ids:
                        duplicate_ids.append(task_id)
                    issues.append({
                        "line": line, "column": "task_id", "type": "duplicate_id", "task_id": task_id,
                        "message": f"task_id {task_id} đã xuất hiện ở line {first_seen[task_id]}."
                    })
                else:
                    first_seen[task_id] = line

                if not owner:
                    missing_owner += 1
                    issues.append({
                        "line": line, "column": "owner", "type": "missing_owner", "task_id": task_id or None,
                        "message": "owner trống."
                    })
                parsed_h = parse_hours(hours)
                if parsed_h is None:
                    invalid_hours += 1
                    issues.append({
                        "line": line, "column": "hours", "type": "invalid_hours", "task_id": task_id or None,
                        "value": hours, "message": f"hours '{hours}' không phải số hữu hạn không âm."
                    })

                # 2. Quy tắc tính tổng giờ và loại dòng
                row_reasons: list[str] = []
                if len(row) != len(columns):
                    row_reasons.append("wrong_field_count")
                if not task_id:
                    row_reasons.append("missing_task_id")
                elif task_id in seen_task_ids:
                    row_reasons.append("duplicate_id")
                else:
                    seen_task_ids.add(task_id)

                if not owner:
                    row_reasons.append("missing_owner")
                if parsed_h is None:
                    row_reasons.append("invalid_hours")

                if row_reasons:
                    excluded_rows.append({
                        "line": line,
                        "task_id": task_id if task_id else None,
                        "reasons": sorted(row_reasons, key=lambda r: REASON_ORDER.index(r)),
                    })
                else:
                    hours_by_owner[owner] = hours_by_owner.get(owner, 0.0) + parsed_h

        except csv.Error as exc:
            raise InputError(f"Lỗi parse CSV ở line {reader.line_num}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise InputError(f"File {path} không phải UTF-8: {exc}") from exc

    cleaned_hours_by_owner = {owner: _clean_number(h) for owner, h in hours_by_owner.items()}
    overloaded = [
        {"owner": owner, "total_hours": _clean_number(h)}
        for owner, h in sorted(hours_by_owner.items(), key=lambda item: item[0])
        if h > max_hours
    ]

    return {
        "input": path,
        "row_count": row_count,
        "missing_owner_count": missing_owner,
        "invalid_hours_count": invalid_hours,
        "duplicate_id_count": len(duplicate_ids),
        "duplicate_ids": duplicate_ids,
        "issues": sorted(issues, key=lambda item: item["line"]),
        "max_hours": _clean_number(max_hours),
        "hours_by_owner": cleaned_hours_by_owner,
        "overloaded_owners": overloaded,
        "excluded_rows": sorted(excluded_rows, key=lambda item: item["line"]),
    }


def parse_cli_max_hours(raw: str) -> float:
    try:
        val = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--max-hours phải là số hữu hạn không âm: '{raw}'")
    if not math.isfinite(val) or val < 0:
        raise argparse.ArgumentTypeError(f"--max-hours phải là số hữu hạn không âm: '{raw}'")
    return val


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra chất lượng CSV công việc và tải công việc theo người.")
    parser.add_argument("--input", required=True, help="Đường dẫn CSV, ví dụ data/tasks.csv")
    parser.add_argument("--max-hours", required=True, type=parse_cli_max_hours, help="Ngưỡng giờ tối đa (số hữu hạn không âm)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if exc.code is not None else 2
    try:
        result = analyze(args.input, args.max_hours)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
