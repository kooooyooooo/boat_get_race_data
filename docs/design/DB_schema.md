# DB Schema ― 競艇データ収集基盤

> **目的** : 過去 10 年分のレースデータと半期ごとの選手集計データ（ファン手帳）を一体で管理し、機械学習・シミュレーションで横断的に利活用できるようにする。

---

## 1. テーブル一覧

| 区分 | テーブル | 粒度 | 主キー | 概要 |
|------|----------|------|--------|------|
| マスタ | `venue` | 場 | `jcd` | 競艇場コードと名称、所在地 |
| マスタ | `player` | 選手 | `player_id` | 基本プロフィール（氏名・支部・出身地・生年月日） |
| 半期集計 | `player_season_summary` | **選手 × 半期** | `(player_id, year, term)` | 勝率・出走数など半期サマリ（ファン手帳 CSV と 1:1 対応） |
| 半期集計 | `player_lane_summary` | **選手 × 半期 × コース** | `(player_id, year, term, lane)` | コース別詳細（lane=0 は“コースなし”統計） |
| レース | `race` | **開催日 × 場 × レースNo** | `race_id` | レース属性＋気象、水面、**season_year / season_term 列でファン手帳期と連携** |
| レース | `race_entry` | **Race × 枠(1–6)** | `entry_id` | 出走表＋直前＋結果を一体化した行単位データ |
| レース | `payout` | **Race × 勝式** | `payout_id` | 払戻金（3連単・2連複…） |

---

## 2. テーブル定義（DDL 抜粋 / SQLite 型）

<details>
<summary>DDL 一覧を表示</summary>

### 2.1 `venue`
```sql
CREATE TABLE venue (
    jcd  CHAR(2) PRIMARY KEY,
    name TEXT,
    pref TEXT
);
```

### 2.2 `player`
```sql
CREATE TABLE player (
    player_id  INTEGER PRIMARY KEY,
    name       TEXT,
    branch     TEXT,
    hometown   TEXT,
    birth_date DATE
);
```

### 2.3 `player_season_summary`
```sql
CREATE TABLE player_season_summary (
    player_id     INTEGER NOT NULL,
    year          SMALLINT NOT NULL,      -- 2024
    term          TINYINT  NOT NULL,      -- 1 = 4–9 月, 2 = 10–翌 3 月
    calc_start    DATE     NOT NULL,
    calc_end      DATE     NOT NULL,
    grade         TEXT,                   -- A1/B1…
    win_rate      DECIMAL(4,2),
    quinella_rate DECIMAL(4,2),
    starts        SMALLINT,
    wins          SMALLINT,
    seconds       SMALLINT,
    avg_st        DECIMAL(3,2),
    ability_idx   DECIMAL(4,2),
    prev_ability_idx DECIMAL(4,2),
    PRIMARY KEY (player_id, year, term),
    FOREIGN KEY (player_id) REFERENCES player(player_id)
);
```

### 2.4 `player_lane_summary`
```sql
CREATE TABLE player_lane_summary (
    player_id  INTEGER NOT NULL,
    year       SMALLINT NOT NULL,
    term       TINYINT  NOT NULL,
    lane       TINYINT  NOT NULL,         -- 0 = コースなし, 1–6
    starts     SMALLINT,
    wins       SMALLINT,
    seconds    SMALLINT,
    thirds     SMALLINT,
    fourths    SMALLINT,
    fifths     SMALLINT,
    sixths     SMALLINT,
    f_count    SMALLINT,
    l0_count   SMALLINT,
    l1_count   SMALLINT,
    k0_count   SMALLINT,
    k1_count   SMALLINT,
    s0_count   SMALLINT,
    s1_count   SMALLINT,
    s2_count   SMALLINT,
    quinella_rate DECIMAL(4,2),
    avg_st        DECIMAL(3,2),
    avg_start_rank DECIMAL(4,2),
    PRIMARY KEY (player_id, year, term, lane),
    FOREIGN KEY (player_id, year, term)
      REFERENCES player_season_summary(player_id, year, term)
);
```

### 2.5 `race`
```sql
CREATE TABLE race (
    race_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hd          DATE NOT NULL,                -- 開催日
    jcd         CHAR(2) NOT NULL REFERENCES venue(jcd),
    rno         TINYINT NOT NULL CHECK(rno BETWEEN 1 AND 12),
    race_name   TEXT,
    distance    SMALLINT,
    deadline    TIME,
    weather     TEXT,
    wind_speed  SMALLINT,
    wind_dir    TEXT,
    water_temp  DECIMAL(4,1),
    wave_height SMALLINT,
    -- ▼ ファン手帳期との連携用
    season_year SMALLINT NOT NULL,            -- 2024
    season_term TINYINT  NOT NULL,            -- 1 or 2
    UNIQUE (hd, jcd, rno)
);
CREATE INDEX idx_race_hd_jcd ON race(hd, jcd);
```

> **season_year / season_term 決定ルール**  
> 04–09 月開催 → `term = 1`、10–翌 03 月開催 → `term = 2`（年度跨ぎでも開始年に合わせる）。  
> 例: 2024‑10‑05 のレース ⇒ `(2024, 2)` → `fan2410.csv` と JOIN 可。

### 2.6 `race_entry`
```sql
CREATE TABLE race_entry (
    entry_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id   INTEGER NOT NULL REFERENCES race(race_id),
    lane      TINYINT NOT NULL CHECK(lane BETWEEN 1 AND 6),
    player_id INTEGER NOT NULL REFERENCES player(player_id),

    -- 出走表
    class          TEXT,
    age            TINYINT,
    weight         DECIMAL(4,1),
    f_count        TINYINT,
    l_count        TINYINT,
    avg_st         DECIMAL(3,2),
    nationwide_two_win_rate  DECIMAL(4,2),
    nationwide_three_win_rate DECIMAL(4,2),
    local_two_win_rate       DECIMAL(4,2),
    local_three_win_rate     DECIMAL(4,2),
    motor_no       SMALLINT,
    motor_two_win_rate  DECIMAL(4,2),
    motor_three_win_rate DECIMAL(4,2),
    boat_no        SMALLINT,
    boat_two_win_rate   DECIMAL(4,2),
    boat_three_win_rate DECIMAL(4,2),

    -- 直前
    tuning_weight   DECIMAL(4,1),
    exhibition_time DECIMAL(4,2),
    tilt            DECIMAL(3,1),
    parts_changed   TEXT,

    -- 結果
    rank_raw     TEXT,                 -- '１','F','失' 等
    rank         TINYINT,              -- 丸め後…F/失⇒6
    race_time    VARCHAR(8),
    start_course TINYINT,
    start_st     DECIMAL(3,2),
    decision     TEXT,

    UNIQUE (race_id, lane)
);
```

### 2.7 `payout`
```sql
CREATE TABLE payout (
    payout_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id    INTEGER NOT NULL REFERENCES race(race_id),
    bet_type   TEXT NOT NULL,           -- 'TRI', 'TRIF', 'QUIN' 等
    combination TEXT NOT NULL,          -- '1-2-3'
    amount     INTEGER,                 -- 円
    popularity SMALLINT
);
CREATE INDEX idx_payout_race ON payout(race_id);
```

</details>

---

## 3. ER 図（簡易テキスト）
```
venue 1──n race 1──n race_entry n──1 player
                  │
                  └──n payout
player 1──n player_season_summary 1──n player_lane_summary
```

---

## 4. ファン手帳 CSV 取り込み手順

半期ごとの選手サマリー（ファン手帳）は **単一テーブル** で管理します。ファイル名から期情報をパースし、`player_season_summary` と `player_lane_summary` に直接 INSERT してください。

| ステップ | 説明 |
|----------|------|
| **① ファイル検出** | ファン手帳は `fanYYMM.csv` または `.parquet` で配置される想定。|
| **② 期情報の決定** | YY → 西暦 20YY / MM から `term` を決定:<br>- 04–09 月 → `term = 1`<br>- 10–12 月 → `term = 2`<br>- 01–03 月 → **前年**に帰属させ `year = 20(YY-1)`, `term = 2` |
| **③ CSV / Parquet 読込** | `pandas.read_csv` / `pd.read_parquet` で DataFrame 化。列名 ↔ テーブル列をマッピング。 |
| **④ player_season_summary** | 前期・後期で一意になる `(player_id, year, term)` を主キーとして UPSERT。|
| **⑤ player_lane_summary** | コース別列を縦持ち展開（lane=0 行含め計 7 行/選手)。同主キーで UPSERT。|
| **⑥ インデックス確認** | 大量 INSERT 時は一時的に INDEX を無効化→再構築すると高速化。|

> **例**  
> - `fan2404.csv` → year = 2024, term = 1  
> - `fan2410.csv` → year = 2024, term = 2  

**race テーブルとの JOIN** は以下の条件で行えます。
```sql
SELECT ...
FROM race_entry e
JOIN race r USING(race_id)
JOIN player_season_summary s
  ON e.player_id = s.player_id
 AND r.season_year = s.year
 AND r.season_term = s.term;
```

---

## 5. インポート／運用メモ
- **SQLite → PostgreSQL 移行**: `AUTOINCREMENT` → `SERIAL / IDENTITY`, `TEXT` → `VARCHAR`, `NUMERIC` の桁数確認。
- JSON 列 (`parts_changed`) は SQLite では TEXT。PostgreSQL では `jsonb` が推奨。
- 気象列の NULL 許容可否はスクレイピング実装時に調整。


*Last update: 2025-04-28*

