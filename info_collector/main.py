#!/usr/bin/env python3
"""
SNSキーワード監視 & メール通知スクリプト
対応プラットフォーム: X (Twitter), Instagram
"""

import json
import logging
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import instaloader
import schedule
import tweepy
import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def load_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict) -> logging.Logger:
    log_file = BASE_DIR / config.get("log_file", "collector.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


def load_state(config: dict) -> dict:
    state_file = BASE_DIR / config.get("state_file", "seen_posts.json")
    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    return {"twitter": [], "instagram": []}


def save_state(state: dict, config: dict) -> None:
    state_file = BASE_DIR / config.get("state_file", "seen_posts.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# X (Twitter) コレクター
# ---------------------------------------------------------------------------

def collect_twitter(keywords: list[str], seen_ids: list[str], config: dict, logger: logging.Logger) -> list[dict]:
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        logger.warning("[Twitter] X_BEARER_TOKEN が未設定です。スキップします。")
        return []

    tw_config = config["platforms"]["twitter"]
    max_results = tw_config.get("max_results_per_keyword", 10)
    exclude_rt = tw_config.get("exclude_retweets", True)

    try:
        client = tweepy.Client(bearer_token=bearer_token)
    except Exception as e:
        logger.error(f"[Twitter] クライアント初期化失敗: {e}")
        return []

    new_posts = []

    for keyword in keywords:
        rt_filter = " -is:retweet" if exclude_rt else ""
        query = f'"{keyword}"{rt_filter}'

        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=max(10, min(max_results, 100)),
                tweet_fields=["created_at", "author_id", "text"],
                expansions=["author_id"],
                user_fields=["username", "name"],
            )
        except tweepy.TooManyRequests:
            logger.warning("[Twitter] レートリミット到達。次サイクルで再試行します。")
            break
        except tweepy.Unauthorized:
            logger.error("[Twitter] 認証エラー。X_BEARER_TOKEN を確認してください。")
            break
        except Exception as e:
            logger.error(f"[Twitter] キーワード '{keyword}' の取得失敗: {e}")
            continue

        if not response.data:
            continue

        authors: dict = {}
        if response.includes and "users" in response.includes:
            for user in response.includes["users"]:
                authors[user.id] = user

        for tweet in response.data:
            tweet_id = str(tweet.id)
            if tweet_id in seen_ids:
                continue

            author = authors.get(tweet.author_id)
            username = author.username if author else "unknown"
            display_name = author.name if author else "unknown"

            new_posts.append({
                "platform": "X (Twitter)",
                "keyword": keyword,
                "id": tweet_id,
                "url": f"https://x.com/{username}/status/{tweet_id}",
                "author": f"{display_name} (@{username})",
                "text": tweet.text,
                "created_at": str(tweet.created_at),
            })
            seen_ids.append(tweet_id)

        # X無料プランは連続リクエストに厳しいため少し待機
        time.sleep(2)

    return new_posts


# ---------------------------------------------------------------------------
# Instagram コレクター
# ---------------------------------------------------------------------------

def collect_instagram(keywords: list[str], seen_ids: list[str], config: dict, logger: logging.Logger) -> list[dict]:
    ig_config = config["platforms"]["instagram"]
    max_posts = ig_config.get("max_posts_per_keyword", 5)

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
        logger.info(f"[Instagram] セッションIDでログイン: @{ig_user}")
    else:
        logger.warning("[Instagram] INSTAGRAM_SESSION_ID または INSTAGRAM_USERNAME が未設定です")

    new_posts = []

    for keyword in keywords:
        # スペースを除去してハッシュタグ化
        hashtag = keyword.replace(" ", "").replace("　", "")

        try:
            tag = instaloader.Hashtag.from_name(loader.context, hashtag)
            count = 0

            for post in tag.get_posts():
                if count >= max_posts:
                    break

                post_id = str(post.mediaid)
                if post_id in seen_ids:
                    count += 1
                    continue

                caption = ""
                if post.caption:
                    caption = post.caption[:300]

                new_posts.append({
                    "platform": "Instagram",
                    "keyword": f"#{hashtag}",
                    "id": post_id,
                    "url": f"https://www.instagram.com/p/{post.shortcode}/",
                    "author": post.owner_username,
                    "text": caption if caption else "(キャプションなし)",
                    "created_at": str(post.date_utc),
                })
                seen_ids.append(post_id)
                count += 1

        except instaloader.exceptions.QueryReturnedNotFoundException:
            logger.info(f"[Instagram] ハッシュタグ '#{hashtag}' は投稿なし or 存在しない")
        except instaloader.exceptions.TooManyRequestsException:
            logger.warning("[Instagram] レートリミット到達。次サイクルで再試行します。")
            break
        except Exception as e:
            logger.error(f"[Instagram] ハッシュタグ '#{hashtag}' の取得失敗: {e}")

        time.sleep(3)

    return new_posts


# ---------------------------------------------------------------------------
# メール通知
# ---------------------------------------------------------------------------

def build_email_html(new_posts: list[dict]) -> str:
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    by_platform: dict[str, list] = {}
    for post in new_posts:
        by_platform.setdefault(post["platform"], []).append(post)

    sections = []
    for platform, posts in by_platform.items():
        items = []
        for p in posts:
            items.append(
                f"""<div style="border:1px solid #e0e0e0;border-radius:6px;padding:12px;margin:8px 0;background:#fafafa;">
  <span style="background:#1da1f2;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">{p['platform']}</span>
  <span style="background:#e8f4e8;color:#2d6a2d;padding:2px 8px;border-radius:4px;font-size:12px;margin-left:6px;">{p['keyword']}</span>
  <p style="margin:8px 0 4px;"><strong>投稿者:</strong> {p['author']}</p>
  <p style="margin:4px 0;color:#555;font-size:14px;">{p['text']}</p>
  <p style="margin:4px 0;font-size:12px;color:#888;">{p['created_at']}</p>
  <a href="{p['url']}" style="color:#1a73e8;font-size:13px;">投稿を見る →</a>
</div>"""
            )
        sections.append(
            f"<h3 style='color:#333;border-bottom:2px solid #eee;padding-bottom:6px;'>"
            f"{platform} <span style='color:#888;font-size:14px;'>({len(posts)}件)</span></h3>"
            + "".join(items)
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Hiragino Kaku Gothic Pro',Meiryo,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333;">
  <h2 style="color:#2c5f8a;border-left:4px solid #2c5f8a;padding-left:12px;">
    松本エリア情報収集レポート
  </h2>
  <p style="color:#666;">取得日時: {now_str} &nbsp;|&nbsp; 新着合計: <strong>{len(new_posts)}件</strong></p>
  <hr style="border:none;border-top:1px solid #eee;">
  {"".join(sections)}
  <p style="font-size:11px;color:#aaa;margin-top:30px;">このメールはSNS情報収集スクリプトにより自動送信されています。</p>
</body>
</html>"""


def send_email(new_posts: list[dict], config: dict, logger: logging.Logger) -> None:
    email_config = config["notification"]["email"]

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    to_addr = email_config.get("to") or os.getenv("NOTIFY_EMAIL")

    if not smtp_user or not smtp_pass:
        logger.warning("[Email] SMTP_USER / SMTP_PASS が未設定です。送信をスキップします。")
        return
    if not to_addr:
        logger.warning("[Email] 送信先アドレスが未設定です（config.yaml の to または NOTIFY_EMAIL）。")
        return

    prefix = email_config.get("subject_prefix", "[情報収集] ")
    subject = f"{prefix}{len(new_posts)}件の新着投稿 ({datetime.now().strftime('%Y/%m/%d %H:%M')})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr

    html_body = build_email_html(new_posts)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info(f"[Email] 通知送信完了: {len(new_posts)}件 → {to_addr}")
    except smtplib.SMTPAuthenticationError:
        logger.error("[Email] 認証失敗。SMTP_USER / SMTP_PASS（またはGmailアプリパスワード）を確認してください。")
    except Exception as e:
        logger.error(f"[Email] 送信失敗: {e}")


# ---------------------------------------------------------------------------
# メイン収集サイクル
# ---------------------------------------------------------------------------

def run_collection(config: dict, logger: logging.Logger) -> None:
    logger.info("=== 収集サイクル開始 ===")
    state = load_state(config)
    keywords: list[str] = config["keywords"]
    new_posts: list[dict] = []

    if config["platforms"]["twitter"]["enabled"]:
        twitter_seen: list[str] = state.get("twitter", [])
        posts = collect_twitter(keywords, twitter_seen, config, logger)
        state["twitter"] = twitter_seen[-2000:]  # 最大2000件保持
        new_posts.extend(posts)
        logger.info(f"[Twitter] 新着 {len(posts)} 件")

    if config["platforms"]["instagram"]["enabled"]:
        ig_seen: list[str] = state.get("instagram", [])
        posts = collect_instagram(keywords, ig_seen, config, logger)
        state["instagram"] = ig_seen[-2000:]
        new_posts.extend(posts)
        logger.info(f"[Instagram] 新着 {len(posts)} 件")

    save_state(state, config)

    if new_posts:
        send_email(new_posts, config, logger)
    else:
        logger.info("新着投稿なし")

    logger.info(f"=== 収集サイクル完了 (合計 {len(new_posts)} 件) ===")


def main() -> None:
    config = load_config()
    logger = setup_logging(config)

    interval = config.get("check_interval_minutes", 60)
    logger.info(f"監視開始: {len(config['keywords'])} キーワード, {interval}分間隔")
    logger.info(f"キーワード: {', '.join(config['keywords'])}")

    # 起動時に即時実行
    run_collection(config, logger)

    schedule.every(interval).minutes.do(run_collection, config=config, logger=logger)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
