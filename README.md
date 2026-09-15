# T19 Phát hiện khoảng mạng suy giảm bằng Isolation Forest

Trong tiểu luận này, nhóm em xây dựng chương trình theo dõi chất lượng mạng và phát hiện các khoảng thời gian có dấu hiệu suy giảm. Bài làm gồm báo cáo sáu chương và hai file Python: `collector_goc.py` để thu thập dữ liệu, `phan_tich.py` để phân tích. Bản báo cáo đã chỉnh cách xưng hô là **Bao_cao_T19_van_phong_nhom.docx**. Thư mục vẫn giữ bản gốc `Bao_cao_T19.docx` và bản Markdown để tra cứu.

Nhóm sử dụng Isolation Forest làm mô hình chính và dùng baseline theo ngưỡng để đối chiếu kết quả. Sau khi chạy mô hình, nhóm phân tích thêm tương quan TCP, TLS, TTFB và HTTP để giải thích những trường hợp HTTP tăng cao. Các chỉ số bổ sung này không được đưa vào đầu vào của Isolation Forest.

## 1. Các file của bài làm

| File hoặc thư mục | Vai trò |
|---|---|
| Bao_cao_T19_van_phong_nhom.docx | Báo cáo đã chỉnh văn phong; kiểm tra thông tin trên bìa trước khi nộp |
| collector_goc.py | Thu theo chu kỳ 30 giây, chạy liên tục, dừng bằng Ctrl+C |
| phan_tich.py | Đọc CSV ngoại tuyến, phân tích và tạo kết quả |
| du_lieu/network_quality_data.csv | Dữ liệu gồm 51.070 dòng, 15 cột được nhóm dùng trong báo cáo |
| du_lieu/network_quality_data.log | Log hoạt động do cùng collector ghi trong lúc thu thập |
| ket_qua | Các bảng CSV, tổng hợp JSON, log phân tích và 7 biểu đồ |
| requirements.txt | Phiên bản thư viện đã dùng |
| HUONG_DAN_DEMO.md | Các bước trình bày và câu hỏi tự ôn |

## 2. Dataset và lịch đo

Bộ dữ liệu nhóm sử dụng có **51.070 bản ghi**, từ **19/08/2026 17:34:00 đến 08/09/2026 01:00:00, UTC+7**. Nhóm thu thập dữ liệu trên máy Windows, sử dụng kết nối Ethernet. Target có nhãn `google`: ping 8.8.8.8, phân giải www.google.com, gửi HTTPS tới www.google.com. Đây là các phép đo liên quan nhưng không hoàn toàn cùng một đích IP.

Nhóm dùng Task Scheduler để đặt giờ hoạt động từ **03:00 đến 01:00 hôm sau**, collector quản lý chu kỳ đo. Có 20 phiên, ngăn cách bởi 19 khoảng nghỉ ban đêm. Trong 4.543 mốc thiếu trên lưới 30 giây có 4.541 mốc ngoài lịch và **hai mốc trong lịch**: 22/08 lúc 20:35:30 và 20:54:30. Mẫu đúng 01:00 được tính trong lịch. Hai mốc 03:00 ngày 20/08 và 21/08 đã có trong bộ này.

Log chứa số đo tương ứng cho 51.070 dòng CSV và 20 thông báo khởi động. Cả 20 thông báo khởi động đều ghi chu kỳ 30 giây, phù hợp với cấu hình collector. Khi phân tích, nhóm vẫn dùng timestamp thực tế để tính cửa sổ. CSV và log được tạo từ cùng kết quả đo nên sự khớp giữa hai file chỉ cho thấy quá trình ghi dữ liệu nhất quán; log không tạo nhãn sự cố độc lập.

Năm lượt còn thiếu một hoặc nhiều chỉ số chính; ba lượt có thông tin chưa nhất quán. Nhóm xuất riêng các dòng này để kiểm tra lại. Nhóm không thay dữ liệu thiếu bằng 0 và không dùng thời gian ngừng đo để kết luận mạng tốt hay bị lỗi.

## 3. Chuẩn bị môi trường chạy

Để chạy lại bài, trước tiên giải nén file ZIP và mở Terminal tại thư mục chứa README này. Nhóm sử dụng Python 3.12 và tạo môi trường riêng bằng hai lệnh sau:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu máy dùng lệnh `py`, thay lệnh đầu bằng `py -3.12 -m venv .venv`. Không cần kích hoạt môi trường vì các lệnh sau gọi trực tiếp Python trong `.venv`.

Các phiên bản nhóm sử dụng trong thực nghiệm: Python 3.12.14; numpy 2.5.3; pandas 3.0.1; matplotlib 3.11.1; scikit-learn 1.9.0. dnspython 2.8.0 dùng khi thu DNS. Môi trường Python không nằm trong ZIP; cần cài thư viện trên máy chạy lại.

## 4. Chạy chương trình phân tích

```powershell
.\.venv\Scripts\python.exe phan_tich.py --input du_lieu/network_quality_data.csv
```

Lệnh này đọc `du_lieu/network_quality_data.csv`, chạy ngoại tuyến và ghi vào `ket_qua`. Đường dẫn mặc định trong mã đã được thống nhất với CSV này; `--input` cho phép chọn file khác khi cần. Khi demo, nhóm có thể lưu kết quả vào thư mục riêng bằng lệnh:

```powershell
.\.venv\Scripts\python.exe phan_tich.py --input du_lieu/network_quality_data.csv --output ket_qua_chay_lai
```

Nhóm giữ cố định cấu hình chính trong mã để bài làm dễ chạy lại: Google, Isolation Forest, cửa sổ 5 phút, contamination 0,05, 100 cây, tối đa 256 mẫu/cây, seed 42. Chương trình chỉ có hai tùy chọn cho vị trí file là `--input` và `--output`; không có lựa chọn mô hình hay target khi chạy.

| Kết quả cần đối chiếu | Giá trị |
|---|---:|
| Dòng CSV / số mẫu đầu phiên bị bỏ | 51.070 / 40 |
| Mẫu đặc trưng | 51.030 |
| Train / test theo thứ tự thời gian | 35.721 / 15.309 |
| Kết thúc train | 02/09/2026 07:23:00 UTC+7 |
| Bắt đầu test | 02/09/2026 07:23:30 UTC+7 |
| Ngưỡng điểm IF | 0,601695 |
| Mẫu IF cảnh báo trên test | 402, tương đương 2,63% |
| Khoảng IF trên test | 21 |
| Mẫu nằm trong các khoảng IF | 371 |
| Tổng độ phủ ước lượng | 185,5 phút |
| Mẫu baseline cảnh báo trên test | 1.624 |

Nhóm tạo chín đặc trưng (feature), gồm trung bình cửa sổ của năm chỉ số chính, độ lệch chuẩn RTT, P95 RTT, P95 HTTP và giờ trong ngày. Nhóm chỉ huấn luyện mô hình và tính trung vị điền thiếu trên tập train. Cửa sổ dùng hiện tại và quá khứ, không đi qua khoảng ngắt trên 60 giây.

Nhóm chỉ giữ những khoảng có ít nhất ba mẫu cảnh báo liên tiếp, cách nhau đúng 30 giây. Ba mẫu trải từ đầu tới cuối 60 giây; chương trình cộng 30 giây sau mẫu cuối để ước lượng độ phủ 90 giây. Đây không phải thời lượng sự cố đã xác nhận. Có 31 trong 402 mẫu cảnh báo nằm ở các đoạn ngắn bị loại khi gộp khoảng.

## 5. Đọc kết quả và phần HTTP nâng cao

| File trong ket_qua | Nội dung |
|---|---|
| hinh_1_timeline.png | Cảnh báo IF trên năm chỉ số trung bình trượt ở tập kiểm tra; vùng xám chưa có dữ liệu cửa sổ |
| hinh_2_tuong_quan.png | Tương quan Pearson giữa RTT, DNS và HTTP trên các cặp giá trị hợp lệ |
| hinh_3_tuong_quan_http.png | Pearson và Spearman của TCP, TLS, TTFB và HTTP trên cùng các lượt đủ dữ liệu |
| hinh_4_anomaly_score.png | Phân bố điểm IF của train và test, với ngưỡng 0,601695 từ train |
| hinh_5_ty_le_theo_ngay.png | Tỷ lệ cảnh báo theo ngày, Isolation Forest là cột chính và ngưỡng là cột đối chiếu |
| hinh_6_theo_gio.png | Trung bình RTT và HTTP theo những giờ có dữ liệu |
| hinh_7_thanh_phan_http.png | Tỷ trọng TCP, TLS, TTFB và phần đọc còn lại trong ba trường hợp |
| intervals.csv | Lọc split=test, method=isolation_forest để xem 21 khoảng |
| scored_data.csv | Số đo, feature, điểm và cờ từng mẫu |
| summary.json | Cấu hình, chất lượng dữ liệu và kết quả mô hình |
| http_detail_summary.json | Số lượt đủ dữ liệu và các trường hợp HTTP được chọn |
| http_episode_comparison.csv | Trung bình train, trung bình khoảng IF và mức tăng từng bước HTTP |
| http_episode_observations.csv | Số đo gốc trong khoảng HTTP được phân tích |
| http_correlation_pearson.csv, http_correlation_spearman.csv | Ma trận tương quan HTTP trên cùng các lượt đủ dữ liệu |
| http_component_inconsistencies.csv | Trường hợp tổng ba thành phần lớn hơn HTTP; lần này không có |
| agreement_test.csv, group_means_test.csv | Mức giao nhau với baseline và trung bình hai nhóm trên test |
| sensitivity.csv | Đối chiếu ngưỡng từ cùng điểm train; không đổi hay huấn luyện lại mô hình |
| cleaned_data.csv | Dữ liệu sau kiểm tra |
| missing_measurements.csv, data_quality_notes.csv | Các dòng thiếu hoặc chưa nhất quán |
| descriptive_stats.csv, hourly_profile.csv | Thống kê mô tả và trung bình theo giờ |
| correlation_pearson.csv, correlation_spearman.csv | Tương quan năm chỉ số chính |

Ở mục 5.5 của báo cáo, nhóm phân tích **51.067 lượt đủ TCP, TLS, TTFB và HTTP tổng**, loại riêng ba lượt thiếu, không điền bằng 0 để tính tương quan.

- Lượt 31/08 lúc 09:12:00 có HTTP 47.294,06 ms, phần TCP chiếm 99,17%. Đây là ví dụ cực trị trong giai đoạn train.
- Khoảng IF ngày 02/09 từ 20:54:30 đến trước 21:23:00 có 57 lượt. So với trung bình train đủ dữ liệu, **TTFB tăng nhiều nhất: 463,12 ms**. Đây là một trong hai khoảng IF dài nhất, cùng 28,5 phút.
- HTTP trung bình số đo gốc trong khoảng là 1.847,48 ms; khác trung bình trượt 1.857,10 ms ở bảng khoảng vì cách tổng hợp khác nhau.

TCP trong collector gồm phân giải tên miền hệ thống; TLS gồm chuẩn bị ngữ cảnh; TTFB gồm gửi yêu cầu và chờ byte đầu. Phần đọc còn lại bằng HTTP tổng trừ ba bước trước, tới khi vòng đọc kết thúc. Vì vậy, nhóm chỉ xác định bước có thời gian tăng, chưa kết luận nguyên nhân gốc nằm ở mạng hay máy chủ. Tương quan với HTTP tổng còn chịu ảnh hưởng do các bước là thành phần của tổng.

Nhóm không dùng baseline làm nhãn đúng và chưa tính F1 vì chưa có nhãn sự cố được xác nhận độc lập. Nhóm chọn contamination 0,05 làm cấu hình thực nghiệm, chưa khẳng định đây là giá trị tối ưu. Bảng sensitivity cho 16, 402 và 1.329 cảnh báo test ở các ngưỡng tương ứng 0,02; 0,05; 0,10. Đây là phân tích độ nhạy, không phải chọn ngưỡng tốt nhất bằng test.

## 6. Thu thêm dữ liệu khi cần

Khi cần thu thêm dữ liệu, nhóm chạy collector trên máy và mạng được phép sử dụng. Riêng phần demo kết quả trong báo cáo chỉ cần chạy chương trình phân tích với CSV đã có.

Mở `collector_goc.py` và sửa hằng số `OUTPUT_CSV` sang một **file mới**. Bản được cung cấp đang giữ nguyên đường dẫn máy ban đầu: `E:\Python\Mangmaytinh (1)\network_quality_data.csv`. Có thể sửa thành `du_lieu/thu_moi.csv` khi chạy từ thư mục bài; thư mục `du_lieu` phải tồn tại. Collector chưa tự tạo thư mục cha và sẽ nối thêm vào file nếu file đã có.

```powershell
.\.venv\Scripts\python.exe collector_goc.py
```

Collector chỉ chạy liên tục theo `INTERVAL_SECONDS=30`; nhấn Ctrl+C để dừng. Không nhận tùy chọn dòng lệnh. Nhật ký mới là `collector.log` trong thư mục làm việc, khác với log lịch sử nằm ở `du_lieu/network_quality_data.log`. Khi dùng Task Scheduler, đặt thư mục làm việc phù hợp và tránh khởi chạy chồng các tiến trình.

Với một target, mỗi lượt gồm bốn ping, một phép DNS và một yêu cầu HTTPS, dự kiến khoảng hai lượt mỗi phút. Nếu một lượt kéo dài hơn 30 giây, lượt kế tiếp bắt đầu sau đó, không chạy bù. Nhóm giữ tần suất đo như cấu hình, không tạo tải để làm mạng suy giảm. Khi thu thêm dữ liệu để so sánh với bộ hiện tại, cần giữ nguyên ba hàm đo.

Phân tích CSV mới có cùng schema và target Google:

```powershell
.\.venv\Scripts\python.exe phan_tich.py --input du_lieu/thu_moi.csv --output ket_qua_thu_moi
```

## 7. Trước khi nộp

Trước khi nộp, nhóm kiểm tra thông tin trên bìa, phần mô tả nguồn dữ liệu và tuyên bố sử dụng AI. Nhóm chạy lại chương trình, đối chiếu các kết quả chính, sau đó tập demo theo `HUONG_DAN_DEMO.md`. Khi trình bày, nhóm cần giải thích được một dòng CSV, một đặc trưng, một khoảng IF và các biểu đồ HTTP dựa trên bộ dữ liệu 51.070 dòng đi kèm.
