"""Export the #poster element of a local HTML file to PNG using Chromium."""

import argparse
from pathlib import Path

from playwright.sync_api import Error as BrowserError, sync_playwright


def render(html, *, scale=1, browser_path=None):
    html = Path(html).resolve(strict=True)
    failed_images = set()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_path)
        page = browser.new_page(device_scale_factor=scale)
        page.on("requestfailed", lambda req: failed_images.add(req.url) if req.resource_type == "image" else None)
        page.on("response", lambda res: failed_images.add(res.url) if res.status >= 400 and res.request.resource_type == "image" else None)
        page.goto(html.as_uri(), wait_until="load")
        poster = page.locator("#poster")
        if poster.count() != 1:
            raise ValueError("HTML must contain exactly one #poster element.")
        page.evaluate("document.fonts.ready")
        broken = poster.locator("img").evaluate_all(
            "imgs => imgs.filter(img => !img.complete || !img.naturalWidth).map(img => img.src)"
        )
        failed_images.update(broken)
        if failed_images:
            raise ValueError("Missing poster image(s): " + ", ".join(sorted(failed_images)))
        return poster.screenshot(type="png", animations="disabled", timeout=15000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=1)
    parser.add_argument("--browser-path", help="Path to an installed Chromium, Chrome or Edge executable.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".png":
        parser.error("Output must be a .png file.")
    try:
        if args.output.exists() and not args.overwrite:
            raise FileExistsError(f"Output already exists: {args.output} (use --overwrite to replace it)")
        png = render(args.html, scale=args.scale, browser_path=args.browser_path)
        with args.output.open("wb" if args.overwrite else "xb") as stream:
            stream.write(png)
    except (BrowserError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
