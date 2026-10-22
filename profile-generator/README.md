# profile-generator

Regenerates the **marked regions** of a profile README — the badge row and the
categorised project list — from the GitHub API, so the counts and the list stay
current without anyone editing the README by hand.

Everything outside the markers is human-written and is never touched: the script
rewrites only the text between `<!-- BADGES:START -->` / `<!-- BADGES:END -->`
and `<!-- PROJECTS:START -->` / `<!-- PROJECTS:END -->`.

## Files

| File | Goes where in your profile repo |
| --- | --- |
| `update_profile.py` | `.github/scripts/update_profile.py` |
| `profile-data.json` | `profile-data.json` (repo root) |
| `update-profile.yml` | `.github/workflows/update-profile.yml` |

## What it does

1. Reads `profile-data.json` — the owner, the category labels, and a curated
   per-repo map (`description`, `category`, `featured`).
2. Fetches the owner's public repos from `https://api.github.com/users/<owner>/repos`
   using the runner's authenticated token (no rate-limit trouble).
3. Merges the two: a curated repo uses its curated description and category; a
   repo nobody has curated yet falls back to `other` ("Other / New") and its
   GitHub description, so a brand-new repo is never dropped.
4. Rewrites only the marked regions of `README.md`, and the workflow commits the
   file if anything changed.

## Configuring it

The owner name and the markers are both configurable — edit `profile-data.json`:

```json
{
  "owner": "YOUR_GITHUB_USERNAME",
  "markers": {
    "badgesStart": "<!-- BADGES:START -->",
    "badgesEnd": "<!-- BADGES:END -->",
    "projectsStart": "<!-- PROJECTS:START -->",
    "projectsEnd": "<!-- PROJECTS:END -->"
  },
  "categories": [
    { "key": "desktop", "label": "Desktop & System Tools" }
  ],
  "repos": {
    "example-project": {
      "category": "desktop",
      "description": "One-line description of the project.",
      "featured": true
    }
  }
}
```

Every value can also be overridden by environment variables, which is handy for
one-off runs and tests:

| Env var | Overrides |
| --- | --- |
| `PROFILE_OWNER` | `owner` |
| `PROFILE_BADGES_START` / `PROFILE_BADGES_END` | the badge markers |
| `PROFILE_PROJECTS_START` / `PROFILE_PROJECTS_END` | the project markers |
| `PROFILE_ROOT` | the repo root (default: two directories up from the script) |
| `PROFILE_README` | path to the README (default: `<repo root>/README.md`) |
| `PROFILE_DATA` | path to the config (default: `<repo root>/profile-data.json`) |

`MOCK_REPOS_JSON` (a JSON file holding the repo list) and `MOCK_PUBLIC_REPOS` (an
integer) let you run it with no network access at all — useful for a dry run.

## Add the markers to your README

The script fails loudly if a marker pair is missing, so put all four markers in
place first:

```markdown
<!-- BADGES:START -->
<!-- BADGES:END -->

...

<!-- PROJECTS:START -->
<!-- PROJECTS:END -->
```

Then run the workflow once (Actions → *Update profile README* → *Run workflow*)
and the two regions fill in.
