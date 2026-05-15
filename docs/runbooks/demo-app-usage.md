# Demo App Usage

## Overview

This runbook covers how to run the demo app and verify each endpoint in Grafana.

## Running the App

```
cd telemetry/app
docker compose up
```

The app will be available at `http://localhost:8082`. Grafana will be available at `http://localhost:3000` (login: admin/admin).

## Endpoints

### GET /hello

A happy path endpoint that returns a success response and emits an info log.

```
curl http://localhost:8082/hello
```

Request-level trace:
```
GET /hello
└── hello()  ✅ 200
```

What to check in Grafana:
- **Tempo**: a trace for `GET /hello` with a short span duration
- **Loki**: a log line `hello endpoint called`

---

### GET /error

Returns a 500 error intentionally. Used to validate error traces and logs.

```
curl http://localhost:8082/error
```

Request-level trace:
```
GET /error
└── error()  ❌ 500
```

What to check in Grafana:
- **Tempo**: a trace for `GET /error` marked as failed
- **Prometheus**: an increase in error rate metrics

---

### GET /slow

Injects a controllable delay to validate latency and span duration. Default delay is 1000ms.

```
curl "http://localhost:8082/slow?ms=2000"
```

Request-level trace:
```
GET /slow
└── slow()  duration: 2000ms  ✅ 200
```

What to check in Grafana:
- **Tempo**: a trace for `GET /slow` with a visibly longer span duration compared to `/hello`
- **Loki**: a log line `injecting delay of 2000 ms`
- **Prometheus**: higher latency metrics for this endpoint
