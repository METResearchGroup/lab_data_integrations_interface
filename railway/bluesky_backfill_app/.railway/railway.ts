// Railway Infrastructure as Code for the backfill fetch workers.
// Not applied on deploy: run `railway config plan` / `railway config apply`
// from this directory. See docs/runbooks/HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md.
import { defineRailway, github, preserve, project, service } from "railway/iac";

export default defineRailway(() =>
  project("bluesky-backfill", {
    resources: [
      service("fetch-repos", {
        source: github("METResearchGroup/lab_data_integrations_interface", { branch: "main" }),
        build: {
          builder: "RAILPACK",
          // The worker imports from bluesky_ingestion_jetstream/ and lib/.
          watchPatterns: [
            "bluesky_backfill_app/**",
            "bluesky_ingestion_jetstream/**",
            "lib/**",
            "pyproject.toml",
            "uv.lock",
          ],
        },
        deploy: {
          startCommand: "python -m bluesky_backfill_app.fetch_repos.main",
          // SQS spreads DIDs across replicas; each holds its own buffer.
          numReplicas: 2,
          restartPolicyType: "ALWAYS",
          // SIGTERM flushes a buffer of up to 1 GB to S3 before exiting.
          drainingSeconds: 300,
        },
        // Values live on Railway, not in git.
        env: {
          AWS_ACCESS_KEY_ID: preserve(),
          AWS_SECRET_ACCESS_KEY: preserve(),
          OTEL_EXPORTER_OTLP_HEADERS: preserve(),
        },
      }),
    ],
  }),
);
