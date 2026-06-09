from __future__ import annotations

import json
from pathlib import Path


class FavoriteStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path()
        self._favorites: set[str] = set()
        self.load()

    @staticmethod
    def default_path() -> Path:
        return Path.home() / ".ifaas_packing" / "favorites.json"

    def load(self) -> None:
        if not self.path.exists():
            self._favorites = set()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._favorites = set()
            return
        favorites = data.get("project_ids", []) if isinstance(data, dict) else []
        self._favorites = {str(item) for item in favorites}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"project_ids": sorted(self._favorites)}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> set[str]:
        return set(self._favorites)

    def contains(self, project_id: int | str | None) -> bool:
        return str(project_id) in self._favorites

    def toggle(self, project_id: int | str | None) -> bool:
        key = str(project_id)
        if key in self._favorites:
            self._favorites.remove(key)
            favorited = False
        else:
            self._favorites.add(key)
            favorited = True
        self.save()
        return favorited


class CredentialStore:
    DEFAULT_USERNAME = "sujiangang"
    DEFAULT_PASSWORD = "Intellif@123"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path()

    @staticmethod
    def default_path() -> Path:
        return Path.home() / ".ifaas_packing" / "credentials.json"

    def load(self) -> dict[str, str | bool]:
        if not self.path.exists():
            return self.defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.defaults()
        if not isinstance(data, dict):
            return self.defaults()
        return {
            "username": str(data.get("username") or self.DEFAULT_USERNAME),
            "password": str(data.get("password") or self.DEFAULT_PASSWORD),
            "remember": bool(data.get("remember", True)),
        }

    def defaults(self) -> dict[str, str | bool]:
        return {
            "username": self.DEFAULT_USERNAME,
            "password": self.DEFAULT_PASSWORD,
            "remember": True,
        }

    def save(self, username: str, password: str, remember: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "username": username if remember else "",
            "password": password if remember else "",
            "remember": remember,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
