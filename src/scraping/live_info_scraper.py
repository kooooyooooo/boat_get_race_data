#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
from typing import Dict, Optional, Any, List, Tuple
import datetime

import requests
from bs4 import BeautifulSoup

# 共通ユーティリティ関数をインポート
from scrape_util import fetch_html, _extract_text, _extract_number

# 共通設定
BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
REQUEST_INTERVAL = 1  # リクエスト間隔（秒）

# ロギング設定
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

# # --- ヘルパー関数 ---
# def _extract_text(element, default=None) -> Optional[str]:
#     """要素からテキストを抽出し、空でなければ返す"""
#     if element:
#         text = element.text.strip()
#         # "---" や空文字は None とする
#         return text if text and text != "---" else default
#     return default

# def _extract_number(text: Optional[str], pattern: str, group: int = 1, type_converter=int, default: Optional[Any] = None) -> Optional[Any]:
#     """テキストから正規表現で数値を抽出し、指定された型に変換する"""
#     if text:
#         match = re.search(pattern, text)
#         if match:
#             try:
#                 return type_converter(match.group(group))
#             except (ValueError, IndexError):
#                 pass
#     return default

# # --- ここから下に直前情報データの抽出関数を追加していきます ---

def generate_beforeinfo_url(date: str, jcd: str, rno: int) -> str:
    """
    直前情報ページのURLを生成する

    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)

    Returns:
        str: 直前情報ページのURL
    """
    return f"{BASE_URL}/beforeinfo?hd={date}&jcd={jcd}&rno={rno}"

def extract_weather_info(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    直前情報ページのHTMLから水面気象情報を抽出する

    Args:
        soup: 直前情報ページのBeautifulSoupオブジェクト

    Returns:
        Dict[str, Any]: 抽出された水面気象情報
    """
    weather_info = {}
    weather_section = soup.select_one("div.weather1")

    if not weather_section:
        logger.warning("気象情報セクションが見つかりませんでした。")
        return weather_info

    # 情報更新時刻
    update_time_elem = weather_section.select_one("p.weather1_title")
    weather_info["weather_update_time"] = _extract_text(update_time_elem)

    # 気温
    temp_elem = weather_section.select_one("div.is-direction span.weather1_bodyUnitLabelData")
    weather_info["temperature"] = _extract_number(_extract_text(temp_elem), r"([\d\.]+)℃", type_converter=float)

    # 天候
    weather_elem = weather_section.select_one("div.is-weather span.weather1_bodyUnitLabelTitle")
    weather_info["weather"] = _extract_text(weather_elem)

    # 風速
    wind_speed_elem = weather_section.select_one("div.is-wind span.weather1_bodyUnitLabelData")
    weather_info["wind_speed"] = _extract_number(_extract_text(wind_speed_elem), r"(\d+)m", type_converter=int)

    # 風向 (クラス名から抽出)
    wind_dir_elem = weather_section.select_one("div.is-windDirection > p.weather1_bodyUnitImage")
    if wind_dir_elem:
        classes = wind_dir_elem.get("class", [])
        for i in range(1, 17): # 風向きは16方位で表現されることがある
            if f"is-wind{i}" in classes:
                weather_info["wind_direction"] = i
                break
        if "wind_direction" not in weather_info:
             # 画像ファイル名からも試行
             img_src = wind_dir_elem.find('img')['src'] if wind_dir_elem.find('img') else None
             if img_src:
                 match = re.search(r'img_corner1_(\d+).png', img_src)
                 if match:
                     weather_info["wind_direction"] = int(match.group(1))
                 else:
                     logger.warning(f"風向きのクラス名・画像ファイル名からの抽出に失敗しました: {classes}, {img_src}")
             else:
                 logger.warning(f"風向きのクラス名・画像が見つかりません: {classes}")
    else:
        logger.warning("風向き要素が見つかりませんでした。")


    # 水温
    water_temp_elem = weather_section.select_one("div.is-waterTemperature span.weather1_bodyUnitLabelData")
    weather_info["water_temperature"] = _extract_number(_extract_text(water_temp_elem), r"([\d\.]+)℃", type_converter=float)

    # 波高
    wave_height_elem = weather_section.select_one("div.is-wave span.weather1_bodyUnitLabelData")
    weather_info["wave_height"] = _extract_number(_extract_text(wave_height_elem), r"(\d+)cm", type_converter=int)

    return weather_info

def extract_live_entries_info(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    直前情報ページのHTMLから全選手の直前情報を抽出する

    Args:
        soup: 直前情報ページのBeautifulSoupオブジェクト

    Returns:
        List[Dict[str, Any]]: 各選手の直前情報リスト (laneキーを含む)
    """
    entries = []
    tbody_elements = soup.select("div.table1 > table.is-w748 > tbody")

    if not tbody_elements:
        logger.warning("選手直前情報テーブルが見つかりませんでした。")
        return entries

    for tbody in tbody_elements:
        entry = {}

        # 枠番 (必須)
        lane_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(1)")
        lane_num = _extract_number(_extract_text(lane_elem), r"(\d+)")
        if lane_num is None:
            logger.warning("直前情報テーブルで枠番が取得できませんでした。スキップします。")
            continue
        entry["lane"] = lane_num

        # 体重 (出走表から取得するが、念のためここでも取る)
        # ※注意: 出走表の体重とは異なる場合がある (前日体重 vs 当日体重)
        # プロトタイプでは tr:nth-child(1) > td:nth-child(4) にあったが、セレクタ変更
        weight_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(2)") # 名前とかが入ってるセル
        if weight_elem:
            weight_text = weight_elem.decode_contents().replace('\n','').strip()
            parts = [p.strip() for p in weight_text.split('<br/>') if p.strip()]
            if len(parts) > 2: # 3行目に kg 表記がある想定
                entry["live_weight"] = _extract_number(parts[2], r"([\d\.]+)kg", type_converter=float)


        # 調整重量
        tuning_weight_elem = tbody.select_one("tr:nth-child(3) > td:nth-child(1)")
        entry["tuning_weight"] = _extract_number(_extract_text(tuning_weight_elem), r"([\d\.]+)", type_converter=float)

        # 展示タイム
        exhibition_time_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(5)")
        entry["exhibition_time"] = _extract_number(_extract_text(exhibition_time_elem), r"([\d\.]+)", type_converter=float)

        # チルト
        tilt_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(6)")
        entry["tilt"] = _extract_number(_extract_text(tilt_elem), r"([\d\.\-]+)", type_converter=float) # マイナス値も考慮

        # プロペラ (通常空白。変更あればテキストが入る)
        propeller_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(7)")
        entry["propeller"] = _extract_text(propeller_elem) # 空白ならNoneになる

        # 部品交換情報 (リストで取得)
        parts_changed = []
        parts_elems = tbody.select("tr:nth-child(1) > td:nth-child(8) > ul.labelGroup1 > li > span")
        for parts_elem in parts_elems:
            part_name = _extract_text(parts_elem)
            if part_name:
                parts_changed.append(part_name)
        # 部品交換がない場合は空リスト、ある場合は ['部品名1', '部品名2'] のようになる
        entry["parts_changed"] = parts_changed if parts_changed else None # 空リストならNone

        entries.append(entry)

    # 抽出された選手数が6名でない場合は警告
    if len(entries) != 6:
        logger.warning(f"抽出された選手直前情報が6名ではありません ({len(entries)}名)。HTML構造を確認してください。")

    return entries 

def extract_start_exhibition_info(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    直前情報ページのHTMLからスタート展示情報を抽出する

    Args:
        soup: 直前情報ページのBeautifulSoupオブジェクト

    Returns:
        List[Dict[str, Any]]: 各艇のスタート展示情報リスト (course, st, is_flying キーを含む)
    """
    start_exhibition = []
    start_display_elems = soup.select("div.table1 > table.is-w238 > tbody > tr div.table1_boatImage1")

    if not start_display_elems:
        logger.warning("スタート展示情報が見つかりませんでした。")
        return start_exhibition

    for elem in start_display_elems:
        exhibition_data = {}

        # コース (枠番をクラス名 is-typeX から取得)
        course_elem = elem.select_one("span.table1_boatImage1Number")
        if course_elem:
            classes = course_elem.get("class", [])
            for i in range(1, 7):
                if f"is-type{i}" in classes:
                    exhibition_data["course"] = i
                    break
        if "course" not in exhibition_data:
             logger.warning("スタート展示のコースが取得できませんでした。スキップします。")
             continue

        # ST (フライング判定含む)
        st_elem = elem.select_one("span.table1_boatImage1Time")
        st_text = _extract_text(st_elem)
        exhibition_data["st"] = _extract_number(st_text, r"([\d\.]+)", type_converter=float)

        # フライング判定 (is-fColor1 クラスの有無)
        exhibition_data["is_flying"] = "is-fColor1" in st_elem.get("class", []) if st_elem else False

        start_exhibition.append(exhibition_data)

    # 抽出された展示情報数が6でない場合は警告 (ただし、欠場等で減る可能性あり)
    if len(start_exhibition) != 6:
        logger.warning(f"抽出されたスタート展示情報が6艇分ではありません ({len(start_exhibition)}艇)。")

    # コース順にソートして返す
    start_exhibition.sort(key=lambda x: x.get("course", 99))

    return start_exhibition 

def scrape_live_info(date: str, jcd: str, rno: int) -> Dict[str, Any]:
    """
    指定されたレースの直前情報ページをスクレイピングし、情報を抽出する

    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)

    Returns:
        Dict[str, Any]: 抽出された直前情報全体の辞書。
                       キー: 'weather_info', 'live_entries_info', 'start_exhibition_info'
                       値がない場合は空の辞書またはリストを返す。
    """
    live_info = {
        "weather_info": {},
        "live_entries_info": [],
        "start_exhibition_info": []
    }

    url = generate_beforeinfo_url(date, jcd, rno)
    html_content = fetch_html(url)

    if not html_content:
        logger.error(f"直前情報HTMLの取得に失敗しました: {url}")
        return live_info

    soup = BeautifulSoup(html_content, "html.parser")

    # 気象情報の抽出
    live_info["weather_info"] = extract_weather_info(soup)

    # 選手直前情報の抽出
    live_info["live_entries_info"] = extract_live_entries_info(soup)

    # スタート展示情報の抽出
    live_info["start_exhibition_info"] = extract_start_exhibition_info(soup)

    logger.info(f"直前情報の抽出完了: {jcd}競艇場 {rno}R")
    return live_info


if __name__ == '__main__':
    # テスト実行用のコード
    test_date = "20250427" # 未来の日付や過去の存在する日付でテスト
    test_jcd = "01"       # 桐生
    test_rno = 1          # 1レース目

    logger.info(f"--- 直前情報スクレイピングテスト 開始 ({test_date} {test_jcd} {test_rno}R) ---")

    scraped_data = scrape_live_info(test_date, test_jcd, test_rno)

    if scraped_data["weather_info"] or scraped_data["live_entries_info"] or scraped_data["start_exhibition_info"]:
        print("--- 気象情報 ---")
        print(scraped_data["weather_info"])
        print("--- 選手直前情報 ---")
        for i, entry in enumerate(scraped_data["live_entries_info"]):
            print(f"[{i+1}] {entry}")
        print("--- スタート展示情報 ---")
        for i, ex in enumerate(scraped_data["start_exhibition_info"]):
            print(f"[{i+1}] {ex}")
    else:
        logger.warning("テスト実行で有効なデータが取得できませんでした。日付やレース番号を確認してください。")

    logger.info(f"--- 直前情報スクレイピングテスト 終了 ---") 