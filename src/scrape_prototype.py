#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
競艇データ収集基盤 プロトタイプ実装
2024/04/27の全会場の1レース目の情報を取得するスクリプト
"""

import os
import time
import datetime
import logging
import sqlite3
import re
from typing import Dict, List, Optional, Tuple, Any, Set

import requests
from bs4 import BeautifulSoup
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# 共通設定
BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
DATE_FORMAT = "%Y%m%d"
TARGET_DATE = "20240427"  # 2024年4月27日
RACE_NO = 1  # 1レース目
REQUEST_INTERVAL = 1  # リクエスト間隔（秒）→1秒に変更
MAX_VENUE_ID = 5  # テスト用に会場IDの上限を5に設定

# データベース設定
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "boat_data.db")
Base = declarative_base()

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "scrape.log"), "a", "utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# 競艇場コードと名称のマッピング
VENUE_MAPPING = {
    "01": "桐生",
    "02": "戸田",
    "03": "江戸川",
    "04": "平和島",
    "05": "多摩川",
    "06": "浜名湖",
    "07": "蒲郡",
    "08": "常滑",
    "09": "津",
    "10": "三国",
    "11": "びわこ",
    "12": "住之江",
    "13": "尼崎",
    "14": "鳴門",
    "15": "丸亀",
    "16": "児島",
    "17": "宮島",
    "18": "徳山",
    "19": "下関",
    "20": "若松",
    "21": "芦屋",
    "22": "福岡",
    "23": "唐津",
    "24": "大村",
}

# SQLAlchemyのモデル定義
class Venue(Base):
    __tablename__ = "venue"
    
    jcd = sa.Column(sa.String(2), primary_key=True)
    name = sa.Column(sa.String)
    pref = sa.Column(sa.String)


class Race(Base):
    __tablename__ = "race"
    
    race_id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    hd = sa.Column(sa.Date, nullable=False)
    jcd = sa.Column(sa.String(2), sa.ForeignKey("venue.jcd"), nullable=False)
    rno = sa.Column(sa.Integer, nullable=False)
    race_name = sa.Column(sa.String)
    distance = sa.Column(sa.Integer)
    deadline = sa.Column(sa.Time)
    weather = sa.Column(sa.String)
    wind_speed = sa.Column(sa.Integer)
    wind_dir = sa.Column(sa.String)
    water_temp = sa.Column(sa.Float)
    wave_height = sa.Column(sa.Integer)
    is_stable_plate_used = sa.Column(sa.Boolean, default=False, nullable=False)
    season_year = sa.Column(sa.Integer, nullable=False)
    season_term = sa.Column(sa.Integer, nullable=False)
    
    entries = relationship("RaceEntry", back_populates="race")
    
    __table_args__ = (
        sa.UniqueConstraint('hd', 'jcd', 'rno'),
    )


class RaceEntry(Base):
    __tablename__ = "race_entry"
    
    entry_id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    race_id = sa.Column(sa.Integer, sa.ForeignKey("race.race_id"), nullable=False)
    lane = sa.Column(sa.Integer, nullable=False)
    player_id = sa.Column(sa.Integer, nullable=False)
    
    # 出走表情報
    class_ = sa.Column("class", sa.String)
    age = sa.Column(sa.Integer)
    weight = sa.Column(sa.Float)
    f_count = sa.Column(sa.Integer)
    l_count = sa.Column(sa.Integer)
    avg_st = sa.Column(sa.Float)
    nationwide_win_rate = sa.Column(sa.Float)  # 追加: 全国勝率
    nationwide_two_win_rate = sa.Column(sa.Float)
    nationwide_three_win_rate = sa.Column(sa.Float)
    local_win_rate = sa.Column(sa.Float)  # 追加: 当地勝率
    local_two_win_rate = sa.Column(sa.Float)
    local_three_win_rate = sa.Column(sa.Float)
    motor_no = sa.Column(sa.Integer)
    motor_two_win_rate = sa.Column(sa.Float)
    motor_three_win_rate = sa.Column(sa.Float)
    boat_no = sa.Column(sa.Integer)
    boat_two_win_rate = sa.Column(sa.Float)
    boat_three_win_rate = sa.Column(sa.Float)
    
    # 直前情報
    tuning_weight = sa.Column(sa.Float)
    exhibition_time = sa.Column(sa.Float)
    tilt = sa.Column(sa.Float)
    parts_changed = sa.Column(sa.String)  # JSON文字列として格納
    
    # 結果情報
    rank_raw = sa.Column(sa.String)
    rank = sa.Column(sa.Integer)
    race_time = sa.Column(sa.String)
    start_course = sa.Column(sa.Integer)
    start_st = sa.Column(sa.Float)
    decision = sa.Column(sa.String)
    
    race = relationship("Race", back_populates="entries")
    
    __table_args__ = (
        sa.UniqueConstraint('race_id', 'lane'),
    )


# 開催中レース場の取得
def get_active_venues(date: str) -> Set[str]:
    """
    指定された日付に開催されているレース場のコード一覧を取得する
    
    Args:
        date: 開催日 (YYYYMMDD形式)
        
    Returns:
        Set[str]: 開催中のレース場コード一覧
    """
    # レース一覧ページのURL
    index_url = f"{BASE_URL}/index?hd={date}"
    
    # HTMLの取得
    html = fetch_html(index_url)
    if not html:
        logger.error(f"レース一覧ページの取得に失敗しました: {index_url}")
        return set()
    
    # HTMLの解析
    soup = BeautifulSoup(html, "html.parser")
    active_venues = set()
    
    # 出走表リンクからjcdを抽出
    race_links = soup.select("a[href*='/owpc/pc/race/racelist']")
    for link in race_links:
        href = link.get("href", "")
        jcd_match = re.search(r"jcd=(\d{2})", href)
        if jcd_match:
            jcd = jcd_match.group(1)
            active_venues.add(jcd)
    
    logger.info(f"開催中のレース場を {len(active_venues)} 件取得しました: {', '.join(sorted(active_venues))}")
    return active_venues


# URLの生成
def generate_urls(date: str, jcd: str, rno: int) -> Dict[str, str]:
    """
    出走表、直前情報、結果のURLを生成する
    
    Args:
        date: 開催日 (YYYYMMDD形式)
        jcd: 会場コード (2桁)
        rno: レース番号 (1-12)
        
    Returns:
        Dict[str, str]: 各ページのURL
    """
    base_params = f"?hd={date}&jcd={jcd}&rno={rno}"
    return {
        "race_list": f"{BASE_URL}/raceindex{base_params}",
        "race_card": f"{BASE_URL}/racelist{base_params}",
        "race_live_info": f"{BASE_URL}/beforeinfo{base_params}",
        "race_result": f"{BASE_URL}/raceresult{base_params}"
    }


# HTMLの取得
def fetch_html(url: str) -> Optional[str]:
    """
    指定されたURLからHTMLを取得する
    
    Args:
        url: 取得対象のURL
        
    Returns:
        Optional[str]: HTML文字列。取得に失敗した場合はNone
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"URL取得エラー {url}: {e}")
        return None


# 出走表ページからの情報抽出
def extract_race_info(html: str) -> Dict[str, Any]:
    """
    出走表ページからレース情報を抽出する
    
    Args:
        html: 出走表ページのHTML文字列
        
    Returns:
        Dict[str, Any]: 抽出されたレース情報
    """
    soup = BeautifulSoup(html, "html.parser")
    race_info = {}
    
    # レース名と距離の抽出
    race_title_elem = soup.select_one("div.heading2_title > h3")
    if race_title_elem:
        race_title_text = race_title_elem.text.strip()
        race_info["race_name"] = race_title_text
        
        # 距離の抽出 (例: "一般戦 1800m")
        import re
        distance_match = re.search(r"(\d+)m", race_title_text)
        if distance_match:
            race_info["distance"] = int(distance_match.group(1))
    
    # 安定板使用の有無
    stable_plate_elem = soup.select_one("div.title16_titleLabels__add2020 > span.label2.is-type1")
    race_info["is_stable_plate_used"] = stable_plate_elem is not None
    
    # 締切時刻の抽出は複雑なため、ここでは省略
    
    # 気象情報の抽出 (実際にはページによって異なる場合がある)
    # 詳細な抽出ロジックはプロトタイプでは省略
    
    return race_info


# 直前情報ページからの情報抽出
def extract_live_info(html: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    直前情報ページからレース情報と選手情報を抽出する
    
    Args:
        html: 直前情報ページのHTML文字列
        
    Returns:
        Tuple[Dict[str, Any], List[Dict[str, Any]]]: レース情報と選手情報のタプル
    """
    soup = BeautifulSoup(html, "html.parser")
    race_info = {}
    entries = []
    
    # 気象情報の抽出
    weather_table = soup.select_one("div.weather1")
    if weather_table:
        # 天候
        weather_elem = weather_table.select_one("div.weather1_bodyUnit.is-weather span.weather1_bodyUnitLabelTitle")
        if weather_elem:
            race_info["weather"] = weather_elem.text.strip()
        
        # 風速
        wind_elem = weather_table.select_one("div.weather1_bodyUnit.is-wind span.weather1_bodyUnitLabelData")
        if wind_elem:
            wind_text = wind_elem.text.strip()
            try:
                race_info["wind_speed"] = int(re.search(r"(\d+)m", wind_text).group(1))
            except (AttributeError, ValueError):
                pass
        
        # 風向き
        wind_dir_elem = weather_table.select_one("div.weather1_bodyUnit.is-windDirection > p.weather1_bodyUnitImage")
        if wind_dir_elem:
            race_info["wind_dir"] = wind_dir_elem.text.strip()
        
        # 水温
        water_temp_elem = weather_table.select_one("div.weather1_bodyUnit.is-waterTemperature span.weather1_bodyUnitLabelData")
        if water_temp_elem:
            water_temp_text = water_temp_elem.text.strip()
            try:
                race_info["water_temp"] = float(re.search(r"(\d+\.?\d*)℃", water_temp_text).group(1))
            except (AttributeError, ValueError):
                pass
        
        # 波高
        wave_elem = weather_table.select_one("div.weather1_bodyUnit.is-wave span.weather1_bodyUnitLabelData")
        if wave_elem:
            wave_text = wave_elem.text.strip()
            try:
                race_info["wave_height"] = int(re.search(r"(\d+)cm", wave_text).group(1))
            except (AttributeError, ValueError):
                pass
    
    # 選手情報の抽出
    for tbody in soup.select("div.table1 > table.is-w748 > tbody"):
        entry = {}
        
        # 枠番の取得（1行目1列目）
        boat_number_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(1)")
        if boat_number_elem:
            try:
                entry["lane"] = int(boat_number_elem.text.strip())
            except ValueError:
                continue
        
        # 調整体重（3行目1列目）
        weight_elem = tbody.select_one("tr:nth-child(3) > td:nth-child(1)")
        if weight_elem:
            try:
                weight_text = weight_elem.text.strip()
                if weight_text and weight_text != "---":
                    entry["tuning_weight"] = float(weight_text)
            except ValueError:
                pass
        
        # 展示タイム（1行目5列目）
        exhibition_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(5)")
        if exhibition_elem:
            time_text = exhibition_elem.text.strip()
            try:
                if time_text and time_text != "---":
                    entry["exhibition_time"] = float(time_text)
            except ValueError:
                pass
        
        # チルト（1行目6列目）
        tilt_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(6)")
        if tilt_elem:
            tilt_text = tilt_elem.text.strip()
            try:
                if tilt_text and tilt_text != "---":
                    entry["tilt"] = float(tilt_text)
            except ValueError:
                pass
        
        # 部品交換（1行目8列目）
        parts_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(8) > ul.labelGroup1 > li > span")
        if parts_elem:
            parts_text = parts_elem.text.strip()
            if parts_text and parts_text != "---":
                entry["parts_changed"] = parts_text
        
        if entry:  # 空のエントリーは追加しない
            entries.append(entry)
    
    return race_info, entries


# 選手情報の抽出
def extract_entry_info(html: str) -> List[Dict[str, Any]]:
    """
    出走表ページから選手情報を抽出する
    
    Args:
        html: 出走表ページのHTML文字列
        
    Returns:
        List[Dict[str, Any]]: 各選手の情報
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    
    # 選手テーブルの各行を処理
    boat_color_selector = ", ".join([f"tr:nth-child(1) > td.is-boatColor{i}" for i in range(1, 7)])
    for tbody in soup.select("div.table1.is-tableFixed__3rdadd > table > tbody"):
        entry = {}
        
        # 枠番の取得
        boat_color_td = tbody.select_one(boat_color_selector)
        if boat_color_td:
            for i in range(1, 7):
                if f"is-boatColor{i}" in boat_color_td.get("class", []):
                    entry["lane"] = i
                    break
        else:
            # 枠番が取得できない場合はスキップ
            continue
        
        # 登録番号と氏名
        player_id_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(3) > div.is-fs11")
        if player_id_elem:
            player_id_text = player_id_elem.text.strip()
            if player_id_text:
                try:
                    entry["player_id"] = int(player_id_text.split()[0])
                except (ValueError, IndexError):
                    # プレイヤーIDが取得できなければスキップ
                    continue
        else:
            continue
        
        # 級別
        class_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(3) > div.is-fs11 > span")
        if class_elem:
            entry["class_"] = class_elem.text.strip()
        
        # 氏名は保存しない (player_idから参照)
        
        # F数、L数、平均ST
        performance_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(4)")
        if performance_elem:
            performance_text = performance_elem.text.strip()
            lines = [line.strip() for line in performance_text.split("\n") if line.strip()]
            if len(lines) >= 3:
                # F数
                f_match = lines[0].lower()
                if f_match.startswith("f"):
                    try:
                        entry["f_count"] = int(f_match[1:]) if f_match[1:].isdigit() else 0
                    except (ValueError, IndexError):
                        entry["f_count"] = 0
                
                # L数
                l_match = lines[1].lower()
                if l_match.startswith("l"):
                    try:
                        entry["l_count"] = int(l_match[1:]) if l_match[1:].isdigit() else 0
                    except (ValueError, IndexError):
                        entry["l_count"] = 0
                
                # 平均ST
                try:
                    entry["avg_st"] = float(lines[2])
                except (ValueError, IndexError):
                    entry["avg_st"] = None
        
        # 全国勝率等のデータ抽出
        nationwide_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(5)")
        if nationwide_elem:
            nationwide_text = nationwide_elem.text.strip()
            lines = [line.strip() for line in nationwide_text.split("\n") if line.strip()]
            if len(lines) >= 3:
                try:
                    entry["nationwide_win_rate"] = float(lines[0])
                    entry["nationwide_two_win_rate"] = float(lines[1])
                    entry["nationwide_three_win_rate"] = float(lines[2])
                except (ValueError, IndexError):
                    pass
        
        # 当地勝率等のデータ抽出
        local_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(6)")
        if local_elem:
            local_text = local_elem.text.strip()
            lines = [line.strip() for line in local_text.split("\n") if line.strip()]
            if len(lines) >= 3:
                try:
                    entry["local_win_rate"] = float(lines[0])
                    entry["local_two_win_rate"] = float(lines[1])
                    entry["local_three_win_rate"] = float(lines[2])
                except (ValueError, IndexError):
                    pass
        
        # モーター情報
        motor_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(7)")
        if motor_elem:
            motor_text = motor_elem.text.strip()
            lines = [line.strip() for line in motor_text.split("\n") if line.strip()]
            if len(lines) >= 3:
                try:
                    entry["motor_no"] = int(lines[0])
                    entry["motor_two_win_rate"] = float(lines[1])
                    entry["motor_three_win_rate"] = float(lines[2])
                except (ValueError, IndexError):
                    pass
        
        # ボート情報
        boat_elem = tbody.select_one("tr:nth-child(1) > td:nth-child(8)")
        if boat_elem:
            boat_text = boat_elem.text.strip()
            lines = [line.strip() for line in boat_text.split("\n") if line.strip()]
            if len(lines) >= 3:
                try:
                    entry["boat_no"] = int(lines[0])
                    entry["boat_two_win_rate"] = float(lines[1])
                    entry["boat_three_win_rate"] = float(lines[2])
                except (ValueError, IndexError):
                    pass
        
        # 体重等のデータは直前情報ページから取得
        
        entries.append(entry)
    
    return entries


# データベース初期化
def init_database():
    """データベースの初期化"""
    # データベースディレクトリの作成
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    # 古いDBファイルが存在する場合は削除する（開発用）
    if os.path.exists(DB_FILE):
        logger.info(f"既存のデータベースファイルを削除します: {DB_FILE}")
        os.remove(DB_FILE)
    
    # SQLAlchemyエンジンとテーブル作成
    engine = sa.create_engine(f"sqlite:///{DB_FILE}")
    Base.metadata.create_all(engine)
    
    # 場コードデータの登録
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # すでに登録されていなければ、会場データを登録
    if session.query(Venue).count() == 0:
        for jcd, name in VENUE_MAPPING.items():
            session.add(Venue(jcd=jcd, name=name))
        session.commit()
    
    session.close()
    return engine


# メイン処理
def main():
    """メイン処理"""
    # データベース初期化
    engine = init_database()
    Session = sessionmaker(bind=engine)
    
    # ログディレクトリ作成
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs"), exist_ok=True)
    
    # 開催中のレース場を取得
    active_venues = get_active_venues(TARGET_DATE)
    
    # 対象レース場の絞り込み (開催中かつID範囲内)
    target_venues = [jcd for jcd in active_venues if int(jcd) <= MAX_VENUE_ID]
    
    if not target_venues:
        logger.warning(f"対象のレース場が見つかりませんでした（開催中: {len(active_venues)}件、条件内: {len(target_venues)}件）")
        return
    
    logger.info(f"対象レース場 {len(target_venues)}件: {', '.join(sorted(target_venues))}")
    
    # 対象レース場の1レース目のデータ取得
    for jcd in sorted(target_venues):
        try:
            logger.info(f"会場コード {jcd} ({VENUE_MAPPING.get(jcd, '不明')}) の処理を開始")
            
            # URLの生成
            urls = generate_urls(TARGET_DATE, jcd, RACE_NO)
            
            # 出走表ページの取得
            race_card_html = fetch_html(urls["race_card"])
            if not race_card_html:
                logger.warning(f"会場 {jcd} の出走表ページが取得できませんでした。開催されていない可能性があります。")
                continue
            
            # レース情報の抽出
            race_info = extract_race_info(race_card_html)
            logger.info(f"レース情報抽出: {race_info}")
            
            # 直前情報ページの取得と情報抽出
            race_live_html = fetch_html(urls["race_live_info"])
            if race_live_html:
                live_race_info, live_entries = extract_live_info(race_live_html)
                # レース情報の更新
                race_info.update(live_race_info)
                logger.info(f"直前情報を追加: {live_race_info}")
            else:
                logger.warning(f"会場 {jcd} の直前情報ページが取得できませんでした")
                live_entries = []
            
            # シーズン年と期の設定（例: 2024年4月なので2024年期1）
            target_date = datetime.datetime.strptime(TARGET_DATE, DATE_FORMAT).date()
            race_info["hd"] = target_date
            race_info["jcd"] = jcd
            race_info["rno"] = RACE_NO
            
            if target_date.month >= 4 and target_date.month <= 9:
                race_info["season_year"] = target_date.year
                race_info["season_term"] = 1
            else:
                race_info["season_year"] = target_date.year
                race_info["season_term"] = 2
            
            # 選手情報の抽出
            entries = extract_entry_info(race_card_html)
            logger.info(f"{len(entries)}名の選手情報を抽出しました")
            
            if len(entries) == 0:
                logger.warning(f"会場 {jcd} の選手情報が抽出できませんでした。開催されていない可能性があります。")
                continue
            
            # 直前情報の統合
            for entry in entries:
                for live_entry in live_entries:
                    if entry["lane"] == live_entry["lane"]:
                        entry.update(live_entry)
            
            # データベースへの保存
            session = Session()
            try:
                # レース情報の保存
                race = Race(**race_info)
                session.add(race)
                session.flush()  # IDを取得するためにフラッシュ
                
                # 選手情報の保存
                for entry_data in entries:
                    # キーエラーを防ぐために存在しないキーはスキップ
                    filtered_entry_data = {k: v for k, v in entry_data.items() if hasattr(RaceEntry, k)}
                    entry = RaceEntry(race_id=race.race_id, **filtered_entry_data)
                    session.add(entry)
                
                session.commit()
                logger.info(f"会場 {jcd} のデータをデータベースに保存しました")
            except Exception as e:
                session.rollback()
                logger.error(f"データベース保存エラー: {e}")
            finally:
                session.close()
            
            # リクエスト間隔を空ける
            time.sleep(REQUEST_INTERVAL)
            
        except Exception as e:
            logger.error(f"会場 {jcd} の処理中にエラーが発生しました: {e}")
    
    logger.info("全会場の処理が完了しました")


if __name__ == "__main__":
    main() 