# MarkovLotto - Hệ Thống Thu Thập & Dự Đoán Xổ Số Siêu Tốc 5 Phút (pmb5p) - CÔNG CỤ HỖ TRỢ NGHIÊN CỨU HỌC THUẬT - CHÚNG TÔI KHÔNG CÓ TRÁCH NHIỆM CHO NHỮNG HÀNH VI LỢI DỤNG VÀ CHIẾM ĐOẠT CỦA BẠN.

`MarkovLotto` là một công cụ pair-programming giúp cào dữ liệu thời gian thực từ WebSocket của trang game chính `vip.ee8833.me` / `ee8822.me` đối với loại hình **Xổ Số Miền Bắc Siêu Tốc 5 Phút (pmb5p)** và áp dụng thuật toán **Xích Markov cấp 1** để phân tích xác suất, chuỗi bệt, từ đó đưa ra dự đoán kết quả (Tài/Xỉu, Chẵn/Lẻ) cho kỳ kế tiếp.

---

## 🛠️ Công Nghệ Sử Dụng

-   **Backend:** Python 3.10+, FastAPI (Tạo API và tài liệu Swagger UI tự động)
-   **Web Server:** Uvicorn
-   **Giao Thức:** WebSockets (Kết nối thời gian thực nhận kết quả)
-   **Tính Toán:** Pandas & Numpy (Xử lý chuỗi số và tính toán ma trận chuyển trạng thái Markov)

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy

### 1. Cài đặt thư viện yêu cầu:
Mở Terminal tại thư mục dự án và chạy lệnh:
```bash
pip install -r requirements.txt
```

### 2. Khởi chạy Server:
Để chạy server cục bộ, bạn chạy lệnh sau (chạy từ thư mục cha của `src`):
```bash
$env:PYTHONPATH=".."; python -m uvicorn main:app --reload --port 8000
```
Sau khi chạy, giao diện tương tác Swagger UI sẽ khả dụng tại: **`http://localhost:8000/docs`**

---

## 🔄 Quy Trình Vận Hành Thời Gian Thực

Do cơ chế bảo mật chữ ký động và mã hóa RSA của trang chính, hệ thống hoạt động thông qua cơ chế lắng nghe WebSocket trực tiếp bằng Token được cấp từ trình duyệt đã đăng nhập.

### Bước 1: Cập nhật Token mới (Sau khi mở máy hoặc Token hết hạn)
1. Đăng nhập tài khoản của bạn tại trang `https://vip.ee8833.me` (hoặc domain phụ tương tự).
2. Nhấn **F12** -> chọn tab **Network** (Mạng) -> chọn bộ lọc **WS** (WebSockets).
3. Tải lại trang (F5) và chọn kết nối có tên `/ws/`.
4. Sao chép toàn bộ giá trị của tham số `token=...` trong URL của kết nối đó.
5. Truy cập Swagger UI `http://localhost:8000/docs`, tìm đến API **`POST /api/config-token`**, bấm *Try it out*, dán mã token vừa sao chép vào rồi bấm **Execute**.

### Bước 2: Nạp nhanh lịch sử để tăng độ chính xác của dự đoán
Do server lưu dữ liệu trong bộ nhớ tạm thời (RAM), lúc mới khởi động sẽ chưa có đủ số lượng kỳ quay để thuật toán dự đoán chính xác (Yêu cầu tối thiểu 10 kỳ, khuyên dùng trên 50 kỳ):
1. Trong tab **Network** (F12) trên trình duyệt, tìm request tên là `drawResult?lottery_id=45...`.
2. Click vào request đó -> chọn tab **Response** (Phản hồi) ở khung bên cạnh -> Copy toàn bộ chuỗi JSON hiển thị trong đó.
3. Trên Swagger UI, tìm API **`POST /api/import-history`**, chọn *Try it out*, dán chuỗi JSON vừa copy vào ô body rồi bấm **Execute**.

### Bước 3: Xem kết quả dự đoán kỳ tiếp theo
1. Gọi API **`GET /api/statistics`** trên Swagger UI.
2. Dữ liệu trả về sẽ hiển thị đầy đủ thông tin:
    -   `probabilities`: Tỉ lệ xuất hiện thực tế (Chẵn, Lẻ, Tài, Xỉu).
    -   `streaks`: Số kỳ đang bệt liên tiếp của trạng thái hiện tại.
    -   `prediction_for_next_issue`: Xác suất phần trăm dự đoán cho kỳ quay tiếp theo dựa trên Markov Chain cấp 1.

---

## 📡 Danh Sách API Endpoints

| Phương thức | Đường dẫn (Endpoint) | Chức năng |
| :--- | :--- | :--- |
| **GET** | `/api/history` | Lấy danh sách lịch sử kỳ quay đã lưu trong RAM |
| **GET** | `/api/statistics` | Xem thống kê xác suất & kết quả dự đoán kỳ tiếp theo |
| **POST** | `/api/config-token` | Cập nhật động token và tự động kết nối lại WebSocket |
| **POST** | `/api/import-history` | Import nhanh dữ liệu lịch sử copy từ Network tab trình duyệt |
| **POST** | `/api/clear` | Xóa sạch lịch sử hiện tại trong bộ lưu trữ |

---

## ⚠️ Lưu Ý Quan Trọng

1.  **Token hết hạn:** Nếu token hết hạn, kết nối WebSocket sẽ bị đóng. Server sẽ tự động chạy ở chế độ giả lập (`simulation mode`) sinh dữ liệu test ngẫu nhiên để API không bị lỗi. Hãy lấy token mới dán vào API để tiếp tục cào số thực.
2.  **Lưu trữ tạm thời:** Dữ liệu được lưu trực tiếp trên RAM để tối ưu tốc độ đọc ghi tính toán nhanh. Khi tắt server, dữ liệu sẽ bị xóa. Bạn chỉ cần thực hiện lại Bước 2 khi khởi chạy lại server để nạp lại lịch sử.
