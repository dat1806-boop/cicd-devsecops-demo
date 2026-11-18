#!/usr/bin/env python3
"""Measure local WorkBoard CI, Docker build and DEV/STAGING smoke-deploy.

This tool is separate from GitHub Actions and the site's interactive release demo.
It never touches the existing cicd-lab-* containers, port 5101-5103, or SQLite volumes.
Default is dry-run. Explicit --execute is required to run commands.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CONTAINERS = {"dev": ("ci-benchmark-dev", 5201), "staging": ("ci-benchmark-staging", 5202)}
HEADERS = [
    "run", "timestamp_utc", "git_sha", "cache_mode", "tests_s", "docker_build_s",
    "deploy_dev_s", "deploy_staging_s", "total_s", "status", "image_id", "note"
]


def invoke(args: list[str], *, timeout: int, log_file: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("  >", " ".join(args))
    try:
        result = subprocess.run(
            args, cwd=PROJECT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            shell=False, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Không tìm thấy công cụ: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Lệnh quá thời gian cho phép: {args[0]}") from exc
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            "COMMAND: " + " ".join(args) + "\nEXIT: " + str(result.returncode)
            + "\n\nSTDOUT:\n" + result.stdout + "\nSTDERR:\n" + result.stderr,
            encoding="utf-8",
        )
    if result.returncode:
        # Avoid dumping arbitrary logs, which could include local file paths or secrets.
        raise RuntimeError(f"Lệnh thất bại (exit={result.returncode}): {args[0]}; xem file log")
    return result


def git_revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=PROJECT,
                              capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown-local"


def health_check(port: int, *, timeout_s: float = 40.0) -> None:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and data.get("status") == "ok":
                    return
                last = f"HTTP {resp.status}: {data!r}"
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Không đạt /health ở localhost:{port}: {last}")


def check_available(docker: str) -> None:
    # Do not overwrite or delete another container using reserved benchmark names.
    invoke([docker, "info", "--format", "{{.ServerVersion}}"], timeout=20)
    for name, port in CONTAINERS.values():
        existing = subprocess.run([docker, "container", "inspect", name],
                                  cwd=PROJECT, capture_output=True, text=True, timeout=10, check=False)
        if existing.returncode == 0:
            raise RuntimeError(f"Container '{name}' đã tồn tại, hãy tự kiểm tra trước khi đo.")
        # Windows netstat could verify ports, but bind failure is also safely caught below.
        print(f"  [sẽ dùng container {name} và cổng {port}]")


def measure_phase(name: str, fn) -> float:
    print(f"  [{name}] bắt đầu")
    start = time.perf_counter()
    fn()
    seconds = round(time.perf_counter() - start, 3)
    print(f"  [{name}] đạt: {seconds:.3f} giây")
    return seconds


def run_once(index: int, args, docker: str, log_dir: Path) -> dict:
    start = time.perf_counter()
    record = {k: "" for k in HEADERS}
    record.update(run=index, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  git_sha=git_revision(), cache_mode="pull" if args.pull else "docker-cache",
                  status="failed", note="")
    created: list[str] = []
    try:
        def test():
            invoke([sys.executable, "-m", "flake8", "app.py", "test_app.py", "--max-line-length=100"],
                   timeout=180, log_file=log_dir / f"run{index}_flake8.txt")
            invoke([sys.executable, "-m", "pytest", "-q"],
                   timeout=240, log_file=log_dir / f"run{index}_pytest.txt")
        record["tests_s"] = measure_phase("Pytest + Flake8", test)

        def build():
            cmd = [docker, "build"]
            if args.pull:
                cmd += ["--pull"]
            cmd += ["-t", "ci-benchmark:local", "."]
            invoke(cmd, timeout=1200, log_file=log_dir / f"run{index}_docker_build.txt")
        record["docker_build_s"] = measure_phase("Docker build", build)
        record["image_id"] = invoke([docker, "image", "inspect", "ci-benchmark:local",
                                     "--format", "{{.Id}}"], timeout=20).stdout.strip()

        for env, (container, port) in CONTAINERS.items():
            def deploy():
                invoke([docker, "run", "-d", "--name", container,
                        "-p", f"127.0.0.1:{port}:5000",
                        "-e", f"APP_ENV={env}", "-e", "APP_VERSION=benchmark",
                        "ci-benchmark:local"],
                       timeout=45, log_file=log_dir / f"run{index}_deploy_{env}.txt")
                created.append(container)
                health_check(port)
            record[f"deploy_{env}_s"] = measure_phase(f"Deploy {env.upper()} + /health", deploy)
        record["status"] = "success"
    except (RuntimeError, OSError) as exc:
        record["note"] = str(exc)
        print("  LỖI:", record["note"])
    finally:
        for name in reversed(created):
            subprocess.run([docker, "rm", "-f", name], cwd=PROJECT, capture_output=True,
                           text=True, timeout=30, check=False)
        record["total_s"] = round(time.perf_counter() - start, 3)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo Pytest/Flake8, Docker Build, DEV và STAGING tại máy local")
    ap.add_argument("--runs", type=int, default=3, help="Số lần đo, mặc định 3")
    ap.add_argument("--execute", action="store_true", help="Chạy thật; mặc định chỉ xem kế hoạch")
    ap.add_argument("--pull", action="store_true", help="Bật docker build --pull, có thể chậm do mạng")
    ap.add_argument("--output", default="KET_QUA_DO", help="Thư mục xuất CSV/JSON và log")
    args = ap.parse_args()
    if args.runs < 1 or args.runs > 10:
        ap.error("--runs phải nằm trong khoảng 1..10")
    output = PROJECT / args.output
    if not (PROJECT / "app.py").is_file() or not (PROJECT / "Dockerfile").is_file():
        ap.error("Hãy đặt thư mục tools/ ngay trong project có app.py và Dockerfile")
    print("DỰ ÁN:", PROJECT)
    print("GHI CHÚ: Chỉ thao tác benchmark containers 5201/5202; KHÔNG đụng Production 5103.")
    print("Không đo chi phí hoặc GitHub Actions; các kết quả sau đây là thời gian LOCAL thực đo.")
    print("KẾ HOẠCH: mỗi lượt chạy Flake8 + Pytest -> docker build -> DEV /health -> STAGING /health")
    if not args.execute:
        print("ĐANG XEM TRƯỚC. Để chạy thật, thêm --execute. Không có container nào được tạo.")
        return 0
    docker = shutil.which("docker")
    if not docker:
        print("Không thấy Docker CLI. Mở Docker Desktop và kiểm tra PATH trước.")
        return 2
    try:
        check_available(docker)
    except (RuntimeError, OSError) as exc:
        print("Không sẵn sàng:", exc)
        return 2
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for i in range(1, args.runs + 1):
        print(f"\n=== LƯỢT {i}/{args.runs} ===")
        row = run_once(i, args, docker, output / "logs")
        records.append(row)
        with (output / "ket_qua_do_local.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(records)
        (output / "ket_qua_do_local.json").write_text(
            json.dumps({"metadata": {"project": str(PROJECT), "scope": "local Docker benchmark",
                                     "only_ports": [5201, 5202], "method": "perf_counter",
                                     "note": "total_s gồm thời gian setup/inspect/cleanup ngoài các phase"},
                        "runs": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        if row["status"] != "success":
            print("Dừng các lượt còn lại vì có lỗi. Dữ liệu đã đo vẫn được lưu.")
            break
    valid = [r for r in records if r["status"] == "success"]
    if valid:
        avg = {k: round(sum(float(r[k]) for r in valid) / len(valid), 3)
               for k in ("tests_s", "docker_build_s", "deploy_dev_s", "deploy_staging_s", "total_s")}
        (output / "trung_binh.json").write_text(
            json.dumps({"successful_runs": len(valid), "averages_seconds": avg}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("\nTRUNG BÌNH CÁC LƯỢT THÀNH CÔNG:", avg)
    print("Tệp kết quả:", output / "ket_qua_do_local.csv")
    return 0 if len(valid) == args.runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
