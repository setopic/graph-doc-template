"""SVGの図から、動きのあるGIFを作る（python -m tools.graph gif）。

READMEのSVGはGitHubでそのまま動く。スライドや記事にはSVGのアニメーションを
貼れないことが多いので、GIFにするコマンドを用意する。任意の道具で、CIでは確かめない。

手順は次のとおりである。

1. SVGの動き（SMIL）の1周を、fpsに合わせた時刻に分ける
2. 時刻ごとに、SVGを埋め込んだHTMLを作り、動きをその時刻で止める
3. EdgeかChromeのヘッドレスで、HTMLをPNGに撮る
4. Pillowで、PNGを1つのGIFにまとめる

ブラウザとPillowは、このツールの前提（標準ライブラリだけで動く）の外にある。
このコマンドだけが使い、無ければ何が要るかを示して終わる。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ブラウザの実行ファイルの名前と、よくある置き場所
BROWSER_NAMES = (
    "msedge",
    "microsoft-edge",
    "microsoft-edge-stable",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "chromium",
    "chromium-browser",
)
BROWSER_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

# 1枚を撮り直す回数。Edgeは続けて呼ぶと、PNGを書かずに終わることがある
RETRIES = 3
# 1回の撮影で、PNGが書かれるのを待つ秒数
WAIT_SECONDS = 30

_SIZE_RE = re.compile(r'<svg\b[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"')
_DUR_RE = re.compile(r'<animate(?:Motion)?\b[^>]*\bdur="([\d.]+)s"')


class GifError(RuntimeError):
    pass


def find_browser(explicit: str | None = None) -> str | None:
    """EdgeかChromeの実行ファイルを探す。explicit、環境変数GRAPH_BROWSER、PATH、よくある置き場所の順に見る。"""
    for candidate in (explicit, os.environ.get("GRAPH_BROWSER")):
        if candidate:
            return candidate if Path(candidate).is_file() or shutil.which(candidate) else None
    for name in BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for path in BROWSER_PATHS:
        if Path(path).is_file():
            return path
    return None


def load_pillow():
    """Pillowを読む。無ければNoneを返す。"""
    try:
        from PIL import Image  # noqa: PLC0415  外部依存は、このコマンドの中だけで読む
    except ImportError:
        return None
    return Image


def missing_message(browser: bool, pillow: bool) -> str:
    """足りないものと、その入れ方を書いた文を返す。"""
    lines = ["GIFを作るのに要るものが足りない。"]
    if not browser:
        lines.append(
            "- EdgeかChrome（Chromium）。PATHに無い場所に入れてあるなら、"
            "--browserか環境変数GRAPH_BROWSERで実行ファイルを指す"
        )
    if not pillow:
        lines.append("- Pillow。python -m pip install Pillow で入れる")
    lines.append("READMEのSVGの図（make readme）は、これらが無くても作れる。")
    return "\n".join(lines)


def svg_size(svg: str) -> tuple[int, int]:
    match = _SIZE_RE.search(svg)
    if not match:
        raise GifError("SVGのwidthとheightが読めない。render --format svgで書き出したSVGを渡す")
    return int(match.group(1)), int(match.group(2))


def svg_period(svg: str) -> float | None:
    """SVGの動きの1周の秒数。動きが無ければNone。"""
    match = _DUR_RE.search(svg)
    return float(match.group(1)) if match else None


def frame_times(period: float | None, fps: float) -> list[float]:
    """撮る時刻の一覧。1周をfpsで分け、最後の時刻は次の周の始まりと重ならないようにする。"""
    if not period:
        return [0.0]
    count = max(1, round(period * fps))
    return [round(period * i / count, 4) for i in range(count)]


def frame_html(svg: str, t: float) -> str:
    """SVGを埋め込み、動きを時刻tで止めるHTML。"""
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>"
        f"</head><body>{svg}<script>"
        "const s=document.querySelector('svg');"
        f"s.pauseAnimations();s.setCurrentTime({t});"
        "</script></body></html>\n"
    )


def _wait_for(png: Path, timeout: float = WAIT_SECONDS) -> bool:
    """PNGが書き終わるのを待つ。

    Windowsのmsedge.exeは、起動を別のプロセスに渡してすぐに終わるので、
    コマンドが終わった時点ではPNGがまだ無いことがある。大きさが変わらなくなるまで待つ。
    """
    deadline = time.monotonic() + timeout
    last = -1
    while time.monotonic() < deadline:
        size = png.stat().st_size if png.is_file() else -1
        if size > 0 and size == last:
            return True
        last = size
        time.sleep(0.25)
    return False


def _shoot(browser: str, html: Path, png: Path, size: tuple[int, int], scale: float, dark: bool, work: Path) -> None:
    for attempt in range(RETRIES):
        profile = work / f"profile-{png.stem}-{attempt}"
        args = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            f"--window-size={size[0]},{size[1]}",
            f"--force-device-scale-factor={scale}",
            f"--screenshot={png}",
        ]
        if dark:
            args += ["--force-dark-mode", "--blink-settings=preferredColorScheme=0"]
        args.append(html.as_uri())
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)
        if _wait_for(png):
            return
    raise GifError(f"ブラウザがPNGを書かなかった（{RETRIES}回試した）: {png.name}")


def make_gif(
    svg: str,
    out: Path,
    *,
    browser: str,
    image_module,
    fps: float = 10,
    scale: float = 1,
    dark: bool = False,
    jobs: int = 4,
    log=print,
) -> int:
    """SVGからGIFを作り、outに書く。撮ったコマの数を返す。"""
    size = svg_size(svg)
    period = svg_period(svg)
    times = frame_times(period, fps)
    log(f"{len(times)}コマを撮る（1周{period or 0:g}秒、{fps:g}コマ/秒、{size[0]}x{size[1]}）")
    # ブラウザが作業のフォルダを掴んだまま終わることがあるので、消せなくても止めない
    with tempfile.TemporaryDirectory(prefix="graph-gif-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        jobs_list = []
        for i, t in enumerate(times):
            html = work / f"f{i:04d}.html"
            html.write_text(frame_html(svg, t), encoding="utf-8", newline="\n")
            jobs_list.append((html, work / f"f{i:04d}.png"))
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = [
                pool.submit(_shoot, browser, html, png, size, scale, dark, work)
                for html, png in jobs_list
            ]
            for future in futures:
                future.result()

        Image = image_module
        frames = [Image.open(png).convert("RGB") for _, png in jobs_list]
        # 全部のコマで同じ色の表を使う。コマごとに作ると、色がちらつく
        first = frames[0].quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        palette = [first] + [
            f.quantize(palette=first, dither=Image.Dither.NONE) for f in frames[1:]
        ]
        out.parent.mkdir(parents=True, exist_ok=True)
        palette[0].save(
            out,
            save_all=True,
            append_images=palette[1:],
            duration=round(1000 / fps),
            loop=0,
            disposal=1,
        )
    return len(times)


def run(svg_path: Path, out: Path, *, browser: str | None, fps: float, scale: float, dark: bool, jobs: int) -> int:
    """gifコマンドの本体。終了コードを返す。"""
    found = find_browser(browser)
    image = load_pillow()
    if found is None or image is None:
        print(missing_message(found is not None, image is not None), file=sys.stderr)
        return 1
    if not svg_path.is_file():
        print(f"エラー: SVGが無い: {svg_path}。先にmake readmeかrender --format svgで書き出す", file=sys.stderr)
        return 1
    if fps <= 0 or scale <= 0:
        print("エラー: --fpsと--scaleは、0より大きい数にする", file=sys.stderr)
        return 1
    svg = svg_path.read_text(encoding="utf-8")
    try:
        make_gif(svg, out, browser=found, image_module=image, fps=fps, scale=scale, dark=dark, jobs=jobs)
    except (GifError, subprocess.TimeoutExpired) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    print(f"GIFを書き出した: {out}")
    return 0
