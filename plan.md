# Kế hoạch triển khai - Hiển thị Xác suất Thực tế 100% (Không quy đổi ảo)

Kế hoạch này điều chỉnh cách hiển thị độ tự tin cược trên giao diện Dashboard thành **Xác suất toán học thực tế 100%** (không dùng công thức quy đổi ảo), đảm bảo tính minh bạch, chính xác và trung thực tuyệt đối của số liệu hệ thống.

## Phương án thiết lập Xác suất thực tế & Ngưỡng động

1. **Hiển thị xác suất thực tế 100%:**
   - Độ tự tin cược (Confidence) hiển thị trên giao diện sẽ bằng chính xác **Xác suất tổng hợp thực tế** (`combined_prob`) tính toán từ Sliding Window và xích Markov:
     $$Confidence_{\text{hiển thị}} = \text{round}(combined\_prob \times 100)\%$$
     Ví dụ: Nếu xác suất tổng hợp thực tế tính ra là `69.3%`, giao diện sẽ hiển thị đúng `69%` hoặc `69.3%`, không làm tròn lên `80%` hay các con số ảo khác.

2. **Ngưỡng cược thích ứng động thực tế:**
   - Chúng ta vẫn giữ nguyên cơ chế **Ngưỡng Động Thích Ứng (Adaptive Threshold)** để cân bằng số lượng dự đoán luôn đạt từ 8 - 12 cược mỗi 30 kỳ:
     - Thị trường giằng co ($AR \ge 0.60$): Chỉ cược khi xác suất thực tế đạt **`>= 68%`**.
     - Thị trường bình thường ($0.40 \le AR < 0.60$): Cược khi xác suất thực tế đạt **`>= 65%`**.
     - Thị trường bệt ổn định ($AR < 0.40$): Cược khi xác suất thực tế đạt **`>= 62%`**.
   - Việc hiển thị xác suất thực tế sẽ giúp bạn biết chính xác thế trận cược mạnh hay yếu ở từng kỳ cược cụ thể.

---

## Các thay đổi đề xuất

### Thành phần: AI Core / Analyzer
#### [SỬA] [analyzer.py](file:///d:/Dev/Projects/DEV_PYTHONs/Xác xuất/src/core/analyzer.py)
- Cập nhật heuristics để xuất trực tiếp `combined_prob` làm `confidence` cho cả cược Parity và Size, hoàn toàn không qua công thức quy đổi ảo.

---

## Kế hoạch kiểm thử

### Kiểm thử tự động
- Chạy lệnh `pytest` để đảm bảo logic toán học thực tế hoạt động trơn tru.
Sẽ thực hiện sau. 