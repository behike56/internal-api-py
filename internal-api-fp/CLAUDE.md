# CLAUDE rule

WEB APIを制作する。
関数型プログラミング(FP)を強く適用する。
ポート＆アダプタを採用。

## 最低限の技術要素

- pydantic
- fastapi
- uvicorn
- returns

## なぜFPとポート＆アダプタは相性が良いのか

ポート＆アダプタの核心は「コアを副作用から隔離する」ことです。FPの核心は「副作用を型で明示し、純粋な関数を中心に組み立てる」ことです。この二つは本質的に同じ問題意識を持っています。OOP的なポート＆アダプタでは「インターフェース（抽象）に依存する」という手段で副作用を隔離しますが、FP的に強く適用すると「副作用を値として表現し、解釈を外に押し出す」という手段に変わります。

## FPを強く適用した場合の階層の考え方

FP的観点から各層に何を置くべきかをOOPとの比較を含めて説明します。
これ以降のコードは例です。

### `core/domain/model` — 不変データと代数的型

ここには純粋なデータ構造だけを置きます。FP的には「データは振る舞いを持たない」が理想に近づきます。Pythonなら `@dataclass(frozen=True)` や `NamedTuple`、あるいは `pydantic` の immutable model を使います。また、ドメインエラーも型として表現します。`Result[T, E]` 型（`returns` ライブラリなど）や `Either` を使うと、エラーが型シグネチャに現れるようになります。

```python
# core/domain/model/order.py
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NewType

OrderId = NewType("OrderId", str)
CustomerId = NewType("CustomerId", str)

@dataclass(frozen=True)  # immutable — FPの基本
class Order:
    id: OrderId
    customer_id: CustomerId
    total: Decimal
    status: OrderStatus  # Enum など代数的型
```

### `core/domain/service` — 純粋な変換関数の集まり

### `core/domain/service` — 型に対して汎用的に（パラメトリックに）定義された純粋変換関数の集まり

ここが最も変わります。OOP的には「サービスクラスがリポジトリをDIされて操作する（サブタイプ多相）」ですが、FP的には「データを受け取ってデータを返す純粋関数」だけを置きます。副作用（DB読み書きなど）は一切ここに入りません。

さらに重要なのは多相の扱い方です。OOPがクラス継承・インターフェースの実装という「名前による約束」で差し替えを実現するのに対し、FP的には「同じシグネチャ（形）であれば何でも渡せる」というパラメトリック多相を用います。副作用が必要な操作は、具体的なリポジトリクラスではなく `Callable` の引数として受け取ります。これにより、この層は特定のIO実装を一切知らずに済みます。

```python
# core/domain/service/order_service.py
from typing import Callable
from returns.result import Result, Success, Failure

def validate_order(
    order: Order,
    # 具体的なリポジトリクラスではなく「関数の形」として受け取る。
    # InMemoryInventory だろうと PostgresInventory だろうと、
    # この関数のシグネチャを満たせば何でも渡せる（パラメトリック多相）。
    stock_lookup: Callable[[ItemId], int],
) -> Result[Order, DomainError]:
    """
    在庫チェックは「渡された関数の形」で判断するため、副作用ゼロ。
    stock_lookup の実装がどこにあるかをこの層は知らない。
    """
    if stock_lookup(order.item_id) < order.quantity:
        return Failure(InsufficientStockError(order.id))
    return Success(order)

def apply_discount(order: Order, discount: Discount) -> Order:
    """完全に純粋な変換。引数も戻り値もデータのみ。"""
    return dataclasses.replace(order, total=order.total * (1 - discount.rate))
```

なお、`Callable[[ItemId], int]` に `StockLookup` という名前をつけた Protocol を `core/ports/outbound` に定義している場合は、それを型ヒントとして使うこともできます。その場合はこの層から `core/ports` を参照することになりますが、「名前をつけて意図を明示する」か「構造だけで語る」かの違いであり、パラメトリック多相という本質は変わりません。

重要なポイントは、「在庫を調べる」という行為をここで行うのではなく、「渡された関数の形で判断する」という形に変えることです。どの実装が渡されるかはこの層の関心外であり、それがFP的インサイドアウト設計とパラメトリック多相の組み合わせの核心です。

### `core/ports` — 副作用の「形」を型で記述する場所

ここが最も概念的に面白い変化です。OOP的ポートは「インターフェース（抽象メソッドの集合）」ですが、FP的ポートは「副作用を表す型の定義」に変わります。Pythonでは完全なHaskell的 `IO` モナドは難しいですが、`Protocol` + `Callable` の組み合わせ、あるいは `returns` ライブラリの `IOResult` を使うことで近づけられます。

```python
# core/ports/outbound/repository.py
from typing import Protocol
from returns.io import IOResult

class OrderRepository(Protocol):
    # 戻り値の型自体が「これはIOを伴う操作だ」と語っている
    def find_by_id(self, order_id: OrderId) -> IOResult[Order, RepositoryError]: ...
    def save(self, order: Order) -> IOResult[None, RepositoryError]: ...
```

`IOResult` を返すことで、「この関数を呼び出した時点ではまだ副作用は起きていない、値として持ち回れる」という性質を持たせることができます。

### 新たに設けるべき層 — `core/usecase`（ユースケース・オーケストレーション層）

現在の構造には明示的にありませんが、FPを強く適用する際に最も重要になる層です。ここは「純粋なドメインロジックと副作用を持つポートをつなぐ、副作用の連鎖を組み立てる場所」です。

```python
# core/usecase/place_order_usecase.py
from returns.result import Result
from returns.pipeline import flow

def place_order(
    order_data: OrderData,
    # 依存する副作用はすべて引数として注入（高階関数的DI）
    find_inventory: Callable[[ItemId], IOResult[int, RepositoryError]],
    save_order: Callable[[Order], IOResult[None, RepositoryError]],
    publish_event: Callable[[DomainEvent], IOResult[None, EventError]],
) -> IOResult[OrderId, AppError]:
    # モナディックな連鎖で副作用を「組み立てる」
    return (
        build_order(order_data)          # 純粋
        .bind(lambda o: validate_with_inventory(o, find_inventory))  # IOResult の連鎖
        .bind(save_order)
        .bind(lambda o: publish_event(OrderPlaced(o.id)))
    )
```

ここでのDIはクラスのコンストラクタインジェクションではなく、関数の引数として渡す「高階関数的DI」になります。

### `adapters` — 副作用が実際に発生する唯一の場所

アダプター層の役割はより明確になります。「ポートが要求する型シグネチャ（`IOResult` を返す関数）を実装し、実際のIO操作を行う」ことです。

```python
# adapters/outbound/postgres_order_repository.py
from returns.io import IOSuccess, IOFailure

def find_order_by_id(order_id: OrderId) -> IOResult[Order, RepositoryError]:
    try:
        row = db.execute("SELECT ...", order_id)  # ← 副作用はここだけ
        return IOSuccess(row_to_order(row))
    except Exception as e:
        return IOFailure(RepositoryError(str(e)))
```

## 実践的なトレードオフについて

`returns` ライブラリのようなモナディックなアプローチはPythonでは型推論が弱く、チームへの学習コストも高いです。完全なFPを追求するよりも、「`core/domain/service` は純粋関数だけ」「`usecase` 層でのみ副作用の連鎖を書く」「`model` は immutable」という3点を守るだけでも、FPのメリット（テストしやすさ、予測可能性）の大半が得られます。どこまでモナドに寄せるかはチームの文脈次第です。

## コードベースの構造

ポート＆アダプターを採用する。

```text
src/internal_api_fp/
├─ core/ 
│   ├─ domain/ 
│   │  ├─ model/ ← frozen dataclass, NewType, Enum（純粋なデータ型） 
│   │  └─ service/ ← 型に対して汎用的に（パラメトリックに）定義された純粋変換関数
│   ├─ ports/ 
│   │  ├─ inbound/ ← ユースケースの関数シグネチャを Protocol で定義 
│   │  └─ outbound/ ← 外部依存の副作用の「形」を Protocol + IOResult で定義 
│   └─ usecase/ ← ユースケース（IOResult の連鎖を組み立てる） 
└─ adapters/ 
   ├─ inbound/ ← HTTPリクエスト → ユースケース呼び出し → HTTPレスポンス 
   └─ outbound/ ← ポートの実装（実際のIO）
```

### 注意点

#### core/ports

ポートはあくまで「コアがアダプターに対して要求する契約」なので、`core/domain/service` や `core/usecase` の両方から参照されます。\
この構造のままで問題ないのですが、`core/ports` は「`core/usecase`のためだけにある」ではなく「coreとadaptersの境界面全体を定義する」という意識を持っておくと、後から責務が混乱しにくくなります。

#### core/domain/service

`core/domain/service` のパラメトリックな純粋関数と `core/usecase` の`IOResult`連鎖の間に、 \
「どこまでが純粋でどこから副作用の組み立てが始まるか」という境界線が最も曖昧になりやすい箇所です。

実装を進める中で「この関数はどちらに属すか？」と迷ったとき、副作用を表す型（`IOResult`など）が\
型シグネチャに登場するかどうかがその判断基準になります。\
登場しないなら `core/domain/service`、\
登場するなら `core/usecase` です。
