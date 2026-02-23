# 1. 基本設計

## 1.1 スコープ（現状できていること）

現状の「注文処理」は、受注〜検証〜価格計算（合計）〜確定（永続化）〜通知（イベント発行）までを、同期的なユースケースとして実装しています。

* 受注：`PlaceOrderCommand` を受け取る（CLI/HTTP）
* 検証：必須項目・数量・単価のチェック
* 価格計算：`Money` と `LineItem.subtotal()` の合計
* 確定：`OrderRepository.save(order)`
* 通知：`EventPublisher.publish(OrderPlaced)`
* 参照：`GET /orders/{id}`（詳細）
* 一覧：`GET /orders`（offset/limit + customer_idフィルタ + created_at/total ソート）

> 「発送/請求」は **現状は未実装**で、通知（イベント発行）までが最終段です。発送/請求は `OrderPlaced` を契機に別ユースケースとして追加するのが自然です（拡張ポイント参照）。

---

## 1.2 アーキテクチャ（Clean / Ports & Adapters）

指定の構造に沿って、依存方向を内側（core）に固定しています。

```
adapters/
  inbound/    … CLI / FastAPI（HTTP）
  outbound/   … 在庫/決済/注文DB/イベント発行（現状は in-memory & ダミー）

core/         … application 相当
  domain/
    model/    … Entity/VO + ドメインエラー
    service/  … ユースケース実装（returnsで合成）
  ports/
    inbound/  … UseCase interface + Command/Query/DTO
    outbound/ … Gateway/Repository interface
```

* **core は frameworks（FastAPI等）に依存しない**
* I/O 境界は **ports**（受信/送信ポート）
* 技術詳細は **adapters**（入出力の変換・例外変換・永続化/外部呼び出し）

---

## 1.3 「returns」による制御フロー

ユースケース実装は `returns` の `Result` を主軸にした **関数合成**で構成されています。

* 成功：`Success(value)`
* 失敗：`Failure(error)`
* 合成：`flow(..., bind(...), map_(...))`

これにより「途中で失敗したら以降の処理が自動的にスキップ」され、例外よりも **制御フローが明示**になります。

---

# 2. 注文処理の基本フロー（受注→確定→通知）

## 2.1 PlaceOrder（受注〜確定〜通知）

入口は CLI / HTTP ですが、どちらも最終的に **同一の受信ポート**へ入ります。

**処理順序（同期）**

1. 入力検証（必須・数量>0・単価>0）
2. Order 生成（`OrderId.new()` / `created_at=now_utc()`）
3. 在庫引当（`InventoryGateway.reserve(reservations)`）
4. 決済（`PaymentGateway.charge(ChargeRequest)`）
5. 永続化（`OrderRepository.save(order)`）
6. イベント通知（`EventPublisher.publish(OrderPlaced(order_id))`）
7. レシート返却（`OrderReceipt`）

**成否**

* 途中で Failure が出たら、以降は実行されず、その error が最終結果になります。

> 重要：現状は「部分成功の補償（Saga/在庫戻し）」は **実装していません**。例えば決済失敗後の在庫戻しは未対応です（拡張ポイントに記載）。

---

# 3. 詳細設計（モジュール別）

## 3.1 domain model（`core/domain/model`）

### `Order` / `LineItem` / `Money`

* `Order`

  * `order_id: OrderId(UUID)`
  * `customer_id: CustomerId(str)`
  * `items: tuple[LineItem, ...]`
  * `created_at: datetime (UTC)`
  * `total(): Money`（items の subtotal 合計）

* `LineItem`

  * `sku: Sku(str)`
  * `unit_price: Money`
  * `quantity: int`
  * `subtotal(): Money = unit_price * quantity`

* `Money`

  * `amount: Decimal`（小数2桁に正規化）
  * `currency: str = "JPY"`
  * `+` と `*` を提供（通貨不一致は例外）

### ドメインエラー（`errors.py`）

* `ValidationError`（400）
* `OutOfStock`（409）
* `PaymentDeclined`（402）
* `PersistenceError`（500）
* `OrderNotFound`（404）
* `PublishError`（503）

---

## 3.2 inbound ports（`core/ports/inbound`）

### PlaceOrder

* `PlaceOrderCommand`

  * `customer_id: str`
  * `payment_token: str`
  * `lines: Sequence[PlaceOrderLine(sku, unit_price, quantity)]`
* `PlaceOrderUseCase.place_order(command) -> Result[OrderReceipt, PlaceOrderError]`

### GetOrder

* `GetOrderQuery(order_id: str(UUID文字列))`
* `GetOrderUseCase.get_order(query) -> Result[OrderView, PlaceOrderError]`

### ListOrders

* `ListOrdersQuery`

  * `offset: int (>=0)`
  * `limit: int (1..100)`
  * `customer_id: Optional[str]`（フィルタ）
  * `sort_by: "created_at" | "total"`
  * `sort_dir: "asc" | "desc"`
* `ListOrdersUseCase.list_orders(query) -> Result[Sequence[OrderSummaryView], PlaceOrderError]`

---

## 3.3 outbound ports（`core/ports/outbound`）

* `InventoryGateway.reserve(reservations) -> Result[None, PlaceOrderError]`
* `PaymentGateway.charge(request) -> Result[None, PlaceOrderError]`
* `OrderRepository`

  * `save(order) -> Result[OrderId, PlaceOrderError]`
  * `get(order_id) -> Result[Order, PlaceOrderError]`
  * `list(offset, limit, customer_id?, sort_by, sort_dir) -> Result[Sequence[Order], PlaceOrderError]`
* `EventPublisher.publish(OrderPlaced) -> Result[None, PlaceOrderError]`

---

## 3.4 domain service（`core/domain/service`）

### `PlaceOrderService`

`returns.pipeline.flow` で以下を直列合成：

1. `_validate_command`

   * `customer_id` 空チェック
   * `payment_token` 空チェック
   * `lines` 非空チェック
   * 各行：sku非空、quantity>0、unit_price>0

2. `_build_context`

   * `Order` を生成（`created_at=now_utc()`）
   * `PlaceOrderContext(order, payment_token)` を作る（tokenをドメインモデルに混ぜない）

3. `_reserve_inventory`

4. `_charge_payment`

5. `_persist`

6. `_publish`

7. `_to_receipt`（戻り値 DTO）

### `GetOrderService`

* `order_id` を UUID にパースできない → `ValidationError`
* `OrderRepository.get` → `OrderView` に map

### `ListOrdersService`

* offset/limit/customer_id/sort_by/sort_dir を検証
* `OrderRepository.list(...)` を呼び、`OrderSummaryView` に map

---

# 4. adapters 設計

## 4.1 inbound adapters

### CLI（`adapters/inbound/cli.py`）

* JSON文字列をパースして `PlaceOrderCommand` を構築
* UseCase 実行
* `Success` → 標準出力に receipt
* `Failure` → 標準出力に error

### FastAPI（`adapters/inbound/web/fastapi_app.py`）

* 受信：HTTP JSON → core の Command/Query に変換
* 応答：core の View/Receipt → HTTPレスポンス DTO に変換
* **例外ハンドラで統一エラー応答**

  * `PlaceOrderError` を HTTP ステータスへマッピング
  * `RequestValidationError`（Pydantic）も 400 に統一
  * 予期せぬ例外は 500

**HTTP API**

* `GET /health` → 200
* `POST /orders` → 201 + `Location: /orders/{id}`
* `GET /orders/{order_id}` → 200 / 400 / 404
* `GET /orders` → 200 / 400

  * params: `offset, limit, customer_id, sort_by, sort_dir`

---

## 4.2 outbound adapters

* `InMemoryInventory`：在庫数を dict 管理、足りなければ `OutOfStock`
* `DummyPaymentGateway`：tokenブラックリスト or 金額上限で `PaymentDeclined`
* `InMemoryOrderRepository`：

  * `save`：重複IDは `PersistenceError`
  * `get`：無ければ `OrderNotFound`
  * `list`：customer_id フィルタ → sort → slice

    * `sort_by=created_at`：`order.created_at`
    * `sort_by=total`：`order.total().amount`（※計算コストあり）
* `StdoutEventPublisher`：標準出力にイベント、fail時 `PublishError`

---

# 5. 仕様（一覧検索・ソート・フィルタ）

## 5.1 ページング

* `offset`/`limit`（`limit` は max 100）

## 5.2 フィルタ

* `customer_id` が指定された場合のみ絞り込み（空文字は ValidationError）

## 5.3 ソート

* `sort_by=created_at|total`
* `sort_dir=asc|desc`

---

# 6. 現状設計の前提と制約（重要）

現状のコードは「分割・境界・入出力の整流」が主目的で、注文処理としては次が **未対応**です。

* **冪等性**：`POST /orders` の重複送信で二重作成の可能性
* **補償（Saga）**：在庫確保後に決済失敗した場合の在庫戻し
* **Transactional Outbox**：DB更新とイベント発行の二重書き込み問題
* **状態遷移（OrderStatus）**：確定/支払済/出荷済/請求済などのステートモデル

> 逆に言うと、これらは **ports/outbound を増やし、domain/service を追加**するだけで自然に拡張できます（いまの構造の強み）。

---

# 7. 拡張ポイント（次に入れると“注文処理らしさ”が完成）

優先度順でおすすめはこれです 🚀

1. **Idempotency**（`POST /orders`）

   * `Idempotency-Key` ヘッダ + `OrderRepository` で重複排除

2. **Saga（補償）**

   * 決済失敗時に `InventoryGateway.release(...)` を追加して補償

3. **Transactional Outbox + Relay**

   * `OrderRepository.save` と `OutboxRepository.add` を同一TXへ

4. **発送/請求の別ユースケース**

   * `ShipOrderUseCase`, `CreateInvoiceUseCase` 等を追加
   * `OrderPlaced` をトリガにする（境界は ports/outbound）
