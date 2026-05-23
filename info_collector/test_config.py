#!/usr/bin/env python3
"""設定ファイルと環境変数の確認スクリプト"""

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def check(label: str, value: str | None, required: bool = True) -> None:
    if value:
        masked = value[:4] + "****" if len(value) > 4 else "****"
        print(f"  {'✓' if required else '○'} {label}: {masked}")
    else:
        mark = "✗" if required else "-"
        note = " (必須)" if required else " (任意)"
        print(f"  {mark} {label}: 未設定{note}")


def main() -> None:
    print("=== 設定確認 ===\n")

    env_file = BASE_DIR / ".env"
    print(f".env ファイル: {'存在する' if env_file.exists() else '存在しない ← .env.example をコピーして作成してください'}\n")

    print("[X (Twitter)]")
    check("X_BEARER_TOKEN", os.getenv("X_BEARER_TOKEN"), required=True)

    print("\n[Instagram]")
    check("INSTAGRAM_USERNAME", os.getenv("INSTAGRAM_USERNAME"), required=False)
    check("INSTAGRAM_PASSWORD", os.getenv("INSTAGRAM_PASSWORD"), required=False)

    print("\n[メール送信]")
    check("SMTP_USER", os.getenv("SMTP_USER"), required=True)
    check("SMTP_PASS", os.getenv("SMTP_PASS"), required=True)
    check("NOTIFY_EMAIL", os.getenv("NOTIFY_EMAIL"), required=True)

    print("\n[config.yaml]")
    config_file = BASE_DIR / "config.yaml"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        print(f"  ✓ キーワード数: {len(config['keywords'])} 件")
        for kw in config["keywords"]:
            print(f"      - {kw}")
        interval = config.get("check_interval_minutes", 60)
        print(f"  ✓ 監視間隔: {interval} 分")
        print(f"  ✓ Twitter: {'有効' if config['platforms']['twitter']['enabled'] else '無効'}")
        print(f"  ✓ Instagram: {'有効' if config['platforms']['instagram']['enabled'] else '無効'}")
        to_addr = config["notification"]["email"].get("to") or os.getenv("NOTIFY_EMAIL")
        print(f"  {'✓' if to_addr else '✗'} 通知先: {to_addr or '未設定'}")
    else:
        print("  ✗ config.yaml が存在しません")

    print("\n=== 確認完了 ===")
    print("問題がなければ: python main.py で起動してください")


if __name__ == "__main__":
    main()
