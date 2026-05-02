"""
診斷：全國法規資料庫的釋字清單頁結構
"""
from playwright.sync_api import sync_playwright

URL = "https://law.moj.gov.tw/Law/LawSearchJudge.aspx?ty=B1&psize=20"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    print(f"載入：{URL}")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    # 等表格
    try:
        page.wait_for_selector("table", timeout=20000)
        print("✅ 找到 table")
    except:
        print("❌ 沒找到 table")

    # 所有 table
    tables = page.query_selector_all("table")
    print(f"共 {len(tables)} 個 table")
    for i, t in enumerate(tables):
        cls = t.get_attribute("class") or ""
        id_ = t.get_attribute("id") or ""
        rows = t.query_selector_all("tr")
        print(f"  [{i}] id={id_!r} class={cls!r} rows={len(rows)}")

    # 找 gvList
    gv = page.query_selector("table[id*='gvList']")
    if gv:
        rows = gv.query_selector_all("tr")
        print(f"\ngvList 有 {len(rows)} 行，印出前5筆：")
        for row in rows[:6]:
            cols = row.query_selector_all("td, th")
            for j, col in enumerate(cols):
                a = col.query_selector("a")
                href = a.get_attribute("href") if a else ""
                txt = col.inner_text().strip()[:60]
                print(f"  col[{j}] {txt!r}  href={href!r}")
            print()
    else:
        print("\n❌ 沒找到 gvList")
        # 印 body 前 800 字
        print("\nbody 前 800 字：")
        print(page.inner_text("body")[:800])

    browser.close()
