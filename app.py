"""Interactive CI/CD teaching application.

The WorkBoard pages are a real Flask application with SQLite-backed CRUD.
The local release lab can run pytest/flake8, build a Docker image and start
separate DEV/STAGING/PRODUCTION containers on the host machine.
GitHub Actions dispatch is optional and requires a server-side token in .env.
"""

from __future__ import annotations

import json
import os
import ipaddress
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, current_app, g, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
REPOSITORY_DEFAULT = "dat1806-boop/cicd-devsecops-demo"
IMAGE_NAME = "cicd-lab:demo"
ENVIRONMENTS = {
    "dev": {"port": 5101, "container": "cicd-lab-dev"},
    "staging": {"port": 5102, "container": "cicd-lab-staging"},
    "production": {"port": 5103, "container": "cicd-lab-production"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL
)
"""

STATE_LOCK = threading.Lock()
DEMO_STATE = {
    "tests": {"status": "not_run", "message": "Chưa chạy kiểm thử."},
    "build": {"status": "not_run", "message": "Chưa build Docker image."},
    "image": None,
    "environments": {
        name: {"status": "not_deployed", "url": None, "image_id": None}
        for name in ENVIRONMENTS
    },
    "production_approved": False,
    "release": None,
    "last_updated": None,
}


def read_env_file() -> None:
    """Load simple KEY=VALUE entries from .env without adding a dependency."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db_path = Path(current_app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript(SCHEMA)
    count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count == 0 and not current_app.config.get("TESTING"):
        now = utc_now()
        connection.executemany(
            "INSERT INTO tasks(title, description, status, priority, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "Hoàn thiện giao diện trang chủ",
                    "Xây dựng khu vực giới thiệu và danh sách công việc.",
                    "done",
                    "high",
                    now,
                ),
                (
                    "Viết kiểm thử API",
                    "Kiểm tra tạo, cập nhật và xóa công việc bằng pytest.",
                    "pending",
                    "high",
                    now,
                ),
                (
                    "Đóng gói ứng dụng bằng Docker",
                    "Build image và triển khai qua các môi trường.",
                    "pending",
                    "normal",
                    now,
                ),
            ],
        )
    connection.commit()
    connection.close()


def get_environment() -> str:
    value = os.getenv("APP_ENV", "local").lower()
    return value if value in {"local", "dev", "staging", "production"} else "local"


def get_version_info() -> dict[str, str]:
    return {
        "environment": get_environment(),
        "version": os.getenv("APP_VERSION", "1.0.0-demo"),
        "commit": os.getenv("GIT_COMMIT", "local-build"),
    }


def local_controls_allowed() -> bool:
    return get_environment() == "local"


def tail_output(value: str, limit: int = 9000) -> str:
    value = value.strip()
    return value[-limit:] if len(value) > limit else value


def run_command(command: list[str], timeout: int = 240) -> dict[str, object]:
    """Run a fixed, server-defined command; never accepts shell input from users."""
    try:
        completed = subprocess.run(
            command,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        return {
            "command": " ".join(command),
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "output": tail_output(output or "Lệnh hoàn tất, không có log."),
        }
    except FileNotFoundError:
        current_app.logger.exception("Không tìm thấy công cụ khi chạy tác vụ CI/CD.")
        return {
            "command": " ".join(command),
            "exit_code": 127,
            "success": False,
            "output": "Không tìm thấy công cụ cần thiết. Hãy kiểm tra cài đặt rồi thử lại.",
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(command),
            "exit_code": 124,
            "success": False,
            "output": f"Lệnh vượt quá thời gian chờ {timeout} giây.",
        }


def docker_available() -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, (
            "Không tìm thấy Docker CLI. Hãy cài/mở Docker Desktop rồi thử lại."
        )
    info = run_command([docker, "info"], timeout=30)
    if not info["success"]:
        return False, (
            "Docker CLI đã có nhưng Docker Engine chưa sẵn sàng. "
            "Mở Docker Desktop."
        )
    return True, docker


def read_github_setting(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def github_request(path: str, token: str | None = None) -> dict[str, object]:
    repo = read_github_setting("GITHUB_REPOSITORY", REPOSITORY_DEFAULT)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GITHUB_REPOSITORY không hợp lệ.")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CI-CD-Lab-Demo",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"https://api.github.com/repos/{repo}/{path}", headers=headers)
    with urlopen(req, timeout=15) as response:  # nosec B310: host is fixed to api.github.com
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {"ok": True}


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    read_env_file()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or os.urandom(32),
        DATABASE=os.getenv("DATABASE_PATH", str(BASE_DIR / "instance" / "tasks.sqlite")),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    @app.context_processor
    def inject_version() -> dict[str, object]:
        return {"version_info": get_version_info()}

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/lab")
    def lab():
        if not local_controls_allowed():
            return render_template("not_local.html"), 403
        return render_template("lab.html", github_ready=bool(read_github_setting("GITHUB_TOKEN")))

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api")
    def api_home():
        return jsonify(message="Hello CI/CD", env=get_environment())

    @app.get("/api/info")
    def info():
        return jsonify(get_version_info())

    @app.get("/api/tasks")
    def list_tasks():
        rows = get_db().execute(
            "SELECT id, title, description, status, priority, created_at "
            "FROM tasks ORDER BY id DESC"
        ).fetchall()
        return jsonify(tasks=[dict(row) for row in rows])

    @app.post("/api/tasks")
    def create_task():
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        priority = str(data.get("priority", "normal")).lower()
        if not title or len(title) > 100:
            return jsonify(error="Tên công việc phải có từ 1 đến 100 ký tự."), 400
        if len(description) > 500:
            return jsonify(error="Mô tả không được vượt quá 500 ký tự."), 400
        if priority not in {"low", "normal", "high"}:
            return jsonify(error="Mức ưu tiên không hợp lệ."), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO tasks(title, description, status, priority, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (title, description, priority, utc_now()),
        )
        db.commit()
        row = db.execute(
            "SELECT id, title, description, status, priority, created_at "
            "FROM tasks WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(task=dict(row), message="Đã tạo công việc."), 201

    @app.patch("/api/tasks/<int:task_id>")
    def update_task(task_id: int):
        data = request.get_json(silent=True) or {}
        allowed = {"title", "description", "status", "priority"}
        if not data or not set(data).issubset(allowed):
            return jsonify(error="Dữ liệu cập nhật không hợp lệ."), 400
        db = get_db()
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return jsonify(error="Không tìm thấy công việc."), 404
        values = {
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "priority": row["priority"],
        }
        values.update(data)
        values = {key: str(value).strip() for key, value in values.items()}
        if not values["title"] or len(values["title"]) > 100:
            return jsonify(error="Tên công việc phải có từ 1 đến 100 ký tự."), 400
        if len(values["description"]) > 500:
            return jsonify(error="Mô tả không được vượt quá 500 ký tự."), 400
        if values["status"] not in {"pending", "done"}:
            return jsonify(error="Trạng thái không hợp lệ."), 400
        if values["priority"] not in {"low", "normal", "high"}:
            return jsonify(error="Mức ưu tiên không hợp lệ."), 400
        db.execute(
            "UPDATE tasks SET title=?, description=?, status=?, priority=? WHERE id=?",
            (
                values["title"],
                values["description"],
                values["status"],
                values["priority"],
                task_id,
            ),
        )
        db.commit()
        updated = db.execute(
            "SELECT id, title, description, status, priority, created_at "
            "FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        return jsonify(task=dict(updated), message="Đã cập nhật công việc.")

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id: int):
        db = get_db()
        cursor = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify(error="Không tìm thấy công việc."), 404
        return jsonify(message="Đã xóa công việc.")

    @app.get("/api/lab/status")
    def lab_status():
        if not local_controls_allowed():
            return jsonify(error="Phòng CI/CD chỉ hoạt động ở chế độ LOCAL."), 403
        with STATE_LOCK:
            return jsonify(DEMO_STATE)

    @app.post("/api/lab/tests")
    def run_tests():
        if not local_controls_allowed():
            return jsonify(error="Thao tác chỉ được phép ở chế độ LOCAL."), 403
        commands = [
            run_command(
                [
                    sys.executable,
                    "-m",
                    "flake8",
                    "app.py",
                    "test_app.py",
                    "--max-line-length=100",
                ],
                timeout=120,
            ),
            run_command([sys.executable, "-m", "pytest", "-q"], timeout=180),
        ]
        success = all(bool(item["success"]) for item in commands)
        with STATE_LOCK:
            DEMO_STATE["tests"] = {
                "status": "success" if success else "failure",
                "message": (
                    "Tất cả kiểm tra local đã đạt."
                    if success
                    else "Có bước kiểm tra thất bại."
                ),
                "commands": commands,
                "updated_at": utc_now(),
            }
            DEMO_STATE["build"] = {
                "status": "not_run",
                "message": "Cần chạy kiểm thử lại trước khi build.",
            }
            DEMO_STATE["image"] = None
            DEMO_STATE["production_approved"] = False
            DEMO_STATE["release"] = None
            for name in ENVIRONMENTS:
                DEMO_STATE["environments"][name] = {
                    "status": "not_deployed",
                    "url": None,
                    "image_id": None,
                }
            DEMO_STATE["last_updated"] = utc_now()
        return jsonify(success=success, tests=commands, state=DEMO_STATE), (200 if success else 422)

    @app.post("/api/lab/build")
    def build_image():
        if not local_controls_allowed():
            return jsonify(error="Thao tác chỉ được phép ở chế độ LOCAL."), 403
        with STATE_LOCK:
            if DEMO_STATE["tests"]["status"] != "success":
                return jsonify(
                    error="Hãy chạy và đạt kiểm thử trước khi build Docker."
                ), 409
        available, docker = docker_available()
        if not available:
            with STATE_LOCK:
                DEMO_STATE["build"] = {"status": "failure", "message": docker}
            return jsonify(error=docker), 503
        build = run_command([docker, "build", "-t", IMAGE_NAME, "."], timeout=600)
        image_id = None
        if build["success"]:
            inspect = run_command(
                [docker, "image", "inspect", IMAGE_NAME, "--format", "{{.Id}}"],
                timeout=30,
            )
            if inspect["success"]:
                image_id = str(inspect["output"]).strip().splitlines()[-1]
        success = bool(build["success"] and image_id)
        with STATE_LOCK:
            DEMO_STATE["build"] = {
                "status": "success" if success else "failure",
                "message": (
                    "Docker image đã được build."
                    if success
                    else "Docker build thất bại."
                ),
                "command": build,
                "image_id": image_id,
                "updated_at": utc_now(),
            }
            DEMO_STATE["image"] = {"tag": IMAGE_NAME, "id": image_id} if success else None
            DEMO_STATE["production_approved"] = False
            for name in ENVIRONMENTS:
                DEMO_STATE["environments"][name] = {
                    "status": "not_deployed",
                    "url": None,
                    "image_id": None,
                }
            DEMO_STATE["last_updated"] = utc_now()
        return jsonify(success=success, build=build, image=DEMO_STATE["image"]), (
            200 if success else 422
        )

    def deploy_environment(name: str) -> tuple[dict[str, object], int]:
        if not local_controls_allowed():
            return {"error": "Thao tác chỉ được phép ở chế độ LOCAL."}, 403
        with STATE_LOCK:
            if not DEMO_STATE["image"]:
                return {"error": "Hãy build Docker image thành công trước."}, 409
            if name == "staging" and DEMO_STATE["environments"]["dev"]["status"] != "success":
                return {"error": "Hãy triển khai DEV thành công trước STAGING."}, 409
            if name == "production":
                if DEMO_STATE["environments"]["staging"]["status"] != "success":
                    return {"error": "Hãy triển khai STAGING thành công trước."}, 409
                if not DEMO_STATE["production_approved"]:
                    return {"error": "Production đang chờ bạn phê duyệt."}, 409
        available, docker = docker_available()
        if not available:
            return {"error": docker}, 503
        spec = ENVIRONMENTS[name]
        container_name = spec["container"]
        port = spec["port"]
        run_command([docker, "rm", "-f", container_name], timeout=20)
        launch = run_command(
            [
                docker,
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{port}:5000",
                "-e",
                f"APP_ENV={name}",
                "-e",
                f"APP_VERSION={DEMO_STATE.get('release', {}).get('version', '1.0.0-demo')}",
                "-e",
                f"GIT_COMMIT={os.getenv('GIT_COMMIT', 'local-demo')}",
                str(DEMO_STATE["image"].get("tag", IMAGE_NAME)),
            ],
            timeout=60,
        )
        if not launch["success"]:
            return {"error": "Không khởi chạy được container.", "details": launch}, 422
        url = f"http://127.0.0.1:{port}"
        healthy = False
        health_error = "Hết thời gian chờ health check."
        for _attempt in range(20):
            try:
                health_url = f"{url}/health"
                with urlopen(health_url, timeout=2) as response:  # nosec B310
                    payload = json.loads(response.read().decode("utf-8"))
                    if response.status == 200 and payload.get("status") == "ok":
                        healthy = True
                        break
                    health_error = (
                        "Health endpoint trả về trạng thái không hợp lệ: "
                        f"{payload}"
                    )
            except (OSError, ValueError, HTTPError):
                current_app.logger.exception("Health check của container thất bại.")
                health_error = "Không thể kiểm tra trạng thái container."
            time.sleep(1)
        if not healthy:
            logs = run_command([docker, "logs", container_name], timeout=20)
            cleanup = run_command([docker, "rm", "-f", container_name], timeout=20)
            return {
                "error": (
                    "Container đã chạy nhưng health check chưa đạt; "
                    "đã thu log và dọn container lỗi."
                ),
                "details": launch,
                "health_error": health_error,
                "container_logs": logs.get("output", "Không lấy được log."),
                "cleanup": cleanup,
            }, 422
        image_id = str(DEMO_STATE["image"]["id"])
        with STATE_LOCK:
            DEMO_STATE["environments"][name] = {
                "status": "success",
                "url": url,
                "image_id": image_id,
                "container": container_name,
                "port": port,
                "updated_at": utc_now(),
            }
            DEMO_STATE["last_updated"] = utc_now()
        return {
            "success": True,
            "environment": name,
            "url": url,
            "image_id": image_id,
            "message": f"Container {name.upper()} đã chạy và health check đạt.",
        }, 200

    @app.post("/api/lab/release/start")
    def start_release():
        """Run real local tests, build a versioned image, then deploy DEV and STAGING."""
        if not local_controls_allowed():
            return jsonify(error="Tạo phiên bản chỉ được phép ở chế độ LOCAL."), 403
        payload = request.get_json(silent=True) or {}
        version = str(payload.get("version", "")).strip()
        description = str(payload.get("description", "")).strip()
        # Bound input length and each numeric component to avoid regex backtracking
        # and prevent user input from becoming part of an operating-system command.
        valid_version = re.fullmatch(
            r"v?[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", version
        )
        if len(version) > 13 or not valid_version:
            return jsonify(
                error="Phiên bản phải theo dạng v1.2.3 hoặc 1.2.3 "
                "(mỗi nhóm tối đa 3 chữ số)."
            ), 400
        if not description or len(description) > 240:
            return jsonify(error="Hãy nhập mô tả thay đổi (tối đa 240 ký tự)."), 400
        version = version if version.startswith("v") else f"v{version}"
        # Use a fixed image tag for Docker commands. The user-supplied version
        # remains release metadata and never reaches subprocess arguments.
        image_tag = IMAGE_NAME
        with STATE_LOCK:
            if (DEMO_STATE.get("release") or {}).get("status") == "running":
                return jsonify(error="Đang có phiên phát hành chạy."), 409
            DEMO_STATE["release"] = {
                "version": version, "description": description,
                "status": "running", "started_at": utc_now(),
            }
            DEMO_STATE["production_approved"] = False

        commands = [
            run_command(
                [
                    sys.executable, "-m", "flake8", "app.py", "test_app.py",
                    "--max-line-length=100",
                ],
                timeout=120,
            ),
            run_command([sys.executable, "-m", "pytest", "-q"], timeout=180),
        ]
        tests_ok = all(bool(item["success"]) for item in commands)
        with STATE_LOCK:
            DEMO_STATE["tests"] = {
                "status": "success" if tests_ok else "failure",
                "message": (
                    "Kiểm thử phiên bản mới đã đạt."
                    if tests_ok
                    else "Kiểm thử thất bại; dừng phát hành."
                ),
                "commands": commands, "updated_at": utc_now(),
            }
        if not tests_ok:
            with STATE_LOCK:
                DEMO_STATE["release"].update(status="failed", message="CI test thất bại.")
            return jsonify(
                success=False,
                error="Kiểm thử thất bại. Không build hoặc deploy phiên bản này.",
                tests=commands,
            ), 422

        available, docker = docker_available()
        if not available:
            with STATE_LOCK:
                DEMO_STATE["release"].update(status="failed", message=docker)
            return jsonify(success=False, error=docker, tests=commands), 503

        build = run_command([docker, "build", "-t", image_tag, "."], timeout=600)
        inspect = (
            run_command(
                [docker, "image", "inspect", image_tag, "--format", "{{.Id}}"],
                timeout=30,
            )
            if build["success"]
            else {"success": False, "output": "Build không thành công."}
        )
        image_id = (
            str(inspect.get("output", "")).strip().splitlines()[-1]
            if inspect.get("success")
            else None
        )
        if not build["success"] or not image_id:
            with STATE_LOCK:
                DEMO_STATE["build"] = {
                    "status": "failure",
                    "message": "Docker build phiên bản mới thất bại.",
                    "command": build,
                }
                DEMO_STATE["release"].update(status="failed", message="Docker build thất bại.")
            return jsonify(success=False, error="Docker build thất bại.", build=build), 422

        with STATE_LOCK:
            DEMO_STATE["image"] = {"tag": image_tag, "id": image_id}
            DEMO_STATE["build"] = {
                "status": "success",
                "message": f"Đã build {image_tag}.",
                "image_id": image_id,
                "command": build,
                "updated_at": utc_now(),
            }
            for env_name, spec in ENVIRONMENTS.items():
                run_command([docker, "rm", "-f", spec["container"]], timeout=20)
                DEMO_STATE["environments"][env_name] = {
                    "status": "not_deployed", "url": None, "image_id": None
                }

        dev_result, dev_code = deploy_environment("dev")
        if dev_code != 200:
            with STATE_LOCK:
                DEMO_STATE["release"].update(status="failed", message="Triển khai DEV thất bại.")
            return jsonify(
                success=False,
                error="Build đạt nhưng triển khai DEV thất bại.",
                details=dev_result,
            ), 422
        staging_result, staging_code = deploy_environment("staging")
        if staging_code != 200:
            with STATE_LOCK:
                DEMO_STATE["release"].update(
                    status="failed", message="Triển khai STAGING thất bại."
                )
            return jsonify(
                success=False,
                error="DEV đạt nhưng triển khai STAGING thất bại.",
                details=staging_result,
            ), 422
        with STATE_LOCK:
            DEMO_STATE["release"].update(
                status="awaiting_approval",
                message=(
                    "Test, build, DEV và STAGING đã đạt; "
                    "đang chờ phê duyệt Production."
                ),
                image_tag=image_tag,
                image_id=image_id,
                completed_at=utc_now(),
            )
        return jsonify(
            success=True,
            release=DEMO_STATE["release"],
            tests=commands,
            build=build,
            dev=dev_result,
            staging=staging_result,
            image=DEMO_STATE["image"],
        )

    @app.post("/api/lab/deploy/<name>")
    def deploy(name: str):
        if name not in ENVIRONMENTS:
            return jsonify(error="Môi trường không hợp lệ."), 404
        payload, status_code = deploy_environment(name)
        if name == "production" and status_code == 200:
            with STATE_LOCK:
                if DEMO_STATE.get("release"):
                    DEMO_STATE["release"].update(status="released", released_at=utc_now())
        return jsonify(payload), status_code

    @app.post("/api/lab/reset")
    def reset_lab():
        if not local_controls_allowed():
            return jsonify(error="Thao tác chỉ được phép ở chế độ LOCAL."), 403
        available, docker = docker_available()
        if available:
            for spec in ENVIRONMENTS.values():
                run_command([docker, "rm", "-f", spec["container"]], timeout=20)
        with STATE_LOCK:
            DEMO_STATE["tests"] = {"status": "not_run", "message": "Chưa chạy kiểm thử."}
            DEMO_STATE["build"] = {"status": "not_run", "message": "Chưa build Docker image."}
            DEMO_STATE["image"] = None
            DEMO_STATE["production_approved"] = False
            DEMO_STATE["release"] = None
            for name in ENVIRONMENTS:
                DEMO_STATE["environments"][name] = {
                    "status": "not_deployed", "url": None, "image_id": None
                }
            DEMO_STATE["last_updated"] = utc_now()
        return jsonify(success=True, message="Đã đặt lại trạng thái phòng CI/CD.")

    @app.post("/api/lab/approve-production")
    def approve_production():
        if not local_controls_allowed():
            return jsonify(error="Thao tác chỉ được phép ở chế độ LOCAL."), 403
        with STATE_LOCK:
            if DEMO_STATE["environments"]["staging"]["status"] != "success":
                return jsonify(
                    error="Chỉ có thể phê duyệt sau khi STAGING thành công."
                ), 409
            DEMO_STATE["production_approved"] = True
            if DEMO_STATE.get("release"):
                DEMO_STATE["release"].update(status="approved", approved_at=utc_now())
            DEMO_STATE["last_updated"] = utc_now()
        return jsonify(success=True, message="Bạn đã phê duyệt triển khai PRODUCTION.")

    @app.get("/api/github/runs")
    def github_runs():
        token = read_github_setting("GITHUB_TOKEN") or None
        try:
            data = github_request("actions/runs?per_page=8", token=token)
            runs = data.get("workflow_runs", [])
            return jsonify(runs=runs, source="GitHub Actions API")
        except (HTTPError, URLError, TimeoutError, ValueError):
            current_app.logger.exception("Không tải được lịch sử GitHub Actions.")
            return jsonify(
                error="Không tải được lịch sử GitHub Actions. Vui lòng thử lại sau."
            ), 502

    @app.post("/api/github/dispatch")
    def github_dispatch():
        # This endpoint uses a privileged server-side GitHub token. Accept only
        # same-origin JSON requests from the local demo to block cross-site form posts.
        allowed_hosts = {"127.0.0.1:5000", "localhost:5000"}
        origin = request.headers.get("Origin", "").rstrip("/")
        expected_origin = request.host_url.rstrip("/")
        try:
            is_loopback = ipaddress.ip_address(request.remote_addr or "").is_loopback
        except ValueError:
            is_loopback = False
        if (
            not request.is_json
            or request.host not in allowed_hosts
            or not is_loopback
            or not origin
            or origin != expected_origin
        ):
            return jsonify(
                error=(
                    "Yêu cầu không hợp lệ. Chỉ chấp nhận JSON cùng nguồn "
                    "từ website chạy local."
                )
            ), 403

        token = read_github_setting("GITHUB_TOKEN")
        if not token:
            return jsonify(
                error=(
                    "Chưa cấu hình GITHUB_TOKEN. Tạo token có quyền Actions: write, "
                    "đặt trong file .env rồi khởi động lại website."
                )
            ), 409
        data = request.get_json(silent=True) or {}
        branch = str(data.get("branch", "main"))
        if branch not in {"main", "develop"}:
            return jsonify(error="Chỉ được chọn nhánh main hoặc develop."), 400
        workflow = read_github_setting("GITHUB_WORKFLOW_FILE", "pipeline.yml")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", workflow):
            return jsonify(error="Tên workflow không hợp lệ."), 400
        repo = read_github_setting("GITHUB_REPOSITORY", REPOSITORY_DEFAULT)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            return jsonify(error="GITHUB_REPOSITORY không hợp lệ."), 400
        body = json.dumps({"ref": branch}).encode("utf-8")
        req = Request(
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "CI-CD-Lab-Demo",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=20) as response:  # nosec B310
                return jsonify(
                    success=response.status == 204,
                    message=f"Đã gửi yêu cầu chạy workflow trên nhánh {branch}.",
                    branch=branch,
                    repository=repo,
                )
        except HTTPError as exc:
            current_app.logger.exception("GitHub từ chối yêu cầu dispatch workflow.")
            return jsonify(
                error=(
                    "GitHub từ chối yêu cầu chạy workflow. "
                    "Hãy kiểm tra token và quyền Actions."
                )
            ), exc.code
        except URLError:
            current_app.logger.exception("Không kết nối được GitHub khi dispatch workflow.")
            return jsonify(error="Không kết nối được GitHub. Vui lòng thử lại sau."), 502

    @app.get("/api/lab/scenario/<name>")
    def scenario(name: str):
        examples = {
            "test": {
                "title": "Unit Test thất bại",
                "tool": "pytest",
                "result": "1 failed, 1 passed",
                "detail": "AssertionError: Hello CI/CD khác Hello WRONG.",
                "effect": (
                    "Job test đỏ; build và deploy bị bỏ qua; "
                    "Pull Request không đủ điều kiện merge."
                ),
                "source": "Kịch bản thực nghiệm trong báo cáo, Hình 2.18–2.19.",
            },
            "secret": {
                "title": "Phát hiện secret giả",
                "tool": "Gitleaks",
                "result": "leaks found: 1",
                "detail": "Luật generic-api-key phát hiện chuỗi trong settings_demo.py.",
                "effect": "Job secret-scan thất bại và Pull Request bị chặn.",
                "source": "Kịch bản thực nghiệm trong báo cáo, Hình 2.26–2.27.",
            },
            "sca": {
                "title": "Thư viện có lỗ hổng",
                "tool": "pip-audit",
                "result": "Flask 3.1.2 — PYSEC-2026-2151",
                "detail": (
                    "Phiên bản được báo cáo là có lỗ hổng; "
                    "bản vá ghi nhận là Flask 3.1.3."
                ),
                "effect": "Job sca thất bại; build và deploy không được tiếp tục.",
                "source": "Kịch bản thực nghiệm trong báo cáo, Hình 2.28–2.30.",
            },
        }
        if name not in examples:
            return jsonify(error="Kịch bản không tồn tại."), 404
        return jsonify(
            mode="illustration",
            warning=(
                "Đây là minh họa theo kết quả báo cáo, "
                "không chạy scanner thật."
            ),
            **examples[name],
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
