---
id: API-01
type: api
title: 予約確定エンドポイント
status: draft
tags: [sample]
depends_on:
  - UC-01
  - DOM-01
related: []
---

# 予約確定エンドポイント

> **サンプルノード。** 実プロジェクトでは差し替えること。

## エンドポイント

```
POST /bookings/{bookingId}/confirm
```

対応するユースケース: [[UC-01]]

## リクエスト

| フィールド | 型 | 必須 | 説明 | 由来（ドメイン） |
| --- | --- | --- | --- | --- |
| bookingId | string (path) | ○ | 対象の予約 | [[DOM-01]] id |

body なし。

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

- すでに `confirmed` の予約への再要求は `200` を返す（UC-01 の A1）
- 重なりの確認と状態更新は同一トランザクションで行う。
  アプリケーション側の事前チェックだけに頼らず、資源 × 時間帯に排他制約を張る

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

**depends_on** — この文書が成立するために前提となるノード

- [DOM-01 予約](../20-domain/dom-01-booking.md)
- [UC-01 予約を確定する](../30-usecases/uc-01-confirm-booking.md)

<!-- graph:auto:end -->
