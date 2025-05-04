#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Generator, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base, Venue, Player, Race, RaceEntry, Payout

# ロギング設定
logger = logging.getLogger(__name__)

# デフォルトのデータベースパス
DEFAULT_DB_PATH = "data/boat_data.db"


def get_engine(db_path: str = DEFAULT_DB_PATH):
    """
    SQLAlchemyエンジンを取得する

    Args:
        db_path: データベースパス

    Returns:
        Engine: SQLAlchemyエンジン
    """
    engine = create_engine(f"sqlite:///{db_path}")
    return engine


def get_session_factory(engine):
    """
    セッションファクトリを取得する

    Args:
        engine: SQLAlchemyエンジン

    Returns:
        sessionmaker: セッションファクトリ
    """
    return sessionmaker(bind=engine)


@contextmanager
def session_scope(session_factory) -> Generator[Session, None, None]:
    """
    トランザクション管理を行うセッションコンテキストマネージャ

    Args:
        session_factory: セッションファクトリ

    Yields:
        Session: SQLAlchemyセッション
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"セッション中にエラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# --- Player関連の操作 ---
def get_or_create_player(session: Session, player_data: Dict[str, Any]) -> Player:
    """
    選手IDを元に選手を検索し、存在しない場合は新規に作成する

    Args:
        session: SQLAlchemyセッション
        player_data: 選手情報の辞書 (必須キー: player_id, name)

    Returns:
        Player: 選手オブジェクト
    """
    player_id = player_data.get("player_id")
    if not player_id:
        raise ValueError("player_idは必須です")

    player = session.query(Player).filter(Player.player_id == player_id).first()
    if player:
        logger.debug(f"選手ID {player_id} が見つかりました: {player.name}")
        # 選手名が異なる場合は更新（改姓などの可能性）
        if player.name != player_data.get("name") and player_data.get("name"):
            player.name = player_data.get("name")
            session.add(player)
            logger.info(f"選手ID {player_id} の名前を更新しました: {player.name} → {player_data.get('name')}")
        return player

    # 存在しない場合は新規作成
    logger.info(f"選手ID {player_id} が見つからないため、新規作成します: {player_data.get('name')}")
    player = Player(
        player_id=player_id,
        name=player_data.get("name"),
        branch=player_data.get("branch"),
        hometown=player_data.get("origin", player_data.get("hometown")),  # 元データが origin か hometown かによる
        birth_date=player_data.get("birth_date")
    )
    session.add(player)
    return player


# --- Venue関連の操作 ---
def get_venue(session: Session, jcd: str) -> Optional[Venue]:
    """
    会場コードを元に会場を検索する

    Args:
        session: SQLAlchemyセッション
        jcd: 会場コード

    Returns:
        Optional[Venue]: 会場オブジェクト。見つからない場合はNone。
    """
    venue = session.query(Venue).filter(Venue.jcd == jcd).first()
    if not venue:
        logger.warning(f"会場コード {jcd} が見つかりません")
    return venue


# --- Race関連の操作 ---
def get_or_create_race(session: Session, race_data: Dict[str, Any]) -> Race:
    """
    開催日・会場・レース番号を元にレースを検索し、存在しない場合は新規に作成する

    Args:
        session: SQLAlchemyセッション
        race_data: レース情報の辞書 (必須キー: hd, jcd, rno, season_year, season_term)

    Returns:
        Race: レースオブジェクト
    """
    hd = race_data.get("hd")
    jcd = race_data.get("jcd")
    rno = race_data.get("rno")

    if not all([hd, jcd, rno]):
        raise ValueError("hd, jcd, rnoは必須です")

    # 必須のシーズン情報
    season_year = race_data.get("season_year")
    season_term = race_data.get("season_term")
    if not all([season_year, season_term]):
        raise ValueError("season_year, season_termは必須です")

    # 既存のレースを検索
    race = session.query(Race).filter(
        Race.hd == hd,
        Race.jcd == jcd,
        Race.rno == rno
    ).first()

    if race:
        logger.debug(f"レース情報が見つかりました: {hd} {jcd} {rno}R")
        return race

    # 存在しない場合は新規作成
    logger.info(f"レース情報が見つからないため、新規作成します: {hd} {jcd} {rno}R")
    race = Race(
        hd=hd,
        jcd=jcd,
        rno=rno,
        race_name=race_data.get("race_name"),
        distance=race_data.get("distance"),
        deadline=race_data.get("deadline"),
        weather=race_data.get("weather"),
        wind_speed=race_data.get("wind_speed"),
        wind_dir=race_data.get("wind_dir"),
        water_temp=race_data.get("water_temp"),
        wave_height=race_data.get("wave_height"),
        season_year=season_year,
        season_term=season_term
    )
    session.add(race)
    return race


def update_race_weather(session: Session, race_id: int, weather_data: Dict[str, Any]) -> Optional[Race]:
    """
    レースIDを元に気象情報を更新する

    Args:
        session: SQLAlchemyセッション
        race_id: レースID
        weather_data: 気象情報の辞書

    Returns:
        Optional[Race]: 更新されたレースオブジェクト。見つからない場合はNone。
    """
    race = session.query(Race).filter(Race.race_id == race_id).first()
    if not race:
        logger.warning(f"レースID {race_id} が見つかりません")
        return None

    # 気象情報の更新
    if "weather" in weather_data:
        race.weather = weather_data["weather"]
    if "wind_speed" in weather_data:
        race.wind_speed = weather_data["wind_speed"]
    if "wind_dir" in weather_data or "wind_direction" in weather_data:
        race.wind_dir = weather_data.get("wind_dir") or weather_data.get("wind_direction")
    if "water_temp" in weather_data or "water_temperature" in weather_data:
        race.water_temp = weather_data.get("water_temp") or weather_data.get("water_temperature")
    if "wave_height" in weather_data:
        race.wave_height = weather_data["wave_height"]

    session.add(race)
    logger.info(f"レースID {race_id} の気象情報を更新しました")
    return race


# --- RaceEntry関連の操作 ---
def get_race_entry(session: Session, race_id: int, lane: int) -> Optional[RaceEntry]:
    """
    レースIDと枠番を元に出走情報を検索する

    Args:
        session: SQLAlchemyセッション
        race_id: レースID
        lane: 枠番

    Returns:
        Optional[RaceEntry]: 出走情報オブジェクト。見つからない場合はNone。
    """
    entry = session.query(RaceEntry).filter(
        RaceEntry.race_id == race_id,
        RaceEntry.lane == lane
    ).first()
    return entry


def upsert_race_entry(session: Session, entry_data: Dict[str, Any]) -> RaceEntry:
    """
    レースIDと枠番を元に出走情報を検索し、存在しない場合は新規に作成、
    存在する場合は更新する

    Args:
        session: SQLAlchemyセッション
        entry_data: 出走情報の辞書 (必須キー: race_id, lane, player_id)

    Returns:
        RaceEntry: 出走情報オブジェクト
    """
    race_id = entry_data.get("race_id")
    lane = entry_data.get("lane")
    player_id = entry_data.get("player_id")

    if not all([race_id, lane, player_id]):
        raise ValueError("race_id, lane, player_idは必須です")

    # 既存の出走情報を検索
    entry = get_race_entry(session, race_id, lane)

    if entry:
        logger.debug(f"出走情報が見つかりました: レースID {race_id} 枠番 {lane}")
        # 選手IDが異なる場合は更新
        if entry.player_id != player_id:
            logger.warning(f"選手IDが異なります: {entry.player_id} → {player_id} （レースID {race_id} 枠番 {lane}）")
            entry.player_id = player_id
    else:
        # 存在しない場合は新規作成
        logger.info(f"出走情報が見つからないため、新規作成します: レースID {race_id} 枠番 {lane}")
        entry = RaceEntry(
            race_id=race_id,
            lane=lane,
            player_id=player_id
        )

    # 出走表情報の更新
    if "class_" in entry_data or "class" in entry_data:
        entry.class_ = entry_data.get("class_") or entry_data.get("class")
    if "age" in entry_data:
        entry.age = entry_data["age"]
    if "weight" in entry_data:
        entry.weight = entry_data["weight"]
    if "f_count" in entry_data:
        entry.f_count = entry_data["f_count"]
    if "l_count" in entry_data:
        entry.l_count = entry_data["l_count"]
    if "avg_st" in entry_data:
        entry.avg_st = entry_data["avg_st"]
    if "nationwide_two_win_rate" in entry_data:
        entry.nationwide_two_win_rate = entry_data["nationwide_two_win_rate"]
    if "nationwide_three_win_rate" in entry_data:
        entry.nationwide_three_win_rate = entry_data["nationwide_three_win_rate"]
    if "local_two_win_rate" in entry_data:
        entry.local_two_win_rate = entry_data["local_two_win_rate"]
    if "local_three_win_rate" in entry_data:
        entry.local_three_win_rate = entry_data["local_three_win_rate"]
    if "motor_no" in entry_data:
        entry.motor_no = entry_data["motor_no"]
    if "motor_two_win_rate" in entry_data:
        entry.motor_two_win_rate = entry_data["motor_two_win_rate"]
    if "motor_three_win_rate" in entry_data:
        entry.motor_three_win_rate = entry_data["motor_three_win_rate"]
    if "boat_no" in entry_data:
        entry.boat_no = entry_data["boat_no"]
    if "boat_two_win_rate" in entry_data:
        entry.boat_two_win_rate = entry_data["boat_two_win_rate"]
    if "boat_three_win_rate" in entry_data:
        entry.boat_three_win_rate = entry_data["boat_three_win_rate"]

    # 直前情報の更新
    if "tuning_weight" in entry_data:
        entry.tuning_weight = entry_data["tuning_weight"]
    if "exhibition_time" in entry_data:
        entry.exhibition_time = entry_data["exhibition_time"]
    if "tilt" in entry_data:
        entry.tilt = entry_data["tilt"]
    if "parts_changed" in entry_data:
        # JSONとして保存（文字列またはリスト→文字列）
        if entry_data["parts_changed"] is not None:
            if isinstance(entry_data["parts_changed"], str):
                entry.parts_changed = entry_data["parts_changed"]
            else:
                entry.parts_changed = json.dumps(entry_data["parts_changed"], ensure_ascii=False)
        else:
            entry.parts_changed = None

    # 結果情報の更新
    if "rank_raw" in entry_data:
        entry.rank_raw = entry_data["rank_raw"]
    if "rank" in entry_data:
        entry.rank = entry_data["rank"]
    if "race_time" in entry_data:
        entry.race_time = entry_data["race_time"]
    if "start_course" in entry_data:
        entry.start_course = entry_data["start_course"]
    if "start_st" in entry_data:
        entry.start_st = entry_data["start_st"]
    if "decision" in entry_data:
        entry.decision = entry_data["decision"]

    session.add(entry)
    return entry


# --- Payout関連の操作 ---
def create_payouts(session: Session, race_id: int, payout_data_list: List[Dict[str, Any]]) -> List[Payout]:
    """
    払戻金情報を一括登録する

    Args:
        session: SQLAlchemyセッション
        race_id: レースID
        payout_data_list: 払戻金情報のリスト (各要素は辞書で、必須キー: bet_type, combination, amount)

    Returns:
        List[Payout]: 登録された払戻金オブジェクトのリスト
    """
    if not payout_data_list:
        logger.warning(f"登録する払戻金情報がありません: レースID {race_id}")
        return []

    # 既存の払戻金情報を削除（重複登録防止）
    existing_payouts = session.query(Payout).filter(Payout.race_id == race_id).all()
    if existing_payouts:
        for payout in existing_payouts:
            session.delete(payout)
        logger.info(f"レースID {race_id} の既存の払戻金情報を削除しました: {len(existing_payouts)}件")

    # 新規に払戻金情報を登録
    payouts = []
    for payout_data in payout_data_list:
        bet_type = payout_data.get("bet_type")
        combination = payout_data.get("combination")
        amount = payout_data.get("amount")

        if not all([bet_type, combination, amount]):
            logger.warning(f"払戻金情報の必須項目が不足しています: {payout_data}")
            continue

        payout = Payout(
            race_id=race_id,
            bet_type=bet_type,
            combination=combination,
            amount=amount,
            popularity=payout_data.get("popularity")
        )
        session.add(payout)
        payouts.append(payout)

    logger.info(f"レースID {race_id} の払戻金情報を {len(payouts)}件 登録しました")
    return payouts


# --- 共通処理 ---
def init_database(db_path: str = DEFAULT_DB_PATH, create_tables: bool = True) -> Tuple:
    """
    データベースの初期化処理

    Args:
        db_path: データベースパス
        create_tables: テーブルを作成するかどうか

    Returns:
        Tuple: (Engine, SessionFactory)
    """
    engine = get_engine(db_path)
    session_factory = get_session_factory(engine)

    if create_tables:
        # テーブルの作成
        Base.metadata.create_all(engine)
        logger.info(f"データベース {db_path} のテーブルを作成しました")

        # 初期データ投入（Venueテーブル）
        with session_scope(session_factory) as session:
            venues = session.query(Venue).all()
            if not venues:
                logger.info("会場マスタの初期データを登録します")
                venues_data = [
                    Venue(jcd="01", name="桐生", pref="群馬"),
                    Venue(jcd="02", name="戸田", pref="埼玉"),
                    Venue(jcd="03", name="江戸川", pref="東京"),
                    Venue(jcd="04", name="平和島", pref="東京"),
                    Venue(jcd="05", name="多摩川", pref="東京"),
                    Venue(jcd="06", name="浜名湖", pref="静岡"),
                    Venue(jcd="07", name="蒲郡", pref="愛知"),
                    Venue(jcd="08", name="常滑", pref="愛知"),
                    Venue(jcd="09", name="津", pref="三重"),
                    Venue(jcd="10", name="三国", pref="福井"),
                    Venue(jcd="11", name="びわこ", pref="滋賀"),
                    Venue(jcd="12", name="住之江", pref="大阪"),
                    Venue(jcd="13", name="尼崎", pref="兵庫"),
                    Venue(jcd="14", name="鳴門", pref="徳島"),
                    Venue(jcd="15", name="丸亀", pref="香川"),
                    Venue(jcd="16", name="児島", pref="岡山"),
                    Venue(jcd="17", name="宮島", pref="広島"),
                    Venue(jcd="18", name="徳山", pref="山口"),
                    Venue(jcd="19", name="下関", pref="山口"),
                    Venue(jcd="20", name="若松", pref="福岡"),
                    Venue(jcd="21", name="芦屋", pref="福岡"),
                    Venue(jcd="22", name="福岡", pref="福岡"),
                    Venue(jcd="23", name="唐津", pref="佐賀"),
                    Venue(jcd="24", name="大村", pref="長崎"),
                ]
                for venue in venues_data:
                    session.add(venue)
                logger.info(f"会場マスタに {len(venues_data)}件 の初期データを登録しました")

    return engine, session_factory


if __name__ == "__main__":
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )
    
    # テスト実行
    print("db_handler.py - 直接実行されました。テスト処理を実行します。")
    print("データベースの初期化...")
    engine, session_factory = init_database()
    print("初期化完了。") 