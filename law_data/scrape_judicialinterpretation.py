"""
司法院大法官解釋（釋字第1～813號）完整爬蟲
======================================================
輸出：law_data/JUDGE_B1.json（格式與憲判相同）

特性：
- 可中斷續跑：已抓過的筆數不會重複爬取
- 進度顯示：每筆即時顯示進度
- 自動存檔：每 20 筆存一次，避免中途損失
- 清單來源：https://cons.judicial.gov.tw/judcurrentNew1.aspx?fid=100

用法：
    python scrape_judicialinterpretation.py            # 正常執行（跳過已有資料）
    python scrape_judicialinterpretation.py --force    # 強制重新抓取所有
"""

import json
import os
import sys
import time
import datetime
import re
from playwright.sync_api import sync_playwright

# ── 設定 ──────────────────────────────────────────
OUTPUT_PATH = os.path.join("law_data", "JUDGE_B1.json")
LIST_URL    = "https://cons.judicial.gov.tw/judcurrentNew1.aspx?fid=100"
BASE_URL    = "https://cons.judicial.gov.tw"
SAVE_EVERY  = 20      # 每幾筆存一次
PAGE_TIMEOUT = 30000  # 每頁 timeout (ms)
FORCE_MODE  = "--force" in sys.argv
# ──────────────────────────────────────────────────


def load_existing():
    """載入已有的 JSON，回傳 data dict"""
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  讀取現有 JSON 失敗（{e}），從空白開始")
    return {}


def save(data):
    """存檔"""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def normalize_key(text):
    """
    把各種格式的釋字標題統一化
    例如 '司法院釋字第 1 號' → '釋字第1號'
         '釋字第813號'       → '釋字第813號'
    """
    text = re.sub(r'\s+', '', text.strip())
    m = re.search(r'第(\d+)號', text)
    if m:
        return f"釋字第{m.group(1)}號"
    return text


def scrape_links(page):
    """
    從清單頁抓取所有釋字的 (key, url) 清單
    清單頁會用 JavaScript 載入，需等待
    """
    print(f"📋 載入釋字清單：{LIST_URL}")
    page.goto(LIST_URL, wait_until="networkidle", timeout=60000)

    # 先找所有 <a> 連結，篩出含 fid=100 的判決連結
    all_links = page.query_selector_all("a[href*='docdata.aspx']")
    print(f"   找到 {len(all_links)} 個 docdata 連結，開始篩選...")

    result = []
    seen_ids = set()

    for a in all_links:
        href  = a.get_attribute("href") or ""
        text  = (a.inner_text() or "").strip().replace("\n", "").replace(" ", "")

        # 只要 fid=100 的（釋字），排除憲判 fid=38
        if "fid=100" not in href and "fid=100" not in (a.get_attribute("href") or ""):
            # href 可能是相對路徑，先補完
            if href and not href.startswith("http"):
                href = BASE_URL + "/" + href.lstrip("/")
            if "fid=100" not in href:
                continue

        # 補完 URL
        if href and not href.startswith("http"):
            href = BASE_URL + "/" + href.lstrip("/")

        # 抽出 id 參數，避免重複
        m = re.search(r'id=(\d+)', href)
        if not m:
            continue
        doc_id = m.group(1)
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)

        # 確認文字含釋字號碼
        if not re.search(r'第\s*\d+\s*號', text) and not re.search(r'\d+號', text):
            continue

        key = normalize_key(text)
        if not key.startswith("釋字第"):
            continue

        result.append((key, href))

    # 依號碼排序
    def sort_num(item):
        m = re.search(r'第(\d+)號', item[0])
        return int(m.group(1)) if m else 0

    result.sort(key=sort_num)
    return result


def scrape_detail(page, url):
    """抓取單一釋字詳情頁，回傳文字內容"""
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

    # 嘗試各種內容容器 selector（依優先順序）
    selectors = [
        ".lawPage",
        ".lawList",
        ".jud-content",
        "#divJudContent",
        ".judContent",
        "article",
        "main",
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if len(text) > 100:
                return text

    # fallback：整個 body（去掉導覽列噪音）
    return page.inner_text("body").strip()


def is_valid_content(text):
    """判斷抓到的內容是否有效"""
    if len(text) < 100:
        return False
    keywords = ["解釋文", "解釋理由書", "主文", "理由", "聲請人", "釋字"]
    return any(kw in text for kw in keywords)


def main():
    print("=" * 60)
    print("  司法院大法官解釋（釋字）完整爬蟲")
    print(f"  模式：{'強制重抓全部' if FORCE_MODE else '跳過已有資料（續跑模式）'}")
    print("=" * 60)

    # 載入現有資料
    data = load_existing()
    existing_count = len([k for k in data if k != "_metadata"])
    print(f"📂 現有資料：{existing_count} 筆")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        list_page = context.new_page()

        # ── Step 1：抓清單 ──
        links = scrape_links(list_page)
        list_page.close()

        if not links:
            print("❌ 清單抓取失敗，請確認網路連線或清單頁 selector 需要調整")
            browser.close()
            return

        print(f"✅ 清單共 {len(links)} 筆釋字")
        print(f"   第一筆：{links[0][0]}  →  {links[0][1]}")
        print(f"   最後筆：{links[-1][0]}  →  {links[-1][1]}")
        print()

        # ── Step 2：逐筆抓詳情 ──
        detail_page = context.new_page()
        new_count = 0
        skip_count = 0
        fail_count = 0

        for i, (key, url) in enumerate(links, 1):
            # 跳過已有且有效的資料（非強制模式）
            if not FORCE_MODE:
                existing = data.get(key, "")
                if existing and is_valid_content(existing):
                    skip_count += 1
                    # 每 50 筆顯示一次跳過進度
                    if skip_count % 50 == 0:
                        print(f"  ⏭  已跳過 {skip_count} 筆（已有資料）...")
                    continue

            prefix = f"[{i:3d}/{len(links)}]"
            print(f"{prefix} 抓取 {key} ...", end="", flush=True)

            try:
                text = scrape_detail(detail_page, url)

                if is_valid_content(text):
                    data[key] = text
                    new_count += 1
                    print(f" ✅ {len(text):,} 字")
                else:
                    # 內容可疑，存但標記
                    data[key] = text if text else "（詳情頁內容為空）"
                    fail_count += 1
                    print(f" ⚠️  內容疑似不完整（{len(text)} 字）")

            except Exception as e:
                data[key] = f"（抓取失敗：{e}）"
                fail_count += 1
                print(f" ❌ {e}")

            # 每 SAVE_EVERY 筆存一次
            if new_count > 0 and new_count % SAVE_EVERY == 0:
                data["_metadata"] = {
                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total": len([k for k in data if k != "_metadata"])
                }
                save(data)
                print(f"  💾 進度存檔（已抓 {new_count} 筆新資料）")

        detail_page.close()
        browser.close()

    # ── 最終存檔 ──
    data["_metadata"] = {
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len([k for k in data if k != "_metadata"])
    }
    save(data)

    total = len([k for k in data if k != "_metadata"])
    print()
    print("=" * 60)
    print(f"✅ 完成！")
    print(f"   新抓取：{new_count} 筆")
    print(f"   跳過（已有）：{skip_count} 筆")
    print(f"   失敗/疑似無效：{fail_count} 筆")
    print(f"   JSON 總計：{total} 筆")
    print(f"   存檔路徑：{OUTPUT_PATH}")
    print("=" * 60)

    if fail_count > 0:
        print(f"\n⚠️  有 {fail_count} 筆失敗，可再次執行腳本補跑（續跑模式會自動重試失敗筆數）")
        print("   或加 --force 參數強制重抓所有")


if __name__ == "__main__":
    main()
