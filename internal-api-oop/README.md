# internal-api

ネットワーク内のAPIを想定。

---

## 起動手順（確認用）

### 1) Web API（FastAPI）

```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn order_service.asgi:app --reload --port 8000
```

* `POST /orders`（201 + Location）
* `GET /orders/{order_id}`（詳細）
* `GET /orders?offset=&limit=&customer_id=&sort_by=&sort_dir=`（一覧）

例：

```bash
curl -i -X POST http://localhost:8000/orders \
  -H 'content-type: application/json' \
  -d '{"customer_id":"c-1","payment_token":"tok_ok","lines":[{"sku":"SKU-1","unit_price":"1200.00","quantity":2}]}'
```

一覧（合計金額降順）：

```bash
curl -s 'http://localhost:8000/orders?sort_by=total&sort_dir=desc'
```

### 2) CLI（既存）

```bash
PYTHONPATH=src python -m order_service.main \
'{"customer_id":"c-1","payment_token":"tok_ok","lines":[{"sku":"SKU-1","unit_price":"1200.00","quantity":2}]}'
```

---

次は、`cursor pagination`（offset/limitの代替）か、Outbound を実DB（SQLite/Postgres）へ差し替えるのが自然な発展です。
