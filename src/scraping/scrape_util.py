#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
from typing import Optional, Any

import requests

# ロギング設定 (呼び出し元で設定される想定だが、独立して使う場合も考慮)
logger = logging.getLogger(__name__)


# HTMLの取得
def fetch_html(url: str) -> Optional[str]:
    """
    指定されたURLからHTMLを取得する

    Args:
        url: 取得対象のURL

    Returns:
        Optional[str]: HTML文字列。取得に失敗した場合はNone
    """
    logger.info(f"Fetching HTML from: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding # 文字化け対策
        logger.info(f"Successfully fetched HTML from: {url}")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"URL取得エラー {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました {url}: {e}")
        return None

# --- ヘルパー関数 ---
def _extract_text(element, default=None) -> Optional[str]:
    """要素からテキストを抽出し、空でなければ返す"""
    if element:
        text = element.text.strip()
        # "---" や空文字は None とする
        return text if text and text != "---" else default
    return default

def _extract_number(text: Optional[str], pattern: str, group: int = 1, type_converter=int, default: Optional[Any] = None) -> Optional[Any]:
    """テキストから正規表現で数値を抽出し、指定された型に変換する"""
    if text:
        match = re.search(pattern, text)
        if match:
            try:
                return type_converter(match.group(group))
            except (ValueError, IndexError):
                pass
    return default 