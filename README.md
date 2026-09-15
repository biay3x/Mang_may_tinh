# T19 - Phát hiện khoảng mạng suy giảm bằng Isolation Forest

Trong tiểu luận này, nhóm 9 em xây dựng chương trình theo dõi chất lượng mạng và phát hiện các khoảng thời gian có dấu hiệu suy giảm. Bài làm gồm báo cáo sáu chương và hai file Python: `collector.py` để thu thập dữ liệu, `phan_tich.py` để phân tích. Báo cáo chính là **Bao_cao_T19.docx**.
Nhóm đã lựa chọn mô hình chính là Isolation Forest trong việc phát hiện abnormally. Baseline theo ngưỡng do nhóm xây dựng chỉ để đối chiếu. Phần tương quan TCP, TLS, TTFB và phân tích HTTP do em chạy sau mô hình, do đó không thêm đầu vào cho Isolation Forest.

## 1. Các file trong bộ bài của nhóm em

| File hoặc thư mục | Vai trò |
|---|---|
| Bao_cao_T19.pdf | Báo cáo chính; nhóm em đã điền thông tin cá nhân trên bìa |
| collector.py | Thu theo chu kỳ 30 giây, chạy liên tục, dừng bằng Ctrl+C |
| phan_tich.py | Đọc CSV ngoại tuyến, phân tích và tạo kết quả |
| du_lieu/network_quality_data.csv | Dataset 51.070 dòng, 15 cột dùng trong báo cáo |
| du_lieu/network_quality_data.log | Log do collector ghi, dùng để đối chiếu với CSV |
| ket_qua | Các bảng CSV, tổng hợp JSON, log phân tích và 7 biểu đồ đã được tạo |
| requirements.txt | Phiên bản thư viện nhóm đã dùng |

## 2. Dataset và lịch đo do nhóm em thu thập

Dataset gồm 51.070 bản ghi, từ 19/08/2026 17:34:00 đến 08/09/2026 01:00:00, UTC+7. Nhóm thu trên máy Windows, kết nối Ethernet. Target có nhãn `google` do em cấu hình: ping 8.8.8.8, phân giải www.google.com, gửi HTTPS tới www.google.com. Đây là các phép đo liên quan nhưng không hoàn toàn cùng một đích IP - điểm này nhóm em đã phân tích kỹ ở Chương 2.

Nhóm em dùng Task Scheduler quản lý giờ hoạt động từ 03:00 đến 01:00 hôm sau, còn collector do nhóm em viết quản lý chu kỳ đo. Khi kiểm tra lại dữ liệu, nhóm tách được 20 phiên, ngăn cách bởi 19 khoảng nghỉ ban đêm. Trong 4.543 mốc thiếu trên lưới 30 giây, nhóm em xác định 4.541 mốc ngoài lịch và hai mốc trong lịch: 22/08 lúc 20:35:30 và 20:54:30. Mẫu đúng 01:00 vẫn được nhóm tính trong lịch.

Khi làm sạch, nhóm phát hiện năm lượt còn thiếu một hoặc nhiều chỉ số chính và ba lượt có thông tin chưa nhất quán; nhóm em xuất các dòng này ra file riêng để xem lại, em không thay dữ liệu thiếu thành 0 và không tự coi thởi gian ngừng đo là mạng tốt hay mạng lỗi.

## 3. Cài môi trường để chạy lại theo hướng dẫn của nhóm em
Giải nén ZIP, mở Terminal trong thư mục chứa README này. Nhóm em dùng Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu máy dùng lệnh `py`, thay lệnh đầu bằng `py -3.12 -m venv .venv`.

Môi trường thực nghiệm được sử dụng trong báo cáo: Python 3.12.14; numpy 2.5.3; pandas 3.0.1; matplotlib 3.11.1; scikit-learn 1.9.0; dnspython 2.8.0 dùng khi thu DNS. Môi trường Python không nằm trong ZIP; người dùng cần cài thư viện trên máy chạy lại theo đúng phiên bản đã ghi.

## 4. Chạy phân tích

```powershell
.\.venv\Scripts\python.exe phan_tich.py
```

Lệnh này đọc `du_lieu/network_quality_data.csv`, chạy ngoại tuyến và ghi vào `ket_qua`. 

Nhóm em cố định cấu hình chính trong mã: Google, Isolation Forest, cửa sổ 5 phút, contamination 0,05, 100 cây, tối đa 256 mẫu/cây, seed 42. Chương trình của nhóm chỉ có hai tùy chọn cho vị trí file là `--input` và `--output`.

| Kết quả nhóm em cần đối chiếu | Giá trị |
|---|---:|
| Dòng CSV / số mẫu đầu phiên bị bỏ | 51.070 / 40 |
| Mẫu đặc trưng | 51.030 |
| Train / test theo thứ tự thởi gian | 35.721 / 15.309 |
| Kết thúc train | 02/09/2026 07:23:00 UTC+7 |
| Bắt đầu test | 02/09/2026 07:23:30 UTC+7 |
| Ngưỡng điểm IF | 0,601695 |
| Mẫu IF cảnh báo trên test | 402, tương đương 2,63% |
| Khoảng IF trên test | 21 |
| Mẫu nằm trong các khoảng IF | 371 |
| Tổng độ phủ ước lượng | 185,5 phút |
| Mẫu baseline cảnh báo trên test | 1.624 |

Chín feature mà nhóm em đưa vào mô hình gồm trung bình cửa sổ của năm chỉ số chính, độ lệch chuẩn RTT, P95 RTT, P95 HTTP và giờ trong ngày. Mô hình và bộ điền thiếu của nhóm em chỉ học trên train. Cửa sổ do nhóm em thiết kế dùng hiện tại và quá khứ, không đi qua khoảng ngắt trên 60 giây.

Khoảng được nhóm em giữ phải có ít nhất ba mẫu cảnh báo liên tiếp, cách nhau đúng 30 giây. Ba mẫu trải từ đầu tới cuối 60 giây; chương trình của nhóm em cộng 30 giây sau mẫu cuối để ước lượng độ phủ 90 giây. Nhóm nhấn mạnh đây không phải thởi lượng sự cố đã xác nhận. Có 31 trong 402 mẫu cảnh báo nằm ở các đoạn ngắn bị nhóm em loại khi gộp khoảng.

## 5. Đọc kết quả và phần HTTP nâng cao của nhóm em## 5. Đọc kết quả và phần HTTP nâng cao

| File trong ket_qua | Nội dung |
|---|---|
| hinh_1_timeline.png | Timeline chỉ số mạng và các mẫu IF cảnh báo do nhóm em vẽ |
| hinh_2_anomaly_score.png | Phân bố điểm IF và ngưỡng từ train |
| hinh_3_tuong_quan.png | Quan hệ RTT, DNS và HTTP |
| hinh_4_ty_le_theo_ngay.png | Tỷ lệ cảnh báo IF và baseline theo ngày |
| hinh_5_theo_gio.png | RTT và HTTP trung bình theo giờ có dữ liệu |
| hinh_6_tuong_quan_http.png | Pearson và Spearman giữa TCP, TLS, TTFB và HTTP tổng |
| hinh_7_thanh_phan_http.png | Tỷ trọng thởi gian các bước HTTP ở ba trường hợp |
| intervals.csv | Lọc split=test, method=isolation_forest để xem 21 khoảng |
| scored_data.csv | Số đo, feature, điểm và cờ từng mẫu |
| summary.json | Cấu hình, chất lượng dữ liệu và kết quả mô hình |
| http_detail_summary.json | Số lượt đủ dữ liệu và các trường hợp HTTP được chọn |
| http_episode_comparison.csv | Trung bình train, trung bình khoảng IF và mức tăng từng bước HTTP |
| http_episode_observations.csv | Số đo gốc trong khoảng HTTP được phân tích |
| http_correlation_pearson.csv, http_correlation_spearman.csv | Ma trận tương quan HTTP trên cùng các lượt đủ dữ liệu |
| http_component_inconsistencies.csv | Trường hợp tổng ba thành phần lớn hơn HTTP; nhóm em kiểm tra và không phát hiện trường hợp nào |
| agreement_test.csv, group_means_test.csv | Mức giao nhau với baseline và trung bình hai nhóm trên test |
| sensitivity.csv | Đối chiếu ngưỡng từ cùng điểm train; nhóm em không đổi hay huấn luyện lại mô hình |
| cleaned_data.csv | Dữ liệu sau kiểm tra của nhóm em |
| missing_measurements.csv, data_quality_notes.csv | Các dòng thiếu hoặc chưa nhất quán mà nhóm em ghi nhận |
| descriptive_stats.csv, hourly_profile.csv | Thống kê mô tả và trung bình theo giờ |
| correlation_pearson.csv, correlation_spearman.csv | Tương quan năm chỉ số chính |

Ở mục 5.5 của báo cáo, nhóm phân tích **51.067 lượt đủ TCP, TLS, TTFB và HTTP tổng**, loại riêng ba lượt thiếu, không điền bằng 0 để tính tương quan.

- Lượt 31/08 lúc 09:12:00 có HTTP 47.294,06 ms, phần TCP chiếm 99,17%. Đây là ví dụ cực trị trong giai đoạn train.
- Khoảng IF ngày 02/09 từ 20:54:30 đến trước 21:23:00 có 57 lượt. So với trung bình train đủ dữ liệu, **TTFB tăng nhiều nhất: 463,12 ms**. Đây là một trong hai khoảng IF dài nhất, cùng 28,5 phút.
- HTTP trung bình số đo gốc trong khoảng là 1.847,48 ms; khác trung bình trượt 1.857,10 ms ở bảng khoảng vì cách tổng hợp khác nhau.

TCP trong collector gồm phân giải tên miền hệ thống; TLS gồm chuẩn bị ngữ cảnh; TTFB gồm gửi yêu cầu và chờ byte đầu. Phần đọc còn lại bằng HTTP tổng trừ ba bước trước, tới khi vòng đọc kết thúc. Vì vậy, nhóm chỉ xác định bước có thời gian tăng, chưa kết luận nguyên nhân gốc nằm ở mạng hay máy chủ. Tương quan với HTTP tổng còn chịu ảnh hưởng do các bước là thành phần của tổng.

Nhóm không dùng baseline làm nhãn đúng và chưa tính F1 vì chưa có nhãn sự cố được xác nhận độc lập. Nhóm chọn contamination 0,05 làm cấu hình thực nghiệm, chưa khẳng định đây là giá trị tối ưu. Bảng sensitivity cho 16, 402 và 1.329 cảnh báo test ở các ngưỡng tương ứng 0,02; 0,05; 0,10. Đây là phân tích độ nhạy, không phải chọn ngưỡng tốt nhất bằng test.

## 6. Thu thêm dữ liệu khi cần

Phần này có truy cập mạng; nhóm em chỉ thu trên máy và mạng được phép. Để tái lập kết quả báo cáo, chỉ cần chạy phần phân tích, không cần thu lại.

Ngưởi dùng mở `collector.py` và sửa hằng số `OUTPUT_CSV` sang một **file mới**. Bản nhóm em cung cấp đang giữ nguyên đường dẫn máy ban đầu: `E:\Python\Mangmaytinh (1)\network_quality_data.csv`. Có thể sửa thành `du_lieu/thu_moi.csv` khi chạy từ thư mục bài.

```powershell
.\.venv\Scripts\python.exe collector.py
```

Collector do nhóm em viết chỉ chạy liên tục theo `INTERVAL_SECONDS=30`; nhấn Ctrl+C để dừng. Chương trình không nhận tùy chọn dòng lệnh. Nhật ký mới là `collector.log` trong thư mục làm việc, khác với log lịch sử nằm ở `du_lieu/network_quality_data.log`. Khi dùng Task Scheduler, nhóm em đặt thư mục làm việc phù hợp và tránh khởi chạy chồng các tiến trình.

Với một target, mỗi lượt do collector của nhóm em thực hiện gồm bốn ping, một phép DNS và một yêu cầu HTTPS, dự kiến khoảng hai lượt mỗi phút. Nếu một lượt kéo dài hơn 30 giây, lượt kế tiếp bắt đầu sau đó, không chạy bù. Nhóm em không tăng tần suất hay tạo tải để gây suy giảm. Ngưởi dùng nên giữ nguyên ba hàm đo nếu muốn so sánh với dataset hiện tại của nhóm em.

Phân tích CSV mới có cùng schema và target Google:

```powershell
.\.venv\Scripts\python.exe phan_tich.py --input du_lieu/thu_moi.csv --output ket_qua_thu_moi
```
