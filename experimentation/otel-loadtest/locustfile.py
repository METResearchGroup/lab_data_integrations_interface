"""
Breaking-point load test for grafana/otel-lgtm all-in-one container.

Three attack surfaces:
  OtlpUser    (port 4318) - OTLP HTTP receiver: traces, metrics, logs, batches
  GrafanaUser (port 3000) - query/read layer: Tempo, Loki, Prometheus via Grafana

User distribution is weighted 10 : 1 — OTLP ingest vs. Grafana read path.

Run (headless, staircase shape drives the ramp):
  locust -f locustfile.py --headless --run-time 10m

Run (headful UI at http://localhost:8089):
  locust -f locustfile.py

Watch Locust's charts: when p99 latency spikes or error rate climbs past ~5%,
the container has hit its limit. Raise the ceiling in BreakingPointShape.stages
if it survives all stages comfortably.
"""

import random
import string
import time

from locust import HttpUser, LoadTestShape, between, task

OTLP_HOST = "http://localhost:4318"
GRAFANA_HOST = "http://localhost:3000"

_HEX = string.hexdigits[:16]


def _trace_id() -> str:
  return "".join(random.choices(_HEX, k=32))


def _span_id() -> str:
  return "".join(random.choices(_HEX, k=16))


def _now_ns() -> str:
  return str(int(time.time_ns()))


class OtlpUser(HttpUser):
  """
  Directly hammers the OTLP HTTP receiver — the primary ingest bottleneck.
  Short wait_time to maximise throughput per virtual user.
  """

  host = OTLP_HOST
  wait_time = between(0.1, 0.5)
  weight = 10

  @task(4)
  def send_trace(self):
    now = int(time.time_ns())
    payload = {
      "resourceSpans": [
        {
          "resource": {
            "attributes": [
              {"key": "service.name", "value": {"stringValue": "locust-svc"}},
              {"key": "service.version", "value": {"stringValue": "0.1.0"}},
            ]
          },
          "scopeSpans": [
            {
              "scope": {"name": "locust.tracer"},
              "spans": [
                {
                  "traceId": _trace_id(),
                  "spanId": _span_id(),
                  "name": random.choice(
                    ["GET /api/items", "POST /api/events", "DELETE /api/session"]
                  ),
                  "kind": random.choice([1, 2, 3]),
                  "startTimeUnixNano": str(now),
                  "endTimeUnixNano": str(now + random.randint(1_000_000, 500_000_000)),
                  "attributes": [
                    {
                      "key": "http.method",
                      "value": {"stringValue": random.choice(["GET", "POST", "DELETE"])},
                    },
                    {
                      "key": "http.status_code",
                      "value": {"intValue": str(random.choice([200, 201, 400, 500]))},
                    },
                  ],
                  "status": {"code": random.choice([1, 2])},
                }
              ],
            }
          ],
        }
      ]
    }
    self.client.post(
      "/v1/traces",
      json=payload,
      headers={"Content-Type": "application/json"},
      name="/v1/traces",
    )

  @task(3)
  def send_log(self):
    severity, level = random.choice([(5, "DEBUG"), (9, "INFO"), (13, "WARN"), (17, "ERROR")])
    payload = {
      "resourceLogs": [
        {
          "resource": {
            "attributes": [
              {"key": "service.name", "value": {"stringValue": "locust-svc"}}
            ]
          },
          "scopeLogs": [
            {
              "scope": {"name": "locust.logger"},
              "logRecords": [
                {
                  "timeUnixNano": _now_ns(),
                  "severityNumber": severity,
                  "severityText": level,
                  "body": {
                    "stringValue": f"[locust] {level} request processed id={random.randint(1, 99999)}"
                  },
                  "attributes": [
                    {
                      "key": "http.status_code",
                      "value": {"intValue": str(random.choice([200, 400, 500]))},
                    },
                    {
                      "key": "trace_id",
                      "value": {"stringValue": _trace_id()},
                    },
                  ],
                }
              ],
            }
          ],
        }
      ]
    }
    self.client.post(
      "/v1/logs",
      json=payload,
      headers={"Content-Type": "application/json"},
      name="/v1/logs",
    )

  @task(2)
  def send_metric(self):
    now = _now_ns()
    payload = {
      "resourceMetrics": [
        {
          "resource": {
            "attributes": [
              {"key": "service.name", "value": {"stringValue": "locust-svc"}}
            ]
          },
          "scopeMetrics": [
            {
              "scope": {"name": "locust.meter"},
              "metrics": [
                {
                  "name": "http.server.request.duration",
                  "unit": "ms",
                  "gauge": {
                    "dataPoints": [
                      {
                        "asDouble": random.uniform(5, 2000),
                        "timeUnixNano": now,
                        "attributes": [
                          {
                            "key": "http.route",
                            "value": {
                              "stringValue": random.choice(["/api/items", "/api/events"])
                            },
                          },
                          {
                            "key": "http.status_code",
                            "value": {"intValue": str(random.choice([200, 400, 500]))},
                          },
                        ],
                      }
                    ]
                  },
                },
                {
                  "name": "locust.active.users",
                  "unit": "1",
                  "sum": {
                    "dataPoints": [
                      {
                        "asInt": str(random.randint(1, 1000)),
                        "timeUnixNano": now,
                      }
                    ],
                    "isMonotonic": False,
                    "aggregationTemporality": 2,
                  },
                },
              ],
            }
          ],
        }
      ]
    }
    self.client.post(
      "/v1/metrics",
      json=payload,
      headers={"Content-Type": "application/json"},
      name="/v1/metrics",
    )

  @task(1)
  def send_trace_batch(self):
    """20-span batch — stresses Tempo write throughput and collector batching."""
    now_ns = int(time.time_ns())
    trace_id = _trace_id()
    root_span_id = _span_id()
    spans = []
    for i in range(20):
      span: dict = {
        "traceId": trace_id,
        "spanId": _span_id() if i > 0 else root_span_id,
        "name": f"batch-op-{i}",
        "kind": 1,
        "startTimeUnixNano": str(now_ns + i * 10_000_000),
        "endTimeUnixNano": str(now_ns + i * 10_000_000 + 5_000_000),
        "status": {"code": 1},
      }
      if i > 0:
        span["parentSpanId"] = root_span_id
      spans.append(span)

    payload = {
      "resourceSpans": [
        {
          "resource": {
            "attributes": [
              {"key": "service.name", "value": {"stringValue": "locust-svc-batch"}}
            ]
          },
          "scopeSpans": [{"scope": {"name": "locust.tracer.batch"}, "spans": spans}],
        }
      ]
    }
    self.client.post(
      "/v1/traces",
      json=payload,
      headers={"Content-Type": "application/json"},
      name="/v1/traces (batch-20)",
    )


class GrafanaUser(HttpUser):
  """
  Queries Grafana's read path to surface bottlenecks in the
  Tempo / Loki / Prometheus query layer.
  """

  host = GRAFANA_HOST
  wait_time = between(2, 5)
  weight = 1

  def on_start(self):
    # admin:admin — default otel-lgtm credentials
    self.client.headers.update({"Authorization": "Basic YWRtaW46YWRtaW4="})

  @task(1)
  def query_prometheus(self):
    """Forces Grafana to query Prometheus internally."""
    self.client.post(
      "/api/ds/query",
      json={
        "queries": [{
          "datasource": {"type": "prometheus", "uid": "prometheus"},
          "expr": "up",
          "refId": "A",
          "instant": True,
        }],
        "from": "now-5m",
        "to": "now",
      },
      headers={"Content-Type": "application/json"},
      name="grafana → prometheus",
    )

  @task(1)
  def query_loki(self):
    """Forces Grafana to query Loki internally."""
    self.client.post(
      "/api/ds/query",
      json={
        "queries": [{
          "datasource": {"type": "loki", "uid": "loki"},
          "expr": '{service_name="locust-svc"}',
          "refId": "A",
          "queryType": "range",
          "maxLines": 100,
        }],
        "from": "now-5m",
        "to": "now",
      },
      headers={"Content-Type": "application/json"},
      name="grafana → loki",
    )

  @task(1)
  def query_tempo(self):
    """Forces Grafana to query Tempo internally."""
    self.client.post(
      "/api/ds/query",
      json={
        "queries": [{
          "datasource": {"type": "tempo", "uid": "tempo"},
          "queryType": "traceql",
          "query": '{resource.service.name="locust-svc"}',
          "refId": "A",
          "limit": 20,
        }],
        "from": "now-5m",
        "to": "now",
      },
      headers={"Content-Type": "application/json"},
      name="grafana → tempo",
    )


class BreakingPointShape(LoadTestShape):
  """
  Staircase ramp to find the container's breaking point.

  Each tuple is (cumulative_duration_s, total_users, spawn_rate).
  The test stops automatically when all stages are complete.

  Raise the ceiling (last stage) if the container survives comfortably —
  otel-lgtm is single-node so 400-800 concurrent users typically exposes limits.
  """

  stages = [
    (60,  10,  10),
    (120, 25,   5),
    (180, 50,  10),
    (240, 100, 20),
    (300, 200, 25),
    (420, 400, 50),
    (540, 800, 100),
  ]

  def tick(self):
    t = self.get_run_time()
    for duration, users, rate in self.stages:
      if t < duration:
        return users, rate
    return None
