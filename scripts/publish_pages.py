"""Publish and verify the Computational Social Science portfolio on GitHub Pages."""

import argparse
import base64
from collections import Counter, defaultdict
import csv
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
OWNER = "Computational-social-science"
NAME = "computational-social-science.github.io"
ORIGIN = f"https://github.com/{OWNER}/{NAME}.git"
SITE = f"https://{NAME}/"
API = "https://api.github.com"
REPO_PATH = f"/repos/{OWNER}/{NAME}"
PAGES_PATH = REPO_PATH + "/pages"
SOURCE = {"branch": "main", "path": "/"}
EXPERIMENT_FILES = (
    "explorer.html", "figures-a4.pdf", "figures-a4.html",
    "name-rules.html", "name-rules.csv", "name-rules.svg", "name-rules.png", "name-rules.jpg",
    *(f"{panel}.{ext}" for panel in ("english-name-usage", "legacy-workbook")
      for ext in ("svg", "png", "jpg")),
)
EVIDENCE_FIGURES = {
    stem: tuple(f"{stem}.{ext}" for ext in ("svg", "png", "jpg"))
    for stem in ("entity-challenge", "sentence-transfer", "testimony-pairs")
}
EVIDENCE_FIGURE_PAGES = tuple(
    f"matthew-matilda/{name}" for files in EVIDENCE_FIGURES.values() for name in files
)
TESTIMONY_SCORES_PAGE = "matthew-matilda/testimony-scores.csv"
WORD_BUDGET_PAGE = "matthew-matilda/word-budget-scores.csv"
STATUS_CUE_PAGE = "matthew-matilda/status-cue-scores.csv"
STATUS_CUE_FIELDS = (
    "vignette", "block", "condition", "target_alias", "delivery", "response_category", "answer", "prompt",
)
STATUS_CUE_MAX_BYTES = 131_072
STATUS_CUE_APPROVED_SHA256 = "31634709ddba26133df13affa7e32584fe1dffe914d3170cf0f55353f0fa7022"
CONTEXT_CUE_PAGE = "matthew-matilda/context-cue-scores.csv"
CONTEXT_CUE_VIEW_PAGE = "matthew-matilda/context-cue-comparison.html"
CONTEXT_CUE_MAX_BYTES = 131_072
CONTEXT_CUE_APPROVED_SHA256 = "eb5fea4bc5eceda5a73f4511421abfa8f9b7072d6f5f649fff3a26aeb0b88d6d"
CONTEXT_CUE_FIELDS = (
    "slot_id", "block", "vignette", "evidence", "cue", "marked_actor", "gold_actor", "delivery",
    "action_status", "attribution", "endorsed_actors", "explicit_uncertainty", "response_category", "answer", "prompt",
)
WINDOW_SENSITIVITY_PAGE = "matthew-matilda/window-sensitivity.csv"
WINDOW_REPLAY_PAGE = "matthew-matilda/reproduce-windows.py"
PAGE_FILES = (
    "index.html", "manuscript.html", "historical-fame.html", "people.html",
    "assets/matthew-effect-poster.pdf", "assets/matthew-effect-poster.svg", "assets/fieser-portraits.jpg",
    *(f"matthew-matilda/{file}" for file in EXPERIMENT_FILES),
    *EVIDENCE_FIGURE_PAGES,
    TESTIMONY_SCORES_PAGE,
    WORD_BUDGET_PAGE, STATUS_CUE_PAGE, CONTEXT_CUE_PAGE, CONTEXT_CUE_VIEW_PAGE,
    WINDOW_SENSITIVITY_PAGE, WINDOW_REPLAY_PAGE,
    "matthew-matilda/name-usage-view.html", "matthew-matilda/testimony-pairs-view.html",
    "matthew-matilda/report.html", "matthew-matilda/annual.csv",
    "matthew-matilda/method.html", "matthew-matilda/name-queries.csv", "matthew-matilda/witness-panel.csv",
    "matthew-matilda/book-access.csv", "matthew-matilda/english-subcorpora.csv", "matthew-matilda/readable-editions.csv",
)
STATIC = frozenset((*PAGE_FILES, ".nojekyll", "reader.css", "style.css"))
ALLOWED = STATIC | {"README.md", "scripts/sync_horisma.py", "scripts/publish_pages.py",
                   "scripts/context_cue_view.py"}
INTERNAL = re.compile(
    rb"localhost|127\.0\.0\.1|file://|(?<![\w:])[a-z]:[/\\]|"
    rb"data/(?:editorial|intake)/|ops/state/|<code>(?:passage:|evt-)|scientific_acceptance",
    re.IGNORECASE,
)
MAX_FILE_BYTES = 12 * 1024 * 1024
PORTRAIT_PATH = re.compile(r"assets/people/(?=[^/]{1,80}\.webp$)[a-z0-9]+(?:-[a-z0-9]+)*\.webp")
MAX_PORTRAITS = 60
TRANSIENT = {408, 429, 500, 502, 503, 504}


class PublishError(RuntimeError):
    """A bounded publication step could not be verified."""


def status_cue_rows(raw):
    if not 0 < len(raw) <= STATUS_CUE_MAX_BYTES or INTERNAL.search(raw):
        raise ValueError("Status-cue exhibit size or disclosure check failed.")
    reader = csv.DictReader(StringIO(raw.decode("utf-8"), newline=""), strict=True)
    try:
        if tuple(reader.fieldnames or ()) != STATUS_CUE_FIELDS:
            raise ValueError("The status-cue exhibit has an unexpected public schema.")
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError("The status-cue exhibit contains invalid CSV.") from exc
    blocks = defaultdict(list)
    for row in rows:
        if set(row) != set(STATUS_CUE_FIELDS) or None in row.values():
            raise ValueError("Malformed status-cue row.")
        blocks[row["block"]].append(row)
        delivered = row["delivery"] == "DELIVERED"
        if delivered:
            valid = row["response_category"] in {"SOLE_CORRECT", "SOLE_FOIL", "JOINT", "UNRESOLVED", "ABSENT"}
            valid = valid and bool(row["answer"].strip())
        else:
            valid = row["delivery"] == row["response_category"] == "TECHNICAL_FAILURE" and not row["answer"]
        if not valid or row["target_alias"] not in {"A", "B"} or not row["prompt"].strip():
            raise ValueError("Invalid status-cue disposition or stimulus.")
        for field, limit in (("answer", 2_000), ("prompt", 1_000)):
            value = row[field]
            if (len(value) > limit or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
                    or value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))):
                raise ValueError("Unsafe or oversized status-cue text.")
    if set(blocks) != {f"B{number:02d}" for number in range(1, 9)} or len(rows) != 24:
        raise ValueError("The status-cue exhibit must contain all 24 assignments.")
    for group in blocks.values():
        if (len(group) != 3 or {row["condition"] for row in group} != {"neutral", "correct_cued", "wrong_cued"}
                or len({row["vignette"] for row in group}) != 1
                or len({row["target_alias"] for row in group}) != 1):
            raise ValueError("A status-cue block differs from the matched design.")
    if {name: sum(row["vignette"] == name for row in rows) for name in ("interviews", "reading")} != {
        "interviews": 12, "reading": 12,
    }:
        raise ValueError("The status-cue exhibit must contain both vignette families.")
    return rows


def approved_status_cue(raw):
    if sha256(raw).hexdigest() != STATUS_CUE_APPROVED_SHA256:
        raise ValueError("The status-cue exhibit differs from the disclosure-reviewed CSV.")


def context_cue_rows(raw):
    if not 0 < len(raw) <= CONTEXT_CUE_MAX_BYTES or INTERNAL.search(raw):
        raise ValueError("Context-cue exhibit size or disclosure check failed.")
    try:
        reader = csv.DictReader(StringIO(raw.decode("utf-8"), newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != CONTEXT_CUE_FIELDS:
            raise ValueError("The context-cue exhibit has an unexpected public schema.")
        rows = list(reader)
    except (csv.Error, UnicodeDecodeError) as exc:
        raise ValueError("The context-cue exhibit contains invalid CSV.") from exc
    evidence = {"DIRECT", "INDIRECT", "INDETERMINATE"}
    markers = {"NEUTRAL": "", "A_MARKED": "A", "B_MARKED": "B"}
    aliases = {"A", "B"}
    vignettes = {"interviews", "reading"}
    if len(rows) != 72:
        raise ValueError("The context-cue exhibit must contain all 72 assigned outputs.")
    slots = set()
    blocks = defaultdict(list)
    for row in rows:
        if set(row) != set(CONTEXT_CUE_FIELDS) or None in row.values():
            raise ValueError("Malformed context-cue row.")
        if (row["evidence"] not in evidence or row["vignette"] not in vignettes
                or row["cue"] not in markers or row["marked_actor"] != markers[row["cue"]]
                or row["gold_actor"] not in (
                    {"UNDETERMINED"} if row["evidence"] == "INDETERMINATE" else aliases
                )):
            raise ValueError("Invalid context-cue assignment identity.")
        if row["slot_id"] in slots:
            raise ValueError("Duplicate context-cue assignment.")
        slots.add(row["slot_id"])
        if not row["prompt"].strip():
            raise ValueError("Context-cue assignments require a stimulus.")
        if row["delivery"] == "TECHNICAL_FAILURE":
            if row["response_category"] != "TECHNICAL_FAILURE" or any(
                row[key] for key in ("answer", "action_status", "attribution", "endorsed_actors", "explicit_uncertainty")
            ):
                raise ValueError("Technical failures require blank response and grading fields.")
        elif row["delivery"] == "DELIVERED":
            if not row["answer"].strip() or row["response_category"] != context_cue_category(row):
                raise ValueError("Invalid context-cue answer or response category.")
        else:
            raise ValueError("Invalid context-cue delivery state.")
        for field, limit in (("answer", 2_000), ("prompt", 2_000)):
            value = row[field]
            if (len(value) > limit or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
                    or value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))):
                raise ValueError("Unsafe or oversized context-cue text.")
        blocks[row["block"]].append(row)
    if set(blocks) != {f"B{index:02d}" for index in range(1, 9)}:
        raise ValueError("Unexpected context-cue blocks.")
    design = {(level, cue) for level in evidence for cue in markers}
    balance = Counter()
    for block, group in blocks.items():
        names = {row["vignette"] for row in group}
        gold = {row["gold_actor"] for row in group if row["evidence"] != "INDETERMINATE"}
        if (len(group) != 9 or {(row["evidence"], row["cue"]) for row in group} != design
                or len(names) != 1 or len(gold) != 1 or {row["slot_id"] for row in group} != {
                    f"C{block[1:]}-{position:02d}" for position in range(1, 10)
                }):
            raise ValueError("Context-cue rows do not cover the matched block design.")
        balance[next(iter(names)), next(iter(gold))] += 1
    if balance != {(name, alias): 2 for name in vignettes for alias in aliases}:
        raise ValueError("Context-cue blocks do not balance vignette and resolved alias.")
    return rows


def context_cue_category(row):
    action = row["action_status"]
    attribution = row["attribution"]
    actors = row["endorsed_actors"]
    uncertainty = row["explicit_uncertainty"]
    if (action not in {"IN_SCOPE", "OMITTED", "OTHER_ACTION"}
            or attribution not in {"NONE", "ALTERNATIVES", "CATEGORICAL", "TENTATIVE"}
            or actors not in {"", "A", "B", "A+B"} or uncertainty not in {"0", "1"}
            or bool(actors) != (attribution in {"CATEGORICAL", "TENTATIVE"})
            or (attribution != "NONE" or uncertainty == "1") and action != "IN_SCOPE"
            or attribution == "ALTERNATIVES" and uncertainty != "1"):
        raise ValueError("Invalid context-cue grading fields.")
    if actors == "A+B":
        return "JOINT"
    if actors:
        gold = row["gold_actor"]
        if gold == "UNDETERMINED":
            return "SOLE_UNSUPPORTED"
        return "SOLE_CORRECT" if actors == gold else "SOLE_FOIL"
    return "EXPLICIT_UNCERTAINTY" if uncertainty == "1" else "UNASSIGNED"


def approved_context_cue(raw):
    if not CONTEXT_CUE_APPROVED_SHA256 or sha256(raw).hexdigest() != CONTEXT_CUE_APPROVED_SHA256:
        raise ValueError("The context-cue exhibit has not passed its reviewed exact-byte hash gate.")


class PeoplePortraits(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.paths = set()
        self.feed(markup)
        if not 1 <= len(self.paths) <= MAX_PORTRAITS:
            raise PublishError("The people directory exceeds its portrait bounds or has no portraits.")

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            path = dict(attrs).get("src", "")
            if not PORTRAIT_PATH.fullmatch(path):
                raise PublishError(f"Invalid portrait image in the people directory: {path}")
            self.paths.add(path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect)


def git(*args, input_bytes=None, extra_env=None, check=True):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_TRACE")}
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    env.update(extra_env or {})
    try:
        result = subprocess.run(
            ("git", *args), cwd=ROOT, input=input_bytes, capture_output=True, env=env, timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PublishError(f"Git {args[0]} did not complete.") from None
    if check and result.returncode:
        raise PublishError(f"Git {args[0]} failed. Inspect local Git state and access to the assigned repository.")
    return result


def local_edition():
    if git("branch", "--show-current").stdout.strip() != b"main":
        raise PublishError("Check out main before publishing.")
    if git("status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise PublishError("Commit the reviewed portfolio files and leave a clean working tree.")
    head = git("rev-parse", "HEAD").stdout.decode("ascii").strip()
    paths = git("ls-tree", "-r", "--name-only", "-z", head).stdout.decode("utf-8").split("\0")[:-1]
    declared_portraits = PeoplePortraits(git("show", f"{head}:people.html").stdout.decode("utf-8")).paths
    if not STATIC | declared_portraits <= set(paths) <= ALLOWED | declared_portraits:
        raise PublishError("The committed tree differs from the public portfolio file list.")
    # A push includes previous revisions. Validate the paths and file modes of those revisions too.
    history = git("log", "--format=", "--raw", "--no-abbrev", "--no-renames", "--root", "-m", head)
    checked = set()
    for line in history.stdout.decode("utf-8").splitlines():
        if not line:
            continue
        values, _, path = line.partition("\t")
        old_mode, mode, old_blob, blob, _change = values.lstrip(":").split()
        portrait = PORTRAIT_PATH.fullmatch(path)
        if (path not in ALLOWED and not portrait) or {old_mode, mode} - {"000000", "100644", "100755"}:
            raise PublishError("Git history contains a path or file mode outside the public portfolio.")
        for oid in (old_blob, blob):
            if (path not in STATIC and not portrait) or (path, oid) in checked or set(oid) == {"0"}:
                continue
            checked.add((path, oid))
            limit = (CONTEXT_CUE_MAX_BYTES if path == CONTEXT_CUE_PAGE else
                     STATUS_CUE_MAX_BYTES if path == STATUS_CUE_PAGE else MAX_FILE_BYTES)
            if int(git("cat-file", "-s", oid).stdout) > limit:
                raise PublishError(f"{path} exceeds the public file size limit.")
            if path == STATUS_CUE_PAGE:
                raw = git("cat-file", "blob", oid).stdout
                status_cue_rows(raw)
                approved_status_cue(raw)
            if path == CONTEXT_CUE_PAGE:
                raw = git("cat-file", "blob", oid).stdout
                context_cue_rows(raw)
                approved_context_cue(raw)
            inspect_text = path.endswith((".html", ".svg", ".css", ".py")) or path in {
                WORD_BUDGET_PAGE, CONTEXT_CUE_PAGE, WINDOW_SENSITIVITY_PAGE, WINDOW_REPLAY_PAGE,
            }
            if inspect_text and INTERNAL.search(git("cat-file", "blob", oid).stdout):
                raise PublishError(f"{path} has a private workspace reference in Git history.")
    return head


def credential():
    query = f"protocol=https\nhost=github.com\nusername={OWNER}\npath={OWNER}/{NAME}.git\n\n"
    result = git("credential", "fill", input_bytes=query.encode(), check=False)
    parts = dict(line.split("=", 1) for line in result.stdout.decode("utf-8").splitlines() if "=" in line)
    token = parts.get("password")
    if result.returncode or not token:
        raise PublishError(f"No usable GitHub credential for {OWNER}. Sign in locally with Git Credential Manager.")
    return token


def read_url(url, *, token=None, payload=None, accept_missing=False, max_bytes=MAX_FILE_BYTES):
    headers = {"User-Agent": "computational-social-science-pages-publisher", "Cache-Control": "no-cache"}
    if token:
        headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        })
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        with OPENER.open(req, timeout=10) as response:
            body = response.read(max_bytes + 1)
    except HTTPError as exc:
        if exc.code == 404 and accept_missing:
            return None
        error = PublishError(f"{req.get_method()} {req.host}{req.selector.split('?')[0]} returned HTTP {exc.code}.")
        if exc.code in TRANSIENT:
            raise URLError(error) from None
        raise error from None
    except TimeoutError:
        raise URLError(f"{req.host} did not respond in time.") from None
    if len(body) > max_bytes:
        raise PublishError("The returned file exceeds the public file size limit.")
    return body


def api(path, token, *, payload=None, missing=False):
    body = read_url(API + path, token=token, payload=payload, accept_missing=missing, max_bytes=1_048_576)
    return None if body is None else json.loads(body)


def ensure_api_resource(path, create_path, token, payload):
    # Recheck after an ambiguous create response. A second POST is unnecessary.
    try:
        api(create_path, token, payload=payload)
    except (PublishError, URLError):
        existing = api(path, token, missing=True)
        if existing is None:
            raise
        return existing
    return api(path, token)


def verify_origin():
    remotes = git("remote").stdout.decode().splitlines()
    if "origin" not in remotes:
        return False
    for flags in (("--all",), ("--push", "--all")):
        if git("remote", "get-url", *flags, "origin").stdout.decode().splitlines() != [ORIGIN]:
            raise PublishError(f"Origin must resolve to {ORIGIN} for fetch and push.")
    return True


def push_origin(head, token):
    if not verify_origin():
        git("remote", "add", "origin", ORIGIN)
        verify_origin()
    # Git receives the checked token through per-process config, leaving no credential in argv or Git config files.
    basic = base64.b64encode(f"{OWNER}:{token}".encode()).decode("ascii")
    settings = (
        ("http.https://github.com/.extraHeader", ""),
        ("http.https://github.com/.extraHeader", f"Authorization: Basic {basic}"),
        ("http.followRedirects", "false"),
        ("credential.helper", ""),
    )
    env = {"GIT_CONFIG_COUNT": str(len(settings))}
    for index, (key, value) in enumerate(settings):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    refs = dict(line.split("\t", 1)[::-1] for line in
                git("ls-remote", "origin", extra_env=env).stdout.decode().splitlines())
    upstream = refs.get("refs/heads/main")
    if refs and not upstream:
        raise PublishError("Origin already has references outside main. Inspect its history before publishing.")
    if upstream and git("merge-base", "--is-ancestor", upstream, head, check=False).returncode:
        raise PublishError("Origin main is unavailable locally, unrelated or ahead. Inspect the remote history.")
    if git("rev-parse", "main").stdout.decode().strip() != head:
        raise PublishError("Local main changed during verification.")
    if upstream != head:
        git("push", "--no-follow-tags", "--recurse-submodules=no", "origin",
            f"{head}:refs/heads/main", extra_env=env)


def verify_pages_config(pages):
    if (pages.get("source") != SOURCE or pages.get("build_type", "legacy") != "legacy" or pages.get("cname") or
            pages.get("html_url", "").rstrip("/").casefold() != SITE.rstrip("/")):
        raise PublishError("This repository has a different Pages source or custom domain. Inspect its existing settings.")


def verify_live(head, token, timeout):
    portraits = PeoplePortraits(git("show", f"{head}:people.html").stdout.decode("utf-8")).paths
    files = {"": "index.html", **{path: path for path in (*PAGE_FILES, "style.css", "reader.css", *sorted(portraits))}}
    expected = {path: git("show", f"{head}:{file}").stdout for path, file in files.items()}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            build = api(PAGES_PATH + "/builds/latest", token, missing=True)
            if build and build.get("commit") == head:
                if build.get("status") == "errored":
                    raise PublishError("GitHub Pages reported an error for the requested commit.")
                if build.get("status") == "built" and all(
                    read_url(f"{SITE}{path}?edition={head}", accept_missing=True) == body
                    for path, body in expected.items()
                ):
                    return
        except URLError:
            pass
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise PublishError("Pages did not serve the requested commit within the verification window. Run again to recheck.")


def publish(head, timeout):
    verify_origin()
    token = credential()
    if api("/user", token).get("login") != OWNER:
        raise PublishError(f"The GitHub credential must belong to {OWNER}.")
    repo = api(REPO_PATH, token, missing=True)
    if repo is None:
        repo = ensure_api_resource(REPO_PATH, "/user/repos", token, {"name": NAME, "private": False, "auto_init": False})
    if (repo.get("full_name", "").casefold() != f"{OWNER}/{NAME}".casefold() or
            repo.get("private") is not False or repo.get("archived")):
        raise PublishError("The target is not the expected public, writable portfolio repository.")
    pages = api(PAGES_PATH, token, missing=True)
    if pages:
        verify_pages_config(pages)
    elif repo.get("has_pages"):
        raise PublishError("GitHub reports a Pages site, but its configuration could not be read.")
    push_origin(head, token)
    if pages is None:
        pages = ensure_api_resource(PAGES_PATH, PAGES_PATH, token, {"source": SOURCE, "build_type": "legacy"})
        verify_pages_config(pages)
    verify_live(head, token, timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Check the committed site locally without signing in.")
    parser.add_argument("--timeout", type=int, default=300, choices=range(10, 901), metavar="SECONDS")
    args = parser.parse_args()
    try:
        head = local_edition()
        if args.check_only:
            print(f"Local public edition verified at {head}")
        else:
            publish(head, args.timeout)
            print(f"Verified {SITE} at {head}")
    except (PublishError, URLError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
