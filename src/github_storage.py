"""
Backend de persistencia que usa la **GitHub Contents API** como almacén.

Por qué GitHub:
  - Cero infraestructura extra (mismo repo donde vive la app).
  - Versionado nativo (cada cambio = commit con diff).
  - Compatible con cualquier hosting de Streamlit (Cloud, local, AWS…).
  - Gratis hasta 5 000 requests/hora con un Personal Access Token.

Configuración requerida (en Streamlit Cloud → Settings → Secrets):
    [github]
    token = "ghp_xxxxxxxxxxxxxxxxx"   # PAT con scope 'repo'
    repo  = "usuario/fondos-recompra-bmv"
    branch = "main"                   # opcional, default main
    base_path = "data/activos"        # opcional, default data/activos
    author_name = "App Fondos Recompra"   # opcional
    author_email = "noreply@app.local"     # opcional

Local: si en st.secrets no hay sección [github] o estás corriendo sin
Streamlit, las funciones devolverán `False` en `is_enabled()` y el
backend caerá al filesystem local automáticamente.
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class GithubConfig:
    token: str
    repo: str            # 'owner/repo'
    branch: str = "main"
    base_path: str = "data/activos"
    author_name: str = "Fondos Recompra Bot"
    author_email: str = "bot@fondos-recompra.local"


# ---------------------------------------------------------------------------
# Configuración (lazy: lee st.secrets sólo cuando se invoca)
# ---------------------------------------------------------------------------

def _leer_config() -> Optional[GithubConfig]:
    # 1) Streamlit secrets
    try:
        import streamlit as st  # noqa
        if "github" in st.secrets:
            gh = st.secrets["github"]
            if gh.get("token") and gh.get("repo"):
                return GithubConfig(
                    token=gh["token"],
                    repo=gh["repo"],
                    branch=gh.get("branch", "main"),
                    base_path=gh.get("base_path", "data/activos"),
                    author_name=gh.get("author_name", "Fondos Recompra Bot"),
                    author_email=gh.get("author_email", "bot@fondos-recompra.local"),
                )
    except Exception:
        pass

    # 2) Variables de entorno
    token = os.environ.get("GH_STORAGE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GH_STORAGE_REPO") or os.environ.get("GITHUB_REPO")
    if token and repo:
        return GithubConfig(
            token=token,
            repo=repo,
            branch=os.environ.get("GH_STORAGE_BRANCH", "main"),
            base_path=os.environ.get("GH_STORAGE_BASE_PATH", "data/activos"),
        )
    return None


def is_enabled() -> bool:
    return _leer_config() is not None


def config_info() -> dict:
    cfg = _leer_config()
    if not cfg:
        return {"enabled": False}
    return {
        "enabled": True,
        "repo": cfg.repo,
        "branch": cfg.branch,
        "base_path": cfg.base_path,
    }


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def _headers(cfg: GithubConfig) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {cfg.token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fondos-recompra-bmv/1.0",
    }


def _url_contents(cfg: GithubConfig, path: str) -> str:
    return f"https://api.github.com/repos/{cfg.repo}/contents/{path}"


def _full_path(cfg: GithubConfig, relative_path: str) -> str:
    # Une base_path con relative_path con / sin duplicar barras
    base = cfg.base_path.strip("/")
    rel = relative_path.lstrip("/")
    return f"{base}/{rel}" if base else rel


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------

def read_bytes(relative_path: str) -> Optional[bytes]:
    """Lee un archivo del repo. Devuelve None si no existe."""
    cfg = _leer_config()
    if not cfg:
        return None
    url = _url_contents(cfg, _full_path(cfg, relative_path))
    params = {"ref": cfg.branch}
    r = requests.get(url, headers=_headers(cfg), params=params, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"GitHub GET {r.status_code}: {r.text[:200]}")
    data = r.json()
    if isinstance(data, list):
        # Es un directorio; no es archivo
        return None
    if data.get("encoding") == "base64" and data.get("content"):
        return base64.b64decode(data["content"])
    # Para archivos grandes (>1MB) GitHub no incluye `content` y hay que
    # usar el download_url.
    if data.get("download_url"):
        r2 = requests.get(data["download_url"], headers=_headers(cfg), timeout=60)
        if r2.status_code == 200:
            return r2.content
    return None


def write_bytes(relative_path: str, contenido: bytes, mensaje: Optional[str] = None) -> bool:
    """
    Crea o actualiza un archivo en el repo via Contents API.
    Devuelve True si el commit se hizo, False si falló.
    """
    cfg = _leer_config()
    if not cfg:
        return False
    path = _full_path(cfg, relative_path)
    url = _url_contents(cfg, path)

    # Obtener sha actual si existe
    sha = None
    rget = requests.get(url, headers=_headers(cfg), params={"ref": cfg.branch}, timeout=30)
    if rget.status_code == 200 and isinstance(rget.json(), dict):
        sha = rget.json().get("sha")

    body = {
        "message": mensaje or f"chore(data): update {relative_path}",
        "content": base64.b64encode(contenido).decode("ascii"),
        "branch": cfg.branch,
        "committer": {"name": cfg.author_name, "email": cfg.author_email},
    }
    if sha:
        body["sha"] = sha

    r = requests.put(url, headers=_headers(cfg), json=body, timeout=60)
    if r.status_code in (200, 201):
        return True
    raise RuntimeError(f"GitHub PUT {r.status_code}: {r.text[:300]}")


def delete_path(relative_path: str, mensaje: Optional[str] = None) -> bool:
    """Borra un archivo del repo."""
    cfg = _leer_config()
    if not cfg:
        return False
    path = _full_path(cfg, relative_path)
    url = _url_contents(cfg, path)
    rget = requests.get(url, headers=_headers(cfg), params={"ref": cfg.branch}, timeout=30)
    if rget.status_code != 200:
        return False
    sha = rget.json().get("sha")
    if not sha:
        return False
    body = {
        "message": mensaje or f"chore(data): delete {relative_path}",
        "branch": cfg.branch,
        "sha": sha,
        "committer": {"name": cfg.author_name, "email": cfg.author_email},
    }
    r = requests.delete(url, headers=_headers(cfg), json=body, timeout=30)
    return r.status_code in (200, 204)


def list_dir(relative_path: str = "") -> list[dict]:
    """Lista contenidos de un directorio dentro del base_path."""
    cfg = _leer_config()
    if not cfg:
        return []
    path = _full_path(cfg, relative_path)
    url = _url_contents(cfg, path)
    r = requests.get(url, headers=_headers(cfg), params={"ref": cfg.branch}, timeout=30)
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        return []
    data = r.json()
    if not isinstance(data, list):
        return []
    return data


def latest_commit_for(relative_path: str) -> Optional[str]:
    """Devuelve la fecha ISO del último commit que tocó un archivo (o None)."""
    cfg = _leer_config()
    if not cfg:
        return None
    url = f"https://api.github.com/repos/{cfg.repo}/commits"
    r = requests.get(
        url,
        headers=_headers(cfg),
        params={"path": _full_path(cfg, relative_path), "sha": cfg.branch, "per_page": 1},
        timeout=20,
    )
    if r.status_code == 200:
        data = r.json()
        if data:
            return data[0].get("commit", {}).get("committer", {}).get("date")
    return None
