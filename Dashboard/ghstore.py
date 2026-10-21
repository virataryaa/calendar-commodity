"""Tiny GitHub "database": read / write files in the calendar-commodity repo through the Contents API.

Used by the Entry tab. Needs `github_token` in Streamlit Secrets (Contents: read and write on the repo).
One keep-alive session, the last sha of every file is remembered, so a save is a single PUT (re-read once on a conflict).
"""
import base64

import requests
import streamlit as st

REPO = "virataryaa/calendar-commodity"
BRANCH = "entries"   # app data branch: commits here do not redeploy the app (it runs from main)


class GitHubError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def enabled() -> bool:
    try:
        return "github_token" in st.secrets
    except Exception:                                  # no secrets file at all (local run)
        return False


@st.cache_resource
def _session():
    s = requests.Session()
    tok = str(st.secrets["github_token"]).strip().strip('"').strip("'")
    s.headers.update({"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return s


@st.cache_resource
def _state() -> dict:
    """{path: {"text": ..., "sha": ...}} - shared across reruns and sessions."""
    return {}


def _url(path: str) -> str:
    return f"https://api.github.com/repos/{REPO}/contents/{path}"


def _check(r):
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", "")
        except ValueError:
            msg = r.text[:200]
        hint = {401: "token is wrong or expired - re-paste github_token in Secrets",
                403: "token has no write access - give it Contents: Read and write on calendar-commodity",
                404: "token cannot see the calendar-commodity repo (or the file) - check the token",
                409: "file changed meanwhile - press Save again"}.get(r.status_code, "")
        raise GitHubError(f"GitHub {r.status_code}: {msg}. {hint}", r.status_code)


def cached_text(path: str):
    """Last known text of a file, or None if it hasn't been read in this server process yet."""
    hit = _state().get(path)
    return hit["text"] if hit else None


def read(path: str) -> tuple[str, str]:
    r = _session().get(_url(path), params={"ref": BRANCH}, timeout=20)
    _check(r)
    j = r.json()
    text = base64.b64decode(j["content"]).decode("utf-8")
    _state()[path] = {"text": text, "sha": j["sha"]}
    return text, j["sha"]


def commit(path: str, change, message: str):
    """change(text) -> (new_text, info). One PUT using the remembered sha; re-read once if the file moved on."""
    st_ = _state()
    text, sha = (st_[path]["text"], st_[path]["sha"]) if path in st_ else read(path)
    new_text, info = change(text)
    for attempt in (0, 1):
        body = {"message": message, "branch": BRANCH, "sha": sha,
                "content": base64.b64encode(new_text.encode("utf-8")).decode()}
        try:
            r = _session().put(_url(path), json=body, timeout=20)
            _check(r)
            break
        except GitHubError as ex:
            if attempt == 0 and ex.status in (409, 422):           # someone else changed the file: re-read once
                text, sha = read(path)
                new_text, info = change(text)
                continue
            raise
    j = r.json()
    st_[path] = {"text": new_text, "sha": j["content"]["sha"]}
    return new_text, info
