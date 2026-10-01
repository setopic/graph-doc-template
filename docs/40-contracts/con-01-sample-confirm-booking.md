---
id: CON-01
type: contract
title: 予約確定エンドポイント
status: draft
tags: [sample]
depends_on:
  - UC-01
  - DOM-01
related: []
---

# 予約確定エンドポイント

> これはサンプルノードである。実際のプロジェクトでは差し替えること。

## エンドポイント

```
POST /bookings/{bookingId}/confirm
```

対応するユースケース: [UC-01](../30-usecases/uc-01-sample-confirm-booking.md)

## リクエスト

| フィールド | 型 | 必須 | 説明 | 由来（ドメイン） |
| --- | --- | --- | --- | --- |
| bookingId | string (path) | ○ | 対象の予約 | [DOM-01](../20-domain/dom-01-sample-booking.md) id |

bodyは無い。

## レスポンス（成功）

`200 OK`

| フィールド | 型 | 説明 |
| --- | --- | --- |
| id | string | 予約の識別子 |
| status | string | 常に `confirmed` |
| resourceId | string | 確保された資源 |
| startAt | string (ISO 8601) | 開始時刻 |
| endAt | string (ISO 8601) | 終了時刻 |

```json
{
  "id": "bkg_01H...",
  "status": "confirmed",
  "resourceId": "res_01H...",
  "startAt": "2026-09-01T10:00:00+09:00",
  "endAt": "2026-09-01T11:00:00+09:00"
}
```

## エラー

| コード | 条件 | body | 対応する例外フロー |
| --- | --- | --- | --- |
| 404 | 予約が存在しない | `{"code": "BOOKING_NOT_FOUND"}` | E3 |
| 409 | 時間帯が重なる確定予約がある | `{"code": "SLOT_TAKEN", "conflictingBookingId": "..."}` | E1 |
| 409 | 保持期限切れ | `{"code": "HOLD_EXPIRED"}` | E2 |

## 冪等性・整合性

すでに`confirmed`になっている予約に再び要求が来たら、`200`を返す（UC-01のA1）。

重なりの確認と状態の更新は、同じトランザクションで行う。
アプリケーション側の事前チェックだけに頼らず、資源と時間帯の組に排他制約を張る。

## 変更するときの影響

**呼ぶ側は別々に配置されるので、片方だけが古いまま動く。** 次の3つは、
互換性を失う変更にあたる。

| 変えるもの | 何が起きるか |
| --- | --- |
| エラーの`code`の綴り | 呼ぶ側は文字列で分岐しているので、気づかないうちにどの分岐にも当たらなくなる |
| `status`に新しい値を足す | 既存の値の意味を変えずに足す。値を増やすこと自体は互換性を失わない |
| パスの`bookingId`の形式 | 発行済みのURLに含まれているので、過去のリンクが解決できなくなる |

エラーを増やすことは、互換性を失う変更ではない。知らない`code`を受け取った側は、
未知の失敗として扱えばよい。増やす前に、UC-01に対応する例外フローを足す。

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

`depends_on`: この文書が成立するために前提となるノード

- [DOM-01 予約](../20-domain/dom-01-sample-booking.md)
- [UC-01 予約を確定する](../30-usecases/uc-01-sample-confirm-booking.md)

<!-- graph:auto:end -->
