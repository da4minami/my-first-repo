#!/usr/bin/env python3
"""
廃棄物行政 法令・通知 自動収集スクリプト
NotebookLM取り込み用

使い方:
    pip install -r requirements_waste_laws.txt
    python download_waste_laws.py           # フル取得（テキストも保存）
    python download_waste_laws.py --urls    # URLリストのみ生成（ネット不要）

出力先: ./waste_laws_for_notebooklm/
  01_法律/       ← 各法律のテキスト
  02_政令/       ← 各政令のテキスト
  03_省令/       ← 各省令のテキスト
  04_通知/       ← 環境省通知のテキスト
  url_list_for_notebooklm.txt  ← NotebookLM の「URL追加」用
"""

import os
import re
import sys
import time
import json
import logging
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, urljoin
from datetime import datetime

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ─── 設定 ─────────────────────────────────────────────────
OUTPUT_DIR  = Path("waste_laws_for_notebooklm")
EGOV_API    = "https://laws.e-gov.go.jp/api/1"
EGOV_VIEW   = "https://laws.e-gov.go.jp/law"   # 法令表示URL prefix
DELAY       = 2.0
TIMEOUT     = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WasteLawCollector/1.0; "
        "+https://github.com/da4minami/my-first-repo)"
    )
}


# ─── 対象法令定義（法令ID付き）─────────────────────────────
# law_id: e-Gov の法令ID（{時代番号}{年号2桁}{AC/CO/M...}{番号}）
#   3=昭和, 4=平成, 5=令和 | AC=法律, CO=政令, M=省令
TARGET_LAWS = [
    # ======== 法律 ========
    {
        "category": "01_法律",
        "name": "廃棄物処理法",
        "official": "廃棄物の処理及び清掃に関する法律",
        "law_id": "345AC0000000137",    # 昭和45年法律第137号
        "law_num": "昭和45年法律第137号",
    },
    {
        "category": "01_法律",
        "name": "循環型社会形成推進基本法",
        "official": "循環型社会形成推進基本法",
        "law_id": "412AC0000000110",    # 平成12年法律第110号
        "law_num": "平成12年法律第110号",
    },
    {
        "category": "01_法律",
        "name": "資源有効利用促進法",
        "official": "資源の有効な利用の促進に関する法律",
        "law_id": "403AC0000000048",    # 平成3年法律第48号
        "law_num": "平成3年法律第48号",
    },
    {
        "category": "01_法律",
        "name": "容器包装リサイクル法",
        "official": "容器包装に係る分別収集及び再商品化の促進等に関する法律",
        "law_id": "407AC0000000112",    # 平成7年法律第112号
        "law_num": "平成7年法律第112号",
    },
    {
        "category": "01_法律",
        "name": "家電リサイクル法",
        "official": "特定家庭用機器再商品化法",
        "law_id": "410AC0000000097",    # 平成10年法律第97号
        "law_num": "平成10年法律第97号",
    },
    {
        "category": "01_法律",
        "name": "建設リサイクル法",
        "official": "建設工事に係る資材の再資源化等に関する法律",
        "law_id": "412AC0000000104",    # 平成12年法律第104号
        "law_num": "平成12年法律第104号",
    },
    {
        "category": "01_法律",
        "name": "食品リサイクル法",
        "official": "食品循環資源の再生利用等の促進に関する法律",
        "law_id": "412AC0000000116",    # 平成12年法律第116号
        "law_num": "平成12年法律第116号",
    },
    {
        "category": "01_法律",
        "name": "自動車リサイクル法",
        "official": "使用済自動車の再資源化等に関する法律",
        "law_id": "414AC0000000087",    # 平成14年法律第87号
        "law_num": "平成14年法律第87号",
    },
    {
        "category": "01_法律",
        "name": "小型家電リサイクル法",
        "official": "使用済小型電子機器等の再資源化の促進に関する法律",
        "law_id": "424AC0000000057",    # 平成24年法律第57号
        "law_num": "平成24年法律第57号",
    },
    {
        "category": "01_法律",
        "name": "PCB廃棄物特別措置法",
        "official": "ポリ塩化ビフェニル廃棄物の適正な処理の推進に関する特別措置法",
        "law_id": "413AC0000000065",    # 平成13年法律第65号
        "law_num": "平成13年法律第65号",
    },
    {
        "category": "01_法律",
        "name": "土壌汚染対策法",
        "official": "土壌汚染対策法",
        "law_id": "414AC0000000053",    # 平成14年法律第53号
        "law_num": "平成14年法律第53号",
    },
    {
        "category": "01_法律",
        "name": "浄化槽法",
        "official": "浄化槽法",
        "law_id": "358AC0000000043",    # 昭和58年法律第43号
        "law_num": "昭和58年法律第43号",
    },
    # ======== 政令 ========
    {
        "category": "02_政令",
        "name": "廃棄物処理法施行令",
        "official": "廃棄物の処理及び清掃に関する法律施行令",
        "law_id": "345CO0000000300",    # 昭和45年政令第300号
        "law_num": "昭和45年政令第300号",
    },
    {
        "category": "02_政令",
        "name": "容器包装リサイクル法施行令",
        "official": "容器包装に係る分別収集及び再商品化の促進等に関する法律施行令",
        "law_id": "408CO0000000396",    # 平成8年政令第396号
        "law_num": "平成8年政令第396号",
    },
    {
        "category": "02_政令",
        "name": "家電リサイクル法施行令",
        "official": "特定家庭用機器再商品化法施行令",
        "law_id": "411CO0000000372",    # 平成11年政令第372号
        "law_num": "平成11年政令第372号",
    },
    {
        "category": "02_政令",
        "name": "建設リサイクル法施行令",
        "official": "建設工事に係る資材の再資源化等に関する法律施行令",
        "law_id": "413CO0000000495",    # 平成13年政令第495号
        "law_num": "平成13年政令第495号",
    },
    {
        "category": "02_政令",
        "name": "食品リサイクル法施行令",
        "official": "食品循環資源の再生利用等の促進に関する法律施行令",
        "law_id": "413CO0000000310",    # 平成13年政令第310号
        "law_num": "平成13年政令第310号",
    },
    {
        "category": "02_政令",
        "name": "自動車リサイクル法施行令",
        "official": "使用済自動車の再資源化等に関する法律施行令",
        "law_id": "415CO0000000224",    # 平成15年政令第224号
        "law_num": "平成15年政令第224号",
    },
    {
        "category": "02_政令",
        "name": "PCB廃棄物特別措置法施行令",
        "official": "ポリ塩化ビフェニル廃棄物の適正な処理の推進に関する特別措置法施行令",
        "law_id": "414CO0000000390",    # 平成14年政令第390号
        "law_num": "平成14年政令第390号",
    },
    {
        "category": "02_政令",
        "name": "土壌汚染対策法施行令",
        "official": "土壌汚染対策法施行令",
        "law_id": "414CO0000000336",    # 平成14年政令第336号（要確認）
        "law_num": "平成14年政令第336号",
    },
    # ======== 省令 ========
    {
        "category": "03_省令",
        "name": "廃棄物処理法施行規則",
        "official": "廃棄物の処理及び清掃に関する法律施行規則",
        "law_id": "345M50000140006",    # 昭和45年厚生省令第35号（要確認）
        "law_num": "昭和46年厚生省令第35号",
        "search_fallback": "廃棄物の処理及び清掃に関する法律施行規則",
    },
    {
        "category": "03_省令",
        "name": "廃棄物処理施設技術基準省令",
        "official": "廃棄物処理施設の技術上の基準を定める省令",
        "law_id": None,
        "law_num": "昭和52年総理府令第6号",
        "search_fallback": "廃棄物処理施設の技術上の基準",
    },
    {
        "category": "03_省令",
        "name": "家電リサイクル法省令",
        "official": "特定家庭用機器再商品化法施行規則",
        "law_id": None,
        "law_num": "平成11年通商産業省・厚生省令第1号",
        "search_fallback": "特定家庭用機器再商品化法施行規則",
    },
    {
        "category": "03_省令",
        "name": "建設リサイクル法省令",
        "official": "建設工事に係る資材の再資源化等に関する法律施行規則",
        "law_id": None,
        "law_num": "平成14年国土交通省令第17号",
        "search_fallback": "建設工事に係る資材の再資源化等に関する法律施行規則",
    },
    {
        "category": "03_省令",
        "name": "自動車リサイクル法省令",
        "official": "使用済自動車の再資源化等に関する法律施行規則",
        "law_id": None,
        "law_num": "平成15年経済産業省・環境省令第7号",
        "search_fallback": "使用済自動車の再資源化等に関する法律施行規則",
    },
    {
        "category": "03_省令",
        "name": "PCB廃棄物特別措置法省令",
        "official": "ポリ塩化ビフェニル廃棄物の適正な処理の推進に関する特別措置法施行規則",
        "law_id": None,
        "law_num": "平成14年環境省令第21号",
        "search_fallback": "ポリ塩化ビフェニル廃棄物",
    },
]

# 環境省 通知・通達のインデックスページ
ENV_NOTICE_PAGES = [
    {
        "label": "廃棄物処理法・一般廃棄物関連通知",
        "url": "https://www.env.go.jp/recycle/waste_tech/ippan/index.html",
    },
    {
        "label": "産業廃棄物関連通知",
        "url": "https://www.env.go.jp/recycle/waste_tech/sangyo/index.html",
    },
    {
        "label": "廃棄物・リサイクルトップ",
        "url": "https://www.env.go.jp/recycle/index.html",
    },
    {
        "label": "PCB廃棄物関連",
        "url": "https://www.env.go.jp/recycle/poly/index.html",
    },
    {
        "label": "土壌汚染対策法関連",
        "url": "https://www.env.go.jp/water/dojo/law/index.html",
    },
    {
        "label": "廃棄物処理施設整備関連",
        "url": "https://www.env.go.jp/recycle/waste_tech/facility/index.html",
    },
]


# ─── e-Gov API ────────────────────────────────────────────

def check_egov_accessible() -> bool:
    """e-Gov APIにアクセスできるか確認する。"""
    try:
        res = requests.get(
            f"{EGOV_API}/lawlists/2",
            headers=HEADERS,
            timeout=10,
        )
        if "Host not in allowlist" in res.text or res.status_code == 403:
            return False
        return res.status_code < 500
    except Exception:
        return False


def egov_search_keyword(keyword: str) -> list[dict]:
    """キーワードで e-Gov 法令APIを検索する。"""
    url = f"{EGOV_API}/keyword?keyword={quote(keyword)}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.encoding = "utf-8"
        if "Host not in allowlist" in res.text:
            return []
        root = ET.fromstring(res.text)
        laws = []
        for law_elem in root.findall(".//Law"):
            laws.append({
                "law_id":   law_elem.findtext("LawId")   or "",
                "law_num":  law_elem.findtext("LawNum")  or "",
                "law_name": law_elem.findtext("LawName") or "",
                "law_type": law_elem.findtext("LawType") or "",
            })
        return laws
    except Exception as exc:
        log.debug("  検索エラー %s: %s", keyword, exc)
        return []


def egov_fetch_fulltext(law_id: str) -> str:
    """法令IDで全文XMLを取得しプレーンテキストに変換する。"""
    url = f"{EGOV_API}/lawdata/{law_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.encoding = "utf-8"
        if "Host not in allowlist" in res.text:
            return ""
        root = ET.fromstring(res.text)
        return _xml_to_plaintext(root)
    except Exception as exc:
        log.debug("  取得エラー law_id=%s: %s", law_id, exc)
        return ""


def _xml_to_plaintext(elem: ET.Element) -> str:
    """法令XMLをプレーンテキストに整形する。"""
    lines = []
    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    heading_map = {
        "LawTitle":      "【法令名】",
        "LawNum":        "【法令番号】",
        "EnactStatement":"【制定文】",
        "PartTitle":     "\n■ ",
        "ChapterTitle":  "\n▼ ",
        "SectionTitle":  "\n◇ ",
        "ArticleTitle":  "",
        "ParagraphNum":  "",
        "ItemNum":       "",
    }

    if tag in heading_map:
        text = (elem.text or "").strip()
        if text:
            lines.append(f"{heading_map[tag]}{text}")
    elif tag in ("Sentence", "TableSentence"):
        text = (elem.text or "").strip()
        if text:
            lines.append(text)
    elif tag == "AmendProvision":
        return ""  # 改正規定はスキップ
    else:
        if elem.text and elem.text.strip():
            lines.append(elem.text.strip())

    for child in elem:
        child_text = _xml_to_plaintext(child)
        if child_text:
            lines.append(child_text)
        if child.tail and child.tail.strip():
            lines.append(child.tail.strip())

    return "\n".join(filter(None, lines))


# ─── 環境省 通知収集 ─────────────────────────────────────

def collect_env_notice_links() -> list[dict]:
    """環境省サイトから通知・通達のリンクを収集する。"""
    if not HAS_BS4:
        log.warning("beautifulsoup4 未インストール。通知収集をスキップします。")
        return []

    results = []
    for page in ENV_NOTICE_PAGES:
        log.info("  [環境省] %s", page["label"])
        try:
            res = requests.get(page["url"], headers=HEADERS, timeout=TIMEOUT)
            if res.status_code != 200:
                log.warning("    アクセス失敗 (%d): %s", res.status_code, page["url"])
                time.sleep(DELAY)
                continue
            res.encoding = res.apparent_encoding or "utf-8"
            soup = BeautifulSoup(res.text, "lxml")

            base = "https://www.env.go.jp"
            for a in soup.find_all("a", href=True):
                href  = a["href"]
                title = a.get_text(strip=True)
                if len(title) < 6:
                    continue
                if any(kw in title for kw in [
                    "通知", "通達", "について", "に関する通知", "Q&A", "Q＆A",
                    "ガイドライン", "マニュアル", "解釈",
                ]):
                    full_url = urljoin(base, href)
                    if full_url.startswith("https://www.env.go.jp"):
                        results.append({
                            "label": page["label"],
                            "title": title,
                            "url":   full_url,
                        })
            time.sleep(DELAY)
        except Exception as exc:
            log.error("    エラー %s: %s", page["url"], exc)

    # 重複除去
    seen, unique = set(), []
    for item in results:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    return unique


def fetch_page_text(url: str) -> str:
    """ページ本文をテキストで取得する。"""
    if not HAS_BS4:
        return ""
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if res.status_code != 200:
            return ""
        res.encoding = res.apparent_encoding or "utf-8"
        soup = BeautifulSoup(res.text, "lxml")
        for selector in ["#main", "#content", "main", "article", ".content", ".main"]:
            main = soup.select_one(selector)
            if main:
                return main.get_text(separator="\n", strip=True)
        return soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        log.debug("  テキスト取得エラー %s: %s", url, exc)
        return ""


# ─── ユーティリティ ──────────────────────────────────────

def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def egov_law_url(law_id: str) -> str:
    return f"{EGOV_VIEW}/{law_id}"


def egov_search_url(law_name: str) -> str:
    return (
        "https://laws.e-gov.go.jp/search/elawsSearch/elaws_search/lsg0100/"
        f"?searchName={quote(law_name)}&searchButton=検索"
    )


# ─── メイン ──────────────────────────────────────────────

def main():
    urls_only = "--urls" in sys.argv

    log.info("=" * 60)
    log.info("廃棄物行政 法令・通知 収集スクリプト")
    if urls_only:
        log.info("モード: URLリスト生成のみ")
    log.info("出力先: %s", OUTPUT_DIR.resolve())
    log.info("=" * 60)

    OUTPUT_DIR.mkdir(exist_ok=True)
    url_entries: list[dict] = []
    stats = {"saved": 0, "url_only": 0, "error": 0}

    # ── e-Gov 接続確認 ──
    egov_ok = False
    if not urls_only:
        log.info("e-Gov API 接続確認...")
        egov_ok = check_egov_accessible()
        if egov_ok:
            log.info("  → 接続OK。法令テキストを取得します。")
        else:
            log.warning("  → e-Gov API に接続できません。")
            log.warning("    URLリストのみ生成します（--urls モード相当）。")
            log.warning("    ローカルPC で実行すると法令テキストも取得できます。")

    # ── 法律・政令・省令の処理 ──
    for item in TARGET_LAWS:
        cat_dir = OUTPUT_DIR / item["category"]
        cat_dir.mkdir(exist_ok=True)

        law_id  = item.get("law_id")
        view_url = egov_law_url(law_id) if law_id else egov_search_url(item["official"])

        url_entries.append({
            "category": item["category"],
            "name":     item["name"],
            "url":      view_url,
            "law_num":  item.get("law_num", ""),
        })

        if urls_only or not egov_ok:
            log.info("[URL登録] %s (%s)", item["name"], item.get("law_num", ""))
            stats["url_only"] += 1
            continue

        out_path = cat_dir / f"{sanitize(item['name'])}.txt"
        if out_path.exists():
            log.info("[スキップ] 既存: %s", out_path.name)
            stats["saved"] += 1
            continue

        # law_id があれば直接取得、なければキーワード検索
        if law_id:
            log.info("[取得] %s (%s)", item["name"], law_id)
            text = egov_fetch_fulltext(law_id)
            time.sleep(DELAY)
        else:
            kw = item.get("search_fallback", item["official"])
            log.info("[検索] %s", kw)
            candidates = egov_search_keyword(kw)
            time.sleep(DELAY)
            if not candidates:
                log.warning("  ヒットなし: %s", kw)
                stats["error"] += 1
                continue
            best = next(
                (c for c in candidates if item["official"] in c["law_name"]),
                candidates[0],
            )
            log.info("  → %s (%s)", best["law_name"], best["law_num"])
            text = egov_fetch_fulltext(best["law_id"])
            law_id = best["law_id"]
            time.sleep(DELAY)

        if not text.strip():
            log.warning("  テキスト空: %s", item["name"])
            stats["error"] += 1
            continue

        header = (
            f"法令名: {item['official']}\n"
            f"通称: {item['name']}\n"
            f"法令番号: {item.get('law_num', '')}\n"
            f"取得日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"出典: e-Gov 法令検索 ({egov_law_url(law_id)})\n"
            f"{'=' * 60}\n\n"
        )
        out_path.write_text(header + text, encoding="utf-8")
        kb = out_path.stat().st_size / 1024
        log.info("  [保存] %s (%.1f KB)", out_path.name, kb)
        stats["saved"] += 1

    # ── 環境省 通知収集 ──
    log.info("")
    log.info("[環境省] 通知・通達リスト収集...")
    notice_dir = OUTPUT_DIR / "04_通知"
    notice_dir.mkdir(exist_ok=True)
    notices: list[dict] = []

    if not urls_only and egov_ok:
        notices = collect_env_notice_links()
        log.info("  %d 件の通知リンクを検出", len(notices))

        if notices:
            # カテゴリ別URLリストを保存
            by_label: dict[str, list] = {}
            for n in notices:
                by_label.setdefault(n["label"], []).append(n)

            for label, items in by_label.items():
                fname = sanitize(label) + "_URLリスト.txt"
                lines = [
                    f"# {label}",
                    f"# 収集日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    f"# 件数: {len(items)} 件", "",
                ]
                for n in items:
                    lines += [f"## {n['title']}", f"URL: {n['url']}", ""]
                (notice_dir / fname).write_text("\n".join(lines), encoding="utf-8")

            # 本文テキスト取得（上位30件）
            log.info("  通知本文取得中（最大30件）...")
            text_dir = notice_dir / "texts"
            text_dir.mkdir(exist_ok=True)
            for i, n in enumerate(notices[:30], 1):
                fname = f"{i:03d}_{sanitize(n['title'])[:60]}.txt"
                out_path = text_dir / fname
                if out_path.exists():
                    continue
                log.info("  [%d/30] %s", i, n["title"][:45])
                body = fetch_page_text(n["url"])
                if body:
                    hdr = (
                        f"タイトル: {n['title']}\n"
                        f"URL: {n['url']}\n"
                        f"取得日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                        f"{'=' * 60}\n\n"
                    )
                    out_path.write_text(hdr + body, encoding="utf-8")
                time.sleep(DELAY)

            for n in notices:
                url_entries.append({
                    "category": "04_通知",
                    "name":     n["title"],
                    "url":      n["url"],
                    "law_num":  "",
                })
    else:
        # URLリストのみモード: 環境省インデックスページURLを登録
        for page in ENV_NOTICE_PAGES:
            url_entries.append({
                "category": "04_通知",
                "name":     page["label"],
                "url":      page["url"],
                "law_num":  "",
            })
        log.info("  通知インデックス %d ページ分のURLを登録", len(ENV_NOTICE_PAGES))

    # ── URLリスト出力 ──
    url_path = OUTPUT_DIR / "url_list_for_notebooklm.txt"
    lines = [
        "# ============================================================",
        "# NotebookLM URL追加用リスト",
        "# 使い方: ソースを追加 → URL → 以下のURLを1件ずつ入力",
        f"# 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# 合計: {len(url_entries)} 件",
        "# ============================================================",
        "",
    ]
    current_cat = ""
    for e in url_entries:
        if e["category"] != current_cat:
            current_cat = e["category"]
            lines += ["", f"## {current_cat}", ""]
        num_str = f" ({e['law_num']})" if e["law_num"] else ""
        lines.append(f"# {e['name']}{num_str}")
        lines.append(e["url"])
        lines.append("")
    url_path.write_text("\n".join(lines), encoding="utf-8")

    # ── サマリー JSON ──
    summary = {
        "generated_at": datetime.now().isoformat(),
        "mode": "url_only" if (urls_only or not egov_ok) else "full",
        "egov_accessible": egov_ok,
        "total_url_entries": len(url_entries),
        "law_texts_saved": stats["saved"],
        "law_texts_url_only": stats["url_only"],
        "law_errors": stats["error"],
        "notices_collected": len(notices),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── 完了メッセージ ──
    log.info("")
    log.info("=" * 60)
    log.info("完了")
    log.info("  URLリスト: %s (%d件)", url_path, len(url_entries))
    if not urls_only and egov_ok:
        log.info("  保存テキスト: %d件", stats["saved"])
        log.info("  収集通知: %d件", len(notices))
    log.info("")
    log.info("【NotebookLMへの取り込み方法】")
    log.info("  ① テキストファイル → ソース追加 > ファイルアップロード")
    log.info("     %s 以下の .txt ファイルを選択", OUTPUT_DIR)
    log.info("  ② URL直接追加 → ソース追加 > URL")
    log.info("     %s を開いて1件ずつURLを入力", url_path)
    log.info("  ※ NotebookLMは1ノートブック50ソースまで")
    log.info("     法律/政令省令/通知 に分けて複数ノートブックの利用を推奨")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
