# TaskFlow

**Project & Team Workspace**

Website quản lý dự án và công việc nhóm, xây dựng bằng Django + MySQL + Bootstrap 5.

## Yêu cầu

- Windows 10/11
- Python 3.11+ (đã kiểm tra với Python 3.14)
- MySQL 8.0
- Visual Studio Code

Không dùng Docker. Không dùng SQLite.

## Cài đặt trên Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Tạo file `.env` từ mẫu:

```bash
copy .env.example .env
```

Điền mật khẩu MySQL vào `DB_PASSWORD` trong `.env`. Không ghi mật khẩu trực tiếp trong source code.

Tạo database:

```sql
CREATE DATABASE project_management
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Migration và dữ liệu demo:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Truy cập: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Nếu terminal đã đặt biến môi trường DEBUG, Django ưu tiên giá trị đó. Khi chạy thử bằng PowerShell, dùng `$env:DEBUG = "True"` để `runserver` phục vụ CSS và JavaScript.

Nếu cần tạo lại dữ liệu demo:

```bash
python manage.py seed_data --reset
```

## Tài khoản demo

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Admin | `admin@projecthub.local` | `Admin@123` |
| Project Manager | `manager@projecthub.local` | `Manager@123` |
| Member | `member@projecthub.local` | `Member@123` |

Cũng có thể đăng nhập bằng username: `admin`, `lan.pham`, `member`.

## Chức năng chính

- Đăng ký / đăng nhập (username hoặc email), quên mật khẩu, hồ sơ, avatar
- Phân quyền hệ thống: Admin, Project Manager, Member
- Phân quyền trong dự án: Owner, Manager, Member, Viewer
- Chỉnh sửa dự án, quản lý thành viên và giao việc cho nhiều người
- Kanban kéo thả theo luật chuyển trạng thái của từng dự án
- Comment, checklist, tài liệu
- Thông báo, activity log, calendar, báo cáo Excel/CSV/PDF
- Dashboard riêng cho Admin / Manager / Member
- Tìm kiếm, lọc, phân trang, dark mode

## Vận hành dự án và công việc

- Trong **Dự án → Settings**, Owner/Admin có thể lưu trữ dự án để đưa về chế độ chỉ xem, hoặc kích hoạt lại. Chỉ dự án chưa từng có công việc hay tài liệu mới có nút xóa. Thao tác xóa yêu cầu nhập mã dự án. Dùng bộ lọc **Đã lưu trữ** trong danh sách dự án để mở lại hồ sơ cũ.
- Tại **Settings → Cấu hình luồng công việc**, Owner/Manager/Admin thiết lập cột Kanban, chọn trạng thái khởi đầu và vai trò cho từng bước chuyển. Luồng mặc định cho người được giao bắt đầu, báo chậm, tạm hoãn và nộp kết quả. Quản lý quyết định duyệt, từ chối hoặc yêu cầu làm lại ở bước chờ duyệt. Hệ thống lưu người thao tác, thời điểm và ghi chú trong lịch sử công việc.
- Quản lý có thể tạo, đổi tên và ngừng dùng các loại công việc riêng cho dự án. Khi tạo hoặc sửa công việc, chọn loại và mức ưu tiên ở phần **Phân loại**.
- Vào **Dự án → Tasks → Nhập Excel** để tải mẫu Excel có thông tin của dự án. Điền tối đa 500 hàng vào sheet **Tasks** rồi tải lại tệp. Hệ thống trả lỗi theo dòng, chỉ nhập khi toàn bộ hợp lệ và ghi nhận tệp đã nhập để tránh tạo trùng khi gửi lại.
- Chọn **Quá hạn** hoặc **Chờ duyệt** ở trang công việc. Trong **Reports**, Admin xem toàn hệ thống, quản lý xem phạm vi mình phụ trách và thành viên xem công việc được giao. Báo cáo hỗ trợ lọc ngày tạo, dự án và xuất theo phạm vi đang xem.

## Kiểm thử

```bash
python manage.py test accounts projects tasks notifications
```

Django sẽ tạo database kiểm thử `test_project_management` trên MySQL.

## Ghi chú

- Mật khẩu và `SECRET_KEY` chỉ nằm trong `.env`
- File upload bị chặn phần mở rộng thực thi
- User / Project / Task dùng soft delete
- Quên mật khẩu: nếu chưa cấu hình SMTP, môi trường Development sẽ hiện reset link trên trang






- Vòng đời dự án. Chỉ Owner hoặc Admin được xóa dự án chưa từng phát sinh công việc hoặc tài liệu, sau khi nhập đúng mã xác nhận. Dự án đã có dữ liệu có thể chuyển sang chế độ chỉ xem và kích hoạt lại khi cần.
- Luồng công việc theo dự án. Quản lý có thể cấu hình các cột Kanban, trạng thái khởi đầu, luật chuyển theo vai trò và loại công việc. Theo luồng mặc định, người được giao cập nhật tiến độ và nộp kết quả. Quản lý duyệt, từ chối hoặc yêu cầu làm lại. Mỗi lần chuyển đều được ghi vào lịch sử.
- Báo cáo theo vai trò. Admin xem toàn hệ thống, quản lý xem các dự án mình phụ trách, thành viên xem công việc được giao. Có bộ lọc nhanh Quá hạn, Hạn trong 3 ngày và Chờ duyệt, cùng chức năng xuất Excel, CSV và PDF.
- Nhập Excel. Vào Dự án → Tasks → Nhập Excel để tải mẫu riêng của dự án. Hệ thống nhập tối đa 500 công việc mỗi tệp, báo lỗi theo dòng và chỉ tạo công việc khi toàn bộ tệp hợp lệ. Gửi lại cùng tệp sẽ được chặn để tránh tạo trùng.

Tài khoản: demo-kt-lead
Mật khẩu: RJxTLFpCTpMwPSsL