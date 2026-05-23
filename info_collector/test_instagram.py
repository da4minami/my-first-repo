#!/usr/bin/env python3
"""
Instagram ハッシュタグ検索テスト
ブラウザのセッションIDを使ってログインします
"""

import os
import time
from dotenv import load_dotenv
from pathlib import Path
import instaloader

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

KEYWORDS = [
    "松本",
    "誰かに語りたくなる暮らし",
    "三の丸エリアプラットフォーム",
    "松本城三の丸エリアビジョン",
    "三の丸サポーター",
    "松本まちづくり",
]


def main():
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
    )

    session_id = os.getenv("INSTAGRAM_SESSION_ID")
    ig_user = os.getenv("INSTAGRAM_USERNAME")

    if session_id and ig_user:
        loader.context._session.cookies.set("sessionid", session_id, domain=".instagram.com")
        loader.context.username = ig_user
        print(f"セッションIDでログイン: @{ig_user}\n")
    else:
        print("エラー: .env に INSTAGRAM_SESSION_ID と INSTAGRAM_USERNAME を設定してください\n")
        return

    for keyword in KEYWORDS:
        hashtag = keyword.replace(" ", "").replace("　", "")
        print(f"=== #{hashtag} ===")

        try:
            tag = instaloader.Hashtag.from_name(loader.context, hashtag)
            count = 0
            for post in tag.get_posts():
                if count >= 3:
                    break
                caption = (post.caption or "")[:100].replace("\n", " ")
                print(f"  投稿者: @{post.owner_username}")
                print(f"  日時  : {post.date_utc.strftime('%Y-%m-%d %H:%M')}")
                print(f"  内容  : {caption}")
                print(f"  URL   : https://www.instagram.com/p/{post.shortcode}/")
                print()
                count += 1

            if count == 0:
                print("  投稿なし（ハッシュタグが存在しないか非公開）\n")

        except instaloader.exceptions.QueryReturnedNotFoundException:
            print("  ハッシュタグが存在しません\n")
        except instaloader.exceptions.TooManyRequestsException:
            print("  レートリミット到達。しばらく時間をおいて再実行してください。\n")
            break
        except Exception as e:
            print(f"  エラー: {e}\n")

        time.sleep(3)  # レートリミット対策


if __name__ == "__main__":
    main()
