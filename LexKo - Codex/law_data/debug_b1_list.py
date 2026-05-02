"""
診斷：印出釋字清單頁的前30個 docdata 連結，看 href 實際長什麼樣
"""
from playwright.sync_api import sync_playwright
import re

LIST_URL = "https://cons.judicial.gov.tw/judcurrentNew1.aspx?fid=100"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    print(f"載入：{LIST_URL}")
    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
    print(f"標題：{page.title()}")

    all_links = page.query_selector_all("a[href*='docdata.aspx']")
    print(f"\n找到 {len(all_links)} 個 docdata 連結，印出前30個：\n")

    for i, a in enumerate(all_links[:30]):
        href = a.get_attribute("href") or ""
        text = (a.inner_text() or "").strip().replace("\n", " ")[:40]
        print(f"  [{i:2d}] href={href!r}")
        print(f"        text={text!r}")
        print()

    browser.close()
