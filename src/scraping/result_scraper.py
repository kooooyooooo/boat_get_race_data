#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
from typing import Dict, Optional, Any, List

from bs4 import BeautifulSoup

# 共通ユーティリティ関数をインポート
from scrape_util import fetch_html, _extract_text, _extract_number

# 共通設定
BASE_URL = "https://www.boatrace.jp/owpc/pc/race"

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def generate_result_url(date: str, jcd: str, rno: int) -> str:
    """
    レース結果ページのURLを生成する

    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)

    Returns:
        str: レース結果ページのURL
    """
    return f"{BASE_URL}/raceresult?hd={date}&jcd={jcd}&rno={rno}"

def extract_race_results(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    レース結果ページのHTMLから着順情報を抽出する

    Args:
        soup: レース結果ページのBeautifulSoupオブジェクト

    Returns:
        List[Dict[str, Any]]: 各艇の着順結果リスト
            (keys: 'rank', 'lane', 'player_id', 'name', 'race_time')
    """
    results = []
    # is-w495 クラスを持つテーブル内の全ての tbody を取得
    all_tbody_elements = soup.select("div.table1 > table.is-w495 > tbody")

    if not all_tbody_elements:
        logger.warning("着順結果テーブルまたは払戻金テーブルが見つかりませんでした。")
        return results

    for tbody in all_tbody_elements:
        # この tbody が実際の着順情報を含んでいるかチェック (例: 選手ID要素があるか)
        player_id_elem_check = tbody.select_one("tr > td:nth-child(3) > span.is-fs12")
        if not player_id_elem_check:
            # 選手ID要素がなければ、これは着順行ではない（払戻金行など）と判断してスキップ
            continue

        # --- 以下は着順行と判断された場合の処理 ---
        result = {}
        row = tbody.select_one("tr")
        if not row:
            continue

        # 着順 (td:nth-child(1)) - F, 失などもそのままテキストで取得
        rank_elem = row.select_one("td:nth-child(1)")
        result["rank"] = _extract_text(rank_elem)

        # 枠番 (td:nth-child(2)) - クラス名からも取得できるが、テキストからも取得
        lane_elem = row.select_one("td:nth-child(2)")
        result["lane"] = _extract_number(_extract_text(lane_elem), r"(\d+)")
        # クラス名からも取得試行 (より確実な場合がある)
        if not result["lane"] and lane_elem:
            classes = lane_elem.get("class", [])
            for i in range(1, 7):
                if f"is-boatColor{i}" in classes:
                    result["lane"] = i
                    break

        # 登録番号・選手名 (td:nth-child(3))
        player_elem = row.select_one("td:nth-child(3)")
        if player_elem:
            reg_num_elem = player_elem.select_one("span.is-fs12")
            result["player_id"] = _extract_number(_extract_text(reg_num_elem), r"(\d+)")

            name_elem = player_elem.select_one("span.is-fs18.is-fBold")
            extracted_name = _extract_text(name_elem)
            if extracted_name:
                result["name"] = extracted_name.replace('\u3000', '') # 全角スペース除去
            else:
                result["name"] = None
        else:
            result["player_id"] = None
            result["name"] = None

        # レースタイム (td:nth-child(4))
        time_elem = row.select_one("td:nth-child(4)")
        result["race_time"] = _extract_text(time_elem) # "1'50"4" のような形式

        # 有効なデータ（最低限、枠番と着順がある）のみ追加
        if result.get("lane") is not None and result.get("rank") is not None:
            results.append(result)
        else:
            logger.warning(f"着順情報の一部が欠損しているためスキップ: {result}")


    # 抽出された結果数が6でない場合は警告 (欠場等で減る場合もある)
    if len(results) != 6:
        logger.warning(f"抽出された着順結果が6艇分ではありません ({len(results)}艇)。欠場等の可能性があります。")

    # 念のため枠番順にソートして返す (通常は着順でソートされているはず)
    results.sort(key=lambda x: x.get("lane", 99))

    return results

def extract_payouts(soup: BeautifulSoup) -> Dict[str, List[Dict[str, Any]]]:
    """
    レース結果ページのHTMLから払戻金情報を抽出する

    Args:
        soup: レース結果ページのBeautifulSoupオブジェクト

    Returns:
        Dict[str, List[Dict[str, Any]]]: 勝式ごとの払戻金情報リスト
            例: {'三連単': [{'boats': [1, 2, 3], 'payout': 5300, 'popularity': 22}], ...}
               人気がない勝式(単勝/複勝)では 'popularity' キーは含まれない。
    """
    payouts_data = {}
    # 払戻金テーブルを特定 (着順テーブルと区別するため親要素で絞り込む)
    # payout_table_area = soup.select_one("div.grid_unit:not(.h-mt10)")
    # if not payout_table_area:
    #     logger.warning("払戻金情報エリアが見つかりませんでした。")
    #     return payouts_data

    # payout_table = payout_table_area.select_one("div.table1 > table.is-w495")
    # if not payout_table:
    #     logger.warning("払戻金テーブルが見つかりませんでした。")
    #     return payouts_data
    payout_table = soup.select_one(
        "div.grid.is-type2.h-clear:not(.h-mt10) table.is-w495"
    )
    if not payout_table:
        logger.warning("払戻金テーブルが見つかりませんでした。")
        return payouts_data

    tbody_elements = payout_table.find_all("tbody")
    current_bet_type = None

    for tbody in tbody_elements:
        # 勝式を取得 (最初のtd、rowspanされている可能性あり)
        bet_type_td = tbody.select_one("tr:nth-child(1) > td:nth-child(1)")
        # rowspanを持つtdは一度だけ取得
        if bet_type_td and bet_type_td.has_attr('rowspan'):
            current_bet_type = _extract_text(bet_type_td)
        # rowspanがない場合 or 最初のtbody以外は前の勝式を引き継ぐ想定だが、
        # 安全のため、tdが存在しテキストがあればそれを勝式とする
        elif bet_type_td and _extract_text(bet_type_td):
             current_bet_type = _extract_text(bet_type_td)

        if not current_bet_type:
            # logger.debug("勝式が特定できないtbodyをスキップします。") # デバッグ用
            continue

        # 最初のtbodyのヘッダ行などはスキップするロジック（より堅牢に）
        if not tbody.select_one('td span.numberSet1_number'):
             # logger.debug(f"払戻金情報が含まれないtbody({current_bet_type})をスキップします。") # デバッグ用
             continue


        # tbody内の各tr（組み合わせ）を処理
        rows = tbody.select("tr")
        if current_bet_type not in payouts_data:
            payouts_data[current_bet_type] = []

        for row in rows:
            payout_info = {}

            # 組番を取得 (td:nth-child(2))
            combination_td = row.select_one("td:nth-child(2)")
            boats = []
            if combination_td:
                boat_spans = combination_td.select("div.numberSet1_row > span.numberSet1_number")
                for span in boat_spans:
                    boat_num_str = _extract_text(span)
                    boat_num = _extract_number(boat_num_str, r"(\d+)")
                    if boat_num is not None:
                        boats.append(boat_num)
                    # is-typeX クラスからも取得試行 (より確実)
                    else:
                         classes = span.get("class", [])
                         for i in range(1, 7):
                             if f"is-type{i}" in classes:
                                 boats.append(i)
                                 break
            if not boats: # 組番が取れなければスキップ
                 # logger.debug(f"組番が取得できない行({current_bet_type})をスキップします。") # デバッグ用
                 continue
            payout_info["boats"] = boats

            # 払戻金を取得 (td:nth-child(3))
            payout_td = row.select_one("td:nth-child(3)")
            payout_val_str = _extract_text(payout_td.select_one("span.is-payout1") if payout_td else None)
            payout_info["payout"] = _extract_number(payout_val_str, r"([,\d]+)", type_converter=lambda x: int(x.replace(',', '')))

            # 人気を取得 (td:nth-child(4)) - 単勝/複勝にはない
            popularity_td = row.select_one("td:nth-child(4)")
            popularity_val = _extract_number(_extract_text(popularity_td), r"(\d+)")
            if popularity_val is not None:
                 payout_info["popularity"] = popularity_val

            # 有効なデータのみ追加
            if payout_info.get("payout") is not None:
                 payouts_data[current_bet_type].append(payout_info)
            else:
                 logger.warning(f"払戻金が取得できなかったためスキップ: 勝式={current_bet_type}, 組番={boats}")

    return payouts_data

def extract_winning_technique(soup: BeautifulSoup) -> Optional[str]:
    """
    レース結果ページのHTMLから決まり手を抽出する

    Args:
        soup: レース結果ページのBeautifulSoupオブジェクト

    Returns:
        Optional[str]: 決まり手の文字列。見つからない場合はNone。
    """
    # 決まり手は専用のボックスにある ('データ項目定義・セレクタマッピング.md' 参照)
    kimarite_elem = soup.select_one("div.table1 > table.is-w243.is-h108__3rdadd > tbody > tr > td")
    return _extract_text(kimarite_elem)

def scrape_race_result(date: str, jcd: str, rno: int) -> Dict[str, Any]:
    """
    指定されたレースの結果ページをスクレイピングし、情報を抽出する

    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)

    Returns:
        Dict[str, Any]: 抽出されたレース結果情報。
                       キー: 'results', 'winning_technique'
                       値がない場合は空のリストまたはNoneを返す。
                       取得失敗時は空の辞書を返す。
    """
    race_result_data = {
        "results": [],
        "winning_technique": None
    }

    url = generate_result_url(date, jcd, rno)
    html_content = fetch_html(url)

    if not html_content:
        logger.error(f"レース結果HTMLの取得に失敗しました: {url}")
        return {} # 取得失敗時は空辞書

    soup = BeautifulSoup(html_content, "html.parser")

    # 着順結果の抽出
    race_result_data["results"] = extract_race_results(soup)

    # 払戻金情報の抽出
    race_result_data["payouts"] = extract_payouts(soup)

    # 決まり手の抽出
    race_result_data["winning_technique"] = extract_winning_technique(soup)

    # 結果が全く取れていない場合は警告
    if not race_result_data["results"] and not race_result_data["winning_technique"]:
         logger.warning(f"レース結果・決まり手の両方が取得できませんでした: {url}")
         # この場合も空ではない辞書を返す（処理は試みたため）

    logger.info(f"レース結果情報の抽出完了: {jcd}競艇場 {rno}R")
    return race_result_data


if __name__ == '__main__':
    # テスト実行用のコード
    # 過去の実際に結果が出ている日付/会場/レースで試してください
    test_date = "20240310"  # 例: 過去日付
    test_jcd = "01"        # 例: 桐生
    test_rno = 12          # 例: 12レース目

    logger.info(f"--- レース結果スクレイピングテスト 開始 ({test_date} {test_jcd} {test_rno}R) ---")

    scraped_data = scrape_race_result(test_date, test_jcd, test_rno)

    if scraped_data:
        print("--- 着順結果 ---")
        # 結果を見やすく表示
        if scraped_data.get("results"):
             for entry in sorted(scraped_data["results"], key=lambda x: (isinstance(x.get("rank"), str) and x["rank"].isdigit(), int(x["rank"]) if isinstance(x.get("rank"), str) and x["rank"].isdigit() else float('inf'))): # rankが数字なら数値順、そうでなければ最後に
                # None の可能性がある値は str() で囲んでから書式指定する
                rank_str = str(entry.get('rank', '?'))
                lane_str = str(entry.get('lane', '?'))
                player_id_str = str(entry.get('player_id', 'N/A'))
                name_str = str(entry.get('name', 'N/A'))
                race_time_str = str(entry.get('race_time', 'N/A'))
                print(f"  着順:{rank_str:<3} 枠:{lane_str} ID:{player_id_str:<5} 名前:{name_str:<10} タイム:{race_time_str}")
        else:
             print("  着順結果データなし")

        print("\n--- 払戻金情報 ---")
        if scraped_data.get("payouts"):
            for bet_type, payouts in scraped_data["payouts"].items():
                print(f"  {bet_type}:")
                for payout in payouts:
                    boats_str = ", ".join(str(boat) for boat in payout["boats"])
                    payout_str = f"{payout['payout']:,}" # 3桁区切り
                    popularity_str = str(payout.get("popularity", "-")) # 人気がない場合はハイフン
                    print(f"    組:{boats_str:<10} 払戻:{payout_str:>8}円   人気:{popularity_str:>3}")
        else:
            print("  払戻金情報データなし")

        print("\n--- 決まり手 ---")
        print(f"  {scraped_data.get('winning_technique', '取得失敗')}")
    else:
        logger.warning("テスト実行で有効なデータが取得できませんでした。日付やレース番号を確認してください。")

    logger.info(f"--- レース結果スクレイピングテスト 終了 ---") 