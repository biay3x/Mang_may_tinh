"""T19: Đọc CSV -> làm sạch -> rolling -> baseline/Isolation Forest -> kết quả.

Chạy: python phan_tich.py
Phân tích Google bằng Isolation Forest, cửa sổ 5 phút, contamination 0,05.
Baseline chỉ dùng đối chiếu. --input và --output chỉ đổi vị trí file.
TCP/TLS/TTFB chỉ dùng giải thích HTTP sau mô hình; tổng cộng bảy biểu đồ.
Không có nhãn sự cố độc lập: đánh giá bằng điểm số và phân tích cảnh báo.
Chương trình phân tích ngoại tuyến, không gửi gói tin hoặc request ra mạng.
"""
import argparse
import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer

METRICS = ["rtt_ms", "jitter_ms", "loss_rate", "dns_latency_ms", "http_latency_ms"]
NAMES = ["RTT", "Jitter", "Mất phản hồi ICMP", "DNS latency", "HTTP latency"]
LIMITS = dict(zip(METRICS, [100, 20, 0.05, 100, 1000]))
STEP_SECONDS = 30
GAP_SECONDS = 60
SEED = 42
# Cấu hình cố định cho bài tiểu luận.
WINDOW_MINUTES = 5
CONTAMINATION = 0.05


def read_and_clean(path):
    """Giữ số đo lớn; chỉ sửa giá trị không hợp lệ hoặc không đo được."""
    df = pd.read_csv(path)
    required = ["timestamp"] + METRICS
    if not set(required).issubset(df.columns):
        raise ValueError(f"CSV cần các cột {required}")
    audit = {"input_rows": len(df), "input_columns": len(df.columns),
             "missing_before": df.isna().sum().to_dict()}
    if "target_id" not in df:
        df["target_id"] = "google"
    df = df.loc[df.target_id == "google"].copy()
    if df.empty:
        raise ValueError("Không có dữ liệu cho target google.")
    df["timestamp"] = pd.to_datetime(df.timestamp, errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
    audit["invalid_timestamps"] = int(df.timestamp.isna().sum())
    df = df.dropna(subset=["timestamp"])
    audit["exact_duplicates"] = int(df.duplicated().sum())
    df = df.drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    if df.duplicated(["timestamp"]).any():
        raise ValueError(
            "Có hai dòng khác dữ liệu nhưng cùng thời điểm; cần kiểm tra nguồn."
        )
    for col in METRICS:
        # Chuyển dữ liệu sang số; giá trị không hợp lệ hoặc vô cực được xem là thiếu.
        df[col] = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        # Các chỉ số đo thời gian và tỷ lệ không thể nhận giá trị âm.
        df.loc[df[col] < 0, col] = np.nan
    # loss_rate là tỷ lệ nên chỉ hợp lệ trong khoảng từ 0 đến 1.
    df.loc[df.loss_rate > 1, "loss_rate"] = np.nan
    audit["jitter_corrected"] = 0
    if "n_received" in df:
        bad = (pd.to_numeric(df.n_received, errors="coerce") < 2) & df.jitter_ms.notna()
        audit["jitter_corrected"] = int(bad.sum())
        df.loc[bad, "jitter_ms"] = np.nan
    df["missing_metric_count"] = df[METRICS].isna().sum(axis=1)
    # Ghi nhận điểm không nhất quán, không tự chọn số nào là số đo đúng.
    df["measurement_consistency_issue"] = False
    if {"n_sent", "n_received"}.issubset(df.columns):
        sent = pd.to_numeric(df.n_sent, errors="coerce")
        received = pd.to_numeric(df.n_received, errors="coerce")
        mismatch = sent.gt(0) & ((df.loss_rate - (1 - received / sent)).abs() > 0.0001)
        df.loc[mismatch, "measurement_consistency_issue"] = True
        audit["loss_count_mismatches"] = int(mismatch.sum())
    http_times = ["tcp_connect_ms", "tls_handshake_ms", "ttfb_ms", "http_latency_ms"]
    if set(http_times + ["http_status_code"]).issubset(df.columns):
        incomplete = df.http_status_code.notna() & df[http_times].isna().all(axis=1)
        df.loc[incomplete, "measurement_consistency_issue"] = True
        audit["http_status_without_times"] = int(incomplete.sum())
    gaps = df.timestamp.diff().dt.total_seconds()
    df["session_id"] = gaps.gt(GAP_SECONDS).cumsum()
    audit.update(clean_rows=len(df), sessions=int(df.session_id.nunique()),
                 gaps_over_60s=int(gaps.gt(GAP_SECONDS).sum()),
                 median_gap_seconds=float(gaps.median()),
                 missing_after=df[METRICS].isna().sum().to_dict(),
                 start=str(df.timestamp.min()), end=str(df.timestamp.max()))
    return df, audit


def make_features(df, minutes):
    """Cửa sổ (t - 5 phút, t]; không dùng dữ liệu tương lai hoặc vượt phiên đo."""
    blocks = []
    for _, group in df.groupby("session_id", sort=False):
        group = group.set_index("timestamp")
        roll = group[METRICS].rolling(f"{minutes}min", min_periods=3)
        features = roll.mean().add_suffix("_mean")
        features["rtt_std"] = roll["rtt_ms"].std(ddof=0)
        features["rtt_p95"] = roll["rtt_ms"].quantile(0.95)
        features["http_p95"] = roll["http_latency_ms"].quantile(0.95)
        features["hour"] = features.index.hour + features.index.minute / 60
        # Bỏ hai mẫu đầu của mỗi phiên để có tối thiểu ba thời điểm trong cửa sổ.
        features["ready"] = group["target_id"].rolling(f"{minutes}min").count() >= 3
        blocks.append(features.reset_index())
    result = df.merge(pd.concat(blocks), on="timestamp", validate="one_to_one")
    columns = [m + "_mean" for m in METRICS] + ["rtt_std", "rtt_p95", "http_p95", "hour"]
    return result.loc[result.ready].reset_index(drop=True), columns


def build_intervals(scored, flag, ref_median, ref_iqr):
    """Ít nhất ba mẫu liên tiếp; không nối qua mẫu bình thường, gap, train/test."""
    boundary = (scored[flag].ne(scored[flag].shift()) |
                scored.timestamp.diff().dt.total_seconds().ne(STEP_SECONDS) |
                scored.session_id.ne(scored.session_id.shift()) |
                scored.split.ne(scored.split.shift()))
    rows = []
    for _, group in scored.groupby(boundary.cumsum()):
        if not bool(group[flag].iloc[0]) or len(group) < 3:
            continue
        means = group[[m + "_mean" for m in METRICS]].mean()
        increases = (means - ref_median) / ref_iqr
        dominant = increases.idxmax().removesuffix("_mean") if increases.max() > 0 else "khong_co_muc_tang"
        start, last = group.timestamp.iloc[0], group.timestamp.iloc[-1]
        row = {"method": flag, "split": group.split.iloc[0], "start": start,
               "last_sample": last, "end_exclusive_estimated": last + pd.Timedelta(seconds=STEP_SECONDS),
               "n_samples": len(group), "estimated_minutes": (last - start).total_seconds() / 60 + 0.5,
               "dominant_increase_metric": dominant, "max_score": float(group.anomaly_score.max())}
        row.update({m: float(means[m + "_mean"]) for m in METRICS})
        rows.append(row)
    columns = ["method", "split", "start", "last_sample", "end_exclusive_estimated", "n_samples",
               "estimated_minutes", "dominant_increase_metric", "max_score"] + METRICS
    return pd.DataFrame(rows, columns=columns)


def make_figures(scored, clean, intervals, summary, output):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
    test = scored.loc[scored.split == "test"]
    means = [m + "_mean" for m in METRICS]
    fig, axes = plt.subplots(5, 1, figsize=(11, 10), sharex=True)
    for ax, m, name in zip(axes, METRICS, NAMES):
        scale = 100 if m == "loss_rate" else 1
        # Không vẽ đường nối qua khoảng thiếu quan sát giữa các phiên.
        for _, session in test.groupby("session_id"):
            ax.plot(session.timestamp, session[m + "_mean"] * scale, lw=0.7, color="#24618a")
        gap_mask = test.timestamp.diff().dt.total_seconds().gt(GAP_SECONDS)
        for index in test.index[gap_mask]:
            ax.axvspan(test.loc[index - 1, "timestamp"] + pd.Timedelta(seconds=STEP_SECONDS),
                       test.loc[index, "timestamp"], color="#b7bdc2", alpha=0.25)
        flagged = test.loc[test.isolation_forest]
        ax.scatter(flagged.timestamp, flagged[m + "_mean"] * scale, s=3, color="#ce572d", label="IF cảnh báo")
        ax.axhline(LIMITS[m] * scale, color="#666666", ls="--", lw=0.8)
        axis_name = "Loss ICMP" if m == "loss_rate" else name
        ax.set_ylabel(axis_name + (" (%)" if m == "loss_rate" else " (ms)"))
        ax.grid(alpha=0.15)
    axes[0].legend(loc="upper right")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m", tz=test.timestamp.dt.tz))
    fig.suptitle(f"Hình 1. Cảnh báo Isolation Forest trên tập kiểm tra\nCửa sổ {summary['window_minutes']} phút; vùng xám chưa đủ dữ liệu; nét đứt ngưỡng đối chiếu")
    fig.tight_layout()
    fig.savefig(output / "hinh_1_timeline.png", dpi=180)
    plt.close(fig)

    daily = test.assign(date=test.timestamp.dt.strftime("%d/%m")).groupby("date", sort=False)[["isolation_forest", "baseline"]].mean() * 100
    ax = daily.rename(columns={"baseline": "Ngưỡng đối chiếu", "isolation_forest": "Isolation Forest"}).plot.bar(figsize=(10, 4), color=["#ce572d", "#b0b8bc"])
    ax.set(title="Hình 4. Tỷ lệ mẫu cảnh báo theo ngày\nTập kiểm tra", xlabel="Ngày (chỉ tính các thời điểm có mẫu đủ lịch sử)", ylabel="Tỷ lệ mẫu (%)")
    ax.tick_params(axis="x", rotation=0)
    ax.figure.tight_layout()
    ax.figure.savefig(output / "hinh_4_ty_le_theo_ngay.png", dpi=180)
    plt.close(ax.figure)

    cols = ["rtt_ms", "dns_latency_ms", "http_latency_ms"]
    corr = clean[cols].corr()
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(3), ["RTT", "DNS", "HTTP"])
    ax.set_yticks(range(3), ["RTT", "DNS", "HTTP"])
    for i in range(3):
        for j in range(3):
            value = corr.iloc[i, j]
            ax.text(j, i, f"{value:.3f}", ha="center", va="center",
                    color="white" if abs(value) > .55 else "black")
    fig.suptitle("Hình 3. Tương quan Pearson trên toàn bộ CSV")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(output / "hinh_3_tuong_quan.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4))
    for split, label in [("train", "Huấn luyện"), ("test", "Kiểm tra")]:
        ax.hist(scored.loc[scored.split == split, "anomaly_score"], bins=50, density=True, alpha=0.55, label=label)
    ax.axvline(summary["score_threshold"], color="#ce572d", ls="--", label="Ngưỡng IF từ tập huấn luyện")
    ax.set(title="Hình 2. Phân bố điểm bất thường Isolation Forest", xlabel="Điểm = −score_samples; lớn hơn là khác thường hơn", ylabel="Mật độ")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "hinh_2_anomaly_score.png", dpi=180)
    plt.close(fig)

    profile = clean.assign(hour=clean.timestamp.dt.hour).groupby("hour")[METRICS].mean().reindex(range(24))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, metric, title in zip(axes, ["rtt_ms", "http_latency_ms"], ["RTT", "HTTP latency"]):
        ax.plot(profile.index, profile[metric], marker="o", color="#24618a")
        ax.set(xlabel="Giờ địa phương UTC+7", ylabel=title + " (ms)", xticks=[0, 4, 8, 12, 16, 20, 23])
        ax.grid(alpha=0.2)
    fig.suptitle("Hình 5. Trung bình theo giờ trên toàn bộ CSV cập nhật")
    fig.tight_layout()
    fig.savefig(output / "hinh_5_theo_gio.png", dpi=180)
    plt.close(fig)


def analyze_http_components(clean, scored, intervals, output):
    """Giải thích HTTP sau khi IF đã chạy; không thêm feature vào mô hình."""
    parts = ["tcp_connect_ms", "tls_handshake_ms", "ttfb_ms"]
    columns = parts + ["http_latency_ms"]
    if not set(columns).issubset(clean.columns):
        logging.info("CSV không đủ TCP/TLS/TTFB: bỏ qua phân tích HTTP bổ sung.")
        return
    data = clean[["timestamp"] + columns].copy()
    for col in columns:
        data[col] = pd.to_numeric(data[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        data.loc[data[col] < 0, col] = np.nan
    valid = data.dropna(subset=columns).copy()
    if len(valid) < 3:
        logging.info("Không đủ lượt đo hợp lệ để phân tích tương quan HTTP.")
        return
    # Theo các mốc t0..t4 của collector, phần còn lại là t4-t3.
    valid["remaining_read_ms"] = valid.http_latency_ms - valid[parts].sum(axis=1)
    inconsistent = valid.remaining_read_ms < -0.01
    valid.loc[inconsistent].to_csv(output / "http_component_inconsistencies.csv", index=False, encoding="utf-8-sig")
    correlations = {}
    for method in ["pearson", "spearman"]:
        correlations[method] = valid[columns].corr(method=method)
        correlations[method].to_csv(output / f"http_correlation_{method}.csv")
    # Hai hệ số tính trên cùng tập lượt đủ cả bốn giá trị, không điền thiếu.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, method, title in zip(axes, ["pearson", "spearman"], ["Pearson", "Spearman theo thứ hạng"]):
        matrix = correlations[method]
        ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(4), ["TCP", "TLS", "TTFB", "HTTP"])
        ax.set_yticks(range(4), ["TCP", "TLS", "TTFB", "HTTP"])
        ax.set_title(title)
        for i in range(4):
            for j in range(4):
                value = matrix.iloc[i, j]
                ax.text(j, i, f"{value:.3f}", ha="center", va="center",
                        color="white" if abs(value) > .55 else "black")
    fig.suptitle(f"Hình 6. Tương quan TCP, TLS, TTFB và HTTP\n{len(valid):,} lượt đủ dữ liệu; hệ số từ −1 đến 1")
    fig.tight_layout()
    fig.savefig(output / "hinh_6_tuong_quan_http.png", dpi=180)
    plt.close(fig)
    usable = valid.loc[~inconsistent].copy()
    usable["remaining_read_ms"] = usable.remaining_read_ms.clip(lower=0)
    joined = usable.merge(scored[["timestamp", "split", "isolation_forest"]], on="timestamp", validate="one_to_one")
    train = joined.loc[joined.split == "train"]
    stages = parts + ["remaining_read_ms"]
    result = {"input_rows": len(clean), "complete_rows": len(valid),
              "excluded_missing_or_invalid": len(data) - len(valid),
              "negative_residual_rows": int(inconsistent.sum()),
              "correlation_uses_same_complete_rows": True,
              "not_used_as_isolation_forest_features": parts}
    peak = usable.loc[usable.http_latency_ms.idxmax()]
    result["maximum_http_observation"] = {"timestamp": str(peak.timestamp),
        **{c: float(peak[c]) for c in columns + ["remaining_read_ms"]},
        "tcp_percent_of_total": float(100 * peak.tcp_connect_ms / peak.http_latency_ms)}
    episodes = intervals.loc[(intervals.method == "isolation_forest") & (intervals.split == "test")]
    if len(episodes) and len(train):
        episode = episodes.loc[episodes.estimated_minutes.idxmax()]
        start, end = pd.Timestamp(episode.start), pd.Timestamp(episode.end_exclusive_estimated)
        case = joined.loc[(joined.timestamp >= start) & (joined.timestamp < end)]
        reference = train[stages + ["http_latency_ms"]].mean()
        case_mean = case[stages + ["http_latency_ms"]].mean()
        comparison = pd.DataFrame({"reference_train_mean_ms": reference, "episode_mean_ms": case_mean,
                                   "increase_ms": case_mean - reference})
        comparison.index.name = "metric"
        comparison.to_csv(output / "http_episode_comparison.csv")
        valid.loc[(valid.timestamp >= start) & (valid.timestamp < end)].to_csv(output / "http_episode_observations.csv", index=False, encoding="utf-8-sig")
        result["episode"] = {"start": str(start), "end_exclusive_estimated": str(end),
            "complete_rows": len(case), "reference_rows": len(train), "reference": "Các lượt thuộc train đủ bốn thời gian HTTP, không mặc định đều bình thường",
            "largest_absolute_increase_stage": (case_mean - reference)[stages].idxmax()}
        fig, ax = plt.subplots(figsize=(10, 4.2))
        left = np.zeros(3)
        groups = [reference, case_mean, peak]
        for part, label, color in zip(stages, ["TCP", "TLS", "Chờ byte đầu", "Đọc phần còn lại"],
                                     ["#4477aa", "#ee9955", "#55aa99", "#bbbbbb"]):
            share = np.array([100 * float(g[part]) / float(g["http_latency_ms"]) for g in groups])
            ax.barh(range(3), share, left=left, label=label, color=color)
            left += share
        ax.set_yticks(range(3), ["Trung bình train", "Khoảng IF dài nhất trên test", "Lượt HTTP cao nhất toàn CSV"])
        ax.invert_yaxis()
        ax.set(xlim=(0, 100), xlabel="Tỷ trọng trong thời gian HTTP (%)", title="Hình 7. Cơ cấu thời gian HTTP ở các trường hợp đối chiếu")
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.22), ncol=2)
        fig.tight_layout()
        fig.savefig(output / "hinh_7_thanh_phan_http.png", dpi=180)
        plt.close(fig)
    (output / "http_detail_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=base / "du_lieu" / "network_quality_data.csv")
    parser.add_argument("--output", type=Path, default=base / "ket_qua")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[
        logging.StreamHandler(), logging.FileHandler(args.output / "analysis.log", mode="w", encoding="utf-8")])
    logging.info("Bước 1/5: đọc và làm sạch CSV")
    clean, audit = read_and_clean(args.input)
    clean.to_csv(args.output / "cleaned_data.csv", index=False, encoding="utf-8-sig")
    clean.loc[clean.missing_metric_count > 0].to_csv(args.output / "missing_measurements.csv", index=False, encoding="utf-8-sig")
    clean.loc[clean.measurement_consistency_issue].to_csv(args.output / "data_quality_notes.csv", index=False, encoding="utf-8-sig")
    logging.info("Bước 2/5: tạo đặc trưng trượt và chia theo thời gian")
    scored, features = make_features(clean, WINDOW_MINUTES)
    cut = int(len(scored) * 0.7)
    if cut < 256 or len(scored) - cut < 30:
        raise ValueError("Cần thêm dữ liệu để chia train/test có ý nghĩa.")
    scored["split"] = np.where(np.arange(len(scored)) < cut, "train", "test")
    if scored.loc[:cut - 1, features].isna().all().any():
        raise ValueError("Có đặc trưng trống toàn bộ trong train; kiểm tra collector.")
    imputer = SimpleImputer(strategy="median")
    train_x = imputer.fit_transform(scored.loc[:cut - 1, features])
    all_x = imputer.transform(scored[features])
    logging.info("Bước 3/5: baseline và Isolation Forest")
    scored["baseline"] = pd.concat([scored[m + "_mean"] > v for m, v in LIMITS.items()], axis=1).any(axis=1)
    model = IsolationForest(n_estimators=100, max_samples=256, contamination=CONTAMINATION,
                            random_state=SEED, n_jobs=1)
    model.fit(train_x)
    scored["anomaly_score"] = -model.score_samples(all_x)
    scored["isolation_forest"] = model.predict(all_x) == -1
    means = [m + "_mean" for m in METRICS]
    train = scored.iloc[:cut]
    ref_median = train[means].median()
    ref_iqr = train[means].quantile(.75) - train[means].quantile(.25)
    # Loss thường có IQR=0; dùng std train thay thế, tránh chia cho 0.
    ref_iqr = ref_iqr.where(ref_iqr > 0, train[means].std(ddof=0)).replace(0, 1)
    intervals = pd.concat([build_intervals(scored, method, ref_median, ref_iqr)
                          for method in ["baseline", "isolation_forest"]], ignore_index=True)
    summary = {"audit": audit, "warmup_removed": len(clean) - len(scored), "feature_columns": features,
               "window_minutes": WINDOW_MINUTES, "train_rows": cut, "test_rows": len(scored) - cut,
               "train_end": str(train.timestamp.iloc[-1]), "test_start": str(scored.timestamp.iloc[cut]),
               "contamination": CONTAMINATION, "score_threshold": float(-model.offset_),
               "baseline_thresholds": LIMITS, "n_estimators": 100, "max_samples": 256, "random_state": SEED,
               "evaluation_has_ground_truth": False,
               "missing_feature_cells_before_imputation": int(scored[features].isna().sum().sum()),
               "versions": {"pandas": pd.__version__, "numpy": np.__version__, "sklearn": sklearn.__version__, "matplotlib": matplotlib.__version__},
               "counts": {}, "reference_median": ref_median.to_dict(), "reference_iqr": ref_iqr.to_dict()}
    for split, group in scored.groupby("split"):
        both = int((group.baseline & group.isolation_forest).sum())
        union = int((group.baseline | group.isolation_forest).sum())
        summary["counts"][split] = {"n": len(group), "baseline": int(group.baseline.sum()),
                                     "isolation_forest": int(group.isolation_forest.sum()), "both": both,
                                     "jaccard": both / union if union else None}
    logging.info("Bước 4/5: đánh giá và gộp khoảng cảnh báo")
    test = scored.iloc[cut:]
    pd.DataFrame([{"nhom": name, "so_mau": int(mask.sum())} for name, mask in [
        ("ca_hai_canh_bao", test.baseline & test.isolation_forest),
        ("chi_isolation_forest", ~test.baseline & test.isolation_forest),
        ("chi_nguong_doi_chieu", test.baseline & ~test.isolation_forest),
        ("ca_hai_khong_canh_bao", ~test.baseline & ~test.isolation_forest)
    ]]).to_csv(args.output / "agreement_test.csv", index=False, encoding="utf-8-sig")
    # Đối chiếu ngưỡng trên cùng điểm số; không đổi hay huấn luyện lại mô hình.
    sensitivity = []
    for contamination in [.02, .05, .10]:
        threshold = float(train.anomaly_score.quantile(1 - contamination))
        flags = scored.iloc[cut:].anomaly_score > threshold
        sensitivity.append({"contamination": contamination, "threshold_from_train": threshold,
                            "test_flags": int(flags.sum()), "test_rate": float(flags.mean())})
    pd.DataFrame(sensitivity).to_csv(args.output / "sensitivity.csv", index=False)
    clean[METRICS].describe(percentiles=[.5, .95, .99]).T.to_csv(args.output / "descriptive_stats.csv")
    for kind in ["pearson", "spearman"]:
        clean[METRICS].corr(method=kind).to_csv(args.output / f"correlation_{kind}.csv")
    clean.assign(hour=clean.timestamp.dt.hour).groupby("hour")[METRICS].mean().to_csv(args.output / "hourly_profile.csv")
    scored.iloc[cut:].groupby("isolation_forest")[means].mean().to_csv(args.output / "group_means_test.csv")
    scored.to_csv(args.output / "scored_data.csv", index=False, encoding="utf-8-sig")
    intervals.to_csv(args.output / "intervals.csv", index=False, encoding="utf-8-sig")
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Bước 5/5: tạo 7 biểu đồ và phân tích HTTP")
    make_figures(scored, clean, intervals, summary, args.output)
    analyze_http_components(clean, scored, intervals, args.output)
    logging.info("Hoàn thành: %s", args.output.resolve())


if __name__ == "__main__":
    main()
