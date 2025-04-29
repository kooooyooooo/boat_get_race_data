import argparse
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy.orm import sessionmaker

# models.py からモデル定義と DB 設定をインポート
from models import Player, PlayerSeasonSummary, PlayerLaneSummary, ENGINE, Base

# グローバル変数として Session を定義
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

def parse_filename(filepath: str) -> tuple[int, int]:
    """
    ファイル名 (例: fan2410.csv) から年と期を抽出する。

    Args:
        filepath: CSVファイルのパス。

    Returns:
        (year, term): 年と期 (1 or 2)。

    Raises:
        ValueError: ファイル名が期待される形式でない場合。
    """
    filename = os.path.basename(filepath)
    match = re.match(r"fan(\d{2})(\d{2})\.(csv|parquet)", filename)
    if not match:
        raise ValueError(f"ファイル名 '{filename}' の形式が不正です。'fanYYMM.csv' または 'fanYYMM.parquet' 形式である必要があります。")

    yy = int(match.group(1))
    mm = int(match.group(2))

    year = 2000 + yy

    if 4 <= mm <= 9:
        term = 1
    elif 10 <= mm <= 12:
        term = 2
    elif 1 <= mm <= 3:
        # 1-3月は前年の期(2)に属する
        year -= 1
        term = 2
    else:
        raise ValueError(f"月 '{mm}' の値が不正です。")

    return year, term


def calculate_term_dates(year: int, term: int) -> tuple[date, date]:
    """年と期から集計開始日と終了日を計算する。"""
    if term == 1:
        # 前期: YYYY-04-01 ～ YYYY-09-30
        calc_start = date(year, 4, 1)
        calc_end = date(year, 9, 30)
    elif term == 2:
        # 後期: YYYY-10-01 ～ (YYYY+1)-03-31
        calc_start = date(year, 10, 1)
        calc_end = date(year + 1, 3, 31)
    else:
        # 基本的には parse_filename で弾かれるはず
        raise ValueError(f"不正な期が指定されました: {term}")
    return calc_start, calc_end


def wareki_to_seireki(gengo: str, wareki_date_str: str) -> date | None:
    """和暦文字列 (例: S, 380715) を西暦 date オブジェクトに変換する。"""
    try:
        if not wareki_date_str or len(wareki_date_str) != 6:
            return None
        year = int(wareki_date_str[:2])
        month = int(wareki_date_str[2:4])
        day = int(wareki_date_str[4:6])

        if gengo == 'S': # 昭和
            seireki_year = year + 1925
        elif gengo == 'H': # 平成
            seireki_year = year + 1988
        elif gengo == 'R': # 令和
            seireki_year = year + 2018
        else:
            return None # 不明な元号

        return date(seireki_year, month, day)
    except (ValueError, TypeError):
        return None # 変換失敗


def safe_decimal(value, divisor=100, precision=2) -> Decimal | None:
    """文字列や数値を Decimal に安全に変換する (指定された数で除算)。"""
    try:
        # pd.NA や空文字列を None 扱いにする
        if pd.isna(value) or value == '':
            return None
        # すでに Decimal, float, int の場合も考慮
        if isinstance(value, (Decimal, float, int)):
            num = Decimal(value)
        else:
            num = Decimal(str(value).strip()) # 文字列なら前後の空白を除去

        result = (num / Decimal(divisor)).quantize(Decimal('0.01')) # precision=2 を想定
        # スキーマの精度に合わせて調整 (例: DECIMAL(4,2) なら絶対値が100未満か)
        # ここでは単純に返す (必要ならバリデーション追加)
        return result
    except (InvalidOperation, ValueError, TypeError):
        return None # 変換失敗時は None


def safe_int(value) -> int | None:
    """文字列や数値を int に安全に変換する。"""
    try:
        if pd.isna(value) or value == '':
            return None
        return int(value)
    except (ValueError, TypeError):
        return None


# CSVカラム名とモデル属性名のマッピング
COLUMN_MAP = {
    '登番': 'player_id',
    '名前漢字': 'name',
    '支部': 'branch',
    '出身地': 'hometown',
    '年号': 'gengo', # 和暦変換用
    '生年月日': 'birth_date_str', # 和暦変換用
    '級': 'grade',
    '勝率': 'win_rate',
    '複勝率': 'quinella_rate_fanbook', # DBのquinella_rateとは別カラムとして扱う
    '出走回数': 'starts',
    '1着回数': 'wins',
    '2着回数': 'seconds',
    '平均スタートタイミング': 'avg_st',
    # --- 以下、コース別 --- (後で処理)
}

def main():
    parser = argparse.ArgumentParser(description="ファン手帳CSV/Parquetファイルをデータベースに取り込むスクリプト")
    parser.add_argument("filepath", help="取り込むファン手帳ファイルのパス (例: data/fan2410.csv)")
    parser.add_argument("--init-db", action="store_true", help="データベーステーブルを再作成する")
    args = parser.parse_args()

    if args.init_db:
        print("データベーステーブルを再作成します...")
        Base.metadata.drop_all(bind=ENGINE) # 既存テーブル削除
        Base.metadata.create_all(bind=ENGINE) # テーブル作成
        print("テーブル再作成完了。")

    try:
        year, term = parse_filename(args.filepath)
        print(f"処理対象ファイル: {args.filepath}")
        print(f"抽出された年と期: Year={year}, Term={term}")

        calc_start, calc_end = calculate_term_dates(year, term)
        print(f"集計期間: {calc_start} ～ {calc_end}")

        # CSV/Parquet 読み込み (pandas)
        try:
            if args.filepath.endswith('.csv'):
                # データ型を文字列として読み込む (数値変換エラーを防ぐため)
                df = pd.read_csv(args.filepath, encoding='utf-8', dtype=str)
            elif args.filepath.endswith('.parquet'):
                # Parquet はデータ型情報を持つので dtype 指定は不要な場合が多い
                df = pd.read_parquet(args.filepath)
            else:
                raise ValueError("対応していないファイル形式です。CSV または Parquet を指定してください。")
            print(f"{len(df)} 件のデータを読み込みました。")

            # カラム名をリネーム (マッピングが存在するものだけ)
            df.rename(columns=COLUMN_MAP, inplace=True)

        except UnicodeDecodeError:
            print(f"エラー: ファイルのエンコーディングが不正です (UTF-8 で試行)。Shift-JIS など他のエンコーディングが必要かもしれません。 CSV ファイル: {args.filepath}")
            return
        except pd.errors.ParserError:
            print(f"エラー: CSV ファイルのパースに失敗しました。ファイル形式を確認してください: {args.filepath}")
            return
        except Exception as e:
            print(f"エラー: ファイル読み込み中にエラーが発生しました: {e}")
            return

        # DB接続とデータ処理
        session = SessionLocal()
        try:
            imported_count = 0
            skipped_count = 0
            for index, row in df.iterrows():
                player_id = safe_int(row.get('player_id'))
                if player_id is None:
                    print(f"警告: {index+2}行目の登番が無効です。スキップします。Row: {row.to_dict()}")
                    skipped_count += 1
                    continue

                # 1. Player テーブルへの UPSERT
                birth_date = wareki_to_seireki(row.get('gengo'), row.get('birth_date_str'))
                player_data = {
                    'player_id': player_id,
                    'name': row.get('name'),
                    'branch': row.get('branch'),
                    'hometown': row.get('出身地'), # マップされなかったカラムも直接参照
                    'birth_date': birth_date,
                }
                # None の値を持つキーを除去してから merge
                player_data = {k: v for k, v in player_data.items() if v is not None}
                player_obj = Player(**player_data)
                session.merge(player_obj)

                # 2. PlayerSeasonSummary テーブルへの UPSERT
                summary_data = {
                    'player_id': player_id,
                    'year': year,
                    'term': term,
                    'calc_start': calc_start,
                    'calc_end': calc_end,
                    'grade': row.get('grade'),
                    'win_rate': safe_decimal(row.get('win_rate'), divisor=100),
                    # CSVの複勝率を quinella_rate に入れるかは要検討。今回は入れない。
                    # 'quinella_rate': safe_decimal(row.get('quinella_rate_fanbook'), divisor=100),
                    'starts': safe_int(row.get('starts')),
                    'wins': safe_int(row.get('wins')),
                    'seconds': safe_int(row.get('seconds')),
                    'avg_st': safe_decimal(row.get('avg_st'), divisor=100, precision=2),
                    # ability_idx, prev_ability_idx はCSVにないのでNoneのまま
                }
                summary_data = {k: v for k, v in summary_data.items() if v is not None}
                summary_obj = PlayerSeasonSummary(**summary_data)
                merged_summary = session.merge(summary_obj) # LaneSummaryで使うためmerge結果を取得

                # 3. PlayerLaneSummary テーブルへの UPSERT
                for lane in range(7): # 0:コースなし, 1-6:各コース
                    prefix = f'{lane}コース' if lane > 0 else 'コースなし'
                    lane_data = {
                        'player_id': player_id,
                        'year': year,
                        'term': term,
                        'lane': lane,
                        'starts': safe_int(row.get(f'{prefix}進入回数' if lane > 0 else None)), # コースなしの進入回数はない
                        'wins': safe_int(row.get(f'{prefix}1着回数' if lane > 0 else None)),
                        'seconds': safe_int(row.get(f'{prefix}2着回数' if lane > 0 else None)),
                        'thirds': safe_int(row.get(f'{prefix}3着回数' if lane > 0 else None)),
                        'fourths': safe_int(row.get(f'{prefix}4着回数' if lane > 0 else None)),
                        'fifths': safe_int(row.get(f'{prefix}5着回数' if lane > 0 else None)),
                        'sixths': safe_int(row.get(f'{prefix}6着回数' if lane > 0 else None)),
                        'f_count': safe_int(row.get(f'{prefix}F回数' if lane > 0 else None)),
                        'l0_count': safe_int(row.get(f'{prefix}L0回数')),
                        'l1_count': safe_int(row.get(f'{prefix}L1回数')),
                        'k0_count': safe_int(row.get(f'{prefix}K0回数')),
                        'k1_count': safe_int(row.get(f'{prefix}K1回数')),
                        's0_count': safe_int(row.get(f'{prefix}S0回数' if lane > 0 else None)),
                        's1_count': safe_int(row.get(f'{prefix}S1回数' if lane > 0 else None)),
                        's2_count': safe_int(row.get(f'{prefix}S2回数' if lane > 0 else None)),
                        'quinella_rate': safe_decimal(row.get(f'{prefix}複勝率' if lane > 0 else None), divisor=100),
                        'avg_st': safe_decimal(row.get(f'{prefix}平均スタートタイミング' if lane > 0 else None), divisor=100),
                        'avg_start_rank': safe_decimal(row.get(f'{prefix}平均スタート順位' if lane > 0 else None), divisor=100),
                    }
                    # コースなし (lane=0) の場合の特殊処理
                    if lane == 0:
                        lane_data['starts'] = None # コースなしの進入回数はない想定
                        lane_data['wins'] = None
                        lane_data['seconds'] = None
                        lane_data['thirds'] = None
                        lane_data['fourths'] = None
                        lane_data['fifths'] = None
                        lane_data['sixths'] = None
                        lane_data['f_count'] = None
                        lane_data['s0_count'] = None
                        lane_data['s1_count'] = None
                        lane_data['s2_count'] = None
                        lane_data['quinella_rate'] = None
                        lane_data['avg_st'] = None
                        lane_data['avg_start_rank'] = None
                        # L0, L1, K0, K1 はコースなしでも存在するので残す

                    lane_data = {k: v for k, v in lane_data.items() if v is not None}

                    # データが何もなければ (コースなしで事故もない場合など) スキップ
                    if len(lane_data) <= 4: # player_id, year, term, lane 以外にデータがあるか
                        continue

                    lane_obj = PlayerLaneSummary(**lane_data)
                    session.merge(lane_obj)

                imported_count += 1
                if imported_count % 100 == 0: # 100件ごとに進捗表示
                    print(f"... {imported_count} 件処理完了")

            session.commit()
            print(f"処理完了: {imported_count} 件のデータをインポート/更新しました。{skipped_count} 件スキップしました。")

        except Exception as e:
            session.rollback()
            print(f"エラー: データベース処理中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc() # 詳細なトレースバックを出力
        finally:
            session.close()

    except ValueError as e:
        print(f"エラー: {e}")
    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません: {args.filepath}")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")


if __name__ == "__main__":
    main() 