#!/usr/bin/env python3
"""Сборка автономной демо-версии хелпдеска в один HTML-файл.

Берёт боевой app/static/index.html, инлайнит вендорные библиотеки (React,
Babel, lottie-player — из npm-тарболов), генерирует статический Tailwind CSS
по JSX-исходникам (вместо рантайм-CDN) и вшивает демо-мок API.
Результат — demo/dist/vpn-helpdesk-demo.html: открывается двойным кликом,
без сервера, интернета и каких-либо зависимостей.

Запуск:  python3 demo/build.py
Требуется node/npx (для Tailwind CLI). Вендорные файлы кешируются в
demo/vendor/ — сеть нужна только при первой сборке.
"""
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
STATIC = ROOT / "app" / "static"
VENDOR = DEMO / "vendor"
DIST = DEMO / "dist"

# CDN-тег в index.html → (npm-тарбол, путь внутри пакета, локальное имя)
NPM_VENDORS = {
    "https://unpkg.com/react@18.3.1/umd/react.development.js": (
        "https://registry.npmjs.org/react/-/react-18.3.1.tgz",
        "package/umd/react.production.min.js", "react.js"),
    "https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js": (
        "https://registry.npmjs.org/react-dom/-/react-dom-18.3.1.tgz",
        "package/umd/react-dom.production.min.js", "react-dom.js"),
    "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js": (
        "https://registry.npmjs.org/@babel/standalone/-/standalone-7.29.0.tgz",
        "package/babel.min.js", "babel.js"),
    "https://unpkg.com/@lottiefiles/lottie-player@2/dist/lottie-player.js": (
        "https://registry.npmjs.org/@lottiefiles/lottie-player/-/lottie-player-2.0.12.tgz",
        "package/dist/lottie-player.js", "lottie-player.js"),
}

TAILWIND_TAG = '<script src="https://cdn.tailwindcss.com"></script>'
JSX_ORDER = ["components.jsx", "dialogs.jsx", "statistics.jsx", "settings.jsx", "servers.jsx"]


def fetch_npm_vendor(tarball: str, inner_path: str, local_name: str) -> str:
    dest = VENDOR / local_name
    if not dest.exists():
        print(f"  ↓ {tarball}")
        with tempfile.NamedTemporaryFile(suffix=".tgz") as tmp:
            subprocess.run(["curl", "-fsSL", "-o", tmp.name, tarball], check=True)
            with tarfile.open(tmp.name, "r:gz") as tf:
                member = tf.extractfile(inner_path)
                if member is None:
                    sys.exit(f"В {tarball} нет файла {inner_path}")
                dest.write_bytes(member.read())
    return dest.read_text(encoding="utf-8")


def build_tailwind_css() -> str:
    dest = VENDOR / "tailwind.css"
    if not dest.exists():
        print("  ⚙ tailwindcss CLI (генерация статического CSS по JSX)")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.css"
            src.write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")
            content = ",".join(str(p) for p in [STATIC / "index.html", *STATIC.glob("*.jsx")])
            subprocess.run(
                ["npx", "-y", "tailwindcss@3.4.17",
                 "-i", str(src), "-o", str(dest),
                 "--content", content, "--minify"],
                check=True, cwd=td,
            )
    return dest.read_text(encoding="utf-8")


def safe_inline(js: str) -> str:
    # закрывающий </script> внутри JS-строк не должен разорвать инлайн-тег
    return js.replace("</script", "<\\/script")


def main() -> None:
    VENDOR.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)

    html = (STATIC / "index.html").read_text(encoding="utf-8")

    if TAILWIND_TAG not in html:
        sys.exit("Не найден тег cdn.tailwindcss.com — index.html изменился, обновите demo/build.py")
    css = build_tailwind_css()
    html = html.replace(TAILWIND_TAG, f"<style>{css}</style>", 1)

    print("Вендорные библиотеки:")
    for url, (tarball, inner, local) in NPM_VENDORS.items():
        content = safe_inline(fetch_npm_vendor(tarball, inner, local))
        pattern = re.compile(r'<script src="' + re.escape(url) + r'"[^>]*></script>')
        if not pattern.search(html):
            sys.exit(f"Не найден тег скрипта для {url} — index.html изменился, обновите demo/build.py")
        html = pattern.sub(lambda _m: f"<script>{content}</script>", html, count=1)

    # демо-мок должен встать до JSX-кода приложения
    demo_js = "\n".join(
        f"<script>{safe_inline((DEMO / name).read_text(encoding='utf-8'))}</script>"
        for name in ("demo-data.js", "demo-mock.js")
    )
    html = html.replace('<div id="root"></div>', '<div id="root"></div>\n\n  ' + demo_js, 1)

    for name in JSX_ORDER:
        tag = f'<script type="text/babel" src="/static/{name}"></script>'
        if tag not in html:
            sys.exit(f"Не найден тег {tag} — index.html изменился, обновите demo/build.py")
        jsx = safe_inline((STATIC / name).read_text(encoding="utf-8"))
        html = html.replace(tag, f'<script type="text/babel">\n{jsx}\n</script>', 1)

    html = html.replace("<title>Хелпдеск · VPN Support</title>",
                        "<title>Хелпдеск · VPN Support (демо)</title>", 1)

    out = DIST / "vpn-helpdesk-demo.html"
    out.write_text(html, encoding="utf-8")
    print(f"Готово: {out} ({out.stat().st_size / 1024 / 1024:.1f} МБ)")


if __name__ == "__main__":
    main()
