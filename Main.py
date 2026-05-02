import tkinter as tk
from tkinter import messagebox, ttk
import threading
import json
import os
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# === 考科與法規配置 (方便未來增補) ===
LAWS_CONFIG = {
    "一、憲法與行政法": {
        "中華民國憲法": "A0000001",
        "憲法增修條文": "A0000002",
        "憲法訴訟法": "A0030159",
        "行政程序法": "A0030055",
        "行政訴訟法": "A0030154",
        "國家賠償法": "I0020004",
    },
    "二、民法與民事訴訟法": {
        "民法": "B0000001",
        "民事訴訟法": "B0010001",
        "家事事件法": "B0010048",
        "強制執行法": "B0010004",
        "消費者保護法": "J0170001",
        "消費者保護法施行細則": "J0170002",
    },
    "三、刑法與刑事訴訟法": {
        "中華民國刑法": "C0000001",
        "刑事訴訟法": "C0010001",
        "國民法官法": "A0030320",
        "貪污治治罪條例": "C0010008",
    },
    "四、商事法": {
        "公司法": "J0080001",
        "證券交易法": "G0400001",
        "保險法": "G0390002",
        "票據法": "G0380028",
    },
    "五、經濟法規": {
        "商標法": "J0070001",
        "專利法": "J0070007",
        "專利法施行細則": "J0070008",
        "著作權法": "J0070017",
    },
    "六、其他法規": {
        "信託法": "I0020024",
    },
    "七、司法解釋": {
        "大法官解釋": "JUDGE_B1",
        "憲法法庭判決": "JUDGE_B5",
    }
}

class JudiciaryLawApp:
    def __init__(self, root):
        self.root = root
        self.root.title("司法官考試 - 法典隨身助手 (半形模式)")
        self.root.geometry("1000x750")
        
        self.data_dir = "law_data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        self.current_pcode = None
        self.current_law_name = ""
        self.law_data = {}
        
        self.favorites_path = os.path.join(self.data_dir, "favorites.json")
        self.favorites = self.load_favorites()
        
        self.numpad_visible = True
        self.full_cache = {} # 記憶體快取
        self.last_search_keyword = "" # 紀錄最後一次搜尋
        self.is_in_search_view = False # 是否正在顯示搜尋結果
        
        self.setup_ui()
        self.preload_all_data()

    def format_article_title(self, key, pcode=None):
        """依據法規類型，格式化條號標題"""
        pcode = pcode or self.current_pcode
        if pcode and pcode.startswith("JUDGE_"):
            return key  # 憲判/釋字直接用完整標題
        return f"第 {key} 條"

    def normalize_judge_key(self, raw):
        """把各種輸入格式統一化為 key 格式"""
        raw = raw.strip()
        
        # 處理 112-17 或 112/17 簡寫 -> 112年憲判字第17號
        m_cons = re.match(r'^(\d+)[-/](\d+)$', raw)
        if m_cons:
            return f"{m_cons.group(1)}年憲判字第{m_cons.group(2)}號"
        
        # 處理純數字 748 -> 釋字第748號
        if raw.isdigit():
            return f"釋字第{raw}號"
            
        # 處理已有文字但有多餘空格
        cleaned = re.sub(r'\s+', '', raw)
        return cleaned
        
    def load_favorites(self):
        if os.path.exists(self.favorites_path):
            try:
                with open(self.favorites_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: return []
        return []

    def save_favorites(self):
        with open(self.favorites_path, "w", encoding="utf-8") as f:
            json.dump(self.favorites, f, ensure_ascii=False)

    def setup_ui(self):
        bg_color = "#f5f5f5"
        self.root.configure(bg=bg_color)
        
        # 鍵盤快捷鍵
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus())
        self.root.bind("<Escape>", lambda e: self.search_var.set(""))
        
        # 主佈局：左右分割
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(expand=True, fill="both")
        
        # --- 左側：法規導覽列 ---
        left_frame = ttk.Frame(self.paned, padding="5")
        self.paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="考科法規清單", font=("Microsoft JhengHei", 12, "bold")).pack(pady=5)
        
        self.tree = ttk.Treeview(left_frame, show="tree", selectmode="browse")
        self.tree.pack(expand=True, fill="both")
        
        # 填充資料 (改用函式方便刷新)
        self.refresh_tree()
        
        self.tree.bind("<<TreeviewSelect>>", self.on_law_select)
        
        # --- 右側：顯示與控制區 ---
        right_frame = ttk.Frame(self.paned, padding="10")
        self.paned.add(right_frame, weight=4)
        
        # 控制列
        ctrl_frame = ttk.Frame(right_frame)
        ctrl_frame.pack(fill="x", pady=(0, 10))
        
        self.title_label = tk.Label(ctrl_frame, text="請選擇左側法規", font=("Microsoft JhengHei", 16, "bold"))
        self.title_label.pack(side=tk.LEFT)
        
        self.btn_star = ttk.Button(ctrl_frame, text="☆", style="Star.TButton", command=self.toggle_star, state=tk.DISABLED)
        self.btn_star.pack(side=tk.LEFT, padx=10)

        self.btn_full = ttk.Button(ctrl_frame, text="法條全文", style="Action.TButton", command=self.display_full_law, state=tk.DISABLED)
        self.btn_full.pack(side=tk.LEFT, padx=5)
        
        self.btn_sync = ttk.Button(ctrl_frame, text="🔄 同步/更新此法典", style="Action.TButton", command=self.start_sync_thread, state=tk.DISABLED)
        self.btn_sync.pack(side=tk.RIGHT, padx=5)
        
        # 搜尋列
        self.search_container = ttk.LabelFrame(right_frame, text="搜尋與導覽", padding="10")
        self.search_container.pack(fill="x", pady=5)
        
        search_ctrl_frame = ttk.Frame(self.search_container)
        search_ctrl_frame.pack(fill="x", pady=(0, 5))

        self.search_mode = tk.StringVar(value="no") # "no", "key", "global"
        ttk.Radiobutton(search_ctrl_frame, text="條號查詢", variable=self.search_mode, value="no").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(search_ctrl_frame, text="全文檢索", variable=self.search_mode, value="key").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(search_ctrl_frame, text="跨法檢索", variable=self.search_mode, value="global").pack(side=tk.LEFT, padx=5)

        # 快速導覽按鈕 (前一條/後一條)
        nav_frame = ttk.Frame(search_ctrl_frame)
        nav_frame.pack(side=tk.RIGHT, padx=5)
        
        self.btn_prev = ttk.Button(nav_frame, text="◀ 前一條", width=8, command=lambda: self.navigate_article(-1))
        self.btn_prev.pack(side=tk.LEFT, padx=2)
        
        self.btn_next = ttk.Button(nav_frame, text="後一條 ▶", width=8, command=lambda: self.navigate_article(1))
        self.btn_next.pack(side=tk.LEFT, padx=2)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_container, textvariable=self.search_var, font=("Microsoft JhengHei", 12))
        self.search_entry.pack(side=tk.LEFT, padx=5, expand=True, fill="x")
        self.search_entry.bind("<Return>", lambda e: self.display_law())
        
        self.btn_search = ttk.Button(self.search_container, text="🔍 搜尋", command=self.display_law)
        self.btn_search.pack(side=tk.LEFT, padx=5)
        
        self.btn_back_search = ttk.Button(self.search_container, text="↩ 返回結果", command=self.restore_search_view)
        # 預設隱藏，搜尋後才顯示
        
        # 勾選選項
        options_frame = ttk.Frame(self.search_container)
        options_frame.pack(fill="x", pady=(5, 0))

        self.include_name_var = tk.BooleanVar(value=False)
        self.chk_name = ttk.Checkbutton(options_frame, text="帶入名稱", variable=self.include_name_var)
        self.chk_name.pack(side=tk.LEFT, padx=5)

        self.obsidian_format_var = tk.BooleanVar(value=True)
        self.chk_obsidian = ttk.Checkbutton(options_frame, text="Obsidian 格式", variable=self.obsidian_format_var)
        self.chk_obsidian.pack(side=tk.LEFT, padx=5)
        
        self.btn_copy = ttk.Button(options_frame, text="📋 複製條文", command=self.copy_text, state=tk.DISABLED)
        self.btn_copy.pack(side=tk.LEFT, padx=5)

        self.btn_toggle_numpad = ttk.Button(options_frame, text="︿ 收合鍵盤", command=self.toggle_numpad)
        self.btn_toggle_numpad.pack(side=tk.RIGHT, padx=5)
        
        # --- 數字小鍵盤區 ---
        # --- 樣式設定 ---
        style.configure("Action.TButton", font=("Microsoft JhengHei", 10))
        style.configure("Star.TButton", font=("Microsoft JhengHei", 10), width=3)
        style.configure("Numpad.TButton", font=("Microsoft JhengHei", 12, "bold"), width=4)
        style.configure("NumpadEnter.TButton", font=("Microsoft JhengHei", 12, "bold"), width=4, foreground="#0056b3")
        style.configure("Fav.TButton", font=("Microsoft JhengHei", 9), width=12)
        
        self.keyboard_container = ttk.Frame(right_frame)
        self.keyboard_container.pack(side=tk.TOP, anchor="w", pady=(0, 15), after=self.search_container)
        
        self.numpad_frame = ttk.Frame(self.keyboard_container)
        self.numpad_frame.pack(side=tk.LEFT, padx=(0, 20), anchor="n")
        
        self.favorites_frame = ttk.Frame(self.keyboard_container)
        self.favorites_frame.pack(side=tk.LEFT, fill="y", anchor="n")
        
        # 鍵盤佈局定義 (模擬標準鍵盤)
        button_layout = [
            ['7', '8', '9', 'C'],
            ['4', '5', '6', '←'],
            ['1', '2', '3', '-'],
            ['0', 'Enter']
        ]
        
        for r, row in enumerate(button_layout):
            for c, btn_text in enumerate(row):
                cmd = lambda t=btn_text: self.on_numpad_click(t)
                s = "NumpadEnter.TButton" if btn_text == "Enter" else "Numpad.TButton"
                btn = ttk.Button(self.numpad_frame, text=btn_text, style=s, command=cmd)
                
                # 讓 Enter 鍵大一點或特殊處理
                colspan = 3 if btn_text == "Enter" else 1
                btn.grid(row=r, column=c, columnspan=colspan, padx=3, pady=3, sticky="nsew")
        
        self.refresh_favorites_ui()
        
        # 內容顯示區 (一頁式)
        display_container = ttk.Frame(right_frame)
        display_container.pack(expand=True, fill="both")
        
        scrollbar = ttk.Scrollbar(display_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text_area = tk.Text(display_container, wrap=tk.WORD, font=("Microsoft JhengHei", 12), 
                                padx=20, pady=20, yscrollcommand=scrollbar.set,
                                bg="white", relief="flat")
        self.text_area.pack(side=tk.LEFT, expand=True, fill="both")
        scrollbar.config(command=self.text_area.yview)
        self.text_area.config(state=tk.DISABLED)
        
        # 狀態標籤與進度條
        status_frame = ttk.Frame(right_frame)
        status_frame.pack(side=tk.BOTTOM, fill="x")
        
        self.status_label = tk.Label(status_frame, text="準備就緒", fg="gray", font=("Microsoft JhengHei", 9))
        self.status_label.pack(side=tk.RIGHT, padx=5)
        
        self.progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, length=150, mode='indeterminate')
        # 預設不顯示，同步時才 pack

    def refresh_tree(self):
        # 記錄目前選中的項目，以便刷新後恢復
        selected = self.tree.selection()
        current_pcode = None
        if selected:
            item = self.tree.item(selected[0])
            if item['values']: current_pcode = item['values'][0]

        self.tree.delete(*self.tree.get_children())
        for cat, laws in LAWS_CONFIG.items():
            node = self.tree.insert("", "end", text=cat, open=True)
            for name, pcode in laws.items():
                display_name = f"{name} ⭐" if pcode in self.favorites else name
                new_item = self.tree.insert(node, "end", text=display_name, values=(pcode,))
                if pcode == current_pcode:
                    self.tree.selection_set(new_item)

    def refresh_favorites_ui(self):
        for widget in self.favorites_frame.winfo_children():
            widget.destroy()
            
        if not self.favorites:
            ttk.Label(self.favorites_frame, text="(尚無收藏)", foreground="gray").pack(pady=10)
            return

        ttk.Label(self.favorites_frame, text="⭐ 快速跳轉", font=("Microsoft JhengHei", 10, "bold")).pack(pady=(0, 5))
        
        # 建立 PCode 轉名稱的對照表
        pcode_to_name = {}
        for laws in LAWS_CONFIG.values():
            for name, pcode in laws.items():
                pcode_to_name[pcode] = name
                
        for pcode in self.favorites:
            name = pcode_to_name.get(pcode, pcode)
            btn = ttk.Button(self.favorites_frame, text=name, style="Fav.TButton",
                             command=lambda p=pcode: self.select_law_by_pcode(p))
            btn.pack(fill="x", pady=2)

    def select_law_by_pcode(self, pcode):
        """在 Treeview 中搜尋並選中對應 PCode 的法規 (支援遞迴搜尋)"""
        def search_recursive(items):
            for item in items:
                values = self.tree.item(item).get('values')
                # 確保 values 存在且第一個元素匹配 pcode
                if values and len(values) >= 1 and str(values[0]) == str(pcode):
                    self.tree.selection_set(item)
                    self.tree.see(item)
                    self.on_law_select(None)
                    return True
                # 往子層搜尋
                if search_recursive(self.tree.get_children(item)):
                    return True
            return False
        
        search_recursive(self.tree.get_children(""))

    def toggle_star(self):
        if not self.current_pcode: return
        
        if self.current_pcode in self.favorites:
            self.favorites.remove(self.current_pcode)
            self.btn_star.config(text="☆")
        else:
            self.favorites.append(self.current_pcode)
            self.btn_star.config(text="★")
            
        self.save_favorites()
        self.refresh_tree()
        self.refresh_favorites_ui()

    def on_law_select(self, event):
        selected = self.tree.selection()
        if not selected: return
        
        item = self.tree.item(selected[0])
        # 如果是搜尋結果中的條目 (values 長度為 2: [pcode, article_no])
        if item['values'] and len(item['values']) == 2:
            pcode, article_no = item['values']
            self.current_pcode = pcode
            # 找到法規名稱
            pcode_to_name = {p: n for cats in LAWS_CONFIG.values() for n, p in cats.items()}
            self.current_law_name = pcode_to_name.get(pcode, pcode)
            
            self.title_label.config(text=self.current_law_name)
            self.search_var.set(article_no)
            self.search_mode.set("no")
            self.btn_sync.config(state=tk.NORMAL)
            self.btn_star.config(state=tk.NORMAL)
            self.btn_full.config(state=tk.NORMAL)
            
            self.load_law_data()
            self.root.after(50, self.display_law)
            return

        if not item['values']: # 點到分類標題
            self.btn_star.config(state=tk.DISABLED)
            self.btn_full.config(state=tk.DISABLED)
            return
            
        # 獲取原始名稱 (移除 ⭐)
        raw_name = item['text'].replace(" ⭐", "")
        self.current_law_name = raw_name
        self.current_pcode = item['values'][0]
        self.title_label.config(text=self.current_law_name)
        self.btn_sync.config(state=tk.NORMAL)
        self.btn_star.config(state=tk.NORMAL)
        self.btn_full.config(state=tk.NORMAL)
        
        # 點擊左側一般法規時，隱藏「返回結果」按鈕
        self.btn_back_search.pack_forget()
        self.is_in_search_view = False

        # 更新收藏按鈕文字
        star_text = "★" if self.current_pcode in self.favorites else "☆"
        self.btn_star.config(text=star_text)
        
        # 嘗試讀取本地資料
        self.load_law_data()

    def load_law_data(self):
        file_path = os.path.join(self.data_dir, f"{self.current_pcode}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.law_data = {k: v for k, v in data.items() if k != "_metadata"}
            except (json.JSONDecodeError, Exception):
                # 檔案損毀或為空，當作沒資料處理
                self.law_data = {}
                self.text_area.config(state=tk.NORMAL)
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert(tk.END, "⚠️ 資料檔損毀或為空，請點擊「同步」重新抓取。")
                self.text_area.config(state=tk.DISABLED)
                return

            self.text_area.config(state=tk.NORMAL)
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, f"--- 已載入 {self.current_law_name} ---\n請在上方搜尋條號。")
            self.text_area.config(state=tk.DISABLED)
        else:
            self.law_data = {}
            self.text_area.config(state=tk.NORMAL)
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, "⚠️ 本地無資料，請點擊右上角「同步」按鈕從政府網站抓取。")
            self.text_area.config(state=tk.DISABLED)

    def display_law(self):
        target = self.search_var.get().strip()
        mode = self.search_mode.get()
        
        # 讓 B1 (釋字) 與 B5 (憲判) 都支援自動格式化
        if self.current_pcode in ["JUDGE_B1", "JUDGE_B5"]:
            target = self.normalize_judge_key(target)

        # 如果搜尋框是空的，視為「重設」，恢復原本的法律庫清單
        if not target:
            self.refresh_tree()
            self.btn_back_search.pack_forget()
            self.status_label.config(text="已恢復法律庫目錄", fg="gray")
            return

        # 只有在非全域搜尋模式下才需要先選定法規 (self.law_data)
        if mode != "global" and not self.law_data: 
            self.status_label.config(text="⚠️ 請先從左側選擇法規", fg="orange")
            return
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        
        if self.search_mode.get() == "no":
            # 條號查詢模式
            if target in self.law_data:
                display_title = self.format_article_title(target)
                header = f"【{display_title}】\n" + "-"*30 + "\n"
                self.text_area.insert(tk.END, header, "header")
                self.text_area.insert(tk.END, self.law_data[target])
                self.add_smart_links()
                self.btn_copy.config(state=tk.NORMAL)
            else:
                self.btn_copy.config(state=tk.DISABLED)
                self.text_area.insert(tk.END, f"❌ 此法典中找不到：{self.format_article_title(target)}")
        elif self.search_mode.get() == "key":
            # 全文檢索模式
            self.btn_copy.config(state=tk.DISABLED)
            found_count = 0
            
            # 智慧排序邏輯
            def sort_key(s):
                return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', s)]
            
            sorted_keys = sorted(self.law_data.keys(), key=sort_key)
            
            for key in sorted_keys:
                content = self.law_data[key]
                if target in content:
                    found_count += 1
                    display_title = self.format_article_title(key)
                    self.text_area.insert(tk.END, f"【{display_title}】\n", "article_title")
                    self.text_area.insert(tk.END, f"{content}\n")
                    self.text_area.insert(tk.END, "-"*30 + "\n\n")
            
            if found_count > 0:
                self.status_label.config(text=f"🔍 關鍵字「{target}」共找到 {found_count} 處", fg="#28a745")
                self.highlight_keyword(target)
                self.add_smart_links()
                # 自動捲動到第一個匹配項
                first_match = self.text_area.tag_ranges("match")
                if first_match: self.text_area.see(first_match[0])
            else:
                self.text_area.insert(tk.END, f"❌ 找不到包含「{target}」的條文")
                self.status_label.config(text="未找到符合項目", fg="red")
        elif self.search_mode.get() == "global":
            # 跨法規檢索模式
            self.display_global_search(target)

        self.text_area.tag_configure("header", font=("Microsoft JhengHei", 14, "bold"), foreground="#333")
        self.text_area.tag_configure("article_title", font=("Microsoft JhengHei", 12, "bold"), foreground="#0056b3")
        self.text_area.tag_configure("link", foreground="#0056b3", underline=True)
        self.text_area.tag_bind("link", "<Enter>", lambda e: self.text_area.config(cursor="hand2"))
        self.text_area.tag_bind("link", "<Leave>", lambda e: self.text_area.config(cursor=""))
        self.text_area.config(state=tk.DISABLED)

    def navigate_article(self, direction):
        """智慧導覽：前往前一條或後一條"""
        if not self.law_data: return
        
        current = self.search_var.get().strip()
        
        # 智慧排序邏輯
        def sort_key(s):
            return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', s)]
            
        sorted_keys = sorted(self.law_data.keys(), key=sort_key)
        
        if not current or current not in self.law_data:
            # 如果沒搜尋，預設從第一條或最後一條開始
            target_idx = 0 if direction > 0 else len(sorted_keys) - 1
        else:
            current_idx = sorted_keys.index(current)
            target_idx = current_idx + direction
            
        if 0 <= target_idx < len(sorted_keys):
            target_key = sorted_keys[target_idx]
            self.search_var.set(target_key)
            self.search_mode.set("no") # 切換回條號模式以便導覽顯示
            self.display_law()
        else:
            self.status_label.config(text="已達法條邊界", fg="orange")

    def add_smart_links(self):
        """偵測文本中的條號並加上超連結"""
        # 匹配「第 123 條」或「第 123-1 條」
        # regex = r"第\s*([\d-]+)\s*條"
        content = self.text_area.get("1.0", tk.END)
        for match in re.finditer(r"第\s*([\d-]+)\s*條", content):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            article_no = match.group(1)
            
            # 為此區間建立獨有的 tag，以便綁定點擊事件
            tag_name = f"link_{article_no}_{match.start()}"
            self.text_area.tag_add("link", start_idx, end_idx)
            self.text_area.tag_add(tag_name, start_idx, end_idx)
            self.text_area.tag_bind(tag_name, "<Button-1>", lambda e, a=article_no: self.jump_to_article(a))

    def jump_to_article(self, article_no):
        self.search_var.set(article_no)
        self.search_mode.set("no")
        self.display_law()

    def display_global_search(self, keyword):
        """搜尋所有本地已下載的法規，同時在左側顯示樹狀結構、右側顯示條文預覽"""
        self.last_search_keyword = keyword
        self.is_in_search_view = True
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, f"🌐 全域搜尋關鍵字：「{keyword}」\n", "header")
        self.text_area.insert(tk.END, "="*40 + "\n\n")
        
        # 清空 Treeview 並準備填入搜尋結果
        self.tree.delete(*self.tree.get_children())
        search_root = self.tree.insert("", "end", text=f"🔍 搜尋: {keyword}", open=True)
        
        found_total = 0
        pcode_to_name = {p: n for cats in LAWS_CONFIG.values() for n, p in cats.items()}
        
        for pcode, data in self.full_cache.items():
            law_name = pcode_to_name.get(pcode, pcode)
            matches_in_law = []
            for key, content in data.items():
                if keyword in content:
                    # 擷取預覽
                    idx = content.find(keyword)
                    start = max(0, idx - 20)
                    end = min(len(content), idx + len(keyword) + 30)
                    preview = content[start:end].replace('\n', ' ')
                    matches_in_law.append((key, preview))
            
            if matches_in_law:
                found_total += len(matches_in_law)
                update_date = self.law_update_dates.get(pcode, "未知")
                
                # 1. 填入左側 Treeview (樹狀導覽)
                law_node = self.tree.insert(search_root, "end", text=f"📘 {law_name} ({len(matches_in_law)})", open=False)
                
                # 2. 填入右側 Text Area (文字預覽)
                self.text_area.insert(tk.END, f"📘 {law_name} ({update_date})\n", "law_header")
                
                for key, preview in matches_in_law:
                    display_title = self.format_article_title(key, pcode)
                    # 左側子節點
                    self.tree.insert(law_node, "end", text=display_title, values=(pcode, key))
                    
                    # 右側跳轉連結
                    tag_name = f"jump_{pcode}_{key}"
                    self.text_area.insert(tk.END, f"  • {display_title}: ", "article_title")
                    self.text_area.insert(tk.END, f"...{preview}...\n", tag_name)
                    self.text_area.tag_add("link", f"{tag_name}.first", f"{tag_name}.last")
                    self.text_area.tag_bind(tag_name, "<Button-1>", lambda e, p=pcode, k=key: self.jump_to_global_article(p, k))
                
                self.text_area.insert(tk.END, "\n")

        if found_total > 0:
            self.status_label.config(text=f"✅ 全域搜尋共找到 {found_total} 處", fg="#28a745")
            self.highlight_keyword(keyword)
            # 顯示「返回搜尋結果」按鈕
            self.btn_back_search.pack(side=tk.LEFT, padx=5)
        else:
            self.tree.insert(search_root, "end", text="(查無結果)")
            self.text_area.insert(tk.END, "❌ 所有已下載法規中皆找不到此關鍵字。")
            self.status_label.config(text="全域搜尋無結果", fg="red")
            self.btn_back_search.pack_forget()

        self.text_area.tag_configure("header", font=("Microsoft JhengHei", 14, "bold"), foreground="#333")
        self.text_area.tag_configure("law_header", font=("Microsoft JhengHei", 12, "bold"), foreground="#28a745")
        self.text_area.config(state=tk.DISABLED)

    def restore_search_view(self):
        """返回上一次的搜尋結果視圖"""
        if self.last_search_keyword:
            self.display_global_search(self.last_search_keyword)

    def jump_to_global_article(self, pcode, article_no):
        self.select_law_by_pcode(pcode)
        self.search_var.set(article_no)
        self.search_mode.set("no")
        # 延遲一點點執行 (50ms)，確保 Treeview 的選擇事件處理完畢，才顯示具體法條內容
        self.root.after(50, self.display_law)

    def highlight_keyword(self, keyword):
        self.text_area.tag_remove("match", "1.0", tk.END)
        self.text_area.tag_configure("match", background="#ffeb3b", foreground="black")
        
        start_pos = "1.0"
        while True:
            start_pos = self.text_area.search(keyword, start_pos, stopindex=tk.END)
            if not start_pos: break
            end_pos = f"{start_pos}+{len(keyword)}c"
            self.text_area.tag_add("match", start_pos, end_pos)
            start_pos = end_pos

    def display_full_law(self):
        if not self.law_data: 
            messagebox.showinfo("提示", "請先選擇法規並確保已有資料。")
            return
        
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        
        # 標題
        self.text_area.insert(tk.END, f"📜 {self.current_law_name} - 全文瀏覽\n")
        self.text_area.insert(tk.END, "="*40 + "\n\n")
        
        # 智慧排序邏輯 (處理 199-1 等條號)
        def sort_key(s):
            return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', s)]
            
        sorted_keys = sorted(self.law_data.keys(), key=sort_key)
        
        for key in sorted_keys:
            content = self.law_data[key]
            # 條號標題
            display_title = self.format_article_title(key)
            self.text_area.insert(tk.END, f"【{display_title}】\n", "article_title")
            # 內容
            self.text_area.insert(tk.END, f"{content}\n\n")
            self.text_area.insert(tk.END, "-"*30 + "\n\n")
            
        # 設定標題樣式
        self.text_area.tag_configure("article_title", font=("Microsoft JhengHei", 12, "bold"), foreground="#0056b3")
        
        self.text_area.config(state=tk.DISABLED)
        self.btn_copy.config(state=tk.DISABLED)
        self.status_label.config(text=f"✅ 已載入全文 (共 {len(sorted_keys)} 條)", fg="#0056b3")
        self.text_area.see("1.0") # 回到最上方

    def toggle_numpad(self):
        if self.numpad_visible:
            self.keyboard_container.pack_forget()
            self.btn_toggle_numpad.config(text="﹀ 展開鍵盤")
        else:
            # 將容器插入到搜尋列之後，內容區之前
            # 將容器插入到搜尋列之後，內容區之前
            # 將容器插入到搜尋列之後，內容區之前
            self.keyboard_container.pack(side=tk.TOP, anchor="w", pady=(0, 15), after=self.search_container)
            self.btn_toggle_numpad.config(text="︿ 收合鍵盤")
        self.numpad_visible = not self.numpad_visible

    def on_numpad_click(self, char):
        current = self.search_var.get()
        if char == 'C':
            self.search_var.set("")
        elif char == '←':
            self.search_var.set(current[:-1])
        elif char == 'Enter':
            self.display_law()
        else:
            self.search_var.set(current + char)
        
        self.search_entry.focus()
            
    def to_half_width(self, text):
        """將全形字元轉換為半形字元，但保留常見的中文標點符號"""
        res = []
        # 定義要保留全形的標點符號
        keep_full = {'，', '；', '：', '！', '？', '（', '）'}
        for char in text:
            if char in keep_full:
                res.append(char)
                continue
            num = ord(char)
            if num == 0x3000:  # 全形空格
                res.append(' ')
            elif 0xFF01 <= num <= 0xFF5E:  # 全形字元 (除空格外)
                res.append(chr(num - 0xfee0))
            else:
                res.append(char)
        return "".join(res)


    def copy_text(self):
        target = self.search_var.get().strip()
        if self.current_pcode in ["JUDGE_B1", "JUDGE_B5"]:
            target = self.normalize_judge_key(target)
            
        if target not in self.law_data:
            self.status_label.config(text="❌ 找不到條號，無法複製", fg="red")
            return

        content = self.law_data[target]
        law_name = self.current_law_name.strip()
        
        # 建立標題
        display_title = self.format_article_title(target)
        title_line = f"{law_name} {display_title}" if self.include_name_var.get() else display_title
        
        # 清理內容：統一半形、移除過多換行與特殊字元
        clean_content = self.to_half_width(content.strip()).replace('\xa0', ' ')
        clean_content = re.sub(r'\n{3,}', '\n\n', clean_content) # 最多保留兩個換行
        
        if self.obsidian_format_var.get():
            header = f"> [!law] {title_line}\n"
            obsidian_content = "\n".join([f"> {line}" if line.strip() else ">" for line in clean_content.split("\n")])
            final_text = f"{header}{obsidian_content}\n\n"
        else:
            final_text = f"{title_line}\n{clean_content}\n\n"

        self.root.clipboard_clear()
        self.root.clipboard_append(final_text)
        self.status_label.config(text=f"✅ 已複製至剪貼簿 ({target})", fg="#0056b3")

    def sync_law(self, url):
        self.root.after(0, lambda: self.progress.pack(side=tk.LEFT, padx=10))
        self.root.after(0, self.progress.start)
        
        try:
            is_judge = "LawSearchJudge" in url
            ty = self.current_pcode.split("_")[1] if is_judge else ""
            
            import datetime
            new_data = {
                "_metadata": {
                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
                
                if is_judge and ty == "B5":
                    # 憲法法庭 (B5) 改爬司法院官網
                    new_data = self._scrape_constitutional_court(context, new_data)
                else:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    if is_judge:
                        page.wait_for_selector("table[id*='gvList']", timeout=30000)
                        soup = BeautifulSoup(page.content(), 'html.parser')
                        self._process_judge_list(soup, context, new_data)
                    else:
                        page.wait_for_selector(".law-reg-content", timeout=20000)
                        soup = BeautifulSoup(page.content(), 'html.parser')
                        self._process_normal_law(soup, new_data)
                
                browser.close()

            if len(new_data) > 1:
                self.law_data = {k: v for k, v in new_data.items() if k != "_metadata"}
                file_path = os.path.join(self.data_dir, f"{self.current_pcode}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=4)
                
                self.full_cache[self.current_pcode] = self.law_data
                self.law_update_dates[self.current_pcode] = new_data["_metadata"]["last_updated"]
                self.status_label.config(text="✅ 同步完成", fg="green")
                self.root.after(0, lambda: messagebox.showinfo("完成", f"{self.current_law_name} 同步成功！"))
                self.root.after(0, self.load_law_data)
            else:
                raise Exception("抓取到的資料為空")

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"同步失敗: {str(e)}"))
        finally:
            self.root.after(0, self.progress.stop)
            self.root.after(0, self.progress.pack_forget)
            self.root.after(0, lambda: self.btn_sync.config(state=tk.NORMAL))

    def _scrape_constitutional_court(self, context, new_data):
        """爬司法院憲法法庭官網 (B5)"""
        page = context.new_page()
        # fid=38 為「憲法法庭判決」
        list_url = "https://cons.judicial.gov.tw/judcurrentNew1.aspx?fid=38"
        self.root.after(0, lambda: self.status_label.config(text="📥 載入憲法法庭清單...", fg="blue"))
        
        page.goto(list_url, wait_until="networkidle", timeout=60000)
        
        # 根據診斷結果，頁面不使用 table，而是 div.judgmentList
        items = page.query_selector_all(".judgmentList ul li a")
        print(f"[DEBUG] 抓到 {len(items)} 個憲判連結")
        
        links = []
        for a in items: # 抓取所有找到的連結，不設 60 筆限制
            raw_text = a.inner_text().strip()
            # 格式通常是 "115年憲判字\n\n第3號"，去掉換行
            case_no = raw_text.replace("\n", "").replace(" ", "")
            if "憲判字" not in case_no: continue
            
            href = a.get_attribute("href")
            if href:
                links.append((case_no, href))
        
        for i, (case_no, href) in enumerate(links):
            key = self.normalize_judge_key(case_no)
            existing = self.law_data.get(key, "")
            if existing and len(existing) > 100:
                new_data[key] = existing
                continue
                
            self.root.after(0, lambda i=i, total=len(links), cn=key: 
                self.status_label.config(text=f"📄 抓取 {cn} ({i+1}/{total})...", fg="orange"))
            
            try:
                dp = context.new_page()
                full_url = href if href.startswith("http") else f"https://cons.judicial.gov.tw/{href}"
                dp.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                
                # 根據診斷，詳情頁內容主要在 .lawPage 或 .lawList
                content_el = dp.query_selector(".lawPage, .lawList, .jud-content, #divJudContent")
                if content_el:
                    new_data[key] = content_el.inner_text().strip()
                else:
                    new_data[key] = dp.inner_text("body").strip()
                dp.close()
            except:
                new_data[key] = "抓取失敗，請稍後再試。"
        
        for k, v in self.law_data.items():
            if k not in new_data and "憲判字" in k:
                new_data[k] = v
        return new_data

    def _process_judge_list(self, soup, context, new_data):
        """處理全國法規網的司法解釋清單 (B1)"""
        table = soup.find('table', id=lambda x: x and 'gvList' in x)
        if not table: return
        
        links_to_crawl = []
        for row in table.find_all('tr')[1:101]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                title = self.normalize_judge_key(cols[0].get_text().strip())
                a_tag = cols[0].find('a')
                if a_tag and a_tag.get('href'):
                    link = a_tag['href']
                    if not link.startswith('http'):
                        link = "https://law.moj.gov.tw/LawClass/" + link.replace("../LawClass/", "").replace("LawClass/", "")
                    
                    existing = self.law_data.get(title, "")
                    if not existing or len(existing) < 100:
                        links_to_crawl.append((title, link))
                    else:
                        new_data[title] = existing

        if links_to_crawl:
            page = context.new_page()
            for i, (title, link) in enumerate(links_to_crawl[:50]): # 每次最多 50 筆
                self.root.after(0, lambda i=i, t=len(links_to_crawl), n=title: 
                    self.status_label.config(text=f"📥 深度同步 ({i+1}/{min(t,50)}): {n}", fg="orange"))
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=40000)
                    ds = BeautifulSoup(page.content(), 'html.parser')
                    details = []
                    for r in ds.find_all(['div', 'tr'], class_=re.compile(r'row|tr')):
                        th = r.find(['div', 'th', 'td'], class_=re.compile(r'col-th|header|th'))
                        td = r.find(['div', 'td'], class_=re.compile(r'col-td|content|td'))
                        if th and td:
                            label = th.get_text().strip()
                            if any(k in label for k in ["字號", "日期", "主文", "解釋文"]):
                                details.append(f"【{label}】\n{td.get_text(separator='\n').strip()}")
                    new_data[title] = "\n\n".join(details) if details else "解析失敗。"
                except:
                    new_data[title] = "詳細頁載入失敗。"
            page.close()
            
        for k, v in self.law_data.items():
            if k not in new_data: new_data[k] = v

    def _process_normal_law(self, soup, new_data):
        """處理一般法規解析"""
        articles = soup.find_all('div', class_='row')
        for art in articles:
            no_tag = art.find('div', class_='col-no')
            data_tag = art.find('div', class_='col-data')
            if no_tag and data_tag:
                title_raw = no_tag.get_text().strip()
                match = re.search(r'第\s*(.*?)\s*條', title_raw)
                key = match.group(1).replace(" ", "") if match else title_raw
                text = data_tag.get_text(separator='\n').strip()
                new_data[key] = re.sub(r'\n\s*\n', '\n', text)

    def preload_all_data(self):
        """啟動時將所有本地法規載入記憶體，優化搜尋效能"""
        self.full_cache = {}
        self.law_update_dates = {}
        if not os.path.exists(self.data_dir): return
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".json") and filename != "favorites.json":
                pcode = filename.replace(".json", "")
                try:
                    with open(os.path.join(self.data_dir, filename), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "_metadata" in data:
                            self.law_update_dates[pcode] = data["_metadata"].get("last_updated", "未知")
                            self.full_cache[pcode] = {k: v for k, v in data.items() if k != "_metadata"}
                        else:
                            self.full_cache[pcode] = data
                except: continue

    def start_sync_thread(self):
        self.btn_sync.config(state=tk.DISABLED)
        if self.current_pcode.startswith("JUDGE_"):
            ty = self.current_pcode.split("_")[1]
            url = f"https://law.moj.gov.tw/Law/LawSearchJudge.aspx?ty={ty}&psize=100"
        else:
            url = f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={self.current_pcode}"
            
        thread = threading.Thread(target=self.sync_law, args=(url,))
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.configure("Treeview", font=("Microsoft JhengHei", 10), rowheight=25)
    app = JudiciaryLawApp(root)
    root.mainloop()
