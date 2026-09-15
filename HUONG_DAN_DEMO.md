# Hướng dẫn trình bày và demo tiểu luận T19

Nhóm chuẩn bị sẵn thư mục bài làm, báo cáo và môi trường Python theo README. Các bước dưới đây giúp nhóm trình bày từ bài toán, dữ liệu đến kết quả. Phần lời nói mẫu có thể điều chỉnh cho tự nhiên, nhưng cần giữ đúng nội dung đã thực hiện.

## Bước 1. Giới thiệu đề tài trong khoảng một phút

Nhóm có thể mở đầu như sau:

> Trong đề tài này, nhóm em theo dõi RTT, jitter, loss, DNS và HTTP theo thời gian để tìm những khoảng có dấu hiệu mạng suy giảm. Nhóm dùng Isolation Forest để phát hiện mẫu khác thường và dùng baseline theo ngưỡng để đối chiếu. Do chưa có nhãn sự cố được xác nhận độc lập, nhóm chưa kết luận được độ chính xác phát hiện sự cố thực tế.

Mở bản báo cáo đã chỉnh văn phong `Bao_cao_T19_van_phong_nhom.docx`. Nhóm giới thiệu hai file Python của bài: `collector_goc.py` thu dữ liệu và `phan_tich.py` phân tích. Để demo kết quả đã có, chỉ chạy file phân tích.

## Bước 2. Giới thiệu dữ liệu đã sử dụng

Nhóm mở `du_lieu/network_quality_data.csv`, chọn một dòng để giải thích thời điểm đo và các chỉ số RTT, jitter, loss, DNS, HTTP. Có 51.070 dòng, 15 cột, từ 19/08 tới 08/09/2026 theo UTC+7. Nhóm thu thập dữ liệu trên máy Windows, kết nối Ethernet.

Nhóm giải thích lịch Task Scheduler chạy từ 03:00 đến 01:00 hôm sau; các khoảng nghỉ ban đêm không phải bằng chứng mất mạng. Hai thời điểm trong giờ chạy thiếu mẫu là 22/08 lúc 20:35:30 và 20:54:30. Log đối chiếu số đo nhưng không phải nhãn đúng/sai cho mô hình. Khi được hỏi về nguồn dữ liệu, nhóm trình bày phần đã đối chiếu và các giới hạn trong phần nguồn dữ liệu và phụ lục C, không khẳng định những thông tin chưa xác minh.

## Bước 3. Chạy chương trình và giải thích các bước xử lý

Sau khi cài môi trường theo README, nhóm chạy lệnh sau:

```powershell
.\.venv\Scripts\python.exe phan_tich.py --input du_lieu/network_quality_data.csv --output ket_qua_demo
```

Lệnh trên đọc đúng CSV hiện có và lưu kết quả vào `ket_qua_demo`, tách riêng với thư mục kết quả ban đầu `ket_qua`. Trong lúc trình bày, nhóm giải thích lần lượt:

1. Nhóm đọc CSV, sắp xếp thời gian và kiểm tra dữ liệu. Không xóa chỉ vì số đo cao.
2. Nhóm tách phiên khi ngắt trên 60 giây; cửa sổ 5 phút không đi qua phiên khác.
3. Nhóm tạo 9 đặc trưng từ năm chỉ số chính và giờ. Bỏ 40 mẫu đầu phiên, còn 51.030 mẫu.
4. Nhóm chia 70% mẫu đầu làm train (35.721), 30% mẫu cuối làm test (15.309), không trộn ngẫu nhiên.
5. Nhóm điền thiếu bằng trung vị train, học Isolation Forest trên train, áp dụng cho test.
6. Nhóm đối chiếu baseline, gộp các chuỗi ít nhất ba mẫu cảnh báo liên tiếp rồi xuất bảng và hình.
7. Nhóm phân tích TCP, TLS, TTFB và HTTP sau mô hình; không đưa thêm các chỉ số này vào đặc trưng của mô hình.

Cấu hình nhóm sử dụng được giữ cố định: Google, 5 phút, contamination 0,05, 100 cây, 256 mẫu/cây, seed 42. Nếu cần minh họa ảnh hưởng ngưỡng, mở `sensitivity.csv`; chương trình tính ba ngưỡng từ cùng điểm train, không huấn luyện thêm mô hình.

## Bước 4. Trình bày kết quả phát hiện khoảng suy giảm

Nhóm mở `hinh_1_timeline.png` và `intervals.csv` trong thư mục kết quả demo. Lọc `split=test`, `method=isolation_forest`: **402 mẫu cảnh báo, 21 khoảng, 371 mẫu được gộp, độ phủ ước lượng 185,5 phút**. Có 31 mẫu ở các chuỗi ngắn bị loại khỏi bảng khoảng. Baseline cảnh báo 1.624 mẫu, bao gồm 402 mẫu IF; sự giao nhau này không đo độ chính xác.

Để minh họa, nhóm chọn khoảng 02/09 từ 20:54:30 tới trước 21:23:00: 57 mẫu, 28,5 phút ước lượng. Mẫu cuối là 21:22:30, mốc kết thúc cộng thêm 30 giây. Nhóm giải thích rằng cửa sổ trượt tổng hợp nhiều lượt đo, nên cảnh báo có thể xuất hiện muộn hoặc còn kéo dài sau khi số đo đã giảm.

Tiếp theo, nhóm mở `hinh_3_tuong_quan.png` và giải thích: RTT, DNS và HTTP có thể cùng tăng nhưng phép ping, phép DNS riêng và HTTPS không phải cùng phép đo; HTTP không bằng RTT cộng DNS.

## Bước 5. Giải thích các trường hợp HTTP tăng cao

Nhóm mở Hình 6 và giới thiệu: Pearson mô tả quan hệ tuyến tính, Spearman mô tả quan hệ theo thứ hạng. Có 51.067 lượt đủ cả bốn thời gian. Nhóm xem xét tương quan giữa ba thành phần TCP–TLS–TTFB và mối liên hệ của từng thành phần với HTTP tổng.

Sau đó, nhóm mở `http_episode_comparison.csv` và Hình 7 để trình bày hai trường hợp:

- Trong khoảng IF ngày 02/09, TTFB tăng nhiều nhất so với trung bình train: 463,12 ms.
- Lượt HTTP cực đại ngày 31/08 lúc 09:12 có phần TCP chiếm 99,17% tổng thời gian.
- Hai trường hợp có cơ cấu khác nhau; không kết luận mọi lần HTTP cao đều do TCP.

TCP còn gồm phân giải hệ thống, TLS gồm chuẩn bị ngữ cảnh, TTFB gồm gửi yêu cầu và chờ phản hồi. Từ các số đo này, nhóm xác định bước có thời gian tăng, nhưng chưa chứng minh được nguyên nhân gốc. Hình 7 thể hiện tỷ trọng, không phải độ dài tuyệt đối giữa các trường hợp.

## Một số câu hỏi nhóm cần chuẩn bị

| Câu hỏi | Cách trả lời ngắn gọn |
|---|---|
| Vì sao chia theo thời gian? | Học quá khứ, kiểm tra giai đoạn sau; không trộn tương lai vào train |
| Vì sao chọn 0,05? | Cấu hình ban đầu có đối chiếu độ nhạy; chưa chứng minh tối ưu |
| 0,05 có nghĩa test có 5% cảnh báo không? | Không; ngưỡng đặt từ train, test lần này khoảng 2,63% |
| Điểm 0,7 có phải xác suất lỗi 70% không? | Không; chỉ là điểm khác thường theo quy ước của chương trình |
| Baseline có phải nhãn đúng không? | Không; chỉ đối chiếu hai cách cảnh báo |
| Vì sao không tính F1? | Chưa có nhãn sự cố độc lập để xác định đúng/sai |
| Vì sao bỏ hai mẫu đầu phiên? | Chưa đủ ba thời điểm trong cửa sổ; từng metric còn có thể thiếu riêng |
| Ba mẫu có chứng minh sự cố liên tục 90 giây không? | Không; trải 60 giây giữa hai đầu, 90 giây là độ phủ ước lượng |
| Chỉ số tăng mạnh nhất có phải nguyên nhân không? | Không; chỉ mô tả mức tăng sau chuẩn hóa |
| Có cần chạy collector khi demo không? | Không cần để tái lập; nếu thu mới thì kiểm tra OUTPUT_CSV, chạy liên tục và Ctrl+C để dừng |

## Bước 6. Kết thúc phần demo

Nhóm có thể kết thúc như sau:

> Qua bài làm, nhóm em đã xây dựng được chương trình phân tích dữ liệu mạng và xác định các khoảng cần xem xét bằng Isolation Forest. Kết quả còn giới hạn trong một máy, một cấu hình đích và lịch đo có thời gian nghỉ. Các cửa sổ trượt dùng chung nhiều quan sát; lịch sử dữ liệu cũng cần được đối chiếu. Vì vậy, nhóm trình bày các khoảng phát hiện được như gợi ý kiểm tra, chưa xem đó là các sự cố đã xác nhận.

Trước buổi demo, nhóm tập chạy lại chương trình và giải thích các kết quả bằng cách hiểu của mình.
