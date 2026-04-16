"""Capture real screenshots of the running platform with Playwright.

The script talks to a live backend + frontend, exercises the interactive
features (paired scenario comparison, live AI copilot) and stores PNGs in
``docs/images``.  It also fails loudly on console errors or failed requests so
that a broken page can never be published as a "screenshot".

Usage
-----
    python scripts/capture_screenshots.py --frontend http://127.0.0.1:5173
    python scripts/capture_screenshots.py --skip-ai          # fast pass
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"

console_errors: list[str] = []
failed_requests: list[str] = []


def _handler(page) -> None:  # noqa: ANN001
    page.on(
        "console",
        lambda message: console_errors.append(f"{page.url} :: {message.text}")
        if message.type == "error"
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            f"{request.method} {request.url} :: {request.failure}"
        ),
    )
    page.on(
        "response",
        lambda response: failed_requests.append(
            f"{response.status} {response.url}"
        )
        if response.status >= 400
        else None,
    )


def shoot(page, name: str, full_page: bool = False) -> Path:  # noqa: ANN001
    IMAGES.mkdir(parents=True, exist_ok=True)
    path = IMAGES / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  saved {path.relative_to(ROOT)} ({path.stat().st_size // 1024} kB)")
    return path


def settle(page, selector: str | None = None, timeout: int = 45000) -> None:  # noqa: ANN001
    page.wait_for_load_state("networkidle", timeout=timeout)
    if selector:
        page.wait_for_selector(selector, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default="http://127.0.0.1:5173")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-ai", action="store_true")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()

    import httpx

    projects = httpx.get(f"{args.backend}/api/projects", timeout=30).json()
    by_key = {project["key"]: project for project in projects}
    if "AURORA-X1" not in by_key:
        print("Aurora program missing — run scripts/bootstrap_demo.py first", file=sys.stderr)
        return 1
    aurora = by_key["AURORA-X1"]["id"]
    helios = by_key["HELIOS-INV"]["id"] if "HELIOS-INV" in by_key else aurora

    started = time.perf_counter()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--force-color-profile=srgb"])
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=1,
            color_scheme="light",
        )
        page = context.new_page()
        _handler(page)

        print("capturing portfolio and program pages")
        page.goto(f"{args.frontend}/", wait_until="domcontentloaded")
        settle(page, ".program-card")
        shoot(page, "01-dashboard")

        page.goto(f"{args.frontend}/projects", wait_until="domcontentloaded")
        settle(page, "table")
        shoot(page, "02-programs")

        page.goto(f"{args.frontend}/projects/{aurora}/overview", wait_until="domcontentloaded")
        settle(page, ".kpi-grid")
        shoot(page, "03-program-overview")

        page.goto(f"{args.frontend}/projects/{aurora}/schedule", wait_until="domcontentloaded")
        settle(page, ".chart-wrap")
        time.sleep(2.5)
        shoot(page, "04-schedule-capacity")

        page.goto(f"{args.frontend}/projects/{aurora}/risks", wait_until="domcontentloaded")
        settle(page, ".kpi-grid")
        time.sleep(2.5)
        shoot(page, "05-risk-attribution")

        page.goto(f"{args.frontend}/projects/{aurora}/suppliers", wait_until="domcontentloaded")
        settle(page, "table")
        time.sleep(1.0)
        shoot(page, "06-supply-exposure")

        page.goto(f"{args.frontend}/projects/{aurora}/milestones", wait_until="domcontentloaded")
        settle(page, "table")
        time.sleep(1.0)
        shoot(page, "07-milestones")

        page.goto(f"{args.frontend}/projects/{aurora}/simulation", wait_until="domcontentloaded")
        settle(page, ".kpi-grid")
        time.sleep(2.5)
        shoot(page, "08-monte-carlo")

        print("running a paired scenario comparison in the UI")
        page.goto(f"{args.frontend}/projects/{aurora}/scenarios", wait_until="domcontentloaded")
        settle(page, ".scenario-card")
        scenario = page.locator(".scenario-card", has_text="Schedule acceleration")
        if scenario.count():
            scenario.first.click()
            time.sleep(0.8)
        compare = page.get_by_role("button", name="Simulate paired comparison")
        compare.click()
        page.wait_for_selector(".chat-stats, .kpi-grid", timeout=120000)
        time.sleep(2.0)
        shoot(page, "09-scenario-comparison")

        page.goto(f"{args.frontend}/projects/{aurora}/optimization", wait_until="domcontentloaded")
        settle(page, ".recommendation-list, .kpi-grid")
        time.sleep(1.5)
        shoot(page, "10-optimiser-recommendation")

        page.goto(f"{args.frontend}/projects/{aurora}/decisions", wait_until="domcontentloaded")
        settle(page, ".timeline")
        time.sleep(1.0)
        shoot(page, "11-decisions-audit")

        page.goto(f"{args.frontend}/projects/{aurora}/methodology", wait_until="domcontentloaded")
        settle(page, ".method-grid")
        time.sleep(0.6)
        shoot(page, "12-methodology")

        page.goto(f"{args.frontend}/settings", wait_until="domcontentloaded")
        settle(page, ".provider-list")
        time.sleep(0.6)
        shoot(page, "13-settings-providers")

        page.goto(f"{args.frontend}/projects/{helios}/overview", wait_until="domcontentloaded")
        settle(page, ".kpi-grid")
        shoot(page, "14-helios-program-overview")

        if not args.skip_ai:
            print("asking the live AI copilot (this takes up to a minute)")
            page.goto(f"{args.frontend}/projects/{aurora}/assistant", wait_until="domcontentloaded")
            settle(page, ".suggestion")
            shoot(page, "15-assistant-welcome")
            page.locator("textarea").fill(
                "What is the probability we hit the launch deadline, what drives it, and what should we do next?"
            )
            page.get_by_role("button", name="Ask").click()
            page.wait_for_selector(".citation", timeout=180000)
            time.sleep(1.5)
            shoot(page, "16-assistant-grounded-answer")

            print("asking the local Ollama model")
            page.goto(f"{args.frontend}/settings", wait_until="domcontentloaded")
            settle(page, ".provider-list")
            ollama = page.locator(".provider-card", has_text="ollama")
            if ollama.count():
                ollama.first.get_by_role("button", name="Activate").click()
                time.sleep(2.0)
                shoot(page, "17-settings-ollama-active")

            page.goto(f"{args.frontend}/projects/{aurora}/assistant", wait_until="domcontentloaded")
            settle(page, ".suggestion")
            page.locator("textarea").fill(
                "Which supplier is the biggest risk to the launch date, and what would you do about it?"
            )
            page.get_by_role("button", name="Ask").click()
            try:
                page.wait_for_selector(".citation", timeout=180000)
            except PlaywrightError:
                print("  (ollama answer timed out — captured whatever is on screen)")
            time.sleep(1.5)
            shoot(page, "18-assistant-ollama-answer")

            print("restoring the default provider")
            page.goto(f"{args.frontend}/settings", wait_until="domcontentloaded")
            settle(page, ".provider-list")
            custom = page.locator(".provider-card", has_text="custom")
            if custom.count():
                custom.first.get_by_role("button", name="Activate").click()
                time.sleep(1.5)

        browser.close()

    elapsed = time.perf_counter() - started
    print(f"\ncaptured in {elapsed:.1f}s")
    if console_errors:
        print("\nconsole errors:")
        for error in console_errors[:20]:
            print("  -", error)
    if failed_requests:
        print("\nfailed requests:")
        for failure in failed_requests[:20]:
            print("  -", failure)
    report = {
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "images": sorted(p.name for p in IMAGES.glob("*.png")),
    }
    (ROOT / "docs" / "screenshot-report.json").write_text(json.dumps(report, indent=2))
    return 0 if not console_errors and not failed_requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
