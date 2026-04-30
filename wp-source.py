#!/usr/bin/env python3
"""
wpa - WordPress Production Analyzer

Usage:
    wpa <path>                            Interactive guided setup + saves wpa-report-*.txt
    wpa setup       <path>                Same as above (explicit)
    wpa install                           Install as 'wpa' to /usr/local/bin
    wpa info        <path>                WP version, DB config, themes, plugins
    wpa disk        <path>                Large directories and suspicious files
    wpa gitignore   <path>                Generate .gitignore
    wpa git-init    <path> [remote-url]   Init git + gitignore + push
    wpa local-setup <path>                Step-by-step local dev guide
    wpa deploy-key                        Show server SSH public key

Examples:
    wpa /var/www/html                     # full guided setup
    wpa info /var/www/html
    wpa disk /var/www/html
"""

import datetime
import os
import re
import sys
import shutil
import socket
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BINARY_EXTS = {
    ".sql", ".sql.gz", ".zip", ".tar", ".tar.gz", ".tgz", ".bak",
    ".rar", ".7z", ".dump", ".gz", ".xz", ".psd", ".ai", ".sketch",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv",
}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm", ".flv"}
_DOC_EXTS   = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}

# Paths already covered by the default .gitignore — skip when scanning
_DEFAULT_IGNORED = {
    "wp-content/uploads", "wp-content/cache", "wp-content/backup-db",
    "wp-content/backups", "wp-content/upgrade", "wp-content/wflogs",
    "wp-content/blogs.dir", "wp-includes", "wp-admin",
}


# ---------------------------------------------------------------------------
# Tee: write to terminal + file simultaneously
# ---------------------------------------------------------------------------

class _Tee:
    def __init__(self, file):
        self._file = file
        self._stdout = sys.stdout

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def isatty(self):
        return self._stdout.isatty()


# ---------------------------------------------------------------------------
# WordPress detection
# ---------------------------------------------------------------------------

def find_wp_root(path: str) -> Path:
    root = Path(path).resolve()
    if not root.exists():
        die(f"Path not found: {root}")
    if not (root / "wp-config.php").exists() and not (root / "wp-login.php").exists():
        die(f"No WordPress installation found at: {root}")
    return root


def get_wp_version(root: Path) -> str:
    f = root / "wp-includes" / "version.php"
    if not f.exists():
        return "unknown"
    m = re.search(r"\$wp_version\s*=\s*'([^']+)'", f.read_text(errors="ignore"))
    return m.group(1) if m else "unknown"


def get_themes(root: Path) -> list:
    d = root / "wp-content" / "themes"
    if not d.exists():
        return []
    themes = []
    for item in sorted(d.iterdir()):
        if not item.is_dir() or not (item / "style.css").exists():
            continue
        info = {"slug": item.name}
        text = (item / "style.css").read_text(errors="ignore")
        for field in ("Theme Name", "Version", "Author", "Template"):
            m = re.search(rf"{field}:\s*(.+)", text)
            if m:
                info[field.lower().replace(" ", "_")] = m.group(1).strip()
        themes.append(info)
    return themes


def get_plugins(root: Path) -> list:
    d = root / "wp-content" / "plugins"
    if not d.exists():
        return []
    plugins = []
    for item in sorted(d.iterdir()):
        if item.is_dir():
            main = _find_plugin_main_file(item)
            info = {"slug": item.name, "type": "dir", "main_file": main}
            if main:
                text = (item / main).read_text(errors="ignore")
                for field in ("Plugin Name", "Version", "Author"):
                    m = re.search(rf"{field}:\s*(.+)", text)
                    if m:
                        info[field.lower().replace(" ", "_")] = m.group(1).strip()
            plugins.append(info)
        elif item.suffix == ".php":
            plugins.append({"slug": item.stem, "type": "file", "main_file": item.name})
    return plugins


def _find_plugin_main_file(plugin_dir: Path) -> str | None:
    for f in plugin_dir.glob("*.php"):
        try:
            if "Plugin Name:" in f.read_text(errors="ignore"):
                return f.name
        except Exception:
            pass
    return None


def parse_wp_config(root: Path) -> dict:
    f = root / "wp-config.php"
    if not f.exists():
        return {}
    text = f.read_text(errors="ignore")
    result = {}
    for key in ("DB_NAME", "DB_USER", "DB_HOST", "DB_CHARSET", "table_prefix"):
        if key == "table_prefix":
            m = re.search(r"\$table_prefix\s*=\s*'([^']*)'", text)
        else:
            m = re.search(rf"define\(\s*['\"]" + key + r"['\"],\s*'([^']*)'\s*\)", text)
        if m:
            result[key] = m.group(1)
    result["DB_PASSWORD"] = "***hidden***"
    if "MULTISITE" in text and "define" in text:
        if re.search(r"define\(\s*['\"]MULTISITE['\"]", text):
            result["multisite"] = True
    return result


def get_mu_plugins(root: Path) -> list:
    d = root / "wp-content" / "mu-plugins"
    if not d.exists():
        return []
    return [f.name for f in sorted(d.iterdir()) if f.suffix == ".php" or f.is_dir()]


# ---------------------------------------------------------------------------
# Disk helpers
# ---------------------------------------------------------------------------

def du(path: Path, timeout: int = 30) -> int:
    try:
        r = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout:
            return int(r.stdout.split()[0])
    except Exception:
        pass
    return 0


def du_human(path: Path, timeout: int = 30) -> str:
    try:
        r = subprocess.run(["du", "-sh", str(path)], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout:
            return r.stdout.split()[0]
    except Exception:
        pass
    return "?"


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def find_large_files(root: Path, min_mb: int = 5, exclude_dir: str = "") -> list[tuple[int, Path]]:
    """Return list of (size_bytes, path) for files > min_mb. Falls back to os.walk if find unavailable."""
    min_bytes = min_mb * 1024 * 1024

    # Try GNU find first (fast, Linux/macOS)
    cmd = ["find", str(root), "-type", "f", "-size", f"+{min_mb}M"]
    if exclude_dir:
        cmd += ["!", "-path", f"{exclude_dir}/*"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            results = []
            for line in r.stdout.strip().splitlines():
                if line:
                    p = Path(line)
                    try:
                        results.append((p.stat().st_size, p))
                    except OSError:
                        pass
            return sorted(results, reverse=True)
    except Exception:
        pass

    # Python fallback (cross-platform, slower on large trees)
    results = []
    exclude_path = Path(exclude_dir) if exclude_dir else None
    try:
        for dirpath, _, filenames in os.walk(root):
            dp = Path(dirpath)
            if exclude_path and (dp == exclude_path or dp.is_relative_to(exclude_path)):
                continue
            for fname in filenames:
                fp = dp / fname
                try:
                    size = fp.stat().st_size
                    if size >= min_bytes:
                        results.append((size, fp))
                except OSError:
                    pass
    except Exception:
        pass
    return sorted(results, reverse=True)


def get_upload_type_breakdown(uploads: Path) -> dict[str, list[int]]:
    try:
        r = subprocess.run(
            ["find", str(uploads), "-type", "f", "-printf", "%s %f\n"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return {}
        result: dict[str, list[int]] = {}
        for line in r.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            try:
                size = int(parts[0])
            except ValueError:
                continue
            ext = Path(parts[1]).suffix.lower() or "(no ext)"
            if ext not in result:
                result[ext] = [0, 0]
            result[ext][0] += 1
            result[ext][1] += size
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Interactive setup helpers
# ---------------------------------------------------------------------------

def step(n: int, total: int, title: str):
    print(f"\n{'='*60}")
    print(f"  [{n}/{total}] {title}")
    print(f"{'='*60}\n")


def ask(prompt: str, default: str = "") -> str:
    """Safe input() — returns default on EOF/non-interactive."""
    try:
        val = input(prompt)
        return val.strip() if val.strip() else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def scan_large_not_ignored(root: Path, threshold_mb: int = 50) -> list[tuple[int, str, str]]:
    """
    Find items that will be tracked in git (not in default .gitignore) but are large.
    Returns list of (size_bytes, rel_path, label).
    Also catches binary files (sql/zip/bak) > 1MB regardless of threshold.
    """
    threshold = threshold_mb * 1024 * 1024
    candidates: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    def add(size: int, rel: str, label: str):
        if rel not in seen:
            seen.add(rel)
            candidates.append((size, rel, label))

    # Scan each plugin individually
    plugins_dir = root / "wp-content" / "plugins"
    if plugins_dir.exists():
        print("  Scanning plugins...", end="", flush=True)
        for d in sorted(plugins_dir.iterdir()):
            if d.is_dir():
                size = du(d, timeout=20)
                if size > threshold:
                    rel = f"wp-content/plugins/{d.name}"
                    add(size, rel, f"plugin tracked in git")
        print(" done")

    # Scan each theme individually
    themes_dir = root / "wp-content" / "themes"
    if themes_dir.exists():
        print("  Scanning themes...", end="", flush=True)
        for d in sorted(themes_dir.iterdir()):
            if d.is_dir():
                size = du(d, timeout=20)
                if size > threshold:
                    rel = f"wp-content/themes/{d.name}"
                    add(size, rel, f"theme tracked in git")
        print(" done")

    # Other wp-content/ subdirs not covered by default gitignore
    wp_content = root / "wp-content"
    if wp_content.exists():
        for item in sorted(wp_content.iterdir()):
            rel = item.relative_to(root).as_posix()
            if rel in _DEFAULT_IGNORED:
                continue
            if rel in ("wp-content/plugins", "wp-content/themes", "wp-content/mu-plugins"):
                continue
            if item.is_dir():
                size = du(item, timeout=20)
                if size > threshold:
                    add(size, rel, "wp-content subdir, not gitignored")

    # Binary files outside uploads (always suspicious regardless of threshold)
    uploads_str = str(root / "wp-content" / "uploads")
    for size, path in find_large_files(root, min_mb=1, exclude_dir=uploads_str):
        if path.suffix.lower() in _BINARY_EXTS:
            rel = path.relative_to(root).as_posix()
            add(size, rel, f"binary file {path.suffix} — should not be in git")

    return sorted(candidates, reverse=True)


def get_or_create_ssh_key() -> tuple[str, str]:
    """Returns (public_key_content, pub_key_path). Generates key if none found."""
    ssh_dir = Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        pub = ssh_dir / f"{name}.pub"
        if pub.exists():
            return pub.read_text().strip(), str(pub)

    print("  No SSH key found. Generating ed25519 key...")
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key_path = ssh_dir / "id_ed25519"
    try:
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-C", f"deploy@{_hostname()}",
             "-f", str(key_path), "-N", ""],
            check=True, capture_output=True,
        )
        print(f"  Generated: {key_path}")
    except Exception as e:
        die(f"Could not generate SSH key: {e}")

    return (ssh_dir / "id_ed25519.pub").read_text().strip(), str(ssh_dir / "id_ed25519.pub")


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "server"


def _parse_git_host(remote: str) -> str:
    m = re.search(r"@([^:/]+)", remote)
    if m:
        return m.group(1)
    m = re.search(r"https?://([^/]+)", remote)
    if m:
        return m.group(1)
    return remote


def _test_ssh(host: str):
    print(f"  Testing connection to {host}...", end="", flush=True)
    try:
        r = subprocess.run(
            ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=10", f"git@{host}"],
            capture_output=True, text=True, timeout=15,
        )
        output = (r.stdout + r.stderr).strip()
        if any(x in output for x in ("Welcome", "successfully authenticated", "Hi ")):
            print(f" OK")
            print(f"  {output[:120]}")
        else:
            print(f" (response below)")
            print(f"  {output[:120]}")
    except Exception:
        print(f" could not connect — will know for sure when pushing")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_setup(root: Path):
    """Interactive guided flow: info → large-file scan → gitignore → remote → deploy key → push."""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path.cwd() / ".wpa-reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"wpa-report-{stamp}.txt"
    report_file = open(report_path, "w", encoding="utf-8")
    sys.stdout = _Tee(report_file)

    try:
        _cmd_setup_inner(root)
    finally:
        sys.stdout = report_file._stdout
        report_file.close()

    print(f"\n  Report saved: {report_path}")


def _cmd_setup_inner(root: Path):
    # 1. Info
    step(1, 5, "WordPress Analysis")
    cmd_info(root)

    # 2. Scan large items + ask about each
    step(2, 5, "Scanning for large items (>50MB) not covered by default .gitignore")
    print("  Default .gitignore already covers:")
    print("    uploads/, cache/, backup-db/, wp-admin/, wp-includes/, ...\n")
    print("  Scanning items that WILL be tracked in git:\n")

    candidates = scan_large_not_ignored(root, threshold_mb=50)
    extra_ignores: list[str] = []

    if candidates:
        print(f"\n  Found {len(candidates)} item(s) to review:\n")
        for size, rel, label in candidates:
            print(f"    {format_size(size):>10}  {rel}")
            print(f"                ({label})")
            ans = ask("    Add to .gitignore? [y/N]: ", "n")
            if ans.lower() in ("y", "yes"):
                extra_ignores.append(rel)
                print("    -> Will be ignored.\n")
            else:
                print("    -> Will be tracked in git.\n")
    else:
        print("\n  No large items found outside default coverage.\n")

    # 3. Generate .gitignore
    step(3, 5, "Generating .gitignore")
    cmd_gitignore(root, extra_ignores)

    # 4. Git remote
    step(4, 5, "Git Remote")
    print("  Enter your git remote URL.")
    print("  Examples:")
    print("    git@gitlab.com:youruser/yoursite.git")
    print("    git@github.com:youruser/yoursite.git\n")
    remote = ask("  Remote URL (leave blank to skip push for now): ")
    if not remote:
        print("\n  Skipping push. Will do git init locally only.\n")

    # 5. Deploy key
    step(5, 5, "SSH Deploy Key")
    key, key_path = get_or_create_ssh_key()
    bar = "-" * 58

    print(f"\n  Public key ({key_path}):")
    print(f"  {bar}")
    print(f"  {key}")
    print(f"  {bar}")

    if remote:
        host = _parse_git_host(remote)
        print(f"\n  Add this key to your Git server:")
        print(f"")
        if "gitlab" in host:
            print(f"    GitLab > Project > Settings > Repository > Deploy keys")
        elif "github" in host:
            print(f"    GitHub > Repo > Settings > Deploy keys > Add deploy key")
        elif "bitbucket" in host:
            print(f"    Bitbucket > Repo > Repository settings > Access keys")
        else:
            print(f"    Git server admin > SSH/Deploy keys")
        print(f"")
        print(f"    Title       : deploy@{_hostname()}")
        print(f"    Key         : (paste the key above)")
        print(f"    Write access: NO  (read-only is enough for clone/pull)")
        print(f"")
        ask("  Press Enter when you've added the deploy key... ")
        _test_ssh(host)
    else:
        print("\n  (No remote — deploy key not needed yet)")
        print(f"  When you add a remote later, use this key as your deploy key.")

    # Git init + push
    print()
    cmd_git_init(root, remote if remote else None)

    print("\n  Setup complete!")
    if remote:
        print(f"\n  Local dev next steps:")
        print(f"    wpa local-setup {root}")


def cmd_install():
    target = Path("/usr/local/bin/wpa")
    src = Path(__file__).resolve()

    if not os.access("/usr/local/bin", os.W_OK):
        print("  Need write permission. Run:")
        print(f"    sudo cp {src} /usr/local/bin/wpa && sudo chmod +x /usr/local/bin/wpa")
        return

    shutil.copy2(src, target)
    target.chmod(0o755)
    print(f"  Installed: {target}")
    print("  Usage: wpa /var/www/html")


def cmd_info(root: Path):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  WordPress Info: {root}")
    print(f"{sep}\n")

    print(f"  Version       : {get_wp_version(root)}")

    cfg = parse_wp_config(root)
    if cfg:
        print(f"\n  Database")
        print(f"    DB_NAME     : {cfg.get('DB_NAME', '?')}")
        print(f"    DB_USER     : {cfg.get('DB_USER', '?')}")
        print(f"    DB_HOST     : {cfg.get('DB_HOST', '?')}")
        print(f"    DB_PASS     : {cfg.get('DB_PASSWORD')}")
        print(f"    table_prefix: {cfg.get('table_prefix', 'wp_')}")
        if cfg.get("multisite"):
            print("    multisite   : YES")

    themes = get_themes(root)
    if themes:
        print(f"\n  Themes ({len(themes)} installed)")
        for t in themes:
            parent = f"  [child of: {t.get('template')}]" if t.get("template") else ""
            print(f"    - {t['slug']:<30} v{t.get('version','?')}  {t.get('theme_name','')}{parent}")

    plugins = get_plugins(root)
    if plugins:
        print(f"\n  Plugins ({len(plugins)})")
        for p in plugins:
            print(f"    - {p['slug']:<35} {p.get('plugin_name','')} v{p.get('version','?')}")

    mu = get_mu_plugins(root)
    if mu:
        print(f"\n  Must-Use Plugins ({len(mu)})")
        for m in mu:
            print(f"    - {m}")

    print(f"\n  uploads/ size : {du_human(root / 'wp-content' / 'uploads')}\n")


def cmd_disk(root: Path):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Disk Usage: {root}")
    print(f"{sep}\n")

    # Directory overview
    key_dirs = [
        ("wp-content/uploads",   True),
        ("wp-content/plugins",   False),
        ("wp-content/themes",    False),
        ("wp-content/cache",     True),
        ("wp-content/backup-db", True),
        ("wp-content/backups",   True),
        ("wp-content/wflogs",    True),
        ("wp-content/upgrade",   True),
        ("wp-includes",          True),
        ("wp-admin",             True),
    ]
    rows = [(du(root / r, 60), r, ig) for r, ig in key_dirs if (root / r).exists()]
    rows.sort(reverse=True)

    print("  Directory sizes:")
    for size, rel, ignored in rows:
        flag = "  [gitignored]" if ignored else "  [tracked in git]"
        print(f"    {format_size(size):>10}  {rel}/{flag}")

    # Uploads breakdown
    uploads = root / "wp-content" / "uploads"
    if uploads.exists():
        print(f"\n  File types in uploads/:")
        bd = get_upload_type_breakdown(uploads)
        if bd:
            images = sum(v[1] for k, v in bd.items() if k in _IMAGE_EXTS)
            videos = sum(v[1] for k, v in bd.items() if k in _VIDEO_EXTS)
            docs   = sum(v[1] for k, v in bd.items() if k in _DOC_EXTS)
            other  = sum(v[1] for k, v in bd.items() if k not in _IMAGE_EXTS | _VIDEO_EXTS | _DOC_EXTS)
            total  = sum(v[0] for v in bd.values())
            print(f"    {format_size(images):>10}  images  (jpg/png/gif/webp...)")
            print(f"    {format_size(videos):>10}  video   (mp4/avi/mov...)")
            print(f"    {format_size(docs):>10}  docs    (pdf/doc/xls...)")
            print(f"    {format_size(other):>10}  other")
            print(f"    {'':>10}  {total} files total")
            print(f"\n    Top extensions:")
            for ext, (cnt, sz) in sorted(bd.items(), key=lambda x: -x[1][1])[:8]:
                print(f"      {format_size(sz):>10}  {ext} ({cnt} files)")
        else:
            print("    (could not scan)")

    # Plugins by size
    plugins_dir = root / "wp-content" / "plugins"
    if plugins_dir.exists():
        print(f"\n  Plugins by size (top 10):")
        psize = sorted(
            [(du(d, 15), d.name) for d in plugins_dir.iterdir() if d.is_dir()],
            reverse=True,
        )
        for size, name in psize[:10]:
            print(f"    {format_size(size):>10}  {name}/")

    # Suspicious large files outside uploads
    uploads_str = str(root / "wp-content" / "uploads")
    print(f"\n  Suspicious files outside uploads/ (>5MB):")
    large = find_large_files(root, min_mb=5, exclude_dir=uploads_str)
    if large:
        for size, path in large[:20]:
            rel = path.relative_to(root)
            warn = "  <-- add to .gitignore!" if path.suffix.lower() in _BINARY_EXTS else ""
            print(f"    {format_size(size):>10}  {rel}{warn}")
    else:
        print("    (none found)")

    # Estimated git size
    themes_sz  = du(root / "wp-content" / "themes",     30) if (root / "wp-content" / "themes").exists() else 0
    plugins_sz = du(root / "wp-content" / "plugins",    30) if plugins_dir.exists() else 0
    mu_sz      = du(root / "wp-content" / "mu-plugins", 15) if (root / "wp-content" / "mu-plugins").exists() else 0
    print(f"\n  Estimated git repo size (themes + plugins + mu-plugins):")
    print(f"    ~{format_size(themes_sz + plugins_sz + mu_sz)}  (before removing stock items)\n")


def cmd_gitignore(root: Path, extra_ignores: list[str] | None = None):
    gitignore_path = root / ".gitignore"
    content = build_gitignore(root, extra_ignores or [])

    if gitignore_path.exists():
        if gitignore_path.read_text() == content:
            print("  .gitignore already up to date.")
            return
        (root / ".gitignore.bak").write_text(gitignore_path.read_text())
        print("  Backed up existing .gitignore to .gitignore.bak")

    gitignore_path.write_text(content)
    print(f"  Generated: {gitignore_path}")
    print("\n  TRACKED (custom code):")
    print("    wp-content/themes/     all themes")
    print("    wp-content/plugins/    all plugins")
    print("    wp-content/mu-plugins/")
    print("    wp-config-sample.php   (template, no credentials)")
    print("\n  IGNORED:")
    print("    WordPress core         wp-admin/ wp-includes/ root PHP files")
    print("    Credentials            wp-config.php")
    print("    Media                  wp-content/uploads/")
    print("    Cache & generated      wp-content/cache/ upgrade/ backup-db/")
    print("    Logs, OS, editor files")
    if extra_ignores:
        print("    Extra (user-confirmed):")
        for e in extra_ignores:
            print(f"      {e}")
    print("\n  Review the commented plugin/theme list at the bottom of .gitignore")
    print("  and uncomment stock/vendor items you do NOT want tracked.\n")


def cmd_git_init(root: Path, remote: str | None):
    git_dir = root / ".git"
    if git_dir.exists():
        print("  Git already initialized.")
    else:
        run_git(root, ["git", "init"])
        print("  Initialized git repo.")

    # Create .gitignore only if not already present (setup flow pre-creates it)
    if not (root / ".gitignore").exists():
        cmd_gitignore(root)

    run_git(root, ["git", "add", "-A"])
    status = run_git(root, ["git", "status", "--short"], capture=True)
    if not (status or "").strip():
        print("  Nothing to commit.")
    else:
        run_git(root, ["git", "commit", "-m", "init: WordPress source (custom code only)"])
        print("  Created initial commit.")

    if remote:
        # Check if remote already exists
        existing = run_git(root, ["git", "remote"], capture=True) or ""
        if "origin" not in existing.split():
            run_git(root, ["git", "remote", "add", "origin", remote])
        branch = (run_git(root, ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True) or "main").strip()
        run_git(root, ["git", "push", "-u", "origin", branch])
        print(f"  Pushed to {remote}  (branch: {branch})")
        print(f"\n  Clone on local:")
        print(f"    git clone {remote}\n")
    else:
        branch = (run_git(root, ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True) or "main").strip()
        print(f"\n  To push later:")
        print(f"    git remote add origin <url>")
        print(f"    git push -u origin {branch}\n")


def cmd_local_setup(root: Path):
    cfg = parse_wp_config(root)
    ver = get_wp_version(root)
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  Local Dev Setup Guide")
    print(f"{sep}\n")
    print(f"  1. Clone your git repo:")
    print(f"       git clone <your-repo-url> mysite && cd mysite\n")
    print(f"  2. Download WordPress core (same version as production):")
    print(f"       wp core download --version={ver} --skip-content")
    print(f"       # or: wget https://wordpress.org/wordpress-{ver}.zip")
    print(f"       #     unzip wordpress-{ver}.zip && cp -r wordpress/* . && rm -rf wordpress\n")
    print(f"  3. Create wp-config.php:")
    print(f"       cp wp-config-sample.php wp-config.php")
    print(f"       # Edit:")
    print(f"       #   DB_NAME={cfg.get('DB_NAME','your_db')}")
    print(f"       #   DB_USER=root  (local)")
    print(f"       #   DB_HOST=localhost")
    print(f"       #   DB_PASSWORD=<local_pass>")
    print(f"       #   table_prefix={cfg.get('table_prefix','wp_')}\n")
    print(f"  4. Import database:")
    print(f"       # On production:")
    print(f"       mysqldump -u {cfg.get('DB_USER','user')} -p {cfg.get('DB_NAME','dbname')} > dump.sql")
    print(f"       # On local:")
    print(f"       mysql -u root -p localdb < dump.sql")
    print(f"       wp search-replace 'https://yourdomain.com' 'http://localhost'\n")
    print(f"  5. Copy uploads (optional):")
    print(f"       rsync -avz user@server:/var/www/html/wp-content/uploads/ ./wp-content/uploads/\n")
    print(f"  Tools: WP-CLI, LocalWP, Lando, Docker\n")


def cmd_deploy_key():
    key, key_path = get_or_create_ssh_key()
    bar = "-" * 58
    print(f"\n  Public key ({key_path}):")
    print(f"  {bar}")
    print(f"  {key}")
    print(f"  {bar}")
    print(f"\n  Add to:")
    print(f"    GitLab  > Project > Settings > Repository > Deploy keys")
    print(f"    GitHub  > Repo > Settings > Deploy keys > Add deploy key")
    print(f"    Bitbucket > Repository settings > Access keys\n")
    print(f"  Title: deploy@{_hostname()}")
    print(f"  Write access: NO\n")


# ---------------------------------------------------------------------------
# .gitignore builder
# ---------------------------------------------------------------------------

def build_gitignore(root: Path, extra_ignores: list[str]) -> str:
    plugins = get_plugins(root)
    themes = get_themes(root)

    lines = [
        "# ============================================================",
        "# WordPress .gitignore  -  track custom code only",
        "# Generated by wpa",
        "# ============================================================",
        "",
        "# WordPress core",
        "/wp-admin/",
        "/wp-includes/",
        "/wp-login.php",
        "/wp-blog-header.php",
        "/wp-comments-post.php",
        "/wp-cron.php",
        "/wp-links-opml.php",
        "/wp-load.php",
        "/wp-mail.php",
        "/wp-settings.php",
        "/wp-signup.php",
        "/wp-trackback.php",
        "/xmlrpc.php",
        "/index.php",
        "/license.txt",
        "/readme.html",
        "",
        "# Credentials",
        "/wp-config.php",
        "",
        "# Uploads and generated files",
        "/wp-content/uploads/",
        "/wp-content/cache/",
        "/wp-content/backup-db/",
        "/wp-content/backups/",
        "/wp-content/upgrade/",
        "/wp-content/advanced-cache.php",
        "/wp-content/wp-cache-config.php",
        "/wp-content/object-cache.php",
        "/wp-content/blogs.dir/",
        "/wp-content/wflogs/",
        "",
        "# Logs",
        "*.log",
        "/wp-content/debug.log",
        "",
        "# OS / editor",
        ".DS_Store",
        "Thumbs.db",
        ".vscode/",
        ".idea/",
        "*.swp",
        "*.swo",
        "",
        "# Environment",
        ".env",
        ".env.local",
    ]

    if extra_ignores:
        lines += ["", "# Large/binary items confirmed by user during setup"]
        for e in extra_ignores:
            lines.append(f"/{e}")

    if plugins:
        lines += [
            "",
            "# ============================================================",
            "# Plugins - uncomment to IGNORE (stock/vendor plugins)",
            "# Leave commented for plugins you want to track",
            "# ============================================================",
        ]
        for p in plugins:
            lines.append(f"# /wp-content/plugins/{p['slug']}/   # {p.get('plugin_name', p['slug'])}")

    if themes:
        lines += [
            "",
            "# ============================================================",
            "# Themes - uncomment to IGNORE (stock/vendor themes)",
            "# ============================================================",
        ]
        for t in themes:
            lines.append(f"# /wp-content/themes/{t['slug']}/   # {t.get('theme_name', t['slug'])}")

    lines += [
        "",
        "# Track wp-config template (not wp-config.php)",
        "!/wp-config-sample.php",
        "",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def run_git(cwd: Path, cmd: list, capture: bool = False):
    if capture:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        return r.stdout
    r = subprocess.run(cmd, cwd=str(cwd))
    if r.returncode != 0:
        die(f"Command failed: {' '.join(cmd)}")


def die(msg: str):
    print(f"\n  Error: {msg}\n", file=sys.stderr)
    sys.exit(1)


def usage():
    print(__doc__)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        usage()

    cmd = args[0]

    if cmd == "install":
        cmd_install()
        return

    if cmd == "deploy-key":
        cmd_deploy_key()
        return

    # Path given directly: wpa /var/www/html
    if cmd.startswith("/") or cmd.startswith(".") or cmd.startswith("~"):
        cmd_setup(find_wp_root(cmd))
        return

    if cmd == "setup":
        if len(args) < 2:
            die("Missing <path>: wpa setup /var/www/html")
        cmd_setup(find_wp_root(args[1]))
        return

    if len(args) < 2:
        die(f"Missing <path> for '{cmd}'")

    root = find_wp_root(args[1])

    if cmd == "info":
        cmd_info(root)
    elif cmd == "disk":
        cmd_disk(root)
    elif cmd == "gitignore":
        cmd_gitignore(root)
    elif cmd == "git-init":
        cmd_git_init(root, args[2] if len(args) > 2 else None)
    elif cmd == "local-setup":
        cmd_local_setup(root)
    else:
        die(f"Unknown command: '{cmd}'\nCommands: setup | install | info | disk | gitignore | git-init | local-setup | deploy-key")


if __name__ == "__main__":
    main()
