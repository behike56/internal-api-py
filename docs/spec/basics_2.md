了解です。ここでは **(1) 実装**（追加・変更したファイルの“完全なコード”）を先に提示し、その後に **(2) 設計書（基本設計→詳細設計）** をまとめます。✅

> 前提：あなたの「現在のコード」（`order_service_current.zip` 相当）に対して、**POST /orders の冪等化**を追加します。
> 冪等キーは HTTP ヘッダ `Idempotency-Key` を使用し、キーは **(customer_id, key)** でスコープします。

---

# 1) 実装

## 1.1 追加するファイル

### `src/order_service/core/domain/model/idempotency.py`（新規）

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from order_service.core.domain.model.order import OrderId


IdempotencyStatus = Literal["IN_PROGRESS", "COMPLETED", "FAILED"]


@dataclass(frozen=True)
class IdempotencyRecord:
    status: IdempotencyStatus
    order_id: OrderId
    previous_error: Optional[str] = None
```

### `src/order_service/core/ports/outbound/idempotency.py`（新規）

```python
from __future__ import annotations

from typing import Protocol

from returns.result import Result

from order_service.core.domain.model.errors import PlaceOrderError
from order_service.core.domain.model.idempotency import IdempotencyRecord
from order_service.core.domain.model.order import CustomerId, OrderId


class IdempotencyRepository(Protocol):
    """
    実DBでは (customer_id, key) に UNIQUE 制約を貼り、
    start/complete/fail はトランザクション内で行うのが前提。
    """

    def get(self, customer_id: CustomerId, key: str) -> Result[IdempotencyRecord | None, PlaceOrderError]:
        ...

    def start(self, customer_id: CustomerId, key: str, order_id: OrderId) -> Result[None, PlaceOrderError]:
        """キーが未登録なら IN_PROGRESS を登録（原子的であることが望ましい）。"""
        ...

    def complete(self, customer_id: CustomerId, key: str) -> Result[None, PlaceOrderError]:
        ...

    def fail(self, customer_id: CustomerId, key: str, previous_error: str) -> Result[None, PlaceOrderError]:
        ...
```

### `src/order_service/adapters/outbound/in_memory_idempotency.py`（新規）

```python
from __future__ import annotations

from dataclasses import dataclass, field

from returns.result import Result, Success

from order_service.core.domain.model.idempotency import IdempotencyRecord
from order_service.core.domain.model.order import CustomerId, OrderId
from order_service.core.ports.outbound.idempotency import IdempotencyRepository


@dataclass
class InMemoryIdempotencyRepository(IdempotencyRepository):
    """
    key is (customer_id, idempotency_key)
    実運用では DB の UNIQUE 制約で競合を潰す。
    """
    _store: dict[tuple[str, str], IdempotencyRecord] = field(default_factory=dict)

    def get(self, customer_id: CustomerId, key: str) -> Result[IdempotencyRecord | None, Exception]:
        return Success(self._store.get((customer_id.value, key)))

    def start(self, customer_id: CustomerId, key: str, order_id: OrderId) -> Result[None, Exception]:
        k = (customer_id.value, key)
        self._store.setdefault(k, IdempotencyRecord(status="IN_PROGRESS", order_id=order_id))
        return Success(None)

    def complete(self, customer_id: CustomerId, key: str) -> Result[None, Exception]:
        k = (customer_id.value, key)
        rec = self._store.get(k)
        if rec is not None:
            self._store[k] = IdempotencyRecord(status="COMPLETED", order_id=rec.order_id, previous_error=rec.previous_error)
        return Success(None)

    def fail(self, customer_id: CustomerId, key: str, previous_error: str) -> Result[None, Exception]:
        k = (customer_id.value, key)
        rec = self._store.get(k)
        if rec is not None:
            self._store[k] = IdempotencyRecord(status="FAILED", order_id=rec.order_id, previous_error=previous_error)
        return Success(None)
```

---

## 1.2 変更するファイル

### `src/order_service/core/domain/model/errors.py`（追記）

既存エラーに **Idempotency 用の2つ**を追加します。

```python
# 既存の末尾付近に追記

from dataclasses import dataclass

# ...（ValidationError/OutOfStock/PaymentDeclined/PersistenceError/OrderNotFound/PublishError）...

@dataclass(frozen=True)
class IdempotencyInProgress(PlaceOrderError):
    key: str

    def __str__(self) -> str:  # pragma: no cover
        return f"idempotency_in_progress: {self.key} ({self.message})"


@dataclass(frozen=True)
class IdempotencyFailed(PlaceOrderError):
    key: str
    previous_error: str

    def __str__(self) -> str:  # pragma: no cover
        return f"idempotency_failed: {self.key} prev={self.previous_error} ({self.message})"
```

---

### `src/order_service/core/ports/inbound/place_order.py`（追記）

`PlaceOrderCommand` に `idempotency_key` を追加します（CLIからも渡せるようにしておくと便利）。

```python
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class PlaceOrderCommand:
    customer_id: str
    lines: Sequence[PlaceOrderLine]
    payment_token: str
    idempotency_key: str | None = None  # ★追加
```

---

### `src/order_service/core/domain/service/place_order_service.py`（主要変更）

**冪等処理をユースケース内部に組み込み**ます。これにより「同じキーのリトライで在庫引当・課金・イベント発行を再実行しない」が実現できます。

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from returns.pipeline import flow
from returns.pointfree import bind, map_
from returns.result import Failure, Result, Success

from order_service.core.domain.model.errors import (
    IdempotencyFailed,
    IdempotencyInProgress,
    PlaceOrderError,
    ValidationError,
)
from order_service.core.domain.model.idempotency import IdempotencyRecord
from order_service.core.domain.model.order import CustomerId, LineItem, Money, Order, OrderId, Sku, now_utc
from order_service.core.ports.inbound.place_order import OrderReceipt, PlaceOrderCommand, PlaceOrderUseCase
from order_service.core.ports.outbound.events import EventPublisher, OrderPlaced
from order_service.core.ports.outbound.idempotency import IdempotencyRepository
from order_service.core.ports.outbound.inventory import InventoryGateway, Reservation
from order_service.core.ports.outbound.orders import OrderRepository
from order_service.core.ports.outbound.payment import ChargeRequest, PaymentGateway


@dataclass(frozen=True)
class PlaceOrderDeps:
    inventory: InventoryGateway
    payment: PaymentGateway
    orders: OrderRepository
    events: EventPublisher
    idempotency: IdempotencyRepository  # ★追加


@dataclass(frozen=True)
class PlaceOrderContext:
    order: Order
    payment_token: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PlaceOrderService(PlaceOrderUseCase):
    deps: PlaceOrderDeps

    def place_order(self, command: PlaceOrderCommand) -> Result[OrderReceipt, PlaceOrderError]:
        # 1) validate (pure)
        v = _validate_command(command)
        if isinstance(v, Failure):
            return v
        cmd = v.unwrap()

        customer = CustomerId(cmd.customer_id)
        idem_key = cmd.idempotency_key

        # 2) idempotency pre-check
        if idem_key is not None:
            existing = self.deps.idempotency.get(customer, idem_key)
            if isinstance(existing, Failure):
                return existing
            rec = existing.unwrap()
            if rec is not None:
                return self._resume_from_record(idem_key, rec)

        # 3) allocate order_id and register IN_PROGRESS
        order_id = OrderId.new()
        if idem_key is not None:
            started = self.deps.idempotency.start(customer, idem_key, order_id)
            if isinstance(started, Failure):
                return started  # 実DBなら競合時に再取得して分岐するのが堅い

        # 4) main pipeline（副作用あり）
        result = flow(
            cmd,
            bind(lambda c: _build_context(c, order_id)),
            bind(self._reserve_inventory),
            bind(self._charge_payment),
            bind(self._persist),
            bind(self._publish),
            map_(_to_receipt),
        )

        # 5) finalize idempotency state
        if idem_key is not None:
            if isinstance(result, Success):
                _ = self.deps.idempotency.complete(customer, idem_key)
            else:
                err = result.failure()
                _ = self.deps.idempotency.fail(customer, idem_key, previous_error=type(err).__name__)

        return result

    def _resume_from_record(self, idem_key: str, rec: IdempotencyRecord) -> Result[OrderReceipt, PlaceOrderError]:
        # 既に完了 → 同じ結果を返す（副作用を再実行しない）
        if rec.status == "COMPLETED":
            return self.deps.orders.get(rec.order_id).map(_order_to_receipt)

        # 実行中 → 競合（クライアントの重複送信/並列処理）
        if rec.status == "IN_PROGRESS":
            return Failure(IdempotencyInProgress(message="request with same key is in progress", key=idem_key))

        # 失敗済み → 同キーでの再試行を止める（再課金等の事故防止）
        return Failure(
            IdempotencyFailed(
                message="previous request with same key failed; use a new idempotency key to retry",
                key=idem_key,
                previous_error=rec.previous_error or "unknown",
            )
        )

    def _reserve_inventory(self, ctx: PlaceOrderContext) -> Result[PlaceOrderContext, PlaceOrderError]:
        reservations = tuple(Reservation(li.sku, li.quantity) for li in ctx.order.items)
        return self.deps.inventory.reserve(reservations).map(lambda _: ctx)

    def _charge_payment(self, ctx: PlaceOrderContext) -> Result[PlaceOrderContext, PlaceOrderError]:
        req = ChargeRequest(ctx.order.customer_id, ctx.order.total(), token=ctx.payment_token)
        return self.deps.payment.charge(req).map(lambda _: ctx)

    def _persist(self, ctx: PlaceOrderContext) -> Result[PlaceOrderContext, PlaceOrderError]:
        return self.deps.orders.save(ctx.order).map(lambda _: ctx)

    def _publish(self, ctx: PlaceOrderContext) -> Result[PlaceOrderContext, PlaceOrderError]:
        return self.deps.events.publish(OrderPlaced(ctx.order.order_id)).map(lambda _: ctx)


def _validate_command(cmd: PlaceOrderCommand) -> Result[PlaceOrderCommand, PlaceOrderError]:
    if not cmd.customer_id.strip():
        return Failure(ValidationError("customer_id is required"))
    if not cmd.lines:
        return Failure(ValidationError("at least one line item is required"))
    if not cmd.payment_token.strip():
        return Failure(ValidationError("payment_token is required"))

    if cmd.idempotency_key is not None and not cmd.idempotency_key.strip():
        return Failure(ValidationError("idempotency_key must be non-empty when provided"))

    for i, ln in enumerate(cmd.lines):
        if not ln.sku.strip():
            return Failure(ValidationError(f"lines[{i}].sku is required"))
        if ln.quantity <= 0:
            return Failure(ValidationError(f"lines[{i}].quantity must be > 0"))
        if Decimal(ln.unit_price) <= 0:
            return Failure(ValidationError(f"lines[{i}].unit_price must be > 0"))

    return Success(cmd)


def _build_context(cmd: PlaceOrderCommand, order_id: OrderId) -> Result[PlaceOrderContext, PlaceOrderError]:
    items: Tuple[LineItem, ...] = tuple(
        LineItem(
            sku=Sku(ln.sku),
            unit_price=Money.of(ln.unit_price),
            quantity=ln.quantity,
        )
        for ln in cmd.lines
    )
    order = Order(
        order_id=order_id,
        customer_id=CustomerId(cmd.customer_id),
        items=items,
        created_at=now_utc(),
    )
    return Success(PlaceOrderContext(order=order, payment_token=cmd.payment_token, idempotency_key=cmd.idempotency_key))


def _order_to_receipt(order: Order) -> OrderReceipt:
    return OrderReceipt(order_id=order.order_id, customer_id=order.customer_id, total=order.total())


def _to_receipt(ctx: PlaceOrderContext) -> OrderReceipt:
    return _order_to_receipt(ctx.order)
```

---

### `src/order_service/bootstrap.py`（依存注入の変更）

`InMemoryIdempotencyRepository` を追加して `PlaceOrderDeps` に注入します。

```python
from order_service.adapters.outbound.in_memory_idempotency import InMemoryIdempotencyRepository

# build_usecases 内
idempotency = InMemoryIdempotencyRepository()

place_order = PlaceOrderService(
    PlaceOrderDeps(
        inventory=inventory,
        payment=payment,
        orders=orders,
        events=events,
        idempotency=idempotency,  # ★追加
    )
)
```

---

### `src/order_service/adapters/inbound/web/fastapi_app.py`（POST /orders にヘッダ追加）

`Idempotency-Key` を受け取り、`PlaceOrderCommand.idempotency_key` に渡します。
加えて idempotency エラーは **409** にマップします。

```python
from fastapi import Header

# place_order endpoint signature
def place_order(
    req: PlaceOrderRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),  # ★追加
) -> Any:
    cmd = PlaceOrderCommand(
        customer_id=req.customer_id,
        payment_token=req.payment_token,
        idempotency_key=idempotency_key,  # ★追加
        lines=...
    )
    ...
```

エラーマッピング（既存の `_map_error_to_http` に追記）：

```python
from order_service.core.domain.model.errors import IdempotencyInProgress, IdempotencyFailed

if isinstance(err, (IdempotencyInProgress, IdempotencyFailed)):
    return 409, ErrorResponse(type=type(err).__name__, message=str(err))
```

---

### `src/order_service/adapters/inbound/cli.py`（任意：CLIでも使えるように）

JSON の `idempotency_key` を読んでコマンドに入れます。

```python
idem = payload.get("idempotency_key", None)
return PlaceOrderCommand(
    ...,
    idempotency_key=str(idem) if idem is not None else None,
)
```

---

## 1.3 動作イメージ（POST /orders）

* 初回（成功）
  `Idempotency-Key: abc` → 201 + order_id=X
  （内部：IN_PROGRESS → COMPLETED、注文作成/課金/在庫引当/イベント発行を実施）

* リトライ（同じキー）
  `Idempotency-Key: abc` → 201 + order_id=X
  （内部：COMPLETED を検出し、**orders.get(X) のみ**で同一レシートを返す）

* 並行二重実行（同時に同じキー）
  片方 IN_PROGRESS 中 → 409（IdempotencyInProgress）

* 失敗後に同じキーで再試行
  FAILED → 409（IdempotencyFailed）
  ※「同じキーで再実行しない」方針（再課金など事故防止）。再試行は **新しい Idempotency-Key** で行う。

---

# 2) 設計書（Idempotency: POST /orders）

以下は上記実装をベースにした **基本設計 → 詳細設計**です。

---

## 2.1 基本設計

### 目的

* **クライアントのリトライ**（タイムアウト、通信断、再送、ロードバランサの再試行）により、`POST /orders` が複数回実行されても
  **二重注文・二重課金・二重在庫引当を防ぐ**。

### 冪等キーの仕様

* 入力：HTTPヘッダ `Idempotency-Key`（任意だが推奨）
* スコープ：`(customer_id, idempotency_key)`
  → ユーザ間衝突を避けるため。

### 期待する振る舞い

* 同じ `(customer_id, key)` のリクエストは **同じ結果**を返す
* 同時実行は「片方のみ進める」または「片方は 409」で抑止

---

## 2.2 詳細設計

### 2.2.1 データモデル（永続化するなら）

（実装は in-memory だが、DB化するならこうなる、という設計）

**Table: `idempotency_keys`**

* `customer_id` (PK part)
* `key` (PK part)
* `status` enum (`IN_PROGRESS`, `COMPLETED`, `FAILED`)
* `order_id` (UUID)
* `previous_error` (text, nullable)
* `created_at`, `updated_at`

制約：

* `UNIQUE(customer_id, key)`（最重要）
* `order_id` は orders テーブル参照（FK は任意）

### 2.2.2 outbound port

* `IdempotencyRepository.get(customer_id, key)`

  * 既存レコードを取得（なければ None）
* `start(customer_id, key, order_id)`

  * 未登録なら IN_PROGRESS を作成（**原子的**であることが望ましい）
* `complete(customer_id, key)`

  * COMPLETED に更新
* `fail(customer_id, key, previous_error)`

  * FAILED に更新し原因コードを記録

### 2.2.3 PlaceOrder の処理手順（アルゴリズム）

1. 入力検証（必須・数量・単価）
2. `idempotency_key` があれば `get`

   * COMPLETED → `orders.get(order_id)` でレシート返却（副作用なし）
   * IN_PROGRESS → 409
   * FAILED → 409（新キーで再試行を促す）
3. 新規処理なら `order_id` を採番し `start`（IN_PROGRESS 登録）
4. 通常処理（在庫→決済→保存→イベント）
5. 成功なら `complete`、失敗なら `fail`

### 2.2.4 API（HTTP）仕様

**POST /orders**

* Request header: `Idempotency-Key`（任意）
* Success: 201 + `Location: /orders/{order_id}` + receipt
* Error:

  * ValidationError: 400
  * OutOfStock: 409
  * PaymentDeclined: 402
  * PublishError: 503
  * PersistenceError: 500
  * IdempotencyInProgress / IdempotencyFailed: 409

### 2.2.5 競合とトランザクション（実DBでの注意点）

* `start()` は **INSERT with UNIQUE** にする

  * 競合したら `get()` で状態を見て振る舞いを決める
* `orders.save` と `idempotency.complete` は可能なら同一トランザクションで更新

  * さらに進めるなら **Transactional Outbox** と合わせて「保存＋イベント」を同一TXに寄せる

---

## 2.3 今回の実装の意図・割り切り

* **FAILED の同一キー再試行を禁止**：安全側（再課金事故防止）
  → 再試行は新しいキーで行う
* Outbox/Saga は未導入：次のステップで拡張可能

  * Saga（決済失敗時の在庫戻し）
  * Transactional Outbox（保存とイベントの二重書き込み回避）

---

次にやると綺麗に繋がるのは、**(a) Transactional Outbox** と **(b) Saga（補償：決済失敗→在庫戻し）** です。
どちらから進めますか？🚀
