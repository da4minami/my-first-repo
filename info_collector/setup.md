# SNS情報収集システム セットアップガイド

監視キーワード: 松本、誰かに語りたくなる暮らし、三の丸エリアプラットフォーム、  
松本城三の丸エリアビジョン、三の丸サポーター、松本まちづくり

---

## 必要なもの

| 項目 | 必須 | 説明 |
|------|------|------|
| Python 3.10+ | ✓ | |
| X (Twitter) APIキー | ✓ | 無料プランのBearer Tokenで動作 |
| Gmailアカウント + アプリパスワード | ✓ | 通知メール送信用 |
| Instagramアカウント | 任意 | ログインするとレート制限が緩和 |

---

## ステップ1: X (Twitter) APIキーの取得

1. https://developer.twitter.com にアクセス
2. 「Sign up for Free Account」でアカウント作成（無料）
3. Projectを作成 → Appを作成
4. 「Keys and Tokens」→「Bearer Token」をコピー

> **注意**: 無料プランは1リクエスト/15分の制限があります。  
> 頻繁な収集が必要な場合はBasicプラン($100/月)を検討してください。

---

## ステップ2: Gmailアプリパスワードの設定

1. Googleアカウントにアクセス → セキュリティ
2. 「2段階認証」を有効化（必須）
3. 「アプリパスワード」→「その他」→ 任意の名前を入力 → 生成
4. 表示された16桁のパスワードをコピー

---

## ステップ3: 環境設定

```bash
cd info_collector

# .envファイルを作成
cp .env.example .env

# .envを編集してAPIキーを設定
nano .env   # またはお好みのエディタで
```

`.env` に設定する内容:
```
X_BEARER_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
SMTP_USER=your_gmail@gmail.com
SMTP_PASS=xxxx xxxx xxxx xxxx   # 16桁のアプリパスワード
NOTIFY_EMAIL=通知先のメールアドレス@example.com
```

---

## ステップ4: インストールと起動

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 設定確認
python test_config.py

# 起動
python main.py
```

---

## Facebook（手動フォロー）

Facebookは関連ページ・グループを直接フォローして確認します。自動収集の対象外です。

フォロー推奨の検索キーワード（Facebook内で検索）:
- 松本まちづくり
- 三の丸エリア
- 松本城三の丸

フォロー後はFacebookのホームフィードまたは「お気に入り」に登録しておくと見逃しを防げます。

---

## 定期実行の設定（サーバー運用時）

`main.py` 自体にスケジューラーが組み込まれているので、起動したままにします。

**systemdサービスとして登録（Linux）:**

```ini
# /etc/systemd/system/sns-collector.service
[Unit]
Description=SNS情報収集サービス

[Service]
ExecStart=/usr/bin/python3 /path/to/info_collector/main.py
WorkingDirectory=/path/to/info_collector
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable sns-collector
sudo systemctl start sns-collector
```

---

## ログの確認

```bash
tail -f collector.log
```

---

## キーワードの変更

`config.yaml` の `keywords:` セクションを編集して、スクリプトを再起動するだけです。
