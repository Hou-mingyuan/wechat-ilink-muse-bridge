# wechat-ilink-muse-bridge

[![CI](https://github.com/gfydfhcf/wechat-ilink-muse-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/gfydfhcf/wechat-ilink-muse-bridge/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gfydfhcf/wechat-ilink-muse-bridge)](https://github.com/gfydfhcf/wechat-ilink-muse-bridge/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

[中文](README.md) | [English](README.en.md) | [日本語](README.ja.md)

**Muse（Meta のパーソナル AI アシスタント）を WeChat に接続します。**

Tencent 公式の iLink / ClawBot プロトコル（`ilinkai.weixin.qq.com`）をベースにしています。
一度 QR コードで認証すれば、Muse が WeChat 上でリアルタイムにあなたとチャットできるようになります。
あなたがメッセージを送れば数秒で返信し、さらにプロアクティブな通知
（配達、サーバーアラート、リマインダーなど）をプッシュすることもでき、
アプリ + WeChat の 2 チャネル体制を実現します。

コアクライアント `ilink.py` はフレームワークに依存しません。単体で取り出せば
最小構成の iLink クライアントとして使えます。リポジトリには 2 種類のロングポーリングドライバーも同梱されています。
スタンドアロンの `daemon.py` と、本番環境で使われている Muse hook 構成です。

<p align="center">
  <img src="docs/demo-chat-1.jpg" alt="実際の使用例：日常のチャットと動画の送信" width="300">
  <img src="docs/demo-chat-2.jpg" alt="実際の使用例：授業のプッシュ通知と日次ダイジェスト" width="300">
  <br><em>実際の使用スクリーンショット：毎日のプッシュ通知、日常のチャット、動画の送信（機密情報は伏せています）</em>
</p>

## Muse 内でのクイックデプロイ

Muse に次の一文を送ってください。

```
Use wechat-ilink-muse-bridge to connect WeChat to you: https://github.com/gfydfhcf/wechat-ilink-muse-bridge
```

Muse はリポジトリのルートにある [`AGENTS.md`](AGENTS.md) に従って、すべて自分でデプロイします。
あなたが WeChat を手に取る必要があるのは、QR コードをスキャンするステップの 1 回だけです。

ログイン後、オーナーを紐付けるために **10 分以内に bot へ最初のメッセージを送る** よう求められます。
最初の送信者が Owner になり、4 部構成のウェルカムメッセージを受け取ります
（4 つ目ではリリースリマインダーの購読について尋ねられます）。時間内に誰もメッセージを送らなかった場合は、
再度リマインドされ、紐付けウィンドウが再び開かれます。

デプロイ後に知っておくと良い日常的なフローが 1 つあります。**新しい送信者の承認** です。
許可リスト外の人（たとえば、あなた自身の 2 つ目の WeChat アカウント）からのメッセージは無視されますが、
送信者の id は承認キューである `data/unknown_senders.json` に記録されます。
その人を許可するには、Muse とのメインチャットでそう伝えるだけです。Muse が保留中の id を
検出回数とともに一覧表示して確認を求め、承認されたものを `owner.json` に追加します。
これは次回のポーリングから有効になります。承認はメインチャットからのみ行え、
WeChat の会話内からは決して行えません。このロックにより、見知らぬ人が言葉巧みに許可リストへ入り込むことを防いでいます。

## 機能

- **公式プロトコル、QR コードログイン** — リバースエンジニアリングや
  個人アカウントのハックは不要です。すべて Tencent 公式の iLink チャネル上で動作します
- **リアルタイムのロングポーリング** — サーバーは各 `getupdates` リクエストを
  最大 35 秒保持し、メッセージが届いた瞬間に返すため、遅延は数秒です
  （この分野のプロジェクトはどれもロングポーリングを行っていますが、このリポジトリのパラメーターと
  バックオフ戦略はそのままコピーして使えます）
- **連投メッセージの統合** — ユーザーが立て続けに複数のメッセージを送ると、
  iLink はそれらを複数のレスポンスに分割します。このリポジトリは **送信前の再確認** を行います。
  返信を作成した後、実際に送信する前にもう一度キューを確認し、新しいものがあれば
  統合して文脈に沿って答えます。連投 1 回につき返信は 1 回です。**調査した SDK でこれを行っているものはありません**。
  メッセージごとに返信する bot は機械的に感じられ、古い文脈に
  返信してしまいます
- **画像・ファイル・動画の送信** — `getuploadurl` → AES-128-ECB 暗号化 → CDN
  アップロード → メディアアイテム付きの `sendmessage`。画像、ファイル、動画に
  対応しており、返信モードとプロアクティブモードの両方で使えます。プロトコルには落とし穴
  （2 つの enum/エンコーディングの不一致）があり、コードコメントに記載しています
- **「入力中…」インジケーター** — 返信の作成中に点灯します
  （`getconfig` で `typing_ticket` を取得し、`sendtyping` で切り替えます。チケットは
  9 分間キャッシュされます）。これにより、ユーザーは bot が動いていることを確認できます
- **プロアクティブプッシュ** — ドキュメント化されていませんが、キャッシュした
  `context_token` を使った `sendmessage` でユーザーに先にメッセージを送れます
  （キャッシュしたトークンが古い場合は、トークンなしでのフォールバック再試行を行います）
- **再開可能なメディアダウンロード** — 画像やファイルは暗号化された CDN 経由で届きます。
  中断されたダウンロードは HTTP Range + 指数バックオフによる再試行で再開します
  （弱いネットワークでは、画像全体をやり直すと 90% のところで失敗することがよくあります）
- **重複送信なし** — 失敗した送信をむやみに再試行することはありません（サーバーは
  まれにメッセージを受け付けたのに受領確認を落とすことがあり、むやみに再試行すると
  ユーザーに 2 通届いてしまいます）
- **受信メッセージの重複排除** — サーバーはまれに同じメッセージを再配信します。
  poll は `message_id` でフィルタリングする（直近 500 件をディスクに永続化）ため、1 つのメッセージに
  2 回返信することはありません
- **Owner 許可リスト** — `owner.json` に記載された送信者だけが bot を
  起こせます（コードで強制。同じ人物の複数アカウントも可）。
  それ以外の人はポーリング時に破棄され、キューに入ることも
  エージェントを起こすこともありません。その id は手動レビュー用の承認キューに入ります。
  許可リストが設定されていない場合、デフォルトで全員が拒否されます
- **クローズドループのアラート** — 悪いニュース *も* 良いニュースも伝えます。トークンの期限切れは
  1 回報告された後、1 時間ごとに報告されます。ポーリングの失敗は 10 分間連続した場合にのみ
  アラートします（揺らぎで騒ぎ立てることはありません）。復旧は通知されます。10 分以上
  停止したワーカーはキューが回収され、フラグが立てられます
- **health セルフチェック** — `ilink.py health` は、ログイン経過時間、ライブのトークン
  プローブ、キューの滞留、最後のポーリングエラーを 1 つのコマンドで表示し、
  監視用に終了コード 0/1/2 を返します
- **トークン期限切れの通知は 1 回だけ** — 期限切れになるとマーカーファイルが書き込まれ、
  ユーザーには再スキャンをちょうど 1 回だけ依頼します
- **引用メッセージの復元** — WeChat でメッセージを引用して質問すると、
  bot は引用元（テキストまたはファイル）を参照できます。poll は
  サーバーの引用参照と、id から元メッセージへのローカルキャッシュ
  （30 日 / 1 万件、bot 自身のメッセージを含む）を保持します。キャッシュが存在する前の
  メッセージは後から復元できません。サーバーには
  id で取得するエンドポイントがないためです
- **購読制のアップデートリマインダー + 一言でインストール** —
  `version-check` は upstream の最新 Release を照会します。Owner は
  「订阅」と返信して購読し、通知は購読した Owner にのみ
  バージョンごとに 1 回届きます。「安装更新」と返信すると新しいリリースを
  バックグラウンドでインストールします（まずすべてを検証してから入れ替え、失敗時はロールバックし、
  状態ファイルには触れません）
- **死活監視ウォッチドッグ** — hook は実行のたびにハートビートを touch します。
  `ilink.py watchdog` は 30 分経過すると古いと判定し、15 分ごとの
  cron が最初の検出と復旧を報告します。繰り返しの古い状態は
  通知しません。ブリッジを意図的に停止している間は、メンテナンスフラグで通知を止められます
- **運用コマンド** — `rollback`（最新の .bak-* バックアップから
  復元）、`stats`（オフラインのスナップショット、サーバー呼び出しなし）、`preflight`
  （ログイン前の環境チェック）、`smoke-test`（エンドツーエンドのセルフチェック）、
  `prune-media`（メディアの保持期間クリーンアップ）、`rotate-chatlog`（月次の
  チャットログのアーカイブ）。下のチートシートを参照してください
- **人間らしい返信、磨き上げ済み** — 返信は人間がメッセージを打つように読めます。
  長い文は短い文に分け、結論を先に、その後に
  詳細を、テンプレート的な言い回しを使わず平易な言葉で書きます。自然に区切れる内容は
  2〜3 個の短い吹き出し（反応、本題、質問）として送り、1 つの文を複数の吹き出しに分けることはありません。
  感情が急に切り替わることはなく、間が空いた後も会話を自然に
  再開します。各返信は、トーン、長さ、言葉選び、構成、感情の率直さについて
  セルフチェックされます。複雑な技術的
  内容では長い文を保つこともあり、短文のデフォルトが正確さより
  優先されることはありません。`AGENTS.md` の配信に関する条項を参照してください

## 送信メッセージの Markdown レンダリング

bot が送るテキストメッセージは、WeChat クライアントによって Markdown として
レンダリングされます。事前にプレーンテキストへ変換する必要はありません（Android 版 WeChat クライアントで
3 回のライブテストにより確認済み、2026-10-25）。

レンダリングされるもの：複数レベルの見出し、太字、斜体（`*...*` と `_..._` の両方が
使え、`***...***` は太字斜体）、インラインコード、コードブロック（
言語ラベル、コピーボタン、シンタックスハイライト付き）、箇条書き /
番号付き / ネストしたリスト、リンク、表、取り消し線、引用、
水平線。

レンダリングされないもの：タスクリスト（`[ ]` / `[x]` がそのまま付いた箇条書きに
なります）、画像構文（alt テキストだけが残り、画像は表示されません。画像を送るには
`send-image` / `proactive-image` を使ってください）、数式（`$`
区切り文字が取り除かれ、内容は数式ではなくそのまま表示されます）。

斜体は中国語のテキストでは気づきにくいため、英語で確認しました。
上記の結果は Android 版 WeChat クライアントでのものです。他のクライアント /
バージョンでは異なる場合があります。

## 類似プロジェクトとの違い

GitHub にはすでに多くの iLink プロジェクトがあります。ライブラリとして使うことを想定した SDK
（[corespeed-io/wechatbot](https://github.com/corespeed-io/wechatbot)、
[epiral/weixin-bot](https://github.com/epiral/weixin-bot)）や、
WeChat をコーディングツールのリモコンにする Claude Code ブリッジ
（[crazynomad/weixin-claude-bot](https://github.com/crazynomad/weixin-claude-bot)）
などです。

このリポジトリが接続するのは **パーソナルアシスタントである Muse そのもの** です。長期記憶、目標、
リマインダーを持ち、自ら進んで報告してくるアシスタントであり、
コーディング CLI や素の LLM API ではありません。そのため焦点はライブラリ設計ではなく、**本物のアシスタントが
WeChat 上で暮らすときにぶつかる落とし穴** にあります。連投の統合、
重複送信の防止、1 回だけ通知するトークン期限切れ、そして再配信はあっても
メッセージを黙って失うことのない at-least-once キューです。自由に参考にしてください。

## アーキテクチャ

```
WeChat ──> iLink server ──getupdates long poll──> ilink.py poll
                                                       │ new messages to disk
                                                       ▼
                                               pending queue ──> assistant/worker
                                                       │ merge bursts, compose reply
                                                       ▼
                                               ilink.py send ──> WeChat
Proactive push: any program ──> ilink.py proactive (cached context_token) ──> WeChat
```

ポーリングドライバーは 2 つあります（hook ドライバーが本番グレードのもので、
`daemon.py` はサンプルドライバーです）。同時に動かせるのは 1 つだけで、
現在は共有ドライバーロック
（hook 状態ディレクトリ内の `ilink-driver.lock`）によって強制されています。最初のドライバーが勝ち、
後から来たものは静かに引き下がります。daemon は
hook のハートビートが新しい場合は起動を拒否し、ロックを取得できない hook の実行は
ポーリングもウェイクもせずに終了します。

| ドライバー | 最適な用途 | エントリーポイント |
| --- | --- | --- |
| スタンドアロン daemon（サンプル） | 任意のサーバー / VPS | `daemon.py` |
| Muse hook | Muse ランタイム（本番で使用） | `examples/muse-hook/` |

> 注：`daemon.py` は **サンプルドライバー** で、プロトコルと
> 最小限の実行可能なループを示すために書かれています。処理後にのみコミットするため、
> 連投の途中でクラッシュやハンドラーの例外が起きるとバッチが再配信されます
> （at-least-once、重複の可能性あり）。本番グレードの配信は
> 保証しません。本番グレードの配信（ディスク上の永続キュー、クラッシュ
> リカバリー、クローズドループのアラート）が必要な場合は、hook ドライバーを使ってください。

## クイックスタート

```bash
pip install -r requirements.txt

# 1. QR login (prints a QR image path; scan it with WeChat)
python3 ilink.py qrcode
python3 ilink.py login <qrcode-id>     # session saved to data/session.json

# 2. Bind the owner (required): open the 10-minute binding window, then
#    send the bot any message. The first sender becomes the Owner and
#    gets a four-part welcome confirming the binding (the fourth asks
#    about subscribing to release reminders); on BIND_TIMEOUT
#    just run the command again to reopen the window.
python3 ilink.py bind

# 3. Start long polling (--echo is a demo handler: parrots everything back)
python3 daemon.py --echo

# Now send the bot a couple of WeChat messages in a row —
# you'll get a single merged reply
```

LLM に返信を書かせたい場合（OpenAI 互換の任意の API：OpenAI、
DeepSeek、Qwen、Moonshot、ローカルの Ollama など）は、代わりに `--llm` モードを使います。
設定はすべて環境変数で行います。

```bash
LLM_API_KEY=sk-... python3 daemon.py --llm
# optional: LLM_BASE_URL (default https://api.openai.com/v1),
#           LLM_MODEL (default gpt-4o-mini), LLM_SYSTEM_PROMPT
```

`--llm` はサンプルハンドラーです。ユーザーごとに直近 10 件のメッセージを文脈として保持し、
標準ライブラリのみを使います。ツールと長期記憶を備えたエージェント構成については、
`examples/muse-hook/` を参照してください。

Docker でも動きます。このルートは主に **自分の
VPS / NAS でのセルフホスティング** 向けで、スタンドアロンの `daemon.py` をサーバー上で常時稼働させ、
Muse 環境から独立して動かします。（Muse 内でのデプロイは上記の
AGENTS.md のルートを使います。Docker は不要で、そもそも Muse のサンドボックスには通常
Docker がありません。）セッションとメディアは `./data` ボリュームに永続化されます。

```bash
docker compose run --rm bot python3 ilink.py qrcode        # QR login, once
docker compose run --rm bot python3 ilink.py login <qrcode-id>
docker compose run --rm bot python3 ilink.py bind          # message the bot within 10 min to bind the owner
docker compose up -d                                       # --echo by default
```

コマンドのチートシート：

```bash
python3 ilink.py bind                                   # bind the owner (10-min window, first sender wins)
python3 ilink.py poll                                   # fetch one round of new messages (JSON)
python3 ilink.py send <user_id> <context_token> -       # reply (body via stdin)
python3 ilink.py proactive <user_id> -                  # proactive push (body via stdin)
python3 ilink.py typing <user_id> <start|stop>          # show/cancel "typing…"
python3 ilink.py send-image <user_id> <ctx> <image>     # reply with an image
python3 ilink.py send-file <user_id> <ctx> <file>       # reply with a file
python3 ilink.py send-video <user_id> <ctx> <video>     # reply with a video
python3 ilink.py proactive-image <user_id> <image>      # proactively push an image
python3 ilink.py proactive-file <user_id> <file>        # proactively push a file
python3 ilink.py proactive-video <user_id> <video>      # proactively push a video
python3 ilink.py version-check [--notify]              # check upstream latest Release (--notify: subscribed owners only)
python3 ilink.py subscribe <owner_id>                  # opt in to update reminders
python3 ilink.py unsubscribe <owner_id>                # opt out of update reminders
python3 ilink.py update-to <tag> [--hook-dir <dir>]    # install a Release tag (two-phase, rolls back on failure)
python3 ilink.py rollback [--hook-dir <dir>]           # restore from the newest .bak-* backup
python3 ilink.py watchdog [--max-age-mins N]           # hook heartbeat watchdog (default 30 minutes)
python3 ilink.py stats                                 # offline snapshot (no server calls)
python3 ilink.py preflight                             # pre-login environment check
python3 ilink.py rotate-chatlog                        # archive past-month chatlog lines
python3 ilink.py prune-media [--dry-run]               # media retention cleanup (default 30 days + 500MB)
python3 ilink.py smoke-test [--no-send]                # end-to-end self-check
```

データディレクトリのデフォルトは `./data/` で、
`ILINK_DATA_DIR` 環境変数で上書きできます。

## 既知の制限事項（注意書きを先に）

- **音声メッセージの送信は動作しません（upstream の制限、公式対応待ち）**：
  bot は音声メッセージを *受信* できます（WeChat の文字起こし付き）が、
  *送信* したものは iLink チャネルによってサーバー側で黙って破棄されます。
  API は成功を返しますが、メッセージがクライアントに表示されることはありません。このプロジェクトと複数の
  独立した SDK で再現しています。これは Tencent のチャネルの制限であり、
  この実装の問題ではありません。Tencent の公式リポジトリで要望が出されています
  （Tencent/openclaw-weixin #91、#282）が、未実装のままです。完全な
  `send-voice` 実装（SILK パイプライン一式）がこのリポジトリに同梱されており、
  チャネルが許可した瞬間から動作し始めます。
  それまでの間も、音声はファイルまたは動画メッセージとして届けることができます。
- **ツール呼び出しの進捗メッセージは届きません（プロトコルでは定義されているが、
  チャネルが無視する）**：iLink プロトコルにはこれらが定義されています。
  メッセージタイプ 11（`tool_call_start_item`）と 12
  （`tool_call_result_item`）です。Tencent の公式プラグインは、モデルが
  ツールを呼び出すたびにこれを送信し（ツール名と completed/failed/blocked ステータスを含む
  開始メッセージと結果メッセージ）、WeChat 上で「ツール X を呼び出し中…」という
  進捗として表示されることを意図しています。テスト結果（2026 年 10 月）：
  公式の `reply-progress-sender.ts` が構築するのとまったく同じ形で送信し、
  エンベロープも公式の `send.ts` とフィールド単位で一致させました
  （message_type=2、message_state=2、run_id ありとなしの両方を試行）。
  サーバーは 2 回とも HTTP 200 を返しましたが、ボディは
  空で message_id もありませんでした。同じエンベロープでプレーンテキストを送ると
  通常どおり message_id が返りました。結論：サーバーはこのアイテムタイプに対して
  メッセージを作成しないため、クライアントには表示するものがありません。
  これはチャネルが受け付けていないのであって、クライアントが
  表示に失敗しているのではありません。音声の送信（API は成功を返すが、クライアントには
  表示されない）とは異なり、ツールの進捗はその 1 段階前で失敗します。メッセージが
  まったく作成されないのです。現時点で回避策はありません。ワーカーが作業中の間は、
  「入力中…」インジケーターが唯一の進捗シグナルです。
- **引用付きの送信は動作しません（チャネル側、テスト済み）**：bot は
  あなたが引用したメッセージを復元できます（ローカルの引用キャッシュ）が、
  自ら引用付きの返信を送ることはできません。テスト結果（2026 年 10 月 26 日）：
  受信側で見られる 2 つの形
  （ネストした `message_item.msg_id` とフラットな `msg_id`）の両方で sendmessage に `ref_msg` を追加しました。
  サーバーは 2 回とも message_id を返して配信しましたが、WeChat ではどちらも
  上に引用元のないプレーンなメッセージとして表示されました。3 つの独立した SDK の
  sendmessage 構造にも引用フィールドは存在しません。結論：
  送信メッセージのスキーマには引用という概念がそもそもなく、
  書式の問題ではありません。受信と送信は非対称です。受信時の完全な
  引用は引用元の msg_id だけを持ち（svr_id は svr_id しか持たない参照のための
  フォールバック検索にすぎません）、送信側には対応する
  フィールドがありません。そのため、このプロジェクトは引用付きの送信を実装しておらず、
  元のテキストをメッセージ本文に貼り付けて引用を装うこともしません。
- **セッションの有効期間は不確定です**：初期のコミュニティ報告では
  およそ 24 時間とされていましたが、本番環境ではここでの 1 回のログインが
  3 日以上有効なままでした（2026 年 10 月）。アカウントによって異なる可能性があります。期限切れになると、人間が
  QR コードを再スキャンする必要があります（このリポジトリが実装しているのは「1 回だけ通知」のみで、
  再スキャンは依然として手動です）。
- **bot が見られるのは bot 宛てのメッセージだけです**：iLink は別個の bot
  アイデンティティです。メインアカウントのメッセージ、連絡先、
  モーメンツを見ることはできません。公式プロトコルにはそのようなエンドポイントがそもそもありません。
  それ以外を謳うものは、リバースエンジニアリングされたプロトコルを使っています（アカウント凍結のリスクあり）。
- **送信元のネットワークは安定している必要があります**：国境をまたぐ回線では
  ロングポーリングの接続がときどき切断されます。クライアントはバックオフして
  再接続する必要があります（ここでは対応済みです。ログの `POLL_ERROR` 行はよくあるもので、
  無害です）。
- **アップデート：コードは自動アップグレードされますが、契約（AGENTS.md）はされません**：
  リリースリマインダーを購読すると、新しいリリースのたびに概要付きの WeChat
  通知が届き、「安装更新」と返信すると新しい
  ilink.py と hook スクリプトがバックグラウンドでインストールされます（まずすべてを検証し、
  次にすべてを入れ替え、失敗時はロールバックし、状態ファイルには決して
  触れません）。ただし、AGENTS.md は現在自動アップグレードできず、手動で
  変更する必要があります。リリースで契約が変更されるたびに、
  アップデーターは新しい AGENTS.md をデプロイ先ディレクトリの AGENTS.md.new に
  参考としてダウンロードし、アップデート後のメッセージでそのことを
  明示します。インストールされるのはリリースタグだけで、main の最新コードや
  任意の URL からインストールされることはありません。
- **チャット内のスラッシュコマンド：未実装**：Telegram と違い、WeChat は
  `/` を入力してもコマンドメニューを表示しません。スラッシュコマンドは
  発見の入り口がない単なるプレーンテキストにすぎません。bot は LLM なので、
  自然言語ですでに同じ意図をカバーできます（「調子はどう？」、
  「さっき言ったことは忘れて」）。正確に実行しなければならない操作
  （購読/購読解除/アップデートのインストール）は、スラッシュの代わりに
  キーワードの完全一致を使います。

## インシデントログ：bot が「--key」を送った夜

2026 年 10 月 27 日 00:11、オーナーは寝る前に bot におやすみを言いました
（「a 醇我涂完了，我要睡觉了，晚安」— 夜のケアが終わったので、もう寝ます）。
bot は「涂完就好，晚安，好好睡」（よくできました、
おやすみなさい、ぐっすり眠ってね）と返信するつもりでした。実際に届いたのはこれです。

  <img src="docs/key-incident.jpg" alt="オーナーのおやすみに対して bot が「--key」と返信したスクリーンショット" width="300">

何が起きたか：ワーカーが送信コマンドを組み立てる際に `-` のテキストプレースホルダーを
落としたため、重複排除フラグ `--key` がテキストの位置に入り込みました。
そして、テキストについて何も検証していなかったブリッジは、
それをそのまま送信しました。その後に追加されたガード：send/proactive は
API を呼び出す前にテキストを検証するようになり、空のテキストや
`--` で始まるテキストは即座に拒否され、拒否されたことだけがログに記録されます。不正な形式の
呼び出しは、フラグをメッセージとして届けるのではなく、はっきりと失敗するようになりました。

## セキュリティに関する注意

`data/session.json` は **ログイン認証情報** であり、パスワードと同等です。
ローカルに保管してください。すでに `.gitignore` に入っていますが、**決してコミットしたり共有したりしないでください**。
チャットログと連絡先キャッシュも同様です。

**Owner 許可リスト（コードで強制）**：`data/owner.json` の `owner_ids`
が、bot を起こせる唯一の送信者の集合です（同じ人物の複数アカウントも
可。`owner_id` がプライマリーです）。それ以外の人のメッセージは
ポーリング時に破棄されます。キューに入ることも、エージェントを起こすことも、
連絡先キャッシュに書き込まれることも、メディアがダウンロードされることもありません。送信者の id は
手動承認のために `data/unknown_senders.json` に記録されるだけです。
`owner.json` がまったくない場合は **全員が拒否されます**。まずクイック
スタートのステップ 2（`bind`）を完了してください。紐付けウィンドウはセットアップ時の
10 分間だけのものです。無人のまま開けっ放しにしないでください。

## 謝辞

人間らしい返信の磨き上げは、以下のプロジェクトからアイデアを借りています（コードは借りていません）。
誤ってコピーだと思われないよう、*取り入れなかった* 部分も記載しています。

- [ElmerAlan-an/human_chat_operit](https://github.com/ElmerAlan-an/human_chat_operit) — 短い口語的な文、返信のセルフチェックリスト、繰り返しの防止。スラッシュコマンドの仕組みとペルソナのロールプレイは採用していません
- [oaa529/zhichi](https://github.com/oaa529/zhichi) — リアリズムエンジンのメッセージ分割、入力のリズム、感情の連続性。意図的なタイプミスや言い直しは採用していません
- [huihuihenqiang/WeClone-llm](https://github.com/huihuihenqiang/WeClone-llm) — 1 文ずつの返信。句読点で機械的に分割する方式（句読点を取り除いてしまう）は採用していません
- [Napus-BackendDev/GenieAi-ChatBOT](https://github.com/napus-backenddev/genieai-chatbot/blob/HEAD/CLAUDE.md) — ディスパッチャーにおける区切り文字ベースの吹き出し分割と、長さに応じた間。間の段階はまだ実装しておらず、参考のみです
- [freestylefly/openclaw-wechat](https://deepwiki.com/freestylefly/openclaw-wechat/4.5-reply-dispatcher) — Reply Dispatcher のチャンク分割と配信タイミング
- [molang163/chinese-natural-reply](https://github.com/molang163/chinese-natural-reply) — 結論を先に、平易な言葉で、防御的な予防線を張らない
- [speak-human-tw](https://www.typingmind.com/skills/raymondhou0917-speak-human-tw) — まず事実、次に言い回しから AI っぽさを取り除き、最後に人間らしい味付けを加える
- [Treasure-hub-agent/ai-with-u](https://github.com/Treasure-hub-agent/ai-with-u) — 時間の空白の認識：一晩や数日空いた後も自然に再開する
- [kroxchan/xinyi](https://github.com/kroxchan/xinyi) — 感情ステートマシン（感情が急に切り替わらない、ネガティブなトーンはゆっくり薄れる、段階的に移行する）と 5 つの観点による本物らしさのセルフチェック。特定の人物を学習する / チャット履歴を復号するアプローチは採用していません

プロトコル自体は Tencent 公式の iLink / openclaw-weixin
エコシステムに由来します。WeChat の復号、デスクトップの自動化、チャット履歴による
ファインチューニングでのクローン作成は、いずれも意図的に使用していません。

## ライセンス

MIT
