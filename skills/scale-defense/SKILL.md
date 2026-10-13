---
name: scale-defense
description: Django/Celery/Redis/MySQL scaling and optimization reference. Triggers on Celery internals, DB read/write scaling, Redis cache-vs-broker, or system-design questions.
metadata:
  type: reference
---

# scale-defense

## Purpose

Self-contained scaling/optimization reference for Django + Celery + Redis + MySQL/Postgres. No external file dependencies.

## Celery

### The one idea behind most Celery questions

Celery gives **at-least-once delivery, never exactly-once**. Every mechanism below exists to compensate for that fact. "How do you guarantee exactly-once execution?" — you don't; you make running a task twice harmless (idempotency).

### Delivery guarantees: ack timing

- **Early ack** (`acks_late=False`, default): broker marks the message done the instant the worker *receives* it, before execution. A crash mid-task loses the message silently.
- **Late ack** (`acks_late=True`): broker marks it done only after the task returns (success or a clean exception). A crash mid-task leaves it unacked, so the broker redelivers it.
- **`task_reject_on_worker_lost`**: if a *child* worker process dies abnormally (OOM/SIGKILL) while the *parent* survives and notices, Celery's default (`False`) acks the message anyway — task lost forever, no requeue. Setting `True` makes the parent reject/nack it instead, so it's requeued immediately. Only matters when a parent survives to act — if the whole worker/connection disappears, nobody is left to ack or reject anything.
- **`visibility_timeout`** (Redis transport, `CELERY_BROKER_TRANSPORT_OPTIONS={"visibility_timeout": N}`): the safety net for that second case. Not a Redis feature — a kombu convention: a popped-but-unacked message is timestamped in a sorted set, and a periodic sweep restores anything older than N seconds. **Too low** → a still-running long task gets redelivered and double-executed. **Too high** → a genuinely dead task's work sits invisible for the whole window. Tune to actual observed longest task runtime. RabbitMQ's native AMQP ack/nack needs no equivalent — the broker knows instantly when a consumer disconnects.

### Idempotency patterns (weakest → strongest)

1. Hope (don't).
2. **Natural idempotency via upsert** — `update_or_create`, or native `ON CONFLICT`/`ON DUPLICATE KEY UPDATE` (Django 4.1+: `bulk_create(..., update_conflicts=True)`). Best when the task is "make the DB look like X," not "do X once."
3. **Dedup key + fast-path check** — unique job/idempotency key on the model, check-then-skip. Race condition if two redeliveries run concurrently — close it with a DB unique constraint (catch `IntegrityError`, treat as already-done), not a bare check-then-write.
4. **Distributed lock for the execution window** — Redis `SET key value NX EX ttl` at task start, released/expired at the end.
5. **Externally idempotent calls** — pass an idempotency key the third party itself honors (payment gateways do this natively).

Mentioning #2 and #3 together (not just #3 alone) is the stronger answer — "actually the cleanest version is an upsert, no dedup table needed."

### Timeouts

- `soft_time_limit`: raises `SoftTimeLimitExceeded` *inside* the task, catchable — use it to clean up before dying.
- `time_limit` (hard): after the grace period, Celery sends **SIGKILL**. No cleanup, no `finally` block runs. A lock held via `finally` is never released on a hard kill — locks need external expiry (Redis TTL), not just "release in finally."

### Worker pool types

| Pool | Model | Best for | Watch out for |
|---|---|---|---|
| `prefork` (default) | OS processes | CPU-bound, non-thread-safe C extensions | Higher memory/worker, fork overhead |
| `eventlet`/`gevent` | Greenlets, monkey-patched I/O | High-concurrency I/O-bound | Monkey-patching can silently break libraries using real threads underneath |
| `threads` | OS threads | I/O-bound, lighter than prefork | GIL still limits CPU-bound work |
| `solo` | Single thread | Local debugging only | No concurrency — never for production |

**eventlet/gevent do not bypass the GIL.** Only one thread ever executes Python bytecode. What greenlets buy is interleaving many I/O *waits* on one thread, not parallel computation. Monkey-patching swaps stdlib I/O calls (`socket`, `ssl`) for greenlet-aware versions that yield to the hub instead of blocking when a call would wait. A greenlet only yields at a patched I/O point — a CPU-bound task with no I/O call has no yield point at all and monopolizes the thread, starving every other greenlet (no OS-level preemption to save you, unlike real threads).

### Prefetch and head-of-line blocking

`prefetch count = concurrency × worker_prefetch_multiplier` (default multiplier **4**). With `concurrency=4`, the worker reserves 16 messages up front; only 4 run at once, 12 sit buffered client-side. Exists to amortize broker round-trips for many small homogeneous tasks. Sharp edges when task durations vary and share a queue:
- Long tasks reserved ahead of short ones cause head-of-line blocking.
- Bigger blast radius on crash — with `acks_late=True`, all *reserved* tasks (not just executing ones) wait out `visibility_timeout`.
- Unfair across multiple workers consuming one queue — one worker can greedily reserve a batch invisible to others.

Fixes: `worker_prefetch_multiplier=1` for long/variable-duration queues; route by task-duration class to **separate queues bound to separate worker pools** (the scalable answer — also gives independent autoscaling); `-Ofair` scheduling reduces (not eliminates) one child hogging long tasks. This setting is per worker *process*, not per queue — a single `celery worker` has one prefetch value and one pool type for its whole life regardless of how many queues it's bound to with `-Q`. Different queues needing different prefetch/pool behavior need separate worker processes:
```bash
celery -A myproject worker -Q fast_queue -c 8 --prefetch-multiplier=4
celery -A myproject worker -Q slow_queue -c 2 --prefetch-multiplier=1
```

### Canvas (chain/group/chord) failure modes

- **chain**: sequential, output feeds next. A failed link stops the chain, exception visible.
- **group**: parallel fan-out, results collected into a `GroupResult`.
- **chord**: group + callback firing once all members finish. **Chord completion is polling-based** — a counter increments as each member reaches *some recorded final state*. A clean exception (retries exhausted, `FAILURE` recorded) still increments the counter fine; `link_error`/`on_chord_error` makes that failure visible instead of silently absorbed. A **worker crash** mid-task on a member is categorically worse — no final state is ever written for it, the counter is permanently stuck below the group size, and the chord **hangs forever with no error surfaced at all**, since nothing ever actually failed in an observable way. The real fix is ensuring every member reliably reaches *some* terminal state (solid retries, correctly-tuned `visibility_timeout`, `task_reject_on_worker_lost=True`) — `link_error` only helps the failures that do get recorded.

### Scheduling at scale (Celery Beat)

Beat is a **single scheduler process**. Running more than one instance makes every periodic task fire multiple times — no built-in leader election. Options:
- Run exactly one Beat replica (accept the single point of failure, restart fast on crash).
- **RedBeat** (`celery-redbeat`): stores schedule + runtime metadata in Redis and holds a TTL-based distributed lock — multiple Beat processes can run, only the lock-holder is active; if it dies, the lock expires and a standby takes over, no external leader-election service needed.
- **`django-celery-beat`**: DB-backed, admin-editable schedule — doesn't by itself solve the multi-instance problem; still needs a single active scheduler or RedBeat-style locking underneath. (A DB-backed jobs table with `SELECT...FOR UPDATE SKIP LOCKED` row-claiming across multiple stateless scheduler processes is another way to get the same HA property without a dedicated locking library.)

### Broker choice: Redis vs RabbitMQ

- **Redis**: simple, low operational overhead if already used for caching. Durability depends on persistence config (RDB vs AOF). Ack semantics are *simulated* (poll + `visibility_timeout`), not a native protocol ack. No native priority queues/dead-letter exchanges.
- **RabbitMQ**: true AMQP ack/nack/reject at the protocol level, no polling. Native priority queues, dead-letter exchanges, delayed-message plugin. Extra infra to operate.

### Redis internals relevant to Celery/kombu

- **Producer side**: `.delay()` generates `task_id` client-side, serializes, `LPUSH celery <message>` — a plain list push.
- **Consumer side**: `BRPOP celery 1` — blocking pop with a 1s timeout (not `0`/infinite), so the event loop gets a guaranteed chance to run housekeeping at least once a second. Redis doesn't busy-poll: a blocked client is tracked in a dict mapping key → waiting clients; a push directly serves the oldest waiter.
- **Ack bookkeeping**: on pop, the worker writes into `unacked` (a Hash, keyed by an internal `delivery_tag`) and timestamps that tag into `unacked_index` (a Sorted Set, score = pop time). A sweep computes `now - visibility_timeout` and restores (`LPUSH`) anything older. The sorted set is what makes "find everything older than X" an efficient O(log N) query.
- **No extra locking needed**: Redis command execution is single-threaded — every `LPUSH`/`HSET`/`ZADD` is already atomic. (Optional I/O threads since 6.0 only handle socket reads/writes, never command logic — unrelated to Python's GIL.)
- **Broker/result DB split**: Celery defaults broker to DB 0, results to DB 1 of the *same* instance — same memory, same eviction policy, pure namespacing, not isolation. **Redis Cluster supports only DB 0** (`SELECT` disabled) — moving to Cluster means re-architecting that split.
- **Result pub/sub**: after writing the result into a durable TTL'd String key (`celery-task-meta-<task_id>`), the worker also publishes on a channel so a blocking `.get()` wakes instantly instead of polling. Pub/sub itself is fire-and-forget — a publish with nobody subscribed is simply gone, but the result still sits in the String key regardless, so a missed publish only costs latency, never correctness.
- **RDB vs AOF**: RDB is a periodic snapshot (data since last snapshot is lost on crash); AOF is a continuous write log, replayed on restart. For a cache, losing a few minutes is a non-event. **For a broker, that gap is where queued-but-unconsumed messages live** — no application setting protects against it, since this happens one layer below all of it. Set `appendonly yes` for a Redis-as-broker config.
- **`maxmemory-policy`**: `noeviction` refuses writes when full — loud, visible, the safe default for a broker. `allkeys-lru`/`allkeys-lfu` silently evict keys instead, which can mean dropping an unconsumed queue entry — task loss disguised as normal cache behavior. If chosen anyway for memory headroom, monitor `evicted_keys` and alert on non-zero.

### Dead-letter patterns (Celery has no built-in DLQ)

- Override `Task.on_failure` / connect to `task_failure` to persist failed tasks (args, kwargs, exception, traceback) for manual inspection/replay — also the natural hook for alerting.
- Route truly poisonous messages (malformed payload, will never succeed) to a separate "dead" queue after `max_retries` is exhausted, rather than cycling forever.
- `autoretry_for` scoped to specific transient exceptions only — non-retryable bugs (e.g. a `TypeError`) shouldn't be in that tuple.

### Observability

- **Flower**: live worker/task state dashboard, good for ad-hoc debugging, not a metrics store.
- **Prometheus/APM exporters**: for dashboards/alerting (queue depth, task latency, failure rate).
- **Signals**: `task_prerun`, `task_postrun`, `task_failure`, `task_retry`, `worker_ready`, `worker_shutting_down` — emit custom metrics without touching every task body.
- Growing queue depth with flat worker count means arrival-rate-bound — need more workers or to shed/defer load.
- **APM gotcha**: the worker is a separate OS process from the web app with its own boot path. If `sentry_sdk.init()`/`ddtrace-run` only wraps the web server's start command, the worker process never runs it — it needs its own init call (e.g. in the Celery app module, which is imported at worker boot too) or its own `ddtrace-run` prefix. The most common reason "errors show up for the web app but not Celery" is this, not a broken integration.

### Operational hygiene

- `worker_max_tasks_per_child`/`worker_max_memory_per_child`: recycle a child process after N tasks or a memory threshold — mitigates slow leaks without finding the actual leak.
- Graceful shutdown: **SIGTERM** = warm shutdown (stop pulling new tasks, finish in-flight, exit); **SIGQUIT/SIGKILL** = immediate. In an orchestrator, `terminationGracePeriodSeconds` must exceed the longest expected task duration or deploys hard-kill in-flight tasks — another reason idempotency matters, since a deploy-triggered kill is just another form of redelivery.

### Rate limiting

- `task.rate_limit = "100/m"` is **per-worker**, not global — N workers gives `N × rate_limit` effective throughput.
- For a true global cap (respecting a third-party API limit regardless of worker count), implement a shared token-bucket/counter in Redis every task checks before proceeding.

### Testing

- `task_always_eager=True` runs tasks synchronously in-process — fast for unit-testing task logic, but **skips serialization and the real broker/worker boundary**, so it won't catch a task whose arguments aren't JSON-serializable, or a redelivery/idempotency bug. Testing failure/retry/dedup behavior needs an actual broker+worker in the test environment.

## Django scaling

### Scope the problem before reaching for a tool

- **Too many requests, each cheap** (read-heavy browse/search) → caching, read replicas, CDN, search-index offload.
- **Too few requests, each expensive** (slow queries, N+1s, lock contention) → query/index fixes, batching.
- **Write volume outpaces the primary DB** (event logging, high-frequency inserts) → async offload, queue decoupling, partitioning, possibly a different storage engine.

Cheapest-fix-first order: index/query fix → caching → read replicas → async offload → only then structural changes (partitioning/sharding/CQRS). Jumping straight to sharding on a problem an index would fix is a common tell.

### Read-heavy ladder

1. **Fix the query**: `select_related` (SQL join, FK/O2O, single query) vs `prefetch_related` (separate query + Python-side join, M2M/reverse-FK). `only()`/`defer()` to skip unneeded columns. `values()`/`values_list()` for read-only list views. Detect N+1s with query-count tooling or `assertNumQueries` in tests.
2. **Index it**: composite indexes matching actual `WHERE`/`ORDER BY` column order. **Column order rule**: equality-filtered columns first (any order among themselves), the single range-filtered (`>`,`<`,`BETWEEN`) or `ORDER BY` column last — once a range condition applies, rows stop being usefully ordered for anything after it, so equality columns can stack freely before that point. E.g. `WHERE tenant_id=5 AND status='active' AND created_at > X ORDER BY created_at` → index `(tenant_id, status, created_at)`. Confirm with `EXPLAIN ANALYZE` that the planner actually uses the index — adding one doesn't guarantee it's picked (stale stats, low selectivity).
3. **Cache**: cache-aside (check cache, fall back to DB on miss, write back) — vulnerable to **stampede** (many concurrent misses on a hot key hit the DB together); mitigate with a lock around the recompute or probabilistic early expiration. Write-through (update cache+DB together) lowers read-latency variance at the cost of write-path complexity. Invalidation: TTL-based (simple, accepts staleness) vs explicit `post_save`/`post_delete` signal invalidation (precise, but bulk `.update()` doesn't fire signals).
4. **Read replicas**: multi-db + a router (`db_for_read`→replica, `db_for_write`→primary), or explicit `.using('replica')`. **Replication lag**: a write immediately followed by a read of the same row can read stale data from a lagging replica — fix by routing that request back to primary for a short window, or accept eventual consistency where the UX allows it.
5. **Offload search/filter-heavy reads**: full-text/faceted/geo queries belong in Elasticsearch/OpenSearch (or Postgres `tsvector`/GIN), not `LIKE` or ever-heavier composite indexes. B-tree indexes are built for exact matches/ordered ranges, not relevance-ranked fuzzy text or many live-counted facets — search engines use an **inverted index** (word → documents containing it) so a multi-term query is a fast lookup-and-intersect over posting lists instead of a full scan; those same postings carry the frequency/position data relevance scoring (BM25/TF-IDF) needs. Real trade-off: a second, denormalized, eventually-consistent copy of the data that can fail independently.
6. **Denormalize for specific heavy reads**: materialized views, or a precomputed read table updated async — lightweight CQRS without the full architectural overhead.

### Write-heavy ladder

1. **Batch, don't loop**: `bulk_create`/`bulk_update` instead of per-row `.save()` — each `.save()` is a round trip plus signal overhead.
2. **Native upsert**: Django 4.1+ `bulk_create(..., update_conflicts=True, update_fields=[...], unique_fields=[...])` → `ON CONFLICT`/`ON DUPLICATE KEY UPDATE` — avoids a select-then-decide round trip and is naturally idempotent.
3. **Move anything off the critical path async**: if a write doesn't need synchronous confirmation, queue it — notification fan-out, search-index updates, audit logging, analytics events.
4. **Decouple ingestion from storage at very high write volume**: don't make a high-frequency, append-only analytical workload share a database with the transactional workload — a dedicated write path bypassing the ORM/request cycle, into a column store built for high-throughput append + aggregation (the opposite optimization target from a row-oriented OLTP database).
5. **Partition large time-ordered tables**: range partitioning by date for logs/events/audit trails — smaller indexes, cheap old-partition drops instead of slow `DELETE`s, planner can skip irrelevant partitions for date-ranged queries.
6. **Shard only as a last resort**, when a single primary genuinely can't hold the throughput/volume. Django has no native sharding — done via a custom router keyed on tenant/customer id. Cross-shard queries/joins/transactions become hard or impossible, so the sharding key is a one-way architectural bet.

### Concurrency control on the write path

- **Optimistic locking**: a `version` field incremented on save, update's `WHERE` checks the version is unchanged — cheap, no DB-level lock, but the client must handle "someone else updated this first."
- **Pessimistic locking**: `select_for_update()` in a transaction — a real row lock held until commit. Correct for short, high-contention critical sections (e.g. decrementing inventory at checkout); risks contention/deadlocks if transactions are long or lock rows in inconsistent order.
- **Idempotency keys at the API layer**: for any write endpoint a client might retry, accept a client-generated key, store with a unique constraint, return the original result on a duplicate.

### Connection pooling

`CONN_MAX_AGE` keeps persistent connections per worker process — connection count scales with (app processes/threads) × (instances), which can exceed `max_connections` fast under horizontal scaling. **PgBouncer**/ProxySQL multiplex many app-level connections onto a smaller real-connection pool. Transaction-pooling mode is incompatible with session-level features (advisory locks held across statements, session `SET` variables, some drivers' prepared statements) — know which code paths rely on session state before dropping one in.

### App tier

Stateless app servers behind a load balancer — horizontal scaling is "add more processes," the easy part; the database is almost always the actual bottleneck. Gunicorn/uvicorn: sync workers (one request/worker, fine for already-fast views) vs async (ASGI/async views, or gevent-patched sync workers) for views making multiple outbound I/O calls per request.

### Observability at scale

`pg_stat_statements` (Postgres) / slow query log + `performance_schema` (MySQL) for what's slow in aggregate, not just one traced request. APM traces a request to query-level — dominated by DB time vs app time vs external calls. Start scaling decisions from aggregate slow-query/APM data, not intuition.

## Redis — standalone reference

- **Single-threaded execution**: command execution is one thread, start to finish, no interleaving — every command is already atomic with zero application-level locking. Since 6.0, optional I/O threads only handle socket reads/writes, never command logic.
- **Logical DBs (0-15 by default)**: namespaces inside the *same* process — same memory, same `maxmemory`, same eviction policy, not separate resourcing. **Cluster mode supports only DB 0** — `SELECT` is disabled, since cross-DB atomicity doesn't make sense once data is sharded by key.
- **Data structures actually used by a task-queue broker**: List (queue), Hash (ack bookkeeping), Sorted Set (timestamp index for sweep/redelivery), String (result values), Pub/Sub (ready-notifications, not a stored type). Redis Streams (added in Redis 5, with consumer groups and replay) are arguably a better native fit for a queue than Lists, but most queue libraries predate Streams and don't use them by default.
- **RDB vs AOF**: snapshot (fast restart, loses writes since last snapshot) vs continuous write log (`appendfsync always|everysec|no` trades durability for latency). For a pure cache, losing recent writes on crash is usually fine. For anything acting as a durable queue, that gap is where unconsumed messages live — explicit `appendonly yes` needed.
- **`maxmemory-policy`**: `noeviction` (loud failure, safe default when acting as a queue/broker) vs `allkeys-lru`/`allkeys-lfu` (silent eviction — can silently drop an unconsumed entry). If evicting anyway for memory headroom, alert on `evicted_keys` > 0.
- **Pub/Sub**: pure fire-and-forget, no persistence/replay/ack — a publish with nobody subscribed is gone forever. Never the only storage for something that must not be lost.
- **Replication / Sentinel / Cluster**: async primary→replica (replica can lag) / automatic failover on top of replication (quorum promotes a replica) / shards keys across nodes by hash slot (scales throughput + dataset size, but drops multi-DB support and restricts multi-key ops to same-slot keys).
- **`django-redis` connection pooling**: manages a pool per configured Redis URL automatically, sized via `CACHES[...]["OPTIONS"]["CONNECTION_POOL_KWARGS"]`. Don't assume a pooling library is bug-free just because it's framework-provided — pool-reinitialization regressions have shipped in real cache-client libraries before.
- **Cache stampede**: a bare TTL fails exactly when it matters — a hot key expires and every concurrent request misses at once, hammering the DB together. Real fixes: a distributed lock around the recompute (`SET NX EX`, first requester recomputes, others wait/serve stale) when the recompute is expensive or has write-side effects; probabilistic early expiration (recompute slightly before actual TTL, staggered) when it's cheap and serializing isn't worth it.
- **Memory sizing**: cap `maxmemory` at roughly 50-75% of available RAM — RDB snapshotting forks the process and briefly doubles resident memory via copy-on-write as writes diverge from the snapshot, plus OS/Redis overhead headroom.
- **One instance, two roles (cache + broker)**: same memory budget, same eviction policy, same blast radius regardless of logical-DB separation — a growing cache working set can trigger eviction that drops unconsumed broker messages, and a broker backlog can crowd out cache memory right when the cache matters most. Separate instances/clusters once either workload is non-trivial, so each can run its own `maxmemory-policy`.
- **Sentinel vs Cluster for a given role**: Sentinel (HA, single-primary throughput/size ceiling) is usually enough for a broker, since queue depth is bounded by what you let build up, not by needing to shard data. Cluster (horizontal scale, loses multi-DB/cross-slot ops) is the more defensible default once a cache's working set outgrows one node.
