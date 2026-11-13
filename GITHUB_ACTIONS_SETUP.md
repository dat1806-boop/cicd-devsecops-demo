# Cấu hình GitHub Actions cho CI/CD WorkBoard

## Workflow

Tệp workflow: `.github/workflows/pipeline.yml`

Workflow chạy khi:
- Tạo/cập nhật Pull Request vào `develop` hoặc `main`: chạy lint, test và các bước quét bảo mật; không build/push image.
- Push lên `develop`: chạy đầy đủ CI, build/scan/push/ký image, xác minh chữ ký và smoke-test DEV.
- Push lên `main`: chạy đầy đủ CI, build/scan/push/ký image, xác minh chữ ký, smoke-test STAGING rồi chờ phê duyệt trước smoke-test PRODUCTION.
- `workflow_dispatch`: cho phép chạy thủ công từ tab Actions trên GitHub.

## Các công cụ trong pipeline

1. Flake8 và Pytest: chất lượng mã nguồn và kiểm thử.
2. Gitleaks: phát hiện bí mật bị commit vào Git.
3. Bandit và CodeQL: phân tích bảo mật mã nguồn (SAST).
4. pip-audit: kiểm tra lỗ hổng trong thư viện runtime và development.
5. Docker: build một image duy nhất theo mã commit.
6. Trivy: quét HIGH/CRITICAL trên chính image sẽ được push.
7. GHCR: lưu image theo tag commit và digest bất biến.
8. Cosign: ký image bằng keyless OIDC và xác minh chữ ký trước khi triển khai.
9. SBOM: tạo SPDX JSON và lưu thành workflow artifact.
10. DEV/STAGING/PRODUCTION: chạy container và health check trong runner.

## Cấu hình bắt buộc trên GitHub

Vào repository `dat1806-boop/cicd-devsecops-demo`:

1. Settings → Environments → tạo ba environment có tên chính xác: `dev`, `staging`, `production`.
2. Trong `production`, bật Required reviewers và thêm tài khoản người có quyền phê duyệt. Có thể bật thêm Prevent self-review nếu phù hợp.
3. Settings → Actions → General: cho phép GitHub Actions và cấp quyền đọc repository. Workflow tự khai báo quyền `packages: write` chỉ ở job build/publish; các job khác dùng quyền tối thiểu.
4. Đảm bảo tài khoản/repository có quyền publish package lên GitHub Container Registry (GHCR). Workflow dùng `GITHUB_TOKEN`, không cần tạo PAT riêng.
5. Đặt `main` làm nhánh mặc định. Khuyến nghị bảo vệ `main`: yêu cầu Pull Request và yêu cầu các job kiểm tra thành công trước khi merge.

## Cách chạy

- Phát triển trên `develop`, sau đó push: pipeline sẽ kiểm thử, đóng gói, quét, publish, ký/xác minh image và smoke-test DEV.
- Tạo Pull Request từ `develop` vào `main`: các job kiểm tra chạy trên PR.
- Merge vào `main`: pipeline chạy lại các kiểm tra, publish image, smoke-test STAGING. Job PRODUCTION sẽ chờ người phê duyệt trong GitHub Environment `production`.
- Có thể vào Actions → CI-CD-DevSecOps → Run workflow để chạy thủ công trên `develop` hoặc `main`.

## Lưu ý về phạm vi triển khai

Các job DEV/STAGING/PRODUCTION trong workflow này chạy container tạm thời trên GitHub-hosted runner và kiểm tra endpoint `/health`. Runner bị hủy sau khi job kết thúc, vì vậy đây là mô hình mô phỏng promotion và approval trong CI/CD, **không phải máy chủ hosting thường trực**. Muốn triển khai website công khai thật, cần bổ sung máy chủ/hosting đích và thông tin kết nối an toàn (ví dụ SSH/Deploy token) dưới dạng GitHub Environment secrets, rồi thay phần `docker run` smoke-test bằng lệnh triển khai đến máy chủ đó.

Các bước DEV/STAGING/PRODUCTION trong CI/CD Lab chạy Docker cục bộ trên máy tính của bạn là luồng demo riêng; không tự động điều khiển bởi workflow GitHub Actions này.
