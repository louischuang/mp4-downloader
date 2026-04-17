# YouTube to MP4 Downloader

これはローカル環境または Docker 上で動作する YouTube ダウンロードツールで、以下をサポートします。

- Docker デプロイ
- MP4 の永続保存
- 画質選択
- リアルタイム進捗表示
- 繁体字中国語、簡体字中国語、英語、日本語 UI

> 保存権限のあるコンテンツのみをダウンロードし、YouTube の利用規約と著作権ルールを守ってください。

## プレビュー

![App preview](assets/app-preview.svg)

## 主な機能

- YouTube の `watch`、`youtu.be`、`shorts`、`embed` URL に対応
- `最良の画質`、`1080p`、`720p`、`360p` を選択可能
- ダウンロード中に進捗バーと状態テキストを表示
- `ffmpeg` が利用可能な場合は MP4 に結合して出力
- 右上のボタン列から UI 言語を切り替え可能
- ダウンロード動画をコンテナ外に永続保存可能
- ログイン確認や bot 判定対策のために YouTube cookies を利用可能

## 技術構成

- Python `Flask`
- `yt-dlp`
- `ffmpeg`
- YouTube JavaScript runtime 解析用の `nodejs`
- Docker / Docker Compose

## Docker ですぐに起動

このプロジェクトには以下が含まれています。

- `Dockerfile`
- `docker-compose.yml`
- 永続ストレージ設定
- cookies マウント設定

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

## MP4 の永続保存

ダウンロードされた MP4 は次の bind mount を通してホスト側に保存されます。

```yaml
volumes:
  - ./video-storage:/data/downloads
```

これにより：

- コンテナ再起動後も動画が残る
- コンテナ再構築後も動画が残る
- 動画がコンテナ内部だけに閉じない

別のホストパスを使いたい場合は、たとえば次のように変更できます。

```yaml
volumes:
  - /Users/yourname/Movies/youtube-downloads:/data/downloads
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
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── static/
├── templates/
├── assets/
├── cookies/
└── video-storage/
```

## 使い方

1. ブラウザでアプリを開きます。
2. YouTube 動画 URL を貼り付けます。
3. 希望する画質を選択します。
4. ダウンロードボタンを押します。
5. 画面上で進捗と状態を確認します。
6. 完了後、結果パネルから MP4 をダウンロードします。

## 補足

- `ffmpeg` がない場合は、直接取得できる形式にフォールバックします。
- `ffmpeg` がある場合は、分離された音声と映像を MP4 に結合できます。
- 動画によっては、アカウント、地域、年齢制限、または bot 判定のために有効な cookies が必要になることがあります。

## ライセンス

このプロジェクトは MIT License で提供されています。詳細は [LICENSE](LICENSE) を参照してください。
