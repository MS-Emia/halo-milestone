# 完成までのやることリスト

全部で30分〜1時間くらい。終わった項目は `[ ]` を `[x]` にしていく。

## ① 監視する再生リストの URL を用意する(5分)

- [ ] YouTube で天音かなたさんの「歌ってみた」再生リストを開き、URL をコピーする(`list=` を含むもの)
  - 公式チャンネルの再生リストでも、自分で作った再生リストでもよい
  - 自分で作る場合は「公開」か「限定公開」にする(非公開は取得できない)
- [ ] `config.json` の `"TODO: 利用者が追記"` を、その URL に書き換える

## ② YouTube API キーを取得する(10〜15分)

- [ ] https://console.cloud.google.com/ にログインし、新しいプロジェクトを作る
- [ ] 「API とサービス」→「ライブラリ」で **YouTube Data API v3** を検索し、「有効にする」を押す
- [ ] 「認証情報」→「認証情報を作成」→「API キー」でキーを作る
- [ ] 作ったキーの編集画面で「API の制限」→「キーを制限」を選び、**YouTube Data API v3 だけ**にチェックを入れて保存する

料金はかからない(無料枠の1%程度しか使わない)。

## ③ Discord ウェブフック URL を発行する(5分)

- [ ] 通知を受けたいサーバーを開く(自分専用なら、左端の「＋」で新しいサーバーを作ると手軽)
- [ ] 通知を流したいチャンネル名の横にある**歯車(チャンネルの編集)**を押す
- [ ] **連携サービス** → **ウェブフック** → **新しいウェブフック** を押す
- [ ] 名前(例: `Halo Count`)と投稿先のチャンネルを確認する
- [ ] **ウェブフック URL をコピー** を押す(`https://discord.com/api/webhooks/...` の形)

「連携サービス」が見当たらない場合は、そのサーバーで「ウェブフックの管理」権限がない。

⚠️ この URL を知っている人は誰でもそのチャンネルに投稿できる。コード・`config.json`・このファイルには書かない。漏れたら、同じ画面でウェブフックを削除して作り直す。

## ④ (任意)手元で動作確認する(5分)

PowerShell で次を実行する。

```powershell
cd C:\Users\jiyua\Documents\kanata-milestone-notifier
$env:YOUTUBE_API_KEY = "②のキー"
$env:DISCORD_WEBHOOK_URL = "③のURL"
$env:DRY_RUN = "1"
python scripts\check.py                    # 全動画の判定結果が表示される(送信はしない)
Remove-Item Env:DRY_RUN
python scripts\check.py --test-webhook     # Discord にテスト通知が届く
```

- [ ] DRY_RUN で判定結果が表示された
- [ ] Discord に「🔔 テスト通知」が届いた

## ⑤ GitHub にリポジトリを作って push する(10分)

- [ ] GitHub で新しいリポジトリを作る。**Public** を選び、README などは追加しない
- [ ] このフォルダを push する(Claude Code に「リポジトリ URL は ○○、push して」と頼めば代わりに実行できる)

## ⑥ GitHub の設定をする(5分)

- [ ] **Settings → Secrets and variables → Actions** で、次の2つを登録する
  - `YOUTUBE_API_KEY`
  - `DISCORD_WEBHOOK_URL`
- [ ] **Settings → Pages → Source** を「**GitHub Actions**」にする

## ⑦ 本番の動作確認をする(10分)

**Actions → check milestones → Run workflow** から、次の順に実行する。

| 順番 | mode | 確認すること |
|---|---|---|
| 1 | `dry_run` | ログに全動画の判定が出る。サイトの URL が表示されて開ける |
| 2 | `test_webhook` | Discord に「🔔 テスト通知」が届く |
| 3 | `normal` | 成功(緑)になる。`state.json` の更新 commit ができている |

- [ ] 1. `dry_run` 成功
- [ ] 2. `test_webhook` 成功
- [ ] 3. `normal` 成功 → **完成** 🎉(以降は毎時17分に自動で動く)

## 完成後に気にしておくこと

- 通知が届かなくなったら Actions タブを見る。60日ほど活動が無いと自動実行が止まることがある(その場合は再有効化ボタンを押すだけ)。
- Actions が赤(失敗)になるとメールが届く。ログを Claude Code に貼れば原因を調べてもらえる。

## 決めておくと良いこと(急ぎではない)

- [ ] **YouTube API の30日ルール**: 規約に厳密に従うなら、履歴に「検知時の再生数」を残さないようにできる(詳しくは README の「権利・ガイドライン」)
- [ ] **配色**: 今は仮の水色系。好みの色があれば `site/style.css` の `:root` と `scripts/discord.py` の `EMBED_COLOR` を揃えて変える

## 会話の再開方法

Claude Code での作業を続けるときは、`C:\Users\jiyua\Documents` で `claude --resume` を実行して一覧から選ぶ(または起動後に `/resume`)。会話は初期設定では30日で削除される。
