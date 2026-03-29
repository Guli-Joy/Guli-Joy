from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

# Keep the output path local so the README only depends on repository assets.
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "activity.svg"
STATUS_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "status.svg"
DEFAULT_USERNAME = "Guli-Joy"
MAX_EVENTS = 4
MAX_FEATURED_REPOS = 3


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def format_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return "未知"


def translate_action(action: str) -> str:
    normalized = action.strip().lower()
    action_map = {
        "opened": "创建了",
        "created": "创建了",
        "closed": "关闭了",
        "reopened": "重新打开了",
        "edited": "编辑了",
        "deleted": "删除了",
        "published": "发布了",
        "submitted": "提交了",
        "synchronize": "同步了",
        "assigned": "分配了",
        "unassigned": "取消分配了",
        "review_requested": "请求了评审",
        "review_request_removed": "移除了评审请求",
        "ready_for_review": "标记为可评审",
        "converted_to_draft": "转成了草稿",
        "locked": "锁定了",
        "unlocked": "解锁了",
        "pinned": "置顶了",
        "unpinned": "取消置顶了",
        "transferred": "转移了",
        "milestoned": "设置了里程碑",
        "demilestoned": "移除了里程碑",
    }
    return action_map.get(normalized, "更新了")


def translate_ref_type(ref_type: str) -> str:
    normalized = ref_type.strip().lower()
    ref_type_map = {
        "repository": "仓库",
        "repo": "仓库",
        "branch": "分支",
        "tag": "标签",
    }
    return ref_type_map.get(normalized, "内容")


def safe_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 0


def sort_timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def build_headers(username: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{username}-profile-readme-activity-panel",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        # Optional auth helps with rate limits while still using the public events endpoint.
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str, username: str) -> Any:
    request = urllib.request.Request(
        url=url,
        headers=build_headers(username),
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")

    return json.loads(payload)


def fetch_user_profile(username: str) -> dict[str, Any]:
    data = fetch_json(f"https://api.github.com/users/{username}", username)
    if not isinstance(data, dict):
        raise ValueError("GitHub 用户资料返回格式异常。")
    return data


def fetch_user_repos(username: str, public_repos_count: int) -> list[dict[str, Any]]:
    if public_repos_count <= 0:
        return []

    total_pages = max(1, math.ceil(public_repos_count / 100))
    repos: list[dict[str, Any]] = []

    for page in range(1, total_pages + 1):
        data = fetch_json(
            f"https://api.github.com/users/{username}/repos?type=owner&sort=updated&per_page=100&page={page}",
            username,
        )
        if not isinstance(data, list):
            raise ValueError("GitHub 仓库列表返回格式异常。")
        repos.extend(item for item in data if isinstance(item, dict))
        if len(data) < 100:
            break

    return repos


def fetch_public_events(username: str) -> list[dict[str, Any]]:
    data = fetch_json(
        f"https://api.github.com/users/{username}/events/public?per_page={MAX_EVENTS}",
        username,
    )

    if not isinstance(data, list):
        raise ValueError("GitHub 事件返回格式异常。")
    return [item for item in data if isinstance(item, dict)]


def summarize_event(event: dict[str, Any]) -> tuple[str, str, str]:
    event_type = str(event.get("type", "Activity"))
    repo_name = str(event.get("repo", {}).get("name", "未知仓库"))
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    created_at = format_date(str(event.get("created_at", "")))

    if event_type == "PushEvent":
        size = payload.get("size")
        if not isinstance(size, int):
            commits = payload.get("commits")
            size = len(commits) if isinstance(commits, list) else 0
        return "推送", f"向 {repo_name} 推送了 {size} 次提交", created_at

    if event_type == "PullRequestEvent":
        action = translate_action(str(payload.get("action", "updated")))
        return "拉取请求", f"{repo_name} 中的拉取请求：{action}", created_at

    if event_type == "IssuesEvent":
        action = translate_action(str(payload.get("action", "updated")))
        return "议题", f"{repo_name} 中的议题：{action}", created_at

    if event_type == "IssueCommentEvent":
        return "评论", f"评论了 {repo_name} 中的议题", created_at

    if event_type == "PullRequestReviewEvent":
        return "评审", f"评审了 {repo_name} 中的拉取请求", created_at

    if event_type == "PullRequestReviewCommentEvent":
        return "评论", f"评论了 {repo_name} 中的拉取请求评审", created_at

    if event_type == "CreateEvent":
        ref_type = translate_ref_type(str(payload.get("ref_type", "resource")))
        return "创建", f"在 {repo_name} 中创建了{ref_type}", created_at

    if event_type == "ReleaseEvent":
        return "发布", f"在 {repo_name} 中发布了新版本", created_at

    if event_type == "ForkEvent":
        return "派生", f"派生了 {repo_name}", created_at

    if event_type == "WatchEvent":
        return "标星", f"标星了 {repo_name}", created_at

    if event_type == "CommitCommentEvent":
        return "评论", f"评论了 {repo_name} 中的提交", created_at

    normalized_label = truncate(event_type.replace("Event", "").upper(), 10)
    return normalized_label, f"记录了 {event_type}：{repo_name}", created_at


def build_rows(events: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for event in events[:MAX_EVENTS]:
        label, summary, date_text = summarize_event(event)
        rows.append((truncate(label, 10), truncate(summary, 76), date_text))

    if rows:
        return rows

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [("空闲", "当前没有可显示的最近公开 GitHub 动态。", today)]


def select_featured_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owned_repos = [repo for repo in repos if not bool(repo.get("fork"))]
    candidates = owned_repos or repos
    ranked = sorted(
        candidates,
        key=lambda repo: (
            0 if bool(repo.get("archived")) else 1,
            safe_int(repo.get("stargazers_count")),
            sort_timestamp(str(repo.get("pushed_at", ""))),
            sort_timestamp(str(repo.get("updated_at", ""))),
        ),
        reverse=True,
    )
    return ranked[:MAX_FEATURED_REPOS]


def select_recent_repo(repos: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    if not repos:
        return {}

    return max(
        repos,
        key=lambda repo: (
            sort_timestamp(str(repo.get(field_name, ""))),
            sort_timestamp(str(repo.get("updated_at", ""))),
            sort_timestamp(str(repo.get("pushed_at", ""))),
            safe_int(repo.get("stargazers_count")),
        ),
    )


def build_summary_snapshot(repos: list[dict[str, Any]]) -> dict[str, str]:
    owned_repos = [repo for repo in repos if not bool(repo.get("fork"))]
    candidates = owned_repos or repos

    if not candidates:
        return {
            "total_stars": "0",
            "active_name": "暂无公开仓库",
            "active_meta": "推送：待同步 · 语言：待更新",
            "updated_value": "待同步",
            "updated_meta": "仓库：暂无公开仓库",
        }

    total_stars = sum(safe_int(repo.get("stargazers_count")) for repo in candidates)
    active_repo = select_recent_repo(candidates, "pushed_at")
    updated_repo = select_recent_repo(candidates, "updated_at")

    active_name = truncate(str(active_repo.get("name", "暂无公开仓库")), 22)
    active_date = format_date(str(active_repo.get("pushed_at") or active_repo.get("updated_at") or ""))
    active_language = truncate(str(active_repo.get("language") or "未标注"), 12)

    updated_name = truncate(str(updated_repo.get("name", "暂无公开仓库")), 22)
    updated_date = format_date(str(updated_repo.get("updated_at") or updated_repo.get("pushed_at") or ""))

    return {
        "total_stars": str(total_stars),
        "active_name": active_name,
        "active_meta": f"推送：{active_date} · 语言：{active_language}",
        "updated_value": updated_date,
        "updated_meta": f"仓库：{updated_name}",
    }


def render_status_svg(
    profile: dict[str, Any],
    featured_repos: list[dict[str, Any]],
    summary_snapshot: dict[str, str],
    footer_note: str,
) -> str:
    metric_cards = [
        ("粉丝", str(safe_int(profile.get("followers"))), "#67E8F9"),
        ("关注中", str(safe_int(profile.get("following"))), "#C4B5FD"),
        ("公开仓库", str(safe_int(profile.get("public_repos"))), "#F9A8D4"),
    ]
    metric_positions = [52, 430, 808]
    metric_fragments: list[str] = []
    summary_cards = [
        ("总 Star", summary_snapshot.get("total_stars", "0"), "仅统计非 Fork 公开仓库。", "#67E8F9", "34"),
        (
            "最近活跃仓库",
            truncate(summary_snapshot.get("active_name", "暂无公开仓库"), 18),
            truncate(summary_snapshot.get("active_meta", "推送：待同步 · 语言：待更新"), 30),
            "#C4B5FD",
            "24",
        ),
        (
            "最近更新时间",
            truncate(summary_snapshot.get("updated_value", "待同步"), 18),
            truncate(summary_snapshot.get("updated_meta", "仓库：暂无公开仓库"), 30),
            "#F9A8D4",
            "24",
        ),
    ]
    summary_fragments: list[str] = []

    for (label, value, accent), x in zip(metric_cards, metric_positions):
        metric_fragments.append(
            f'''  <rect x="{x}" y="146" width="340" height="92" rx="24" fill="#FFFFFF" fill-opacity="0.05" stroke="url(#stroke)"/>
  <text x="{x + 32}" y="182" fill="{accent}" font-size="13" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="1.8">{escape(label)}</text>
  <text x="{x + 32}" y="224" fill="#FFFFFF" font-size="34" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(value)}</text>'''
        )

    for (label, value, meta, accent, value_size), x in zip(summary_cards, metric_positions):
        summary_fragments.append(
            f'''  <rect x="{x}" y="254" width="340" height="110" rx="24" fill="#FFFFFF" fill-opacity="0.05" stroke="url(#stroke)"/>
  <text x="{x + 32}" y="288" fill="{accent}" font-size="13" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="1.8">{escape(label)}</text>
  <text x="{x + 32}" y="324" fill="#FFFFFF" font-size="{value_size}" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(value)}</text>
  <text x="{x + 32}" y="348" fill="#94A3B8" font-size="14" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(meta)}</text>'''
        )

    displayed_repos: list[dict[str, Any]] = list(featured_repos[:MAX_FEATURED_REPOS])
    while len(displayed_repos) < MAX_FEATURED_REPOS:
        displayed_repos.append(
            {
                "name": "等待同步",
                "language": "待更新",
                "stargazers_count": "--",
                "updated_at": "",
            }
        )

    repo_positions = [52, 430, 808]
    repo_fragments: list[str] = []

    for index, (repo, x) in enumerate(zip(displayed_repos, repo_positions), start=1):
        name = truncate(str(repo.get("name", "未命名仓库")), 24)
        language = truncate(str(repo.get("language") or "未标注"), 12)
        stars_value = repo.get("stargazers_count", 0)
        stars = str(stars_value) if isinstance(stars_value, str) else str(safe_int(stars_value))
        updated_at = str(repo.get("updated_at", ""))
        updated_text = format_date(updated_at) if updated_at else "待更新"
        repo_fragments.append(
            f'''  <rect x="{x}" y="406" width="340" height="122" rx="24" fill="#FFFFFF" fill-opacity="0.05" stroke="url(#stroke)"/>
  <text x="{x + 32}" y="440" fill="#94A3B8" font-size="12" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="1.2">精选 0{index}</text>
  <text x="{x + 32}" y="474" fill="#FFFFFF" font-size="24" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(name)}</text>
  <text x="{x + 32}" y="496" fill="#CBD5E1" font-size="14" font-family="Inter, Segoe UI, Arial, sans-serif">语言：{escape(language)}</text>
  <text x="{x + 32}" y="516" fill="#94A3B8" font-size="13" font-family="Inter, Segoe UI, Arial, sans-serif">星标：{escape(stars)} · 更新：{escape(updated_text)}</text>'''
        )

    metrics_markup = "\n".join(metric_fragments)
    summary_markup = "\n".join(summary_fragments)
    repos_markup = "\n".join(repo_fragments)

    return f'''<svg width="1200" height="570" viewBox="0 0 1200 570" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="570" gradientUnits="userSpaceOnUse">
      <stop stop-color="#07111F"/>
      <stop offset="0.5" stop-color="#111827"/>
      <stop offset="1" stop-color="#1E1B4B"/>
    </linearGradient>
    <linearGradient id="stroke" x1="114" y1="60" x2="1092" y2="510" gradientUnits="userSpaceOnUse">
      <stop stop-color="#38BDF8" stop-opacity="0.36"/>
      <stop offset="0.5" stop-color="#8B5CF6" stop-opacity="0.26"/>
      <stop offset="1" stop-color="#EC4899" stop-opacity="0.36"/>
    </linearGradient>
    <linearGradient id="title" x1="0" y1="0" x2="320" y2="0" gradientUnits="userSpaceOnUse">
      <stop stop-color="#67E8F9"/>
      <stop offset="1" stop-color="#C084FC"/>
    </linearGradient>
    <radialGradient id="glowA" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(116 56) rotate(42.334) scale(190 170)">
      <stop stop-color="#0EA5E9" stop-opacity="0.40"/>
      <stop offset="1" stop-color="#0EA5E9" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(1060 518) rotate(-130) scale(220 160)">
      <stop stop-color="#EC4899" stop-opacity="0.34"/>
      <stop offset="1" stop-color="#EC4899" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M 34 0 L 0 0 0 34" stroke="#FFFFFF" stroke-opacity="0.05"/>
    </pattern>
  </defs>

  <rect width="1200" height="570" rx="28" fill="url(#bg)"/>
  <rect width="1200" height="570" rx="28" fill="url(#grid)"/>
  <ellipse cx="120" cy="58" rx="174" ry="130" fill="url(#glowA)">
    <animate attributeName="opacity" values="0.72;1;0.72" dur="11s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="translate" values="0 0; 12 8; 0 0" dur="20s" repeatCount="indefinite"/>
  </ellipse>
  <ellipse cx="1060" cy="518" rx="210" ry="138" fill="url(#glowB)">
    <animate attributeName="opacity" values="0.70;0.94;0.70" dur="12.5s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="translate" values="0 0; -12 -10; 0 0" dur="22s" repeatCount="indefinite"/>
  </ellipse>
  <circle cx="1122" cy="74" r="18" fill="#22D3EE" fill-opacity="0.05" stroke="#67E8F9" stroke-opacity="0.26">
    <animate attributeName="r" values="18;26;18" dur="4.8s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="0;0.48;0" dur="4.8s" repeatCount="indefinite"/>
  </circle>
  <circle cx="1122" cy="74" r="6" fill="#67E8F9">
    <animate attributeName="opacity" values="1;0.64;1" dur="4.8s" repeatCount="indefinite"/>
  </circle>

  <text x="62" y="54" fill="#C4B5FD" font-size="14" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="2">主页状态</text>
  <text x="62" y="92" fill="url(#title)" font-size="32" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif">主页状态与统计摘要</text>
  <text x="62" y="122" fill="#CBD5E1" font-size="16" font-family="Inter, Segoe UI, Arial, sans-serif">自动同步 GitHub 公开资料、统计摘要与精选仓库信息。</text>

{metrics_markup}
{summary_markup}

  <text x="62" y="390" fill="#F472B6" font-size="13" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="1.8">精选仓库</text>
{repos_markup}

  <text x="62" y="548" fill="#94A3B8" font-size="13" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(footer_note)}</text>
</svg>
'''


def render_svg(rows: list[tuple[str, str, str]], footer_note: str) -> str:
    row_height = 38
    start_y = 164
    content_box_height = 32 + max(len(rows), 1) * row_height
    canvas_height = 196 + content_box_height
    footer_y = canvas_height - 24

    row_fragments: list[str] = []
    accent_colors = [
        ("#22D3EE", "#67E8F9"),
        ("#8B5CF6", "#C4B5FD"),
        ("#F472B6", "#F9A8D4"),
        ("#38BDF8", "#BAE6FD"),
    ]

    for index, (label, summary, date_text) in enumerate(rows):
        y = start_y + index * row_height
        accent_fill, accent_text = accent_colors[index % len(accent_colors)]
        row_delay = f"{index * 0.8:.1f}s"
        pill_delay = f"{index * 0.4:.1f}s"
        row_fragments.append(
            f'''  <rect x="72" y="{y}" width="1056" height="28" rx="14" fill="#FFFFFF" fill-opacity="0.05">
    <animate attributeName="fill-opacity" values="0.05;0.08;0.05" dur="8s" begin="{row_delay}" repeatCount="indefinite"/>
  </rect>
  <rect x="84" y="{y + 6}" width="96" height="16" rx="8" fill="{accent_fill}" fill-opacity="0.20">
    <animate attributeName="fill-opacity" values="0.18;0.30;0.18" dur="6.5s" begin="{pill_delay}" repeatCount="indefinite"/>
  </rect>
  <text x="132" y="{y + 18}" text-anchor="middle" fill="{accent_text}" font-size="11" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="1.2">{escape(label)}</text>
  <text x="198" y="{y + 18}" fill="#E5E7EB" font-size="14" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(summary)}</text>
  <text x="1104" y="{y + 18}" text-anchor="end" fill="#94A3B8" font-size="12" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(date_text)}</text>'''
        )

    rows_markup = "\n".join(row_fragments)

    return f'''<svg width="1200" height="{canvas_height}" viewBox="0 0 1200 {canvas_height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="{canvas_height}" gradientUnits="userSpaceOnUse">
      <stop stop-color="#07101D"/>
      <stop offset="0.52" stop-color="#111827"/>
      <stop offset="1" stop-color="#172554"/>
    </linearGradient>
    <linearGradient id="stroke" x1="92" y1="76" x2="1112" y2="{canvas_height - 44}" gradientUnits="userSpaceOnUse">
      <stop stop-color="#22D3EE" stop-opacity="0.34"/>
      <stop offset="0.5" stop-color="#8B5CF6" stop-opacity="0.24"/>
      <stop offset="1" stop-color="#F472B6" stop-opacity="0.34"/>
    </linearGradient>
    <radialGradient id="glowA" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(1094 66) rotate(145) scale(220 130)">
      <stop stop-color="#22D3EE" stop-opacity="0.26"/>
      <stop offset="1" stop-color="#22D3EE" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(176 {canvas_height - 38}) rotate(16) scale(240 140)">
      <stop stop-color="#8B5CF6" stop-opacity="0.24"/>
      <stop offset="1" stop-color="#8B5CF6" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M 34 0 L 0 0 0 34" stroke="#FFFFFF" stroke-opacity="0.05"/>
    </pattern>
  </defs>

  <rect width="1200" height="{canvas_height}" rx="28" fill="url(#bg)"/>
  <rect width="1200" height="{canvas_height}" rx="28" fill="url(#grid)"/>
  <ellipse cx="1094" cy="66" rx="200" ry="118" fill="url(#glowA)">
    <animate attributeName="opacity" values="0.68;0.94;0.68" dur="10.5s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="translate" values="0 0; -10 8; 0 0" dur="18s" repeatCount="indefinite"/>
  </ellipse>
  <ellipse cx="176" cy="{canvas_height - 38}" rx="214" ry="118" fill="url(#glowB)">
    <animate attributeName="opacity" values="0.62;0.88;0.62" dur="12s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="translate" values="0 0; 10 -6; 0 0" dur="20s" repeatCount="indefinite"/>
  </ellipse>
  <circle cx="1114" cy="74" r="16" fill="#22D3EE" fill-opacity="0.05" stroke="#67E8F9" stroke-opacity="0.24">
    <animate attributeName="r" values="16;24;16" dur="4.6s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="0;0.42;0" dur="4.6s" repeatCount="indefinite"/>
  </circle>
  <circle cx="1114" cy="74" r="5" fill="#67E8F9">
    <animate attributeName="opacity" values="1;0.62;1" dur="4.6s" repeatCount="indefinite"/>
  </circle>

  <text x="60" y="56" fill="#A78BFA" font-size="14" font-family="Inter, Segoe UI, Arial, sans-serif" letter-spacing="2">最近动态</text>
  <text x="60" y="92" fill="#FFFFFF" font-size="32" font-weight="700" font-family="Inter, Segoe UI, Arial, sans-serif">最新 GitHub 公开活动</text>
  <text x="60" y="120" fill="#CBD5E1" font-size="16" font-family="Inter, Segoe UI, Arial, sans-serif">自动渲染为本地 SVG，让 README 更稳定也更清爽。</text>

  <rect x="52" y="148" width="1096" height="{content_box_height}" rx="24" fill="#FFFFFF" fill-opacity="0.05" stroke="url(#stroke)"/>
{rows_markup}

  <text x="60" y="{footer_y}" fill="#94A3B8" font-size="13" font-family="Inter, Segoe UI, Arial, sans-serif">{escape(footer_note)}</text>
</svg>
'''


def main() -> int:
    username = os.getenv("GITHUB_USERNAME", DEFAULT_USERNAME)
    status_footer_note = "主页状态、统计摘要与精选仓库基于公开资料自动同步。"
    footer_note = "通过 GitHub Actions 从官方公开事件接口自动更新。"

    try:
        profile = fetch_user_profile(username)
        repos = fetch_user_repos(username, safe_int(profile.get("public_repos")))
        featured_repos = select_featured_repos(repos)
        summary_snapshot = build_summary_snapshot(repos)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        profile = {"followers": 0, "following": 0, "public_repos": 0}
        featured_repos = []
        summary_snapshot = build_summary_snapshot([])
        status_footer_note = truncate(f"降级模式：{exc}", 90)

    status_svg = render_status_svg(profile, featured_repos, summary_snapshot, status_footer_note)
    STATUS_OUTPUT_PATH.write_text(status_svg, encoding="utf-8")

    try:
        events = fetch_public_events(username)
        rows = build_rows(events)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        # The fallback keeps the README renderable even when the API is unavailable.
        rows = build_rows([])
        footer_note = truncate(f"降级模式：{exc}", 90)

    svg = render_svg(rows, footer_note)
    OUTPUT_PATH.write_text(svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
