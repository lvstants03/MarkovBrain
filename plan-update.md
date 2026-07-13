Để hệ thống (hoặc một bên thứ ba/engine khác như Antigravity) hiểu và xử lý chính xác tuyệt đối mà không bỏ sót bất kỳ chi tiết, con số thống kê hay dòng log mẫu nào từ ghi chú của bạn, dưới đây là **Bản Đặc Tả Kỹ Thuật Chi Tiết (Technical Specification)** được cấu trúc chuẩn hóa:

---

# BẢN ĐẶC TẢ KỸ THUẬT & KẾ HOẠCH NÂNG CẤP HỆ THỐNG

## 1. QUẢN LÝ VỐN VÀ CHIẾN THUẬT THEO THỜI GIAN (MONEY MANAGEMENT & TIME STRATEGY)

### 1.1 Cấu hình khung giờ chạy Bot (Time-based Restrictions)

Hệ thống cần tự động điều chỉnh mức độ tự tin (Confidence Level) và tiền cược dựa trên thời gian thực tế:

* **Khung giờ thuận lợi (Có lợi/Ưu tiên cược):**
* `10:00 - 12:00` (Trưa)
* `15:00 - 16:00` (3h - 4h chiều)


* **Khung giờ bất lợi (Rủi ro/Hạn chế hoặc tạm dừng cược):**
* `19:30 - 21:00` (7h30 - 9h tối)



### 1.2 Logic đặt cược thông minh theo Tỷ lệ thắng (Dynamic Bet Sizing)

* **Vòng có tỷ lệ cao:** Thêm logic phân tích xác suất. Đánh cược mạnh, ưu tiên dồn vốn vào những vòng có tỷ lệ thắng cao được dự đoán để mang lợi nhuận lớn về.
* **Cơ chế bỏ qua:** Nếu vòng đấu không đạt ngưỡng tỷ lệ an toàn tối thiểu $\rightarrow$ Bỏ qua hoàn toàn (Skip), không vào tiền để bảo toàn vốn.

---

## 2. KIỂM TRA SỰ KIỆN ĐỒNG BỘ ENGINE & TỐI ƯU WIN RATE

### 2.1 Cơ chế nhân vốn khi Đồng thuận (Consensus Bet Multiplier)

* **Điều kiện kích hoạt:** Xây dựng chức năng kiểm tra sự kiện đồng bộ giữa hai Engine: **AI Heuristics** + **Gemini**.
* **Hành động:** Khi cả 2 engine cùng đồng bộ chọn ra một kết quả trùng nhau $\rightarrow$ Tự động **tăng thêm 50% tiền cược** cho lệnh đó (Tiền cược mới = $Tiền cược gốc \times 1.5$).
* **Rà soát nghiêm ngặt (Yêu cầu 8.1):** Viết hàm kiểm tra chéo (Cross-check) để xác thực tỷ lệ đồng thuận: Đảm bảo 2 engine thực sự đồng thuận trên cùng một bộ dữ liệu, tránh việc sai lệch phiên hoặc cache kết quả cũ.

### 2.2 Tối ưu hóa bộ máy dự đoán

* Tập trung cải tiến core logic nhằm **tăng tỷ lệ đồng thuận (Consensus Rate)** giữa hai engine lên cao hơn, từ đó đẩy tỷ lệ thắng tổng thể (Win Rate - WR) của hệ thống đi lên.

---

## 3. KHẮC PHỤC LỖI HỆ THỐNG (BUG FIXING & INCIDENT REPORT)

### 3.1 Bug mất ổn định sau thời gian chờ (Idling Bug)

* **Mô tả hành vi lỗi:** Sau khi hệ thống ngưng hoạt động khoảng **10 phút** (Idling), bot bắt đầu hoạt động không ổn định.
* **Chi tiết kỹ thuật:** Ở **lần cược thứ 1, 2, 3, 4 ngay sau khi chạy lại**, hệ thống mất khả năng tự động tính toán chính xác dữ liệu/số tiền cược.
* **Khu vực cần kiểm tra:** Xem xét lại cơ chế lưu trữ state (trạng thái phiên cược), cơ chế giải phóng bộ nhớ, reset cache dữ liệu hoặc đồng bộ thời gian (timestamp) của hệ thống sau 10 phút ngưng nghỉ.

### 3.2 Khủng hoảng chuỗi thua từ Kỳ 111 (Drawdown Analysis)

Hệ thống cần được đánh giá lại toàn bộ thuật toán dựa trên các số liệu thống kê lịch sử cụ thể sau:

* **Giai đoạn Kỳ 100 - 110:** Vận hành hoàn hảo, kết quả trả về đều đạt **Tỷ lệ thắng > 70%**.
* **Giai đoạn Kỳ 111:** Hệ thống bắt đầu lung lay và rơi vào tình trạng **thua liên tục (Loss Streak)**.
* **Giai đoạn Kỳ 112 - 120:** Tỷ lệ thắng bị kéo tụt nghiêm trọng, lui về mức **50% - 55%**, thậm chí nhiều thời điểm tệ hơn là **< 50%**.
* **Yêu cầu xử lý:** Tìm ra nguyên nhân gãy chuỗi (do game đổi pattern, do quá khớp dữ liệu - overfitting, hay do tràn bộ nhớ cache?). Thiết lập cơ chế cảnh báo hoặc tự động dừng (Circuit Breaker) khi WR tụt dưới 55%.

---

## 4. TÁI CẤU TRÚC CODE & TỰ ĐỘNG HÓA (REFACTORING & AUTO-ACTION)

### 4.1 Quy chuẩn độ dài file nguồn (Code Cleaning)

* **Quy tắc:** Quét toàn bộ source code của dự án, kiểm tra độ dài các file.
* **Hành động:** Tất cả các file có độ dài **vượt quá 750 dòng** bắt buộc phải thực hiện refactor, tách nhỏ ra thành các module, file helper hoặc component độc lập với tiêu chí đảm bảo **dưới 750 dòng mỗi file**.

### 4.2 Tối ưu hóa tổng thể & Auto-action

* Nâng cấp hiệu suất xử lý (Performance) và độ chính xác (Accuracy) của toàn bộ hệ thống code.
* Triển khai hoàn thiện **Connect Script**: Thực hiện các hành động (actions) tự động tương tác và click đặt cược trực tiếp vào trong game dựa trên lệnh từ bot mà không cần can thiệp thủ công.

---

## 5. CHUẨN HÓA LOGS & GIÁM SÁT HỆ THỐNG (LOGGING & MONITORING)

### 5.1 Đánh dấu nguồn gốc dự đoán (Prediction Tagging)

Dựa trên mẫu log hệ thống cung cấp lúc `2026-07-11 17:53:23`:

```log
2026-07-11 17:53:23,959 [INFO] [Gemini] Attempt 1/3
2026-07-11 17:53:25,495 [INFO] [Gemini] Cached prediction for 48_202607110522
2026-07-11 17:53:25,496 [INFO] [INITIAL PHASE] Remaining: 0, bet: 291000

```

* **Yêu cầu:** Đây là dấu hiệu khi Gemini thực hiện dự đoán. Các lệnh cược khi xuất ra log bắt buộc phải được đánh dấu (tagging) rõ ràng nguồn gốc để phục vụ việc trace bug (đặc biệt là để điều tra chuỗi thua kỳ 111-120):
* Nếu chỉ **Gemini** chọn $\rightarrow$ Gắn tag xác nhận cụ thể của Gemini.
* Nếu chỉ **Heuristics** chọn $\rightarrow$ Gắn tag xác nhận cụ thể của Heuristics.
* Nếu **Cả hai engine đồng thuận** $\rightarrow$ Gắn tag xác nhận trạng thái đồng thuận tổng thể.



### 5.2 Ẩn Log Spam API & Triển khai Health Check Endpoint

* **Vấn đề:** Màn hình console hiện đang bị rối mắt bởi các dòng log `INFO: 127.0.0.1 - "GET /api/... HTTP/1.1" 200 OK` lặp đi lặp lại liên tục từ các API sau:

```log
INFO:     127.0.0.1:49393 - "GET /api/statistics?limit=500&t=1783767203615 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/statistics?limit=1&t=1783767203616 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/history?limit=15&t=1783767205500 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/predictions?limit=15&t=1783767205506 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/balance?t=1783767205511 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/socket/history?limit=15&t=1783767205521 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61602 - "GET /api/market-analysis?limit=100&t=1783767205527 HTTP/1.1" 200 OK

```

* **Giải pháp:** 1. Cấu hình logger tắt (Mute/Chặn) hiển thị log `INFO` dạng `200 OK` đối với các endpoint: `/api/statistics` (mọi limit), `/api/history`, `/api/predictions`, `/api/balance`, `/api/socket/history`, và `/api/market-analysis`.
2. Xây dựng một tính năng **Health Check** (Kiểm tra sức khỏe hệ thống): Chức năng này sẽ tự động chạy ngầm để kiểm tra xem các API trên có đang hoạt động hay không. Hệ thống sẽ **không liệt kê log** khi các API chạy bình thường, và chỉ xuất log cảnh báo ra màn hình khi có API bị lỗi hoặc không phản hồi.