#!/usr/bin/env python3
"""Regenerate the marked regions of a GitHub profile README.

It reads a small curated config (``profile-data.json``: the owner, the category
labels, and a per-repo description/category/featured map), fetches the owner's
public repositories from the GitHub API with the runner's authenticated token,
merges the two, and rewrites ONLY the regions of the README that sit between the
HTML comment markers. Everything outside the markers is human-written and is
never touched.

Two regions are produced:
  * the badge row        (between the badges markers)  -- follower/public-repo
                            and project counts, as shields.io badges
  * the project list     (between the projects markers) -- a "Featured" block
                            plus one section per category

Configurable via ``profile-data.json`` (preferred) or environment variables:
  owner                  PROFILE_OWNER            -- the GitHub login to read
  markers.*              PROFILE_BADGES_START / PROFILE_BADGES_END /
                         PROFILE_PROJECTS_START / PROFILE_PROJECTS_END
  README path            PROFILE_README           -- default <repo root>/README.md
  data path              PROFILE_DATA             -- default <repo root>/profile-data.json

The script is expected at ``.github/scripts/update_profile.py``, so the repo root
is two directories up. For local runs / tests you can also set:
  MOCK_REPOS_JSON        path to a JSON file holding the repo list (skips the API)
  MOCK_PUBLIC_REPOS      integer public-repo count (skips the API)
  GH_TOKEN / GITHUB_TOKEN  token for the API calls
"""
import json
import os
import re
import sys
import urllib.request

# --------------------------------------------------------------------------- #
# Paths (overridable)
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PROFILE_ROOT") or os.path.dirname(os.path.dirname(_HERE))
DATA_FILE = os.environ.get("PROFILE_DATA") or os.path.join(ROOT, "profile-data.json")
README = os.environ.get("PROFILE_README") or os.path.join(ROOT, "README.md")

# --------------------------------------------------------------------------- #
# Defaults (used when the config omits a key)
# --------------------------------------------------------------------------- #
DEFAULT_OWNER = "YOUR_GITHUB_USERNAME"

DEFAULT_MARKERS = {
    "badgesStart": "<!-- BADGES:START -->",
    "badgesEnd": "<!-- BADGES:END -->",
    "projectsStart": "<!-- PROJECTS:START -->",
    "projectsEnd": "<!-- PROJECTS:END -->",
}

DEFAULT_LABELS = {
    "desktop": "Desktop & System Tools",
    "games": "Games & Engines",
    "health": "Health & Medicine",
    "mind": "Mind & Wellbeing",
    "audio": "Audio & Media",
    "business": "Business & Productivity",
    "meta": "Meta & Infrastructure",
    "other": "Other / New",
}


# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #
def _get_json(url, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-kit-updater",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers


def fetch_repos(owner, token):
    mock = os.environ.get("MOCK_REPOS_JSON")
    if mock:
        with open(mock, encoding="utf-8") as fh:
            data = json.load(fh)
        return data["repositories"] if isinstance(data, dict) else data

    repos, url = [], "https://api.github.com/users/%s/repos?per_page=100&sort=full_name" % owner
    while url:
        page, headers = _get_json(url, token)
        repos.extend(page)
        link = headers.get("Link", "")
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt else None
    return repos


def fetch_public_repo_count(owner, token):
    mock = os.environ.get("MOCK_PUBLIC_REPOS")
    if mock:
        return int(mock)
    user, _ = _get_json("https://api.github.com/users/%s" % owner, token)
    return int(user["public_repos"])


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def build_projects(api_repos, data, owner):
    curated = {k.lower(): v for k, v in data.get("repos", {}).items()}
    meta = {m.lower() for m in data.get("metaRepos", [])}
    out = []
    for repo in api_repos:
        name = repo["name"]
        if repo.get("fork"):
            continue
        if name.lower() in meta:
            continue
        entry = curated.get(name.lower())
        if entry:
            desc, cat = entry["description"], entry["category"]
            feat = bool(entry.get("featured"))
        else:  # a brand-new repo nobody has curated yet
            desc = (repo.get("description") or "").strip() or "No description yet."
            cat, feat = "other", False
        landing = ("https://%s.github.io/%s/" % (owner, name)
                   if repo.get("has_pages") else repo["html_url"])
        out.append({"name": name, "desc": desc, "cat": cat,
                    "featured": feat, "landing": landing, "source": repo["html_url"]})
    return out


def render_badges(owner, public_repos, project_count):
    return (
        '<div align="center">\n\n'
        '<img src="https://img.shields.io/github/followers/%s?style=flat-square&label=Followers"'
        ' alt="GitHub followers" onerror="this.style.display=\'none\'" />\n'
        '<img src="https://img.shields.io/badge/Public%%20repos-%d-blue?style=flat-square"'
        ' alt="%d public repositories" onerror="this.style.display=\'none\'" />\n'
        '<img src="https://img.shields.io/badge/Projects-%d-blueviolet?style=flat-square"'
        ' alt="%d projects" onerror="this.style.display=\'none\'" />\n\n'
        '</div>' % (owner, public_repos, public_repos, project_count, project_count)
    )


def render_projects(projects, labels):
    def key(p):
        return p["name"].lower()

    lines = ["## Featured", ""]
    for p in sorted([p for p in projects if p["featured"]], key=key):
        lines.append('- **[%s](%s)** \u2014 %s &nbsp;\u00b7&nbsp; [source](%s)'
                     % (p["name"], p["landing"], p["desc"], p["source"]))
    lines += ["", "## Projects by category", ""]
    order = list(labels.keys())
    if "other" not in order:
        order.append("other")
    for cat in order:
        group = sorted([p for p in projects if p["cat"] == cat], key=key)
        if not group:
            continue
        lines.append("### " + labels.get(cat, DEFAULT_LABELS.get(cat, cat.title())))
        for p in group:
            lines.append('- [%s](%s) \u2014 %s' % (p["name"], p["landing"], p["desc"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_region(text, start, end, content):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        sys.exit("ERROR: markers %s / %s not found in %s" % (start, end, README))
    return pattern.sub(lambda _m: start + "\n\n" + content.strip() + "\n\n" + end, text, count=1)


def resolve_markers(data):
    m = dict(DEFAULT_MARKERS)
    m.update({k: v for k, v in (data.get("markers") or {}).items() if v})
    for key, env in (("badgesStart", "PROFILE_BADGES_START"),
                     ("badgesEnd", "PROFILE_BADGES_END"),
                     ("projectsStart", "PROFILE_PROJECTS_START"),
                     ("projectsEnd", "PROFILE_PROJECTS_END")):
        if os.environ.get(env):
            m[key] = os.environ[env]
    return m


def main():
    with open(DATA_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    labels = {c["key"]: c["label"] for c in data.get("categories", [])}
    markers = resolve_markers(data)
    owner = os.environ.get("PROFILE_OWNER") or data.get("owner") or DEFAULT_OWNER

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    api_repos = fetch_repos(owner, token)
    public_repos = fetch_public_repo_count(owner, token)
    projects = build_projects(api_repos, data, owner)

    with open(README, encoding="utf-8") as fh:
        readme = fh.read()

    readme = replace_region(readme, markers["badgesStart"], markers["badgesEnd"],
                            render_badges(owner, public_repos, len(projects)))
    readme = replace_region(readme, markers["projectsStart"], markers["projectsEnd"],
                            render_projects(projects, labels))
    if not readme.endswith("\n"):
        readme += "\n"

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(readme)

    print("OK owner=%s public_repos=%d projects=%d (featured=%d)"
          % (owner, public_repos, len(projects), sum(1 for p in projects if p["featured"])))


if __name__ == "__main__":
    main()
