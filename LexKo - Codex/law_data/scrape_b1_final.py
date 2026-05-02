"""
司法院大法官解釋（釋字第1～813號）完整爬蟲 最終版
======================================================
策略：
  - 清單不需要爬！直接用 CNO=1~813 生成 URL
  - 每筆先進全國法規 ExContent 頁，跟到司法院詳情頁
  - 詳情頁用 .lawPage selector 抓全文

輸出：law_data/JUDGE_B1.json
特性：可中斷續跑，每20筆存一次

用法：
    python scrape_b1_final.py              # 續跑（跳過已有）
    python scrape_b1_final.py --force      # 強制重抓全部
    python scrape_b1_final.py --start 100  # 從第100號開始（測試用）
"""

import json, os, sys, re, datetime
from playwright.sync_api import sync_playwright

OUTPUT_PATH = os.path.join("law_data", "JUDGE_B1.json")
MOJ_BASE    = "https://law.moj.gov.tw"
TOTAL       = 813
SAVE_EVERY  = 20
FORCE_MODE  = "--force" in sys.argv
START_NO    = 1
for arg in sys.argv:
    if arg.startswith("--start"):
        try: START_NO = int(arg.split("=")[1])
        except: pass


def load_existing():
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save(data):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def is_valid(text):
    if len(text) < 200:
        return False
    return any(kw in text for kw in ["解釋文", "解釋理由書", "理由書", "解釋爭點", "釋字"])


def scrape_one(page, cno):
    """
    抓單筆釋字。
    先進全國法規的 ExContent 頁，
    它會列出連結（含司法院詳情頁），直接點進去抓。
    """
    moj_url = f"{MOJ_BASE}/LawClass/ExContent.aspx?ty=C&CC=D&CNO={cno}"
    page.goto(moj_url, wait_until="domcontentloaded", timeout=30000)

    # 找司法院詳情頁連結
    cons_link = page.query_selector("a[href*='cons.judicial.gov.tw']")
    if cons_link:
        cons_url = cons_link.get_attribute("href")
        page.goto(cons_url, wait_until="domcontentloaded", timeout=30000)
    # 若找不到司法院連結，就直接在全國法規頁抓內容

    # 抓內容（司法院詳情頁用 .lawPage；全國法規用 .col-data）
    for sel in [".lawPage", ".lawList", ".col-data", ".law-reg-content", "article", "main"]:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 200:
                return text

    # fallback
    return page.inner_text("body").strip()


def main():
    print("=" * 60)
    print("  大法官解釋（釋字第1～813號）爬蟲 最終版")
    print(f"  模式：{'強制重抓' if FORCE_MODE else '續跑（跳過已有）'}")
    if START_NO > 1:
        print(f"  起始：第 {START_NO} 號")
    print("=" * 60)

    data = load_existing()
    existing = len([k for k in data if k != "_metadata"])
    print(f"📂 現有資料：{existing} 筆\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = ctx.new_page()

        new_count = skip_count = fail_count = 0

        for cno in range(START_NO, TOTAL + 1):
            key = f"釋字第{cno}號"

            # 續跑：跳過已有且有效的
            if not FORCE_MODE:
                existing_val = data.get(key, "")
                if existing_val and is_valid(existing_val):
                    skip_count += 1
                    if skip_count % 100 == 0:
                        print(f"  ⏭  已跳過 {skip_count} 筆...")
                    continue

            print(f"  [{cno:3d}/{TOTAL}] {key} ...", end="", flush=True)

            try:
                text = scrape_one(page, cno)
                if is_valid(text):
                    data[key] = text
                    new_count += 1
                    print(f" ✅ {len(text):,} 字")
                else:
                    data[key] = text or "（內容為空）"
                    fail_count += 1
                    print(f" ⚠️  疑似不完整（{len(text)} 字）")
            except Exception as e:
                data[key] = f"（抓取失敗：{e}）"
                fail_count += 1
                print(f" ❌ {e}")

            # 定期存檔
            if new_count > 0 and new_count % SAVE_EVERY == 0:
                data["_metadata"] = {
                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save(data)
                print(f"  💾 進度存檔（新增 {new_count} 筆）")

        page.close()
        browser.close()

    # 最終存檔
    data["_metadata"] = {
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len([k for k in data if k != "_metadata"])
    }
    save(data)

    total = len([k for k in data if k != "_metadata"])
    print()
    print("=" * 60)
    print(f"✅ 完成！新抓 {new_count} 筆，跳過 {skip_count} 筆，失敗 {fail_count} 筆")
    print(f"   JSON 總計：{total} 筆 → {OUTPUT_PATH}")
    if fail_count > 0:
        print(f"   ⚠️  有 {fail_count} 筆失敗，直接再跑一次會自動補抓")
    print("=" * 60)


if __name__ == "__main__":
    main()
