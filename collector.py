#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
collector.py - Thu thap dinh ky du lieu chat luong mang cho de tai T19.

Do dinh ky cac metric:
    rtt_ms, rtt_min_ms, rtt_max_ms, jitter_ms, n_sent, n_received, loss_rate,
    dns_latency_ms,
    tcp_connect_ms, tls_handshake_ms, ttfb_ms, http_latency_ms, http_status_code
va ghi vao file CSV (moi dong = 1 lan do).

Cach chay:
    python collector.py            # chay lien tuc, do moi INTERVAL_SECONDS

Dung Ctrl+C de dung chuong trinh. Chuong trinh khong co che do chi
do 1 lan roi thoat; day la vong lap lien tuc duy nhat.

Yeu cau thu vien:
    - Bat buoc: khong co (chi dung thu vien chuan cua Python)
    - Khuyen nghi cai them: dnspython (pip install dnspython)
      -> giup do DNS latency chinh xac hon, tranh bi anh huong boi
         DNS cache cua he dieu hanh. Neu khong cai, chuong trinh van
         chay duoc nho co fallback dung socket.getaddrinfo(), nhung
         ket qua se kem chinh xac hon (xem ghi chu trong measure_dns).
"""

import csv
import logging
import os
import platform
import re
import socket
import ssl
import statistics
import subprocess
import time
from datetime import datetime
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# CAU HINH - CHINH SUA CAC GIA TRI DUOI DAY CHO PHU HOP
# ---------------------------------------------------------------------------

# Co the do nhieu "target" trong 1 lan chay bang cach them phan tu vao danh
# sach TARGETS ben duoi. Moi phan tu la 1 dict gom:
#   target_id    : nhan dang de phan biet trong dataset (vd "google")
#   ping_host    : dia chi IP/host dung de do RTT/jitter/loss
#   dns_domain   : domain dung de do DNS latency
#   http_url     : URL dung de do HTTP/HTTPS latency (nen la HTTPS de
#                  do duoc ca tls_handshake_ms)
TARGETS = [
    {
        "target_id": "google",
        "ping_host": "8.8.8.8",             # Google Public DNS - IP on dinh
        "dns_domain": "www.google.com",
        "http_url": "https://www.google.com",
    },
    # Vi du them 1 target thu 2 de so sanh (bo comment neu muon dung):
    # {
    #     "target_id": "cloudflare",
    #     "ping_host": "1.1.1.1",
    #     "dns_domain": "www.cloudflare.com",
    #     "http_url": "https://www.cloudflare.com",
    # },
]

PING_COUNT = 4                     # so goi ICMP gui trong 1 lan do
DNS_RESOLVER_IP = "8.8.8.8"        # resolver dung khi co dnspython, giup
                                    # tranh bi anh huong boi DNS cache cua
                                    # he dieu hanh
HTTP_TIMEOUT = 5                   # timeout (giay) cho 1 request HTTP

INTERVAL_SECONDS = 30              # khoang cach giua 2 CHU KY do (giay)
                                    # 1 chu ky = do het tat ca TARGETS
                                    # KHUYEN NGHI: 15-60s, KHONG nen < 5s

OUTPUT_CSV = r"E:\Python\Mangmaytinh (1)\network_quality_data.csv"
LOG_FILE = "collector.log"

CSV_FIELDS = [
    "timestamp",
    "target_id",
    # --- ping ---
    "rtt_ms",
    "rtt_min_ms",
    "rtt_max_ms",
    "jitter_ms",
    "n_sent",
    "n_received",
    "loss_rate",
    # --- dns ---
    "dns_latency_ms",
    # --- http (chi tiet) ---
    "tcp_connect_ms",
    "tls_handshake_ms",
    "ttfb_ms",
    "http_latency_ms",
    "http_status_code",
  ]


# ---------------------------------------------------------------------------
# THIET LAP LOGGING
# ---------------------------------------------------------------------------
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ---------------------------------------------------------------------------
# DO RTT / JITTER / LOSS BANG PING (khong can quyen root, dung lenh ping he
# thong co san tren Windows/Linux/macOS)
# ---------------------------------------------------------------------------
def measure_ping(host: str, count: int = 4) -> dict:
    """
    Tra ve dict gom:
        rtt_ms       : trung binh RTT cua cac goi nhan duoc (None neu mat het goi)
        rtt_min_ms   : RTT nho nhat trong batch (None neu mat het goi)
        rtt_max_ms   : RTT lon nhat trong batch (None neu mat het goi)
        jitter_ms    : trung binh do lech tuyet doi giua 2 lan do RTT lien
                       tiep trong CUNG 1 batch (None neu khong du >=2 goi
                       thanh cong). Day la dinh nghia jitter "intra-batch",
                       can ghi ro trong bao cao.
        n_sent       : so goi ICMP da gui
        n_received   : so goi ICMP nhan duoc phan hoi
        loss_rate    : ty le mat goi, tu 0.0 den 1.0
    """
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(count), host]
    else:  # Linux / macOS
        cmd = ["ping", "-c", str(count), host]

    empty_result = {
        "rtt_ms": None, "rtt_min_ms": None, "rtt_max_ms": None,
        "jitter_ms": None, "n_sent": count, "n_received": 0,
        "loss_rate": 1.0,
    }

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=count * 5 + 5
        )
        output = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logging.warning(f"Ping toi {host} that bai: {e}")
        return empty_result

    # Lay danh sach cac RTT tu cac dong co "time=" hoac "time<"
    rtt_values = [
        float(x) for x in re.findall(r"time[=<]\s*([\d.]+)\s*ms", output, re.IGNORECASE)
    ]

    # Lay ty le mat goi tu dong tong ket ("...% packet loss" hoac "...% loss")
    loss_match = re.search(r"([\d.]+)\s*%\s*(?:packet\s*)?loss", output, re.IGNORECASE)
    if loss_match:
        loss_rate = float(loss_match.group(1)) / 100.0
    else:
        # fallback: uoc luong tu so goi nhan duoc so voi count
        loss_rate = max(0.0, (count - len(rtt_values)) / count)

    n_received = len(rtt_values)

    if not rtt_values:
        empty_result["loss_rate"] = round(loss_rate, 4)
        return empty_result

    rtt_ms = round(statistics.mean(rtt_values), 3)
    rtt_min_ms = round(min(rtt_values), 3)
    rtt_max_ms = round(max(rtt_values), 3)

    if len(rtt_values) >= 2:
        diffs = [abs(rtt_values[i] - rtt_values[i - 1]) for i in range(1, len(rtt_values))]
        jitter_ms = round(statistics.mean(diffs), 3)
    else:
        jitter_ms = None

    return {
        "rtt_ms": rtt_ms,
        "rtt_min_ms": rtt_min_ms,
        "rtt_max_ms": rtt_max_ms,
        "jitter_ms": jitter_ms,
        "n_sent": count,
        "n_received": n_received,
        "loss_rate": round(loss_rate, 4),
    }


# ---------------------------------------------------------------------------
# DO DNS LATENCY
# ---------------------------------------------------------------------------
def measure_dns(domain: str) -> float | None:
    """
    Tra ve thoi gian phan giai ten mien (ms), hoac None neu that bai.

    Uu tien dung dnspython (truy van thang toi 1 resolver cu the, tranh bi
    anh huong boi DNS cache cua he dieu hanh). Neu khong co dnspython,
    fallback dung socket.getaddrinfo() - LUU Y: ket qua nay se bi anh huong
    boi cache DNS cua he thong, nen sau lan dau tien, cac lan do sau co the
    tra ve gia tri gan bang 0 du mang co van de hay khong. Can ghi ro han
    che nay trong bao cao neu khong cai duoc dnspython.
    """
    try:
        import dns.resolver  # thu vien ngoai: pip install dnspython

        resolver = dns.resolver.Resolver()
        resolver.nameservers = [DNS_RESOLVER_IP]
        resolver.lifetime = HTTP_TIMEOUT
        start = time.perf_counter()
        resolver.resolve(domain, "A")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return round(elapsed_ms, 3)
    except ImportError:
        try:
            start = time.perf_counter()
            socket.getaddrinfo(domain, None)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return round(elapsed_ms, 3)
        except socket.gaierror as e:
            logging.warning(f"DNS (fallback socket) that bai cho {domain}: {e}")
            return None
    except Exception as e:
        logging.warning(f"DNS (dnspython) that bai cho {domain}: {e}")
        return None


# ---------------------------------------------------------------------------
# DO HTTP LATENCY CHI TIET (TCP connect / TLS handshake / TTFB / tong)
# Dung socket + ssl THUAN, khong can thu vien 'requests'
# ---------------------------------------------------------------------------
def measure_http_detailed(url: str, timeout: int = 5) -> dict:
    """
    Do chi tiet 1 request HTTP/HTTPS bang socket thu cong.

    Cac moc thoi gian:
        t0 -> bat dau
        t1 -> sau khi TCP connect xong            => tcp_connect_ms  = t1 - t0
        t2 -> sau khi TLS handshake xong (neu co)  => tls_handshake_ms = t2 - t1
        t3 -> nhan duoc byte dau tien cua response => ttfb_ms        = t3 - t2
        t4 -> doc xong toan bo response            => http_latency_ms = t4 - t0

    Tra ve dict; cac truong co the la None neu that bai o buoc tuong ung.
    """
    empty_result = {
        "tcp_connect_ms": None,
        "tls_handshake_ms": None,
        "ttfb_ms": None,
        "http_latency_ms": None,
        "http_status_code": None,
    }

    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        logging.warning(f"URL khong hop le: {url}")
        return empty_result

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    use_tls = parsed.scheme == "https"

    sock = None
    try:
        t0 = time.perf_counter()

        # --- Buoc 1: TCP connect ---
        sock = socket.create_connection((host, port), timeout=timeout)
        t1 = time.perf_counter()
        tcp_connect_ms = (t1 - t0) * 1000

        # --- Buoc 2: TLS handshake (neu la HTTPS) ---
        conn = sock
        tls_handshake_ms = None
        if use_tls:
            ctx = ssl.create_default_context()
            conn = ctx.wrap_socket(sock, server_hostname=host)
            t2 = time.perf_counter()
            tls_handshake_ms = (t2 - t1) * 1000
        else:
            t2 = t1

        # --- Buoc 3: gui HTTP GET request ---
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: T19-collector/1.0\r\n"
            f"Accept: */*\r\n"
            f"Connection: close\r\n\r\n"
        )
        conn.sendall(request.encode("utf-8"))

        # --- Buoc 4: doi byte dau tien cua response (TTFB) ---
        conn.settimeout(timeout)
        first_chunk = conn.recv(1)
        t3 = time.perf_counter()
        ttfb_ms = (t3 - t2) * 1000

        # --- Buoc 5: doc het phan con lai (de lay status code + dong sach) ---
        rest = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                rest += chunk
                if len(rest) > 2_000_000:  # gioi han 2MB, du de lay status line
                    break
        except socket.timeout:
            pass

        t4 = time.perf_counter()
        http_latency_ms = (t4 - t0) * 1000

        # --- Lay status code tu dong dau response ---
        full_head = first_chunk + rest
        status_line = full_head.split(b"\r\n", 1)[0].decode("latin-1", errors="ignore")
        m = re.match(r"HTTP/\d\.\d\s+(\d+)", status_line)
        status_code = int(m.group(1)) if m else None

        return {
            "tcp_connect_ms": round(tcp_connect_ms, 3),
            "tls_handshake_ms": round(tls_handshake_ms, 3) if tls_handshake_ms is not None else None,
            "ttfb_ms": round(ttfb_ms, 3),
            "http_latency_ms": round(http_latency_ms, 3),
            "http_status_code": status_code,
        }

    except Exception as e:
        logging.warning(f"HTTP (chi tiet) toi {url} that bai: {e}")
        return empty_result

    finally:
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1 LAN THU THAP DAY DU CHO 1 TARGET (goi ca 3 nhom ham do o tren)
# ---------------------------------------------------------------------------
def collect_once_for_target(target: dict) -> dict:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

    ping_result = measure_ping(target["ping_host"], PING_COUNT)
    dns_latency_ms = measure_dns(target["dns_domain"])
    http_result = measure_http_detailed(target["http_url"], HTTP_TIMEOUT)

    row = {
        "timestamp": timestamp,
        "target_id": target["target_id"],
        **ping_result,
        "dns_latency_ms": dns_latency_ms,
        **http_result,
    }
    return row


def collect_once_all_targets() -> list:
    """Do lan luot tat ca cac target trong TARGETS, tra ve list cac dict."""
    rows = []
    for target in TARGETS:
        try:
            row = collect_once_for_target(target)
            rows.append(row)
        except Exception as e:
            logging.error(f"Loi khi do target '{target.get('target_id')}': {e}")
    return rows


# ---------------------------------------------------------------------------
# GHI 1 DONG VAO FILE CSV (tao file + header neu chua co)
# ---------------------------------------------------------------------------
def append_csv(row: dict, path: str = OUTPUT_CSV):
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    setup_logging()

    target_ids = ", ".join(t["target_id"] for t in TARGETS)
    logging.info(
        f"Bat dau thu thap du lieu moi {INTERVAL_SECONDS}s cho target(s): {target_ids}. "
        f"Ghi vao '{OUTPUT_CSV}'. Nhan Ctrl+C de dung."
    )
    try:
        while True:
            cycle_start = time.time()

            rows = collect_once_all_targets()
            for row in rows:
                append_csv(row)
                logging.info(f"Da ghi: {row}")

            elapsed = time.time() - cycle_start
            sleep_time = max(0, INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        logging.info("Da dung thu thap du lieu (Ctrl+C).")


if __name__ == "__main__":
    main()
