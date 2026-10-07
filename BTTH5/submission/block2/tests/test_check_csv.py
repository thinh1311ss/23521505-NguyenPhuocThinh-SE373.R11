"""csv-quality script: thống kê fixture, lỗi input/schema/parse exit 1, lỗi dữ liệu exit 0."""

import json
import subprocess
import sys

import pytest

import paths

SCRIPT = paths.FIXTURES_DIR / "skills" / "csv-quality" / "scripts" / "check_csv.py"


def run(path, max_hours: float | str | None = 8):
    cmd = [sys.executable, str(SCRIPT), "--input", str(path)]
    if max_hours is not None:
        cmd.extend(["--max-hours", str(max_hours)])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


def write_csv(tmp_path, text):
    path = tmp_path / "t.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_fixture_statistics():
    result = run(paths.FIXTURES_DIR / "data" / "tasks.csv")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["row_count"] == 6
    assert data["missing_owner_count"] == 1
    assert data["invalid_hours_count"] == 1
    assert data["duplicate_id_count"] == 1
    assert data["duplicate_ids"] == ["T02"]
    assert [(i["line"], i["column"], i["type"]) for i in data["issues"]] == [
        (4, "owner", "missing_owner"),
        (5, "hours", "invalid_hours"),
        (6, "task_id", "duplicate_id"),
    ]
    assert "total_hours" not in data


@pytest.mark.parametrize("hours", ["NaN", "nan", "Infinity", "-inf", "-1", ""])
def test_non_finite_negative_or_empty_hours_rejected(tmp_path, hours):
    data = json.loads(run(write_csv(tmp_path, f"task_id,owner,hours\nT01,Lan,{hours}\n")).stdout)
    assert data["invalid_hours_count"] == 1
    assert data["issues"][0]["line"] == 2


def test_clean_data_exit_0_without_issues(tmp_path):
    result = run(write_csv(tmp_path, "task_id,owner,hours\nT01,Lan,4\nT02,Minh,2.5\n"))
    assert result.returncode == 0
    assert json.loads(result.stdout)["issues"] == []


def test_missing_file_exit_1(tmp_path):
    result = run(tmp_path / "khong-co.csv")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Không đọc được file" in result.stderr


def test_missing_column_exit_1(tmp_path):
    result = run(write_csv(tmp_path, "task_id,owner\nT01,Lan\n"))
    assert result.returncode == 1
    assert "Thiếu cột bắt buộc: hours" in result.stderr


def test_parse_error_exit_1(tmp_path):
    result = run(write_csv(tmp_path, 'task_id,owner,hours\nT01,"La"n,4\n'))
    assert result.returncode == 1
    assert "Lỗi parse CSV" in result.stderr


def test_script_does_not_modify_input():
    source = paths.FIXTURES_DIR / "data" / "tasks.csv"
    before = source.read_bytes()
    run(source)
    assert source.read_bytes() == before


def test_edge_case_first_occurrence_invalid_hours(tmp_path):
    """Trường hợp đặc biệt: lần xuất hiện đầu tiên của ID có hours không hợp lệ.
    Dòng 2 loại vì hours không hợp lệ; dòng 3 loại vì trùng ID. Không cộng 5 giờ cho Lan."""
    csv_content = """task_id,owner,hours
E01,Lan,abc
E01,Lan,5
E02,Minh,0
"""
    path = write_csv(tmp_path, csv_content)
    result = run(path, max_hours=0)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["hours_by_owner"] == {"Minh": 0}
    assert data["overloaded_owners"] == []
    assert [(r["line"], r["task_id"], r["reasons"]) for r in data["excluded_rows"]] == [
        (2, "E01", ["invalid_hours"]),
        (3, "E01", ["duplicate_id"]),
    ]


def test_missing_or_invalid_max_hours_exit_nonzero(tmp_path):
    path = write_csv(tmp_path, "task_id,owner,hours\nT01,Lan,4\n")
    # Thiếu tham số
    assert run(path, max_hours=None).returncode != 0
    # Giá trị âm hoặc không hợp lệ
    assert run(path, max_hours="-1").returncode != 0
    assert run(path, max_hours="abc").returncode != 0
    assert run(path, max_hours="NaN").returncode != 0
    assert run(path, max_hours="inf").returncode != 0


def test_workload_calculation_and_overload():
    path = paths.WORKSPACE_DIR / "data" / "workload.csv"
    # Ngưỡng 8
    res8 = json.loads(run(path, max_hours=8).stdout)
    assert res8["hours_by_owner"] == {"Lan": 9, "Minh": 3}
    assert res8["overloaded_owners"] == [{"owner": "Lan", "total_hours": 9}]
    assert [(r["line"], r["task_id"], r["reasons"]) for r in res8["excluded_rows"]] == [
        (5, "T04", ["invalid_hours"]),
        (6, "T02", ["duplicate_id"]),
        (7, "T05", ["missing_owner"]),
    ]

    # Ngưỡng 9
    res9 = json.loads(run(path, max_hours=9).stdout)
    assert res9["hours_by_owner"] == {"Lan": 9, "Minh": 3}
    assert res9["overloaded_owners"] == []

