# Hướng dẫn cập nhật WorkBoard có chức năng tạo phiên bản mới

1. Sao lưu thư mục dự án hiện tại.
2. Dừng Flask đang chạy bằng `Ctrl + C` trong cửa sổ PowerShell.
3. Giải nén gói cập nhật vào một thư mục tạm.
4. Sao chép các file/thư mục trong gói cập nhật vào `D:\cicd-devsecops-demo`, chọn ghi đè khi được hỏi.
5. **Không xóa hoặc thay thế `.git`, `.venv`, `instance` và file `.env` hiện có.** Gói cập nhật không chứa các thư mục này.
6. Chạy lại `MO_WEBSITE.bat`.
7. Mở `http://127.0.0.1:5000/`. Khung **Tạo phiên bản mới và triển khai** nằm ngay dưới phần giới thiệu.
8. Nhập phiên bản mới (ví dụ `v1.0.1`) và mô tả thay đổi, sau đó nhấn nút. Chức năng sẽ chạy Flake8, Pytest, Docker build, deploy DEV và STAGING.
9. Khi DEV và STAGING đạt health check, nhấn **Phê duyệt Production**, sau đó **Triển khai Production**.

Lưu ý:
- Docker Desktop phải đang chạy.
- Thao tác build/deploy chạy trên máy tính cá nhân, không phải máy chủ cloud.
- Nút tạo phiên bản đóng gói source code hiện có; nó không tự viết/sửa code.
- Nếu muốn trình diễn thay đổi, hãy sửa source và lưu trước khi tạo phiên bản.
