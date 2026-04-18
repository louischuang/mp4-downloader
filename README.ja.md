# YouTube to MP4 Downloader

これはローカル環境または Docker 上で動作する YouTube ダウンロードと音声文字起こしツールです。

- Docker デプロイ
- MP4 と字幕の永続保存
- `faster-whisper` による文字起こし
- 画質選択
- ダウンロードと文字起こしのリアルタイム進捗表示
- 繁体字中国語、簡体字中国語、英語、日本語 UI
- HTTP API、Swagger、CLI、E2E テストスクリプト

> 保存権限のあるコンテンツのみをダウンロードし、YouTube の利用規約と著作権ルールを守ってください。

## プレビュー

![App preview](assets/app-preview.svg)

## 主な機能

- YouTube の `watch`、`youtu.be`、`shorts`、`embed` URL に対応
- `最良の画質`、`1080p`、`720p`、`360p` を選択可能
- `ダウンロード` または `ダウンロードして文字起こし` を実行可能
- `YouTube ダウンロード` と `MP4 をアップロード` のタブを切り替え可能
- ローカル MP4 を任意タイトル付きでアップロード可能
- アップロード完了後に自動で文字起こしを開始
- ダウンロード中と文字起こし中に進捗と状態を表示
- ローカル MP4 の再生、元の YouTube ページを開く、生成ファイルのダウンロードに対応
- `txt`、`srt`、`vtt`、`json` の文字起こし出力を生成
- 生成された `srt` 字幕をブラウザ上で直接編集可能
- 動画一覧のツールバーから字幕焼き込み済みの新しい MP4 を生成可能
- 焼き込み字幕のフォント、サイズ、文字色、縁取り、行間、マージン、半透明背景を細かく調整可能
- `ffmpeg` が利用可能な場合は MP4 に結合して出力
- 右上のボタン列から UI 言語を切り替え可能
- ダウンロード動画、字幕、モデルキャッシュをコンテナ外に永続保存可能
- ログイン確認や bot 判定対策のために YouTube cookies を利用可能
- 他プラットフォームや AI Agent 向けの HTTP API を提供
- Swagger UI と OpenAPI JSON を提供
- `python3 cli.py` による CLI を提供
- `python3 scripts/e2e_api_test.py` による E2E テストスクリプトを提供

## 技術構成

- Python `Flask`
- `yt-dlp`
- `faster-whisper`
- `ffmpeg`
- YouTube JavaScript runtime 解析用の `nodejs`
- Docker / Docker Compose

## Docker ですぐに起動

このプロジェクトには以下が含まれています。

- `Dockerfile`
- `docker-compose.yml`
- 永続ストレージ設定
- cookies マウント設定
- STT 用の独立サービスコンテナ

起動方法：

```bash
docker-compose up --build -d
```

新しい Compose plugin を使っている場合：

```bash
docker compose up --build -d
```

起動後に以下を開いてください。

```text
http://127.0.0.1:5001
```

Swagger UI：

```text
http://127.0.0.1:5001/api/docs
```

## 永続保存

ダウンロードされた MP4、文字起こし結果、モデルキャッシュは次の bind mount を通してホスト側に保存されます。

```yaml
volumes:
  - ./video-storage:/data/downloads
  - ./transcripts:/data/output
  - ./models:/models/huggingface
```

これにより：

- コンテナ再起動後も動画が残る
- コンテナ再構築後も動画が残る
- 動画、字幕、モデルがコンテナ内部だけに閉じない

別のホストパスを使いたい場合は、たとえば次のように変更できます。

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
```

文字起こし出力の既定値：

```text
./transcripts
```

Whisper モデルキャッシュの既定値：

```text
./models
```

## YouTube Cookies 設定

YouTube で `Sign in to confirm you're not a bot` のようなメッセージが出る場合は、Netscape 形式の cookies をエクスポートして次に配置してください。

```text
./cookies/youtube.txt
```

Docker では以下にマウントされます。

```text
/data/cookies/youtube.txt
```

補足：

- compose は cookies ディレクトリを読み取り専用でマウントします
- アプリは `yt-dlp` 実行前に cookies を書き込み可能な一時領域へコピーします
- コンテナでは `YTDLP_REMOTE_COMPONENTS=ejs:github` も有効です

## Agent API と Swagger

このプロジェクトは他プラットフォームや AI Agent 向けの API を提供します。

- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/v1/downloads`
- `POST /api/v1/uploads`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/videos`
- `POST /api/v1/transcriptions`
- `GET /api/v1/transcriptions/{job_id}`
- `POST /api/v1/burned-videos`
- `GET /api/v1/subtitles/{filename}`
- `PUT /api/v1/subtitles/{filename}`

`POST /api/v1/burned-videos` には `style` オブジェクトを渡せて、字幕の文字設定を細かく指定できます。

- `size`、`font_family`
- `text_color`、`outline_color`、`outline_width`
- `position`、`line_spacing`
- `margin_v`、`margin_l`、`margin_r`
- `shadow`
- `background`、`background_color`、`background_opacity`、`background_size`、`background_radius`
- `max_chars_per_line`

関連ドキュメント：

- Swagger UI：`/api/docs`
- OpenAPI JSON：`/api/openapi.json`
- 詳細ガイド：[docs/AGENT_API.md](docs/AGENT_API.md)
- ツール利用ガイド：[docs/TOOL_USAGE.md](docs/TOOL_USAGE.md)
- CLI ガイド：[docs/CLI_GUIDE.md](docs/CLI_GUIDE.md)

## CLI

例：

```bash
python3 cli.py health
python3 cli.py capabilities --json
python3 cli.py videos --json
python3 cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --wait --json
python3 cli.py transcribe "example-video.mp4" --wait --json
python3 cli.py burn "example-video.mp4" --wait --size plus_20 --font-family sans --text-color "#ffffff" --outline-color "#000000" --background --background-color "#000000" --background-opacity 48 --background-size 24 --background-radius 18
```

## E2E テストスクリプト

API フロー全体を検証：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM"
```

概要だけ表示：

```bash
python3 scripts/e2e_api_test.py --base-url http://127.0.0.1:5000 --url "https://www.youtube.com/watch?v=89bhDV0FBSM" --summary-only
```

## ローカル開発

Docker を使わずに実行したい場合：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

その後、以下を開きます。

```text
http://127.0.0.1:5000
```

macOS で MP4 結合をより安定させたい場合：

```bash
brew install ffmpeg
```

## プロジェクト構成

```text
.
├── app.py
├── cli.py
├── Dockerfile
├── docker-compose.yml
├── docs/
├── docker/
│   └── stt/
├── requirements.txt
├── scripts/
├── static/
├── templates/
├── assets/
├── cookies/
├── video-storage/
├── transcripts/
└── models/
```

## 使い方

1. ブラウザでアプリを開きます。
2. `YouTube ダウンロード` または `MP4 をアップロード` を選びます。
3. YouTube モードでは動画 URL を貼り付け、画質を選択します。
4. アップロードモードではローカル MP4 を選び、動画タイトルを入力します。
5. 現在のモードのメインボタンを押します。
6. 画面上でダウンロードまたは文字起こしの進捗を確認します。
7. 文字起こしを有効にした場合、または MP4 アップロードを使った場合は、完了後に STT が自動で始まります。
8. 動画一覧から動画再生、元 URL を開く、MP4 ダウンロード、`txt` / `srt` / `vtt` / `json` の取得ができます。
9. 字幕を修正したい場合は `字幕を編集` から `srt` を開いて保存できます。
10. 字幕保存後は `字幕焼き込み MP4` を使って新しい MP4 を生成できます。

## 補足

- `ffmpeg` がない場合は、直接取得できる形式にフォールバックします。
- `ffmpeg` がある場合は、分離された音声と映像を MP4 に結合できます。
- 字幕焼き込み MP4 の生成にも `ffmpeg` が必要です。
- 初回の `faster-whisper` 実行時は `./models` にモデルをダウンロードし、その後はキャッシュを再利用します。
- 動画によっては、アカウント、地域、年齢制限、または bot 判定のために有効な cookies が必要になることがあります。

## ライセンス

このプロジェクトは MIT License で提供されています。詳細は [LICENSE](LICENSE) を参照してください。
