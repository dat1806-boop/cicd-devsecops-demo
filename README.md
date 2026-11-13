# WorkBoard – Interactive CI/CD Lab

Ứng dụng mẫu Flask có chức năng CRUD thật và một phòng thực hành CI/CD tương tác. Mục tiêu là để người thuyết trình thao tác ngay trên website, sau đó giải thích từng công đoạn kiểm thử, Docker và triển khai môi trường.

## 1. Website có hai khu vực

- **Ứng dụng WorkBoard (`/`)**: tạo, sửa, đánh dấu hoàn thành và xóa công việc. Dữ liệu được lưu trong SQLite.
- **Phòng CI/CD (`/lab`)**: chạy Flake8 + Pytest thật trên máy; build Docker image thật; tạo container DEV, STAGING, PRODUCTION trên các cổng 5101, 5102, 5103; có bước xác nhận trước Production.

Các thao tác test, Docker build và Docker deploy chạy lệnh thật trên máy tính đang mở Flask. Nếu chưa cài hoặc chưa khởi động Docker Desktop, bước Docker sẽ báo lỗi rõ ràng chứ không giả lập thành công.

Ba thẻ tình huống Unit Test / Secret / SCA là **minh họa theo kết quả đã ghi trong báo cáo**, không chạy Gitleaks hoặc pip-audit thật. Phần GitHub Actions có thể kích hoạt workflow thật nếu đã cấu hình token và bật `workflow_dispatch` trong workflow.

## 2. Chạy trên Windows

1. Cài Python 3.12 và Docker Desktop; mở Docker Desktop nếu muốn trình diễn bước build/deploy.
2. Giải nén thư mục project.
3. Mở thư mục bằng Visual Studio Code.
4. Nhấp đúp `RUN_WINDOWS.bat`, hoặc mở Terminal và chạy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python app.py
```

5. Truy cập:
   - Trang ứng dụng: http://127.0.0.1:5000/
   - Phòng CI/CD: http://127.0.0.1:5000/lab

Giữ Terminal mở trong lúc trình diễn. Nhấn `Ctrl+C` để dừng Flask.

## 3. Cách trình diễn tại lớp

1. Mở trang chủ, tạo một công việc, sửa tên, đánh dấu hoàn thành và xóa một công việc. Đây là thao tác CRUD thật trên SQLite.
2. Mở **Phòng CI/CD**.
3. Bấm **Chạy kiểm thử tự động**. Website thực thi `flake8 app.py test_app.py --max-line-length=100` và `pytest -q`. Log và exit code hiển thị ngay trên trang.
4. Khi test đạt, bấm **Build Docker image**. Website thực thi `docker build -t cicd-lab:demo .` và hiển thị Image ID.
5. Bấm **Triển khai DEV**. Docker tạo container `cicd-lab-dev`, ánh xạ cổng `5101:5000`, đặt `APP_ENV=dev` rồi kiểm tra `/health`. Bấm link để mở bản DEV.
6. Làm tương tự với STAGING ở cổng 5102.
7. Bấm **Phê duyệt phát hành**, xác nhận hộp thoại, rồi bấm **Triển khai PRODUCTION** ở cổng 5103.
8. Mở ba link môi trường. Cùng một image ID nhưng trang web hiển thị môi trường khác nhau. Đây là phần trực quan nhất để giải thích “build một lần, triển khai nhiều môi trường”.
9. Chọn các kịch bản Unit Test, Secret, SCA để giải thích các ảnh minh chứng trong báo cáo. Các thẻ này có nhãn minh họa, không phải scanner chạy thật.

## 4. Yêu cầu Docker

Cài và mở Docker Desktop trước khi nhấn Build. Kiểm tra trong Terminal:

```powershell
docker version
docker info
```

Nếu `docker info` không chạy được, Docker Engine chưa khởi động. Mở Docker Desktop, đợi trạng thái Engine sẵn sàng rồi thử lại.

Các container demo dùng:

| Môi trường | Container | Địa chỉ |
|---|---|---|
| DEV | `cicd-lab-dev` | http://127.0.0.1:5101 |
| STAGING | `cicd-lab-staging` | http://127.0.0.1:5102 |
| PRODUCTION | `cicd-lab-production` | http://127.0.0.1:5103 |

Để dừng các container sau buổi demo:

```powershell
docker rm -f cicd-lab-dev cicd-lab-staging cicd-lab-production
```

## 5. Kích hoạt GitHub Actions thật từ website (tùy chọn)

Nút **Chạy workflow trên GitHub** gọi GitHub REST API từ backend. Token không được đưa xuống trình duyệt.

1. Trong repository GitHub, vào Settings → Developer settings → Fine-grained personal access tokens.
2. Tạo token giới hạn đúng repository `dat1806-boop/cicd-devsecops-demo`, cấp quyền **Actions: Read and write**.
3. Copy `.env.example` thành `.env`, điền token:

```env
GITHUB_TOKEN=PASTE_YOUR_TOKEN_HERE
GITHUB_REPOSITORY=dat1806-boop/cicd-devsecops-demo
GITHUB_WORKFLOW_FILE=pipeline.yml
```

4. Kiểm tra `.env` nằm trong `.gitignore`; tuyệt đối không commit hoặc chụp màn hình token.
5. Workflow `.github/workflows/pipeline.yml` đã có `workflow_dispatch`. Commit/push file workflow này lên GitHub trước khi dùng nút kích hoạt.
6. Chọn `develop` để chạy nhánh DEV; chọn `main` để chạy STAGING rồi đến cổng phê duyệt PRODUCTION theo cấu hình GitHub Environments.

Nếu không cấu hình token, ứng dụng CRUD, local test, Docker build và local deployment vẫn dùng được; chỉ riêng nút kích hoạt workflow thật sẽ báo chưa cấu hình.

## 6. Những điểm cần nói rõ với giảng viên

- Test ở `/lab` chạy thật trên máy tính trình diễn; các job Gitleaks, CodeQL, pip-audit, Trivy, Cosign và SBOM của đề tài được thực thi trong GitHub Actions workflow.
- Docker build/deploy ở `/lab` là triển khai container thật trên máy cá nhân, tách ba cổng local. Nó không phải máy chủ cloud production.
- Nút phê duyệt Production trên `/lab` là cổng minh họa local. Cổng Required reviewers thật vẫn thuộc GitHub Environments trong workflow.
- Các kịch bản Secret/SCA trên trang là minh họa lại kết quả thực nghiệm trong báo cáo; không được trình bày như lượt quét bảo mật mới.
- Workflow đã được đồng bộ theo hướng **build một lần**: Trivy quét image local, sau đó chính image đó được push lên GHCR. Các bước ký Cosign, tạo SBOM và triển khai đều tham chiếu cùng digest.
- Job `verify` dùng `cosign verify` để xác minh chữ ký và danh tính GitHub Actions trước khi cho phép DEV/STAGING/PRODUCTION triển khai.
- DEV chỉ chạy từ nhánh `develop`; STAGING và PRODUCTION chỉ chạy từ `main`. PRODUCTION còn phụ thuộc STAGING thành công và GitHub Environment có thể yêu cầu người duyệt.
- Nếu health check tại job triển khai thất bại, workflow in log container, xóa container lỗi và đánh dấu job thất bại.
- Endpoint kích hoạt workflow từ website chỉ nhận JSON cùng nguồn từ địa chỉ local được cho phép; không nhận form POST từ website bên ngoài. Token GitHub chỉ được giữ ở backend trong `.env`.
- Các job deploy trong GitHub Actions vẫn chạy container trên GitHub-hosted runner để minh họa pipeline; runner là máy tạm thời, không phải hạ tầng cloud production lâu dài. Phần `/lab` chạy container thật trên máy tính trình diễn.

## 7. Cấu trúc chính

```text
CI-CD-LAB-INTERACTIVE/
├── app.py
├── test_app.py
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
├── RUN_WINDOWS.bat
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── lab.html
│   └── not_local.html
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       └── lab.js
└── .github/workflows/pipeline.yml
```

## Tạo phiên bản mới và triển khai từ WorkBoard

Ở chế độ LOCAL, trang chủ có khung **Tạo phiên bản mới và triển khai**. Chức năng này thực hiện trên source code hiện tại trong thư mục dự án:

1. Nhập phiên bản dạng `v1.0.1` và mô tả thay đổi.
2. Chạy Flake8 và Pytest thật; nếu một bước thất bại thì dừng phát hành.
3. Build Docker image có tag riêng, ví dụ `cicd-lab:v1.0.1`.
4. Dùng image vừa build để triển khai DEV rồi STAGING và kiểm tra `/health`.
5. Người trình diễn phê duyệt Production; sau đó mới triển khai image đó lên cổng 5103.

Chức năng này không tự sửa mã nguồn. Muốn demo một thay đổi mới, hãy sửa file ứng dụng trước, lưu lại, rồi tạo phiên bản mới. Đây là quy trình phát hành cục bộ bằng Docker; workflow GitHub Actions là luồng riêng và cần được chạy/kiểm tra trên GitHub.
