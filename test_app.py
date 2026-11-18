import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite"),
            "SECRET_KEY": "test-key",
        }
    )
    with app.test_client() as test_client:
        yield test_client


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"WorkBoard" in response.data
    assert b"Danh s\xc3\xa1ch c\xc3\xb4ng vi\xe1\xbb\x87c" in response.data


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_info_endpoint(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.get_json()
    assert data["environment"] in {"local", "dev", "staging", "production"}
    assert "version" in data
    assert "commit" in data


def test_create_task(client):
    response = client.post(
        "/api/tasks",
        json={
            "title": "Kiểm thử tự động",
            "description": "Viết unit test cho API.",
            "priority": "high",
        },
    )
    assert response.status_code == 201
    task = response.get_json()["task"]
    assert task["title"] == "Kiểm thử tự động"
    assert task["status"] == "pending"
    assert task["priority"] == "high"


def test_create_task_requires_title(client):
    response = client.post("/api/tasks", json={"title": "  "})
    assert response.status_code == 400


def test_update_task_status(client):
    created = client.post("/api/tasks", json={"title": "Tạo Docker image"})
    task_id = created.get_json()["task"]["id"]
    response = client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
    assert response.status_code == 200
    assert response.get_json()["task"]["status"] == "done"


def test_update_task_rejects_invalid_status(client):
    created = client.post("/api/tasks", json={"title": "Task"})
    task_id = created.get_json()["task"]["id"]
    response = client.patch(f"/api/tasks/{task_id}", json={"status": "unknown"})
    assert response.status_code == 400


def test_delete_task(client):
    created = client.post("/api/tasks", json={"title": "Task sẽ xóa"})
    task_id = created.get_json()["task"]["id"]
    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    tasks = client.get("/api/tasks").get_json()["tasks"]
    assert all(task["id"] != task_id for task in tasks)


def test_dashboard_lab_is_available_in_local(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "local")
    app = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "local.sqlite")}
    )
    with app.test_client() as test_client:
        response = test_client.get("/lab")
        assert response.status_code == 200
        assert b"LOCAL RELEASE LAB" in response.data


def test_lab_is_disabled_in_deployed_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "staging")
    app = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "staging.sqlite")}
    )
    with app.test_client() as test_client:
        response = test_client.get("/lab")
        assert response.status_code == 403


def test_github_dispatch_rejects_cross_origin_request(client, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    response = client.post(
        "/api/github/dispatch",
        base_url="http://127.0.0.1:5000",
        headers={"Origin": "https://attacker.example"},
        json={"branch": "main"},
    )
    assert response.status_code == 403


def test_github_dispatch_requires_same_origin_json(client, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    response = client.post(
        "/api/github/dispatch",
        base_url="http://localhost:5000",
        headers={"Origin": "http://localhost:5000"},
        json={"branch": "main"},
    )
    # Request passes local-origin validation and then stops because no token is configured.
    assert response.status_code == 409


def test_new_release_rejects_invalid_version(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    response = client.post(
        "/api/lab/release/start",
        json={"version": "latest", "description": "Cải tiến giao diện"},
    )
    assert response.status_code == 400
    assert "v1.2.3" in response.get_json()["error"]


def test_new_release_requires_description(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    response = client.post(
        "/api/lab/release/start",
        json={"version": "v1.0.1", "description": " "},
    )
    assert response.status_code == 400
    assert "mô tả" in response.get_json()["error"]


def test_upgrade_preset_is_fixed(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    response = client.post(
        "/api/lab/release/start",
        json={"version": "v1.2.0", "description": "Thử phiên bản không có sẵn"},
    )
    assert response.status_code == 400
    assert "v1.1.0" in response.get_json()["error"]


def test_baseline_endpoint_disabled_in_staging(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "staging")
    app = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "stage-baseline.sqlite")}
    )
    with app.test_client() as test_client:
        response = test_client.post("/api/lab/baseline", json={})
        assert response.status_code == 403


def test_feature_flag_controls_new_statistics(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("APP_VERSION", "v1.1.0")
    monkeypatch.setenv("WORKBOARD_FEATURE_SET", "insights")
    app = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "insights.sqlite")}
    )
    with app.test_client() as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        # Check the actual feature container, not explanatory page copy.
        assert 'id="release-insights"' in response.get_data(as_text=True)
        info = test_client.get("/api/info").get_json()
        assert info["version"] == "v1.1.0"
        assert info["features"] == "insights"
    monkeypatch.setenv("APP_VERSION", "v1.0.0")
    monkeypatch.setenv("WORKBOARD_FEATURE_SET", "basic")
    with app.test_client() as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        assert 'id="release-insights"' not in response.get_data(as_text=True)
        info = test_client.get("/api/info").get_json()
        assert info["features"] == "basic"


def test_baseline_remains_until_release_is_approved(monkeypatch, tmp_path):
    """Mock Docker calls to verify the gating logic without Docker in CI."""
    import copy
    import json
    import app as workboard

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setattr(workboard, "docker_available", lambda: (True, "docker"))
    calls = []

    def fake_command(command, timeout=240):
        calls.append(command)
        output = (
            "sha256:baseline" if "cicd-lab:v1.0.0" in command
            else "sha256:upgrade"
        ) if "inspect" in command else "Hoàn thành"
        return {"success": True, "exit_code": 0, "output": output,
                "command": " ".join(command)}

    class HealthyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"status": "ok"}).encode()

    monkeypatch.setattr(workboard, "run_command", fake_command)
    monkeypatch.setattr(workboard, "urlopen", lambda *_args, **_kw: HealthyResponse())
    previous = copy.deepcopy(workboard.DEMO_STATE)
    app = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "release-gates.sqlite")}
    )
    try:
        with app.test_client() as test_client:
            baseline = test_client.post("/api/lab/baseline", json={})
            assert baseline.status_code == 200
            assert baseline.get_json()["production"]["version"] == "v1.0.0"

            upgraded = test_client.post(
                "/api/lab/release/start",
                json={"version": "v1.1.0", "description": "Thống kê mới"},
            )
            assert upgraded.status_code == 200
            result = upgraded.get_json()
            assert result["dev"]["version"] == "v1.1.0"
            assert result["staging"]["version"] == "v1.1.0"
            status = test_client.get("/api/lab/status").get_json()
            assert status["environments"]["production"]["version"] == "v1.0.0"
            assert status["release"]["status"] == "awaiting_approval"

            # The old Production cannot be promoted without approval.
            runs_before_approval = [
                cmd for cmd in calls if cmd[:2] == ["docker", "run"]
                and "cicd-lab-production" in cmd
            ]
            assert len(runs_before_approval) == 1
            assert runs_before_approval[0][-1] == "cicd-lab:v1.0.0"
            denied = test_client.post("/api/lab/deploy/production", json={})
            assert denied.status_code == 409
            assert test_client.post("/api/lab/approve-production", json={}).status_code == 200
            promoted = test_client.post("/api/lab/deploy/production", json={})
            assert promoted.status_code == 200
            assert promoted.get_json()["version"] == "v1.1.0"
            production_runs = [
                cmd for cmd in calls if cmd[:2] == ["docker", "run"]
                and "cicd-lab-production" in cmd
            ]
            assert len(production_runs) == 2
            assert production_runs[-1][-1] == "cicd-lab:v1.1.0"
            assert "cicd-lab-production-data:/app/instance" in production_runs[-1]
            assert any("WORKBOARD_FEATURE_SET=insights" in c for c in calls)
    finally:
        workboard.DEMO_STATE.clear()
        workboard.DEMO_STATE.update(previous)


def test_upgraded_release_requires_old_production(client, monkeypatch):
    import copy
    import app as workboard

    monkeypatch.setenv("APP_ENV", "local")
    old_state = copy.deepcopy(workboard.DEMO_STATE)
    try:
        workboard.DEMO_STATE["baseline"] = {"status": "not_deployed"}
        workboard.DEMO_STATE["environments"]["production"] = {
            "status": "not_deployed", "url": None, "image_id": None
        }
        response = client.post(
            "/api/lab/release/start",
            json={"version": "v1.1.0", "description": "Thống kê"},
        )
        assert response.status_code == 409
        assert "Chuẩn bị website cũ" in response.get_json()["error"]
    finally:
        workboard.DEMO_STATE.clear()
        workboard.DEMO_STATE.update(old_state)


def test_reset_does_not_delete_workboard_volumes(client, monkeypatch):
    import copy
    import app as workboard

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setattr(workboard, "docker_available", lambda: (True, "docker"))
    commands = []

    def fake_command(command, timeout=240):
        commands.append(command)
        return {"success": True, "exit_code": 0, "output": "ok"}

    monkeypatch.setattr(workboard, "run_command", fake_command)
    previous = copy.deepcopy(workboard.DEMO_STATE)
    try:
        response = client.post("/api/lab/reset", json={})
        assert response.status_code == 200
        assert "giữ lại" in response.get_json()["message"]
        assert not any(command[1:3] == ["volume", "rm"] for command in commands)
    finally:
        workboard.DEMO_STATE.clear()
        workboard.DEMO_STATE.update(previous)


def test_production_upgrade_failure_attempts_rollback(client, monkeypatch):
    import copy
    import app as workboard

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setattr(workboard, "docker_available", lambda: (True, "docker"))
    monkeypatch.setattr(workboard.time, "sleep", lambda _duration: None)
    commands = []

    def fake_command(command, timeout=240):
        commands.append(command)
        return {"success": True, "exit_code": 0, "output": "ok"}

    def unhealthy(*_args, **_kwargs):
        raise OSError("not responding")

    monkeypatch.setattr(workboard, "run_command", fake_command)
    monkeypatch.setattr(workboard, "urlopen", unhealthy)
    previous = copy.deepcopy(workboard.DEMO_STATE)
    try:
        workboard.DEMO_STATE["image"] = {
            "tag": "cicd-lab:v1.1.0", "id": "sha256:new"
        }
        workboard.DEMO_STATE["release"] = {
            "version": "v1.1.0", "status": "approved"
        }
        workboard.DEMO_STATE["production_approved"] = True
        workboard.DEMO_STATE["environments"]["staging"] = {
            "status": "success", "version": "v1.1.0"
        }
        workboard.DEMO_STATE["environments"]["production"] = {
            "status": "success", "version": "v1.0.0"
        }
        response = client.post("/api/lab/deploy/production", json={})
        assert response.status_code == 422
        assert workboard.DEMO_STATE["environments"]["production"]["version"] == "v1.0.0"
        assert [
            "docker", "rename", "cicd-lab-production", "cicd-lab-production-rollback"
        ] in commands
        assert [
            "docker", "rename", "cicd-lab-production-rollback", "cicd-lab-production"
        ] in commands
        assert ["docker", "start", "cicd-lab-production"] in commands
    finally:
        workboard.DEMO_STATE.clear()
        workboard.DEMO_STATE.update(previous)


def test_live_evidence_is_local_only(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "staging")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "stage.sqlite")})
    with app.test_client() as client:
        assert client.get("/api/lab/evidence").status_code == 403


def test_live_evidence_reports_missing_docker(client, monkeypatch):
    monkeypatch.setattr(
        "app.docker_available", lambda: (False, "Docker Desktop chưa sẵn sàng.")
    )
    response = client.get("/api/lab/evidence")
    assert response.status_code == 503
    assert "Docker Desktop" in response.get_json()["error"]


def test_live_evidence_reads_real_container_data(client, monkeypatch):
    import json

    monkeypatch.setattr("app.docker_available", lambda: (True, "docker"))

    def fake_command(args, timeout=240):
        if args[1:3] == ["image", "inspect"]:
            return {"success": True, "output": "sha256:abc123"}
        if args[1:3] == ["container", "inspect"]:
            name = args[3]
            return {
                "success": True,
                "output": json.dumps({
                    "image": "sha256:abc123",
                    "running": name == "cicd-lab-dev",
                    "env": [
                        "APP_ENV=dev", "APP_VERSION=v1.1.0",
                        "WORKBOARD_FEATURE_SET=insights", "SECRET_TOKEN=must-not-leak",
                    ],
                }),
            }
        raise AssertionError(f"Lệnh không mong đợi: {args}")

    class FakeResponse:
        status = 200

        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            if self.url.endswith("/health"):
                return b'{"status": "ok"}'
            if self.url.endswith("/api/info"):
                return b'{"environment": "dev", "version": "v1.1.0", "features": "insights"}'
            return b'{"tasks": [{"id": 1}, {"id": 2}]}'

    monkeypatch.setattr("app.run_command", fake_command)
    monkeypatch.setattr("app.urlopen", lambda url, timeout=2: FakeResponse(url))
    response = client.get("/api/lab/evidence")
    assert response.status_code == 200
    data = response.get_json()
    assert data["images"]["cicd-lab:v1.1.0"]["exists"] is True
    assert data["environments"]["dev"]["healthy"] is True
    assert data["environments"]["dev"]["version"] == "v1.1.0"
    assert data["environments"]["dev"]["tasks"] == 2
    assert data["environments"]["production"]["running"] is False
    assert "SECRET_TOKEN" not in str(data)


def test_lab_page_shows_workboard_relationship_and_live_evidence(client):
    response = client.get("/lab")
    assert response.status_code == 200
    assert "workboard-ci-link" in response.get_data(as_text=True)
    assert "evidence-board" in response.get_data(as_text=True)
    assert "verify-docker" in response.get_data(as_text=True)
