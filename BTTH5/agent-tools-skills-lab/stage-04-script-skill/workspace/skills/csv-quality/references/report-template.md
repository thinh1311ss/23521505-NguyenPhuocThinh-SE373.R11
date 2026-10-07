# Báo cáo kiểm tra chất lượng và tải công việc: `{đường dẫn CSV}`

Công cụ: `skills/csv-quality/scripts/check_csv.py` | exit code: {exit_code}

## 1. Kiểm tra tải công việc (Ngưỡng: {max_hours} giờ)

### Tổng giờ theo người
| Người phụ trách | Tổng giờ | Trạng thái quá tải |
|---|---|---|
| {owner} | {total_hours} | {Vượt ngưỡng / Trong định mức} |

### Danh sách người quá tải
{Nếu có người quá tải: liệt kê người và tổng giờ. Nếu không có: "Không có ai vượt ngưỡng {max_hours} giờ."}

### Các dòng bị loại khỏi tính toán
| Dòng (Line) | Task ID | Lý do loại |
|---|---|---|
| {line} | {task_id} | {reasons} |

## 2. Tổng quan chất lượng dữ liệu
| Chỉ số | Giá trị |
|---|---|
| Số dòng dữ liệu (không tính header) | {row_count} |
| Dòng thiếu owner | {missing_owner_count} |
| Dòng hours không hợp lệ | {invalid_hours_count} |
| Số task_id bị lặp (distinct) | {duplicate_id_count} ({duplicate_ids}) |

## 3. Chi tiết lỗi dữ liệu
| Line | Cột | Loại lỗi | Task ID | Mô tả |
|---|---|---|---|---|
| {line} | {column} | {type} | {task_id} | {message} |

## 4. Đánh giá và khuyến nghị
- **Đánh giá**: {Đánh giá về tính toàn vẹn của dữ liệu và mức độ tải công việc}
- **Khuyến nghị**: {Khuyến nghị điều chỉnh dữ liệu đầu vào hoặc phân bổ lại công việc}
