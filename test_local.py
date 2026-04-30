#!/usr/bin/env python3
"""Tests using a fake WordPress structure in a temp directory."""

import importlib.util
import tempfile
from pathlib import Path


def load_wpa():
    spec = importlib.util.spec_from_file_location(
        "wp_source", Path(__file__).parent / "wp-source.py"
    )
    wp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wp)
    return wp


def make_fake_wp(tmp: Path):
    (tmp / "wp-includes").mkdir()
    (tmp / "wp-admin").mkdir()
    (tmp / "wp-content" / "themes"     / "mytheme").mkdir(parents=True)
    (tmp / "wp-content" / "themes"     / "twentytwenty").mkdir(parents=True)
    (tmp / "wp-content" / "plugins"    / "woocommerce").mkdir(parents=True)
    (tmp / "wp-content" / "plugins"    / "my-plugin").mkdir(parents=True)
    (tmp / "wp-content" / "mu-plugins").mkdir(parents=True)
    (tmp / "wp-content" / "uploads"    / "2024").mkdir(parents=True)
    (tmp / "wp-content" / "cache").mkdir(parents=True)

    (tmp / "wp-login.php").write_text("<?php")
    (tmp / "wp-includes" / "version.php").write_text("<?php\n$wp_version = '6.5.3';\n")
    (tmp / "wp-config.php").write_text(
        "<?php\n"
        "define( 'DB_NAME', 'prod_db' );\n"
        "define( 'DB_USER', 'wp_user' );\n"
        "define( 'DB_PASSWORD', 'secret' );\n"
        "define( 'DB_HOST', 'localhost' );\n"
        "$table_prefix = 'wp_';\n"
    )
    (tmp / "wp-content" / "themes" / "mytheme" / "style.css").write_text(
        "/*\nTheme Name: My Theme\nVersion: 1.0.0\nAuthor: Me\n*/"
    )
    (tmp / "wp-content" / "themes" / "twentytwenty" / "style.css").write_text(
        "/*\nTheme Name: Twenty Twenty\nVersion: 2.5\nAuthor: WordPress\n*/"
    )
    (tmp / "wp-content" / "plugins" / "woocommerce" / "woocommerce.php").write_text(
        "<?php\n/*\nPlugin Name: WooCommerce\nVersion: 8.9\nAuthor: Automattic\n*/"
    )
    (tmp / "wp-content" / "plugins" / "my-plugin" / "my-plugin.php").write_text(
        "<?php\n/*\nPlugin Name: My Plugin\nVersion: 1.0\nAuthor: Me\n*/"
    )
    (tmp / "wp-content" / "mu-plugins" / "loader.php").write_text("<?php")
    # Fake SQL dump outside uploads (should be flagged by scan_large_not_ignored)
    (tmp / "wp-content" / "plugins" / "woocommerce" / "export.sql").write_bytes(b"x" * (2 * 1024 * 1024))


def run_tests():
    wp = load_wpa()

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        make_fake_wp(tmp)
        print(f"Fake WP: {tmp}\n")

        root = wp.find_wp_root(str(tmp))

        # --- Unit tests ---
        print("--- get_wp_version ---")
        assert wp.get_wp_version(root) == "6.5.3"
        print("  OK")

        print("--- parse_wp_config ---")
        cfg = wp.parse_wp_config(root)
        assert cfg["DB_NAME"] == "prod_db"
        assert cfg["DB_PASSWORD"] == "***hidden***"
        assert cfg["table_prefix"] == "wp_"
        print("  OK")

        print("--- get_plugins ---")
        slugs = [p["slug"] for p in wp.get_plugins(root)]
        assert "woocommerce" in slugs and "my-plugin" in slugs
        print(f"  {slugs} OK")

        print("--- get_themes ---")
        tslugs = [t["slug"] for t in wp.get_themes(root)]
        assert "mytheme" in tslugs and "twentytwenty" in tslugs
        print(f"  {tslugs} OK")

        print("--- format_size ---")
        assert wp.format_size(0) == "0.0 B"
        assert "KB" in wp.format_size(2048)
        assert "MB" in wp.format_size(5 * 1024 * 1024)
        print("  OK")

        print("--- build_gitignore ---")
        gi = wp.build_gitignore(root, [])
        assert "/wp-admin/" in gi
        assert "/wp-config.php" in gi
        assert "/wp-content/uploads/" in gi
        assert "woocommerce" in gi
        print("  core exclusions + plugin comments OK")

        print("--- build_gitignore with extra_ignores ---")
        gi2 = wp.build_gitignore(root, ["wp-content/plugins/woocommerce"])
        assert "/wp-content/plugins/woocommerce" in gi2
        print("  extra_ignores written OK")

        print("--- scan_large_not_ignored (binary file detection) ---")
        candidates = wp.scan_large_not_ignored(root, threshold_mb=50)
        rels = [r for _, r, _ in candidates]
        # The 2MB SQL file should be detected as a binary file
        assert any("export.sql" in r for r in rels), f"Expected SQL in {rels}"
        print(f"  Detected: {rels} OK")

        # --- Command output tests ---
        print("\n--- cmd_info ---")
        wp.cmd_info(root)
        print("  OK")

        print("\n--- cmd_disk ---")
        wp.cmd_disk(root)
        print("  OK")

        print("\n--- cmd_gitignore ---")
        wp.cmd_gitignore(root, ["wp-content/plugins/woocommerce"])
        gi_file = root / ".gitignore"
        assert gi_file.exists()
        content = gi_file.read_text()
        assert "/wp-config.php" in content
        assert "/wp-content/uploads/" in content
        assert "/wp-content/plugins/woocommerce" in content
        print(f"  .gitignore ({gi_file.stat().st_size}B) with extra ignore OK")

        print("\n--- cmd_local_setup ---")
        wp.cmd_local_setup(root)
        print("  OK")

        print("\n--- deploy-key (_parse_git_host) ---")
        assert wp._parse_git_host("git@gitlab.com:user/site.git") == "gitlab.com"
        assert wp._parse_git_host("git@github.com:user/site.git") == "github.com"
        assert wp._parse_git_host("https://gitlab.com/user/site.git") == "gitlab.com"
        print("  OK")

    print("\nAll tests passed")


if __name__ == "__main__":
    run_tests()
