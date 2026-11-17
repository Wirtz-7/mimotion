"""Resolve and optionally persist one-day manual step overrides for GitHub Actions."""
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CONFIG_PATH = Path(".github/step_override.json")
TODAY = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
MODE = os.environ.get("STEP_MODE", "auto").strip() or "auto"


def check_steps(raw):
    if not raw.isdecimal():
        raise ValueError("固定步数必须是 1～100000 之间的整数")
    steps = int(raw)
    if not 1 <= steps <= 100000:
        raise ValueError("固定步数必须是 1～100000 之间的整数")
    return steps


def save_override(data):
    """Commit only the override JSON via GitHub's contents API (no full-tree git push)."""
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    if not token:
        raise RuntimeError("缺少 GITHUB_TOKEN，无法保存当天的固定步数")
    url = "https://api.github.com/repos/" + repo + "/contents/" + str(CONFIG_PATH)
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mimotion-step-override",
    }
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    for attempt in range(3):
        sha = None
        try:
            with urlopen(Request(url, headers=headers), timeout=15) as response:
                sha = json.load(response)["sha"]
        except HTTPError as exc:
            if exc.code != 404:
                raise
        body = {
            "message": "chore: update temporary step override",
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": os.environ.get("GITHUB_REF_NAME", "master"),
        }
        if sha:
            body["sha"] = sha
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urlopen(request, timeout=20):
                pass
            CONFIG_PATH.write_bytes(raw)
            return
        except HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 2:
                raise
    raise RuntimeError("无法保存当天的固定步数")


def main():
    if MODE not in ("auto", "once", "today", "reset"):
        raise ValueError("不支持的步数模式: " + MODE)
    raw = os.environ.get("STEP_INPUT", "").strip()
    explicit = check_steps(raw) if MODE in ("once", "today") else None

    if MODE == "today":
        save_override({"date": TODAY, "steps": explicit})
        effective = explicit
    elif MODE == "reset":
        save_override({"date": "", "steps": None})
        effective = None
    elif MODE == "once":
        effective = explicit
    else:
        state = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        effective = (
            check_steps(str(state["steps"]))
            if state.get("date") == TODAY and state.get("steps") is not None
            else None
        )

    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env_file:
        env_file.write("FIXED_STEPS=" + (str(effective) if effective is not None else "") + "\n")

    if effective is None:
        print("步数模式：原有时间/天气随机规则")
    else:
        print(f"步数模式：固定 {effective} 步；北京时间日期 {TODAY}")


if __name__ == "__main__":
    main()
