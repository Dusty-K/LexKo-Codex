"""
最終診斷：確認釋字詳情頁連結 + 全文 selector
"""
from playwright.sync_api import sync_playwright

LIST_URL   = "https://law.moj.gov.tw/Law/LawSearchJudge.aspx?ty=B1&psize=20"
DETAIL_URL = "https://cons.judicial.gov.tw/docdata.aspx?fid=100&id=325335"  # 釋字813

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    # ── 清單頁：找詳情頁連結 ──
    print("=== 清單頁：每筆的連結 ===")
    page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("table.jud-content", timeout=15000)

    table = page.query_selector("table.jud-content")
    rows = table.query_selector_all("tr")
    print(f"共 {len(rows)} 行（含表頭），印出前3筆：")
    for row in rows[1:4]:
        cols = row.query_selector_all("td")
        print(f"  欄位數: {len(cols)}")
        for j, col in enumerate(cols):
            links = col.query_selector_all("a")
            txt = col.inner_text().strip()[:80].replace('\n', ' ')
            hrefs = [a.get_attribute("href") for a in links]
            print(f"    col[{j}]: {txt!r}")
            if hrefs:
                print(f"           連結: {hrefs}")
        print()

    # ── 詳情頁：找全文 selector ──
    print("=== 詳情頁（釋字813）：內容 selector ===")
    page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=30000)
    print(f"最終 URL: {page.url}")

    # 嘗試各種 selector
    selectors = [".lawPage", ".lawList", ".jud-content", "#divJudContent",
                 ".judContent", "article", "main", ".container", "#content"]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            print(f"  {sel!r}: {len(text)} 字，開頭={text[:60].replace(chr(10),' ')!r}")
        else:
            print(f"  {sel!r}: 找不到")

    # 印 body 前600字看結構
    print("\nbody 前 600 字:")
    print(page.inner_text("body")[:600])

    browser.close()
