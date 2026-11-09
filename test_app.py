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
