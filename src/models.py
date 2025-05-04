#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import Column, Integer, String, SmallInteger, Date, Time, ForeignKey, Numeric, Text, Boolean, UniqueConstraint, Index, CHAR, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Venue(Base):
    """競艇場マスタ"""
    __tablename__ = 'venue'

    jcd = Column(CHAR(2), primary_key=True)
    name = Column(String)
    pref = Column(String)

    # リレーションシップ
    races = relationship("Race", back_populates="venue")

class Player(Base):
    """選手マスタ"""
    __tablename__ = 'player'

    player_id = Column(Integer, primary_key=True)
    name = Column(String)
    branch = Column(String)
    hometown = Column(String)
    birth_date = Column(Date)

    # リレーションシップ
    race_entries = relationship("RaceEntry", back_populates="player")

class Race(Base):
    """レース情報"""
    __tablename__ = 'race'

    race_id = Column(Integer, primary_key=True, autoincrement=True)
    hd = Column(Date, nullable=False)  # 開催日
    jcd = Column(CHAR(2), ForeignKey('venue.jcd'), nullable=False)
    rno = Column(SmallInteger, nullable=False)
    race_name = Column(String)
    distance = Column(SmallInteger)
    deadline = Column(Time)
    weather = Column(String)
    wind_speed = Column(SmallInteger)
    wind_dir = Column(String)
    water_temp = Column(Numeric(4, 1))
    wave_height = Column(SmallInteger)
    
    # ファン手帳期との連携用
    season_year = Column(SmallInteger, nullable=False)  # 2024
    season_term = Column(SmallInteger, nullable=False)  # 1 or 2

    # 一意制約
    __table_args__ = (
        UniqueConstraint('hd', 'jcd', 'rno', name='uix_race_hd_jcd_rno'),
        Index('idx_race_hd_jcd', 'hd', 'jcd'),
    )

    # リレーションシップ
    venue = relationship("Venue", back_populates="races")
    race_entries = relationship("RaceEntry", back_populates="race", cascade="all, delete-orphan")
    payouts = relationship("Payout", back_populates="race", cascade="all, delete-orphan")

class RaceEntry(Base):
    """レース出走情報（出走表＋直前＋結果）"""
    __tablename__ = 'race_entry'

    entry_id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey('race.race_id'), nullable=False)
    lane = Column(SmallInteger, nullable=False)
    player_id = Column(Integer, ForeignKey('player.player_id'), nullable=False)

    # 出走表
    class_ = Column('class', String)  # class は予約語のため class_ とする
    age = Column(SmallInteger)
    weight = Column(Numeric(4, 1))
    f_count = Column(SmallInteger)
    l_count = Column(SmallInteger)
    avg_st = Column(Numeric(3, 2))
    nationwide_two_win_rate = Column(Numeric(4, 2))
    nationwide_three_win_rate = Column(Numeric(4, 2))
    local_two_win_rate = Column(Numeric(4, 2))
    local_three_win_rate = Column(Numeric(4, 2))
    motor_no = Column(SmallInteger)
    motor_two_win_rate = Column(Numeric(4, 2))
    motor_three_win_rate = Column(Numeric(4, 2))
    boat_no = Column(SmallInteger)
    boat_two_win_rate = Column(Numeric(4, 2))
    boat_three_win_rate = Column(Numeric(4, 2))

    # 直前
    tuning_weight = Column(Numeric(4, 1))
    exhibition_time = Column(Numeric(4, 2))
    tilt = Column(Numeric(3, 1))
    parts_changed = Column(Text)  # JSON形式で保存

    # 結果
    rank_raw = Column(String)  # '１','F','失' 等
    rank = Column(SmallInteger)  # 丸め後…F/失⇒6
    race_time = Column(String)
    start_course = Column(SmallInteger)
    start_st = Column(Numeric(3, 2))
    decision = Column(String)  # 決まり手

    # 一意制約
    __table_args__ = (
        UniqueConstraint('race_id', 'lane', name='uix_race_entry_race_id_lane'),
    )

    # リレーションシップ
    race = relationship("Race", back_populates="race_entries")
    player = relationship("Player", back_populates="race_entries")

class Payout(Base):
    """払戻金情報"""
    __tablename__ = 'payout'

    payout_id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(Integer, ForeignKey('race.race_id'), nullable=False)
    bet_type = Column(String, nullable=False)  # 'TRI', 'TRIF', 'QUIN' 等
    combination = Column(String, nullable=False)  # '1-2-3'
    amount = Column(Integer)  # 円
    popularity = Column(SmallInteger)

    # インデックス
    __table_args__ = (
        Index('idx_payout_race', 'race_id'),
    )

    # リレーションシップ
    race = relationship("Race", back_populates="payouts")

# 使用法:
# engine = create_engine('sqlite:///path/to/db.sqlite3')
# Base.metadata.create_all(engine) 