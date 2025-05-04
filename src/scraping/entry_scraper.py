#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
from typing import Dict, Optional, Any, List

import requests
from bs4 import BeautifulSoup

# 共通ユーティリティ関数をインポート
from scrape_util import fetch_html, _extract_text, _extract_number

# 共通設定
BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
REQUEST_INTERVAL = 1  # リクエスト間隔（秒）

# ロギング設定 (プロトタイプから流用、ファイル出力は後で検討)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# # HTMLの取得
# def fetch_html(url: str) -> Optional[str]:
#     """
#     指定されたURLからHTMLを取得する

#     Args:
#         url: 取得対象のURL

#     Returns:
#         Optional[str]: HTML文字列。取得に失敗した場合はNone
#     """
#     logger.info(f"Fetching HTML from: {url}")
#     try:
#         headers = {
#             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
#         }
#         response = requests.get(url, headers=headers, timeout=30)
#         response.raise_for_status()
#         response.encoding = response.apparent_encoding # 文字化け対策
#         logger.info(f"Successfully fetched HTML from: {url}")
#         return response.text
#     except requests.exceptions.RequestException as e:
#         logger.error(f"URL取得エラー {url}: {e}")
#         return None
#     except Exception as e:
#         logger.error(f"予期せぬエラーが発生しました {url}: {e}")
#         return None

# URLの生成 (出走表)
def generate_racelist_url(date: str, jcd: str, rno: int) -> str:
    """
    出走表ページのURLを生成する

    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)

    Returns:
        str: 出走表ページのURL
    """
    return f"{BASE_URL}/racelist?hd={date}&jcd={jcd}&rno={rno}"

# --- ここから下に出走表データの抽出関数を追加していきます ---

def extract_race_basic_info(html: str, rno: int) -> Dict[str, Any]:
    """
    出走表ページからレース基本情報を抽出する

    Args:
        html: 出走表ページのHTML文字列
        rno: レース番号 (締切時刻抽出用)

    Returns:
        Dict[str, Any]: 抽出されたレース基本情報
    """
    soup = BeautifulSoup(html, "html.parser")
    race_info = {}

    # レース名と距離の抽出 (ユーザー提供のセレクタとロジックに基づき修正)
    race_title_elem = soup.select_one("h3.title16_titleDetail__add2020")
    race_title_text = _extract_text(race_title_elem)
    if race_title_text:
        # Split by any whitespace (including full-width space \u3000)
        parts = re.split(r'\s+', race_title_text.strip())
        # Filter out empty strings that might result from multiple spaces
        parts = [p for p in parts if p]
        if parts:
            # Assume first part is race name
            race_info["race_name"] = parts[0]
            # Extract distance from the original text (more robust than assuming parts[-1])
            race_info["distance"] = _extract_number(race_title_text, r"(\d+)m", type_converter=int)
        else:
            race_info["race_name"] = None
            race_info["distance"] = None # Ensure distance is None if parts is empty
    else:
         race_info["race_name"] = None
         race_info["distance"] = None

    # 安定板使用の有無
    stable_plate_elem = soup.select_one("div.title16_titleLabels__add2020 > span.label2.is-type1")
    race_info["is_stable_plate_used"] = stable_plate_elem is not None

    # 締切予定時刻の抽出 (ナビゲーションテーブルから)
    # セレクタはレース番号に依存する
    deadline_selector = f'table tbody tr td:nth-child({rno + 1})'
    deadline_elem = soup.select_one(deadline_selector)
    race_info["deadline"] = _extract_text(deadline_elem)

    return race_info

def extract_race_entries_info(html: str) -> List[Dict[str, Any]]:
    """
    出走表ページから全選手情報を抽出する

    Args:
        html: 出走表ページのHTML文字列

    Returns:
        List[Dict[str, Any]]: 各選手の情報リスト
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []

    tbody_elements = soup.select("div.table1.is-tableFixed__3rdadd > table > tbody")
    if not tbody_elements:
        logger.warning("選手情報テーブルが見つかりませんでした。")
        return entries

    for tbody in tbody_elements:
        entry = {}

        # 枠番 (クラス名から取得)
        boat_color_td = tbody.select_one("tr:nth-child(1) > td[class*='is-boatColor']")
        if boat_color_td:
            classes = boat_color_td.get("class", [])
            for i in range(1, 7):
                if f"is-boatColor{i}" in classes:
                    entry["lane"] = i
                    break
        if "lane" not in entry:
            logger.warning("枠番が取得できませんでした。スキップします。")
            continue

        # --- 選手基本情報 (td:nth-child(3)) ---
        player_info_td = tbody.select_one("tr:nth-child(1) > td:nth-child(3)")
        if player_info_td:
            # 登録番号
            reg_num_elem = player_info_td.select_one("div.is-fs11")
            entry["player_id"] = _extract_number(_extract_text(reg_num_elem), r"^(\d+)")
            if not entry["player_id"]:
                logger.warning(f"登録番号が取得できませんでした（枠番: {entry['lane']}）。スキップします。")
                continue

            # 級別
            class_elem = player_info_td.select_one("div.is-fs11 > span")
            entry["class"] = _extract_text(class_elem)

            # 氏名
            name_elem = player_info_td.select_one("div.is-fs18 > a")
            extracted_name = _extract_text(name_elem)
            if extracted_name:
                entry["name"] = extracted_name.replace('\u3000', '') # 全角スペースを削除
            else:
                entry["name"] = None

            # 支部/出身地/年齢/体重 (同じ要素内にあるため複雑)
            details_elems = player_info_td.select("div.is-fs11")
            if len(details_elems) > 2: # 3番目の div.is-fs11 に情報がある想定
                details_text = details_elems[2].decode_contents().replace('\n','').strip() # brタグを考慮
                parts = [p.strip() for p in details_text.split('<br/>') if p.strip()]
                if len(parts) >= 2:
                    # 支部/出身地
                    location_parts = [loc.strip() for loc in parts[0].split('/') if loc.strip()]
                    if len(location_parts) >= 1: entry["branch"] = location_parts[0]
                    if len(location_parts) >= 2: entry["origin"] = location_parts[1]
                    # 年齢/体重
                    entry["age"] = _extract_number(parts[1], r"(\d+)歳")
                    entry["weight"] = _extract_number(parts[1], r"([\d\.]+)kg", type_converter=float)

        # --- 成績情報 (td:nth-child(4), (5), (6)) ---
        # F/L/ST (td:nth-child(4))
        flst_td = tbody.select_one("tr:nth-child(1) > td:nth-child(4)")
        if flst_td:
            flst_text = flst_td.decode_contents().replace('\n','').strip()
            lines = [line.strip() for line in flst_text.split('<br/>') if line.strip()]
            if len(lines) >= 1: entry["f_count"] = _extract_number(lines[0], r"F(\d+)", default=0)
            if len(lines) >= 2: entry["l_count"] = _extract_number(lines[1], r"L(\d+)", default=0)
            if len(lines) >= 3: entry["avg_st"] = _extract_number(lines[2], r"([\d\.]+)", type_converter=float)

        # 全国成績 (td:nth-child(5))
        nationwide_td = tbody.select_one("tr:nth-child(1) > td:nth-child(5)")
        if nationwide_td:
            nationwide_text = nationwide_td.decode_contents().replace('\n','').strip()
            lines = [line.strip() for line in nationwide_text.split('<br/>') if line.strip()]
            if len(lines) >= 1: entry["nationwide_win_rate"] = _extract_number(lines[0], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 2: entry["nationwide_two_win_rate"] = _extract_number(lines[1], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 3: entry["nationwide_three_win_rate"] = _extract_number(lines[2], r"([\d\.]+)", type_converter=float)

        # 当地成績 (td:nth-child(6))
        local_td = tbody.select_one("tr:nth-child(1) > td:nth-child(6)")
        if local_td:
            local_text = local_td.decode_contents().replace('\n','').strip()
            lines = [line.strip() for line in local_text.split('<br/>') if line.strip()]
            if len(lines) >= 1: entry["local_win_rate"] = _extract_number(lines[0], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 2: entry["local_two_win_rate"] = _extract_number(lines[1], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 3: entry["local_three_win_rate"] = _extract_number(lines[2], r"([\d\.]+)", type_converter=float)

        # --- モーター/ボート情報 (td:nth-child(7), (8)) ---
        # モーター (td:nth-child(7))
        motor_td = tbody.select_one("tr:nth-child(1) > td:nth-child(7)")
        if motor_td:
            motor_text = motor_td.decode_contents().replace('\n','').strip()
            lines = [line.strip() for line in motor_text.split('<br/>') if line.strip()]
            if len(lines) >= 1: entry["motor_no"] = _extract_number(lines[0], r"(\d+)")
            if len(lines) >= 2: entry["motor_two_win_rate"] = _extract_number(lines[1], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 3: entry["motor_three_win_rate"] = _extract_number(lines[2], r"([\d\.]+)", type_converter=float)

        # ボート (td:nth-child(8))
        boat_td = tbody.select_one("tr:nth-child(1) > td:nth-child(8)")
        if boat_td:
            boat_text = boat_td.decode_contents().replace('\n','').strip()
            lines = [line.strip() for line in boat_text.split('<br/>') if line.strip()]
            if len(lines) >= 1: entry["boat_no"] = _extract_number(lines[0], r"(\d+)")
            if len(lines) >= 2: entry["boat_two_win_rate"] = _extract_number(lines[1], r"([\d\.]+)", type_converter=float)
            if len(lines) >= 3: entry["boat_three_win_rate"] = _extract_number(lines[2], r"([\d\.]+)", type_converter=float)

        entries.append(entry)

    # 抽出された選手数が6名でない場合は警告
    if len(entries) != 6:
        logger.warning(f"抽出された選手情報が6名ではありません ({len(entries)}名)。HTML構造を確認してください。")

    return entries


if __name__ == '__main__':
    # テスト実行用のコードをここに追加します
    test_date = "20250427" # 例として今日の日付に近い日
    test_jcd = "01"       # 桐生
    test_rno = 12          # 1レース目

    racelist_url = generate_racelist_url(test_date, test_jcd, test_rno)
    html_content = fetch_html(racelist_url)

    if html_content:
        logger.info(f"{test_jcd}競艇場 {test_rno}R の出走表HTMLを取得しました。")
        # ここで抽出関数を呼び出して結果を表示する
        race_basic_info = extract_race_basic_info(html_content, test_rno)
        race_entries_info = extract_race_entries_info(html_content)
        print("--- レース基本情報 ---")
        print(race_basic_info)
        print("--- 選手情報 ---")
        for i, entry in enumerate(race_entries_info):
            print(f"[{i+1}] {entry}")
    else:
        logger.error(f"{test_jcd}競艇場 {test_rno}R の出走表HTMLの取得に失敗しました。") 