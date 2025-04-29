import datetime
from sqlalchemy import create_engine, Column, Integer, String, Date, SmallInteger, DECIMAL, ForeignKey, UniqueConstraint, Index, ForeignKeyConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

DB_FILE = 'data/boat_data.db'
ENGINE = create_engine(f'sqlite:///{DB_FILE}', echo=False) # echo=True にするとSQLログ出力

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Player(Base):
    __tablename__ = 'player'

    player_id = Column(Integer, primary_key=True, comment='登番')
    name = Column(String, comment='名前漢字')
    branch = Column(String, comment='支部')
    hometown = Column(String, comment='出身地')
    birth_date = Column(Date, comment='生年月日 (西暦)')

    season_summaries = relationship("PlayerSeasonSummary", back_populates="player")

class PlayerSeasonSummary(Base):
    __tablename__ = 'player_season_summary'

    player_id = Column(Integer, ForeignKey('player.player_id'), primary_key=True)
    year = Column(SmallInteger, primary_key=True, comment='集計年')
    term = Column(SmallInteger, primary_key=True, comment='期 (1:前期, 2:後期)')
    calc_start = Column(Date, nullable=False, comment='集計開始日')
    calc_end = Column(Date, nullable=False, comment='集計終了日')
    grade = Column(String, comment='級別 (A1, B1等)')
    win_rate = Column(DECIMAL(4, 2), comment='勝率')
    quinella_rate = Column(DECIMAL(4, 2), comment='2連対率') # CSVの複勝率とは異なる可能性
    starts = Column(SmallInteger, comment='出走回数')
    wins = Column(SmallInteger, comment='1着回数')
    seconds = Column(SmallInteger, comment='2着回数')
    avg_st = Column(DECIMAL(3, 2), comment='平均スタートタイミング')
    # ability_idx, prev_ability_idx はファン手帳CSVにないのでNullable or デフォルト値が必要かも
    ability_idx = Column(DECIMAL(4, 2), nullable=True)
    prev_ability_idx = Column(DECIMAL(4, 2), nullable=True)

    player = relationship("Player", back_populates="season_summaries")
    lane_summaries = relationship("PlayerLaneSummary", back_populates="season_summary", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint('player_id', 'year', 'term', name='uq_player_season'),)

class PlayerLaneSummary(Base):
    __tablename__ = 'player_lane_summary'

    player_id = Column(Integer, primary_key=True)
    year = Column(SmallInteger, primary_key=True)
    term = Column(SmallInteger, primary_key=True)
    lane = Column(SmallInteger, primary_key=True, comment='コース (0:コースなし, 1-6)')
    starts = Column(SmallInteger, comment='進入回数')
    wins = Column(SmallInteger, comment='1着回数')
    seconds = Column(SmallInteger, comment='2着回数')
    thirds = Column(SmallInteger, comment='3着回数')
    fourths = Column(SmallInteger, comment='4着回数')
    fifths = Column(SmallInteger, comment='5着回数')
    sixths = Column(SmallInteger, comment='6着回数')
    f_count = Column(SmallInteger, comment='F回数')
    l0_count = Column(SmallInteger, comment='L0回数')
    l1_count = Column(SmallInteger, comment='L1回数')
    k0_count = Column(SmallInteger, comment='K0回数')
    k1_count = Column(SmallInteger, comment='K1回数')
    s0_count = Column(SmallInteger, comment='S0回数')
    s1_count = Column(SmallInteger, comment='S1回数')
    s2_count = Column(SmallInteger, comment='S2回数')
    quinella_rate = Column(DECIMAL(4, 2), comment='複勝率 (CSVの値)')
    avg_st = Column(DECIMAL(3, 2), comment='平均ST')
    avg_start_rank = Column(DECIMAL(4, 2), comment='平均ST順位')

    season_summary = relationship("PlayerSeasonSummary", back_populates="lane_summaries")

    __table_args__ = (
        ForeignKeyConstraint(['player_id', 'year', 'term'],
                             ['player_season_summary.player_id', 'player_season_summary.year', 'player_season_summary.term']),
        UniqueConstraint('player_id', 'year', 'term', 'lane', name='uq_player_lane'),
    )

# テーブル作成 (初回実行時など)
def create_tables():
    Base.metadata.create_all(bind=ENGINE)

if __name__ == '__main__':
    # スクリプトとして実行された場合にテーブルを作成
    print(f"データベースファイル: {DB_FILE}")
    print("テーブルを作成します...")
    create_tables()
    print("テーブル作成完了。") 