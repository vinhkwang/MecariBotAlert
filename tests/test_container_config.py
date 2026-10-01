import re
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_NAME = "alert-bot"


def load_compose_file() -> dict[str, Any]:
    compose: dict[str, Any] = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text())
    return compose


def load_compose_service() -> dict[str, Any]:
    service: dict[str, Any] = load_compose_file()["services"][SERVICE_NAME]
    return service


def load_compose_volumes() -> dict[str, Any]:
    volumes: dict[str, Any] = load_compose_file()["volumes"]
    return volumes


def load_image_environment() -> dict[str, str]:
    dockerfile_text = (PROJECT_ROOT / "Dockerfile").read_text().replace("\\\n", " ")
    environment: dict[str, str] = {}
    for line in dockerfile_text.splitlines():
        if line.startswith("ENV "):
            environment.update(re.findall(r"(\w+)=(\S+)", line))
    return environment


def parse_bind_mount_targets() -> dict[str, str]:
    targets: dict[str, str] = {}
    for volume in load_compose_service()["volumes"]:
        source, target, *options = volume.split(":")
        targets[target] = source
        if options:
            targets[f"{target}:options"] = options[0]
    return targets


def read_backup_script_database_path() -> str:
    script_text = (PROJECT_ROOT / "deploy" / "backup.sh").read_text()
    match = re.search(r"DB_PATH_IN_CONTAINER:-([^}]+)\}", script_text)
    assert match is not None
    return match.group(1)


def test_compose_publishes_ui_on_loopback_only() -> None:
    published_ports = load_compose_service()["ports"]

    assert published_ports
    assert all(port.startswith("127.0.0.1:") for port in published_ports)


def test_compose_keeps_database_on_named_volume() -> None:
    mount_sources = parse_bind_mount_targets()

    named_volume = mount_sources["/data"]
    assert named_volume in load_compose_volumes()
    assert not named_volume.startswith((".", "/"))


def test_image_database_path_matches_backup_script() -> None:
    database_path = load_image_environment()["DATABASE_PATH"]

    assert database_path.startswith("/data/")
    assert database_path == read_backup_script_database_path()


def test_image_seed_path_matches_compose_mount() -> None:
    seed_path = load_image_environment()["KEYWORD_SEED_PATH"]
    mount_sources = parse_bind_mount_targets()

    assert seed_path in mount_sources
    assert mount_sources[f"{seed_path}:options"] == "ro"


def test_dockerignore_excludes_secrets_and_local_state() -> None:
    ignored_entries = (PROJECT_ROOT / ".dockerignore").read_text().splitlines()

    for required_entry in (".env", ".git", ".venv", "data/"):
        assert required_entry in ignored_entries
