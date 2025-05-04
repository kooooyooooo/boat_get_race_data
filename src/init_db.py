#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import logging
import os

from db_handler import init_database, DEFAULT_DB_PATH

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def main():
    """
    データベースの初期化処理を実行する
    """
    parser = argparse.ArgumentParser(description="競艇データベースの初期化")
    parser.add_argument(
        "--db_path",
        type=str,
        default=DEFAULT_DB_PATH,
        help=f"データベースファイルのパス (デフォルト: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存のDBファイルを上書きする場合に指定"
    )
    args = parser.parse_args()

    # DBファイルの存在確認
    db_path = args.db_path
    db_exists = os.path.exists(db_path)

    if db_exists and not args.force:
        logger.warning(f"データベースファイル {db_path} は既に存在します。")
        user_input = input("上書きしますか？ (y/n): ")
        if user_input.lower() != 'y':
            logger.info("処理を中止します。")
            return

    # データベースディレクトリの作成
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # 既存のDBファイルを削除（--forceフラグがある場合または上書き確認で'y'の場合）
    if db_exists:
        try:
            os.remove(db_path)
            logger.info(f"既存のデータベースファイル {db_path} を削除しました。")
        except Exception as e:
            logger.error(f"データベースファイルの削除中にエラーが発生しました: {e}")
            return

    # データベースの初期化
    try:
        engine, session_factory = init_database(db_path=db_path, create_tables=True)
        logger.info(f"データベース {db_path} の初期化が完了しました。")
    except Exception as e:
        logger.error(f"データベースの初期化中にエラーが発生しました: {e}")
        return


if __name__ == "__main__":
    main() 