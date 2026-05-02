"""
診斷：釋字清單頁的實際結構
"""
from playwright.sync_api import sync_playwright
import re

LIST_URL = "https://cons.judicial.gov.tw/judcurrentNew1.aspx?fid=100"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)

    # 看 body 前2000字，了解頁面大致結構
    body = page.inner_text("body")
    print("=== body 前 1500 字 ===")
    print(body[:1500])
    print()

    # 找所有含 id= 的 a 連結
    links_with_id = page.query_selector_all("a[href*='id=']")
    print(f"=== 含 id= 的連結：{len(links_with_id)} 個 ===")
    for i, a in enumerate(links_with_id[:20]):
        href = a.get_attribute("href") or ""
        text = (a.inner_text() or "").strip().replace("\n", " ")[:50]
        print(f"  [{i}] {href!r} → {text!r}")

    print()

    # 找含「釋字」文字的元素
    print("=== 含「釋字」文字的元素 ===")
    all_els = page.query_selector_all("*")
    count = 0
    for el in all_els:
        try:
            txt = el.inner_text()
            if "釋字" in txt and len(txt) < 80:
                tag = el.evaluate("e => e.tagName")
                cls = el.get_attribute("class") or ""
                href = el.get_attribute("href") or ""
                print(f"  <{tag}> class={cls!r} href={href!r} → {txt.strip()!r}")
                count += 1
                if count >= 20:
                    print("  ...(只顯示前20筆)")
                    break
        except:
            pass

    # 看有沒有 iframe 或 script 載入資料
    iframes = page.query_selector_all("iframe")
    print(f"\n=== iframe 數量：{len(iframes)} ===")
    for iframe in iframes:
        print(f"  src={iframe.get_attribute('src')!r}")

    browser.close()
