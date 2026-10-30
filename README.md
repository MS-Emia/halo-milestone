# Halo Count — 天音かなた 歌ってみた 再生数マイルストーン通知

天音かなた(hololive)の「歌ってみた」再生リストを1時間ごとに確認し、各動画の再生数が100万の倍数(100万・200万・300万…)に届いたら Discord に通知します。次の節目が近い動画には事前通知も送ります。あわせて、再生数と進捗を一覧できる静的サイトを GitHub Pages で公開します。

**非公式の個人用ファンツールです。** カバー株式会社・hololive production・天音かなたさんとは関係ありません。非営利で、広告は載せずに運用します。

## 使用バージョン

| 対象 | バージョン |
|---|---|
| Python | 3.12(標準ライブラリのみ。外部パッケージなし) |
| YouTube Data API | v3(`playlistItems.list`, `videos.list`) |
| Discord | Webhook(Embed、`allowed_mentions`) |
| GitHub Actions | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`(2026-10-30時点の最新メジャー) |

## セットアップ

1. GitHub リポジトリを作成し、このフォルダの中身を push します。Pages を使うので、公開リポジトリにするか有料プランを使ってください。
2. Google Cloud で **YouTube Data API v3** を有効にし、API キーを作成します。キーには「API の制限」で YouTube Data API v3 だけを許可してください。
3. Discord の サーバー設定 → 連携サービス → ウェブフック でウェブフックを作成し、URL をコピーします。
4. リポジトリの Settings → Secrets and variables → Actions で、次の2つを登録します。
   - `YOUTUBE_API_KEY`
   - `DISCORD_WEBHOOK_URL`
5. Settings → Pages → Build and deployment → Source を **GitHub Actions** にします。
6. `config.json` の `playlist_urls` を、再生リストの URL(`list=` を含むもの)に書き換えます。複数指定でき、ID だけを書いても動きます。再生リストは「公開」か「限定公開」にしてください(非公開は API キーで取得できません)。
7. Actions → check milestones → Run workflow から、次の順で動作を確認します。
   1. `dry_run`: 全動画の判定結果がログに出て、サイトが公開されます。Discord には送らず、`state.json` も保存しません。
   2. `test_webhook`: Discord にテスト通知が1通届きます。
   3. `normal`: 本番実行です。初回は全動画を「基準化」するだけで、到達通知は送りません(次の節目まで5万回以下の動画にだけ事前通知が届きます)。

その後は毎時17分に自動で実行されます。

## 設定(`config.json`)

| キー | 既定値 | 意味 |
|---|---|---|
| `playlist_urls` | — | 監視する再生リストの URL または ID の配列 |
| `milestone_step` | 1000000 | 節目の間隔 |
| `site_approach_remaining` | 100000 | 次の節目までの残りがこの回数以下なら、サイトに「もうすぐ」と表示する |
| `discord_approach_remaining` | 50000 | 次の節目までの残りがこの回数以下なら、節目ごとに1回だけ Discord に事前通知する |

## ローカルでの実行

```sh
python -m unittest discover -s tests          # テスト
DRY_RUN=1 YOUTUBE_API_KEY=... python scripts/check.py
DISCORD_WEBHOOK_URL=... python scripts/check.py --test-webhook
```

PowerShell では環境変数を `$env:DRY_RUN = "1"` のように設定します。

終了コードは 0=正常、1=実行時エラー(API エラー・通知失敗・`state.json` 破損)、2=設定エラーです。

## 仕組み

```
GitHub Actions (cron 毎時17分)
  └ scripts/check.py
      ├ YouTube Data API v3 から再生数を取得
      ├ state.json と比べて通知が必要か判定
      ├ Discord Webhook に通知(送信に成功した動画だけ state を更新)
      └ site/data.json を生成
  └ state.json が変わったときだけ commit
  └ site/ を GitHub Pages にデプロイ
```

- `state.json` は通知状態が変わったときだけ commit します。毎時の再生数は `site/data.json`(git 管理外)に出し、Pages にだけ載せます。こうすることで、毎時の commit で履歴が膨らむのを防いでいます。
- Discord への送信が失敗した動画は state を更新しないので、次回の実行で再送されます。このとき Actions は失敗(赤)になりますが、成功した分の state commit とサイトの更新は行います。
- 再生数が補正で減っても、記録した節目は下げません。
- `state.json` が壊れている場合は上書きせずに異常終了します。中身を直すか、すべてを基準化し直してよい場合はファイルを削除してから再実行してください。

| ファイル | 役割 |
|---|---|
| `scripts/check.py` | エントリポイント |
| `scripts/youtube.py` | 再生リスト ID の解析、動画 ID・再生数の取得 |
| `scripts/milestones.py` | 節目判定(純粋関数) |
| `scripts/discord.py` | Embed の組み立てと Webhook 送信 |
| `scripts/state.py` | `state.json` の読み書き(アトミック書き込み) |
| `scripts/site_data.py` | `site/data.json` の組み立て |
| `scripts/net.py` | HTTP 共通処理(User-Agent の明示、5xx・ネットワーク障害時の指数バックオフ) |
| `site/` | 静的サイト(素の HTML/CSS/JS) |

## クォータ

1回の実行で使うのは、動画 N 本に対して `ceil(N/50)` × 2 ユニットです。100本でも1回4ユニット、1日約100ユニットで、無料枠(10,000ユニット/日)の1%程度に収まります。

## 運用上の注意

- **schedule の自動無効化**: 公開リポジトリでは、60日間リポジトリに活動が無いと schedule が自動で無効になります。workflow による `state.json` の commit が「活動」に数えられるかは確認できていません。通知が止まったら、Actions タブで workflow を再有効化してください。
- cron は遅れたり、まれにスキップされたりします。サイトでは、最終更新から3時間以上たつと警告を出します。
- `state.json` の commit に失敗すると、次回に同じ通知が重複して届くことがあります(仕様として許容しています)。
- GitHub Pages は URL を知っていれば誰でも見られます。検索避けとして `noindex` を付けています。

## 権利・ガイドライン

- 公式イラスト・立ち絵・ロゴ・ファンアートは使っていません。ハロー・羽・きらめきの装飾は、すべて自作の SVG/CSS です。動画サムネイルは、YouTube API が返す URL(i.ytimg.com)を表示用に参照しているだけです。
- **hololive production 二次創作ガイドライン**(2026-10-30 に確認): https://hololivepro.com/terms/
  - ファン活動は「いわゆる同人活動や趣味の範囲」で行うこと。法人による営利目的の利用は原則として認められていません。
  - 公式と誤認されうる表現や、タレント・会社のイメージを著しく損なう表現は控えること。
  - ガイドラインを守っていれば、個別の問い合わせは不要です。
  - 本ツールの対応: 個人利用・非営利・広告なしで運用します。フッターに非公式である旨を明記し、公式ロゴ風のワードマークも使っていません。
- **YouTube API Services**(2026-10-30 に確認): https://developers.google.com/youtube/terms/developer-policies
  - フッターに、YouTube Data API を利用していること、YouTube 利用規約へのリンク、Google プライバシーポリシーへのリンクを載せています。帰属表示はテキストで「データ提供: YouTube」としています。YouTube のロゴ(Brand Features)を使った表示はしていません。
  - **要確認**: ポリシー III.E.4 には、API データ(統計を含む)の保存期間を30日以内とする旨や、定期的に更新する旨の規定があります。`state.json` の `history[].views_at_detection` と動画タイトルは、30日を超えて残ります。厳密に従う場合は、`views_at_detection` を記録しない、または古い履歴を削除する、といった変更を検討してください。

## デザイン

- コンセプトは天使です。ハロー(楕円リング)、羽、星のきらめき、やわらかなパステルの空をモチーフにしています。
- 配色は**仮パレット**です(背景 `#EAF6FF`→`#FFFFFF`、主色 `#8EC9F0`、ハロー `#F6D77A`、差し色 `#F3B6D4`、文字 `#2B3A55`)。公式タレントページ(https://hololive.hololivepro.com/talents/amane-kanata/)を確認しましたが、イメージカラーやカラーコードは載っていませんでした。「青系」がイメージカラーであることは非公式情報でしか確認できていないため、仮パレットのまま運用しています。変更する場合は、`site/style.css` の `:root` と `scripts/discord.py` の `EMBED_COLOR` を揃えてください。
- 「もうすぐ」バッジのハローは光るアニメーションです。`prefers-reduced-motion` が有効な環境では止まります。
- フォントは Zen Maru Gothic(Google Fonts)で、読み込めない場合はシステムの丸ゴシック/ゴシック体を使います。

## 動作確認の状況

| 項目 | 状況 |
|---|---|
| ユニットテスト(判定ロジック、入力検証、Discord ペイロード、429 再試行、state 読み書き、設定エラー) | ✅ ローカル(Python 3.13)で全件成功 |
| `DRY_RUN` による全動画の判定 | ✅ YouTube API をモックし、55本・2ページ・削除動画・再生数非公開を含めて確認 |
| 送信失敗時の再送と重複防止 | ✅ Webhook をモックして確認 |
| サイト表示(1280px / 360px、データ取得失敗、更新停止、動画0件) | ✅ ヘッドレス Chrome で確認 |
| **実際の YouTube Data API 呼び出し** | ❌ 未確認(API キーなし) |
| **実際の Discord への送信、User-Agent が拒否されないか** | ❌ 未確認 → `test_webhook` で確認してください |
| **GitHub Actions の実行と Pages へのデプロイ** | ❌ 未確認 |
| Python 3.12 での実行 | ❌ ローカルは 3.13 のみ。3.12 での実行は Actions 上で確認されます |
