# Chess Vision Analyzer

Ứng dụng Windows chạy cục bộ, tự chụp vùng bàn cờ trên màn hình, nhận dạng bằng OpenCV/template đã hiệu chỉnh và gửi vị trí hợp lệ đến Stockfish. Ứng dụng chỉ hiển thị phân tích; **không điều khiển chuột/bàn phím** và không dành cho trận đấu cạnh tranh trực tuyến.

## Điều kiện

- Windows 10/11, Python 3.12 (64-bit).
- Stockfish bản Windows từ [trang tải chính thức](https://stockfishchess.org/download/). Bản phân phối đặt Stockfish 19 cùng mã nguồn/GPL trong `dist\ChessVisionAnalyzer\engine`; ứng dụng tự phát hiện khi thư mục này nằm cạnh EXE.
- Một bàn cờ 2D vuông, nhìn rõ đủ 64 ô. Template phụ thuộc giao diện/bộ quân cụ thể.

## Cài đặt

Mở PowerShell trong thư mục dự án:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
.\.venv\Scripts\python.exe main.py
```

Script chỉ cài thư viện vào `.venv`, không sửa Python toàn hệ thống. Nếu chưa có Python 3.12, cài từ python.org và bật Python Launcher.

## Chạy tự động

1. Mở trang luyện tập/phân tích hoặc bàn chơi với máy ở **thế xuất phát chuẩn**; không dùng trong trận cạnh tranh trực tuyến.
2. Mở Chess Vision Analyzer, xác nhận thông báo lần đầu, rồi chọn đúng cửa sổ Chrome/Edge trong **Nguồn đọc**. Ứng dụng cố ý chờ ở trạng thái này để không nhận nhầm chính giao diện của nó.
3. Ứng dụng tự tìm Stockfish trong thư mục `engine` đi kèm, `PATH`, cạnh EXE, Program Files hoặc Downloads. Nếu chưa tìm thấy, panel sẽ báo rõ “Stockfish: chưa cài” và bạn có thể chọn file một lần trong Settings.
4. Khi bàn thay đổi, pipeline tự nhận dạng nước hợp lệ và phân tích lại. Gợi ý nhanh xuất hiện trước, sau đó được Stockfish tinh chỉnh ở độ sâu cao hơn. Nếu cửa sổ bàn cờ di chuyển/đổi kích thước, ứng dụng thử tự tìm lại vùng.

Tool chỉ bắt đầu quét sau khi có nguồn hợp lệ. Dùng hộp **Nguồn đọc** trên thanh đầu để chọn cửa sổ trình duyệt đang hiển thị tab bàn cờ; các cửa sổ trùng tên được phân biệt bằng handle. Windows không cho MSS chụp một tab nền riêng biệt, vì vậy tab cờ phải đang hiển thị và không bị cửa sổ khác che bàn cờ. `Tự động — toàn màn hình` chỉ là phương án dự phòng.

Sau mỗi nước, tool kiểm tra thay đổi theo từng ô thay vì chỉ lấy trung bình toàn ảnh, rồi kiểm tra thêm hai khung hình để tránh dừng ở giữa animation. Highlight/animation có confidence thấp vẫn được chấp nhận khi khớp duy nhất một nước hợp lệ của `python-chess`. Nếu bỏ lỡ một khung hình, bộ theo dõi có thể dựng lại tối đa hai nửa-nước hợp lệ để tự đồng bộ, kể cả nước vua/nhập thành của đối thủ. Lịch sử nước được lưu riêng trong SQLite và tải lại khi mở ứng dụng; FEN gần nhất cũng được dùng để tiếp tục ván đang dở.

Sau khi chọn nguồn, không cần bấm phân tích hay nhập FEN/nước đi. Các nút đổi chữ, màu và trạng thái bật/tắt ngay khi lệnh được nhận. Nếu giao diện bàn cờ có hiệu ứng khiến nhận dạng tự động không đủ chắc chắn, dùng **Hiệu chỉnh → Chọn vùng bàn cờ** và **Tạo template từ thế xuất phát** làm phương án dự phòng. Vùng được lưu theo tỉ lệ của cửa sổ nên tiếp tục bám theo khi cửa sổ di chuyển hoặc đổi kích thước.

## Quản lý lịch sử ván đấu

- Mỗi ván mới được tạo và lưu tự động trong SQLite; từng nước, FEN và kết quả Stockfish tiếp tục được cập nhật khi đang chơi.
- **Lưu ván** đặt hoặc đổi tên ván hiện tại. Không cần bấm nút này sau mỗi nước.
- **Lịch sử ván** mở cửa sổ quản lý: tìm ván theo tên, chọn một ván để xem lại trên bàn cờ, chọn từng nước hoặc dùng nút nước trước/sau.
- Có thể đổi tên, xóa riêng một ván hoặc xóa toàn bộ lịch sử. Thao tác xóa luôn yêu cầu xác nhận.
- Cơ sở dữ liệu từ bản cũ được tự nâng cấp; các nước chưa thuộc ván nào được gom vào mục **Ván cũ**.

Nếu vị trí đầu tiên không phải thế xuất phát, ứng dụng hỏi một lần bên đến lượt, quyền nhập thành và ô bắt tốt qua đường. Nó không suy đoán các dữ kiện không thể nhìn thấy từ ảnh tĩnh. Nếu độ tin cậy thấp, ứng dụng giữ nguyên vị trí hợp lệ cuối cùng thay vì vẽ khung nhận diện nhiễu.

## Giới hạn nhận dạng

Template matching là phương pháp xác định theo theme. Sau khi hiệu chỉnh, không đổi zoom, bộ quân, màu bàn hoặc hiệu ứng highlight; nếu đổi, hiệu chỉnh lại. Hiệu ứng nước đi mạnh, animation, tọa độ phủ lên quân và bàn 3D có thể làm giảm độ tin cậy. Bản triển khai không tuyên bố độ chính xác trên mọi website; hãy xác minh với giao diện thực tế trước khi tin kết quả.

Với nguồn cửa sổ, vùng hiệu chỉnh được lưu dưới dạng tỉ lệ tương đối và tự đi theo cửa sổ. Với chế độ toàn màn hình, vùng là tọa độ tuyệt đối và có thể phải chọn lại sau khi thay đổi bố cục màn hình.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Test bao phủ phát hiện bàn tổng hợp, template Chess.com đã hiệu chỉnh, vua đổi màu ô, highlight, ánh xạ/xoay tọa độ, FEN, nước thường, tự bắt kịp hai nửa-nước, bắt tốt qua đường, nhập thành, phong cấp, chiếu hết/hòa, nâng cấp/lưu/xóa/xem lại lịch sử theo từng ván, engine lỗi rồi khởi động lại và phân tích nhanh/tinh chỉnh bất đồng bộ. Kiểm thử Stockfish thật cần EXE cục bộ:

```powershell
$env:STOCKFISH_EXECUTABLE = "C:\path\to\stockfish.exe"
.\.venv\Scripts\python.exe -c "from core.stockfish_engine import StockfishEngine; import chess; e=StockfishEngine(); print(e.analyse(chess.STARTING_FEN, .5)); e.stop()"
```

## Đóng gói EXE

```powershell
.\scripts\build.ps1
```

Kết quả là `dist\ChessVisionAnalyzer\ChessVisionAnalyzer.exe`. Giữ nguyên toàn bộ thư mục `ChessVisionAnalyzer`; không chép riêng EXE ra ngoài vì chương trình cần `_internal` và `engine` bên cạnh. Bản dạng thư mục khởi động nhanh hơn và ít bị Defender chặn hơn bản one-file. Cấu hình, template, log và SQLite được lưu trong `%LOCALAPPDATA%\ChessVisionAnalyzer`.

## Quyền riêng tư và dữ liệu

- Ảnh chụp chỉ ở RAM trong lúc xử lý; không ghi hình hoặc lưu screenshot liên tục.
- Chỉ các ô template do người dùng chủ động hiệu chỉnh được lưu trong `assets/piece_templates/default` (hoặc thư mục dữ liệu của bản EXE).
- Lịch sử FEN/kết quả engine được lưu SQLite cục bộ tại `data/history.db`.
- Không có API cloud hay telemetry.

