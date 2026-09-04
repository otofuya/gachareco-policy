# ガチャれこ — プライバシーポリシー

アプリ「ガチャれこ」のプライバシーポリシーを GitHub Pages で公開するためのリポジトリです。

Google Play / App Store はどちらもプライバシーポリシーの URL 提出を必須としており、
その掲載先としてこのページを使います。

## 公開手順

1. GitHub でこの内容を **public** リポジトリ（例: `gachareco-policy`）として push する
2. リポジトリの **Settings → Pages** を開く
3. **Source** を `Deploy from a branch`、Branch を `main` / `/ (root)` に設定して保存
4. 数分後 `https://<GitHubユーザー名>.github.io/gachareco-policy/` で公開される

## 公開後にやること

公開 URL が確定したら、以下 2 か所を差し替える。

| 差し替え先 | 内容 |
|---|---|
| `mobileapp/lib/config/app_links.dart` | `privacyPolicy` を公開 URL に、`supportEmail` を実際の連絡先に |
| `policy/index.html` | `CONTACT_EMAIL_PLACEHOLDER` を実際の連絡先メールアドレスに |

さらに Play Console と App Store Connect の「プライバシーポリシー URL」欄にも同じ URL を入力する。
