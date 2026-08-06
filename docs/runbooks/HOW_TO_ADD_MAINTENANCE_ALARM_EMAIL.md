# How to Add an Email for Maintenance Alarms

## Overview

The Iceberg maintenance jobs in [`maintenance.tf`](../../terraform/bluesky_ingestion_jetstream/maintenance.tf) raise a CloudWatch alarm when a Step Functions execution fails. The alarm publishes to an SNS topic that has **no subscribers by default**. This runbook adds one.

Terraform creates the topic, the alarm, and the subscription request. You confirm the subscription by clicking a link in an email — AWS will not activate an email subscription without that. `PendingConfirmation` after `apply` is expected, not a failure.

---

## Prerequisites

- AWS credentials for **us-east-2** with SNS, CloudWatch, and IAM permissions.
- `terraform init` already run in `terraform/bluesky_ingestion_jetstream/`.
- Access to the inbox being subscribed.

---

## Step 1: Set the address

Create `terraform/bluesky_ingestion_jetstream/terraform.tfvars`:

```hcl
maintenance_alarm_email = "you@example.com"
```

The variable defaults to `""`, which creates no subscription (`count = 0`). `**/*.tfvars` is gitignored.

---

## Step 2: Apply

```bash
terraform apply
```

Expected, assuming the rest of the stack is up:

```
  # aws_sns_topic_subscription.maintenance_alarms_email[0] will be created
Plan: 1 to add, 0 to change, 0 to destroy.
```

---

## Step 3: Confirm the subscription

AWS sends **"AWS Notification - Subscription Confirmation"** from `no-reply@sns.amazonaws.com`. Click **Confirm subscription**. The link expires after 3 days; check spam if it does not arrive.

---

## Step 4: Verify

```bash
aws sns list-subscriptions-by-topic \
    --region us-east-2 \
    --topic-arn "$(aws sns list-topics --region us-east-2 \
        --query "Topics[?ends_with(TopicArn, ':bluesky_raw_maintenance_alarms')].TopicArn | [0]" \
        --output text)" \
    --query 'Subscriptions[].{Endpoint:Endpoint,Arn:SubscriptionArn}' \
    --output table
```

A confirmed subscription shows a real ARN. An unconfirmed one shows the literal string `PendingConfirmation`, meaning Step 3 did not complete.

---

## Step 5: Test delivery

Force the alarm rather than waiting for a real failure. This exercises alarm → topic → subscription → inbox without touching any table.

```bash
aws cloudwatch set-alarm-state \
    --region us-east-2 \
    --alarm-name bluesky_raw_maintenance_failed \
    --state-value ALARM \
    --state-reason "Testing alarm delivery"
```

Mail should arrive within a minute or two. CloudWatch returns the alarm to `OK` on the next evaluation, or reset it immediately with `--state-value OK`.

---

## Adding more than one recipient

`maintenance_alarm_email` takes a single address. Subscribe a distribution list and manage membership in your mail provider, or add another `aws_sns_topic_subscription` on the same topic — `https` for a webhook, AWS Chatbot for Slack. Only `email` needs manual confirmation.

---

## Important notes

Keep `terraform.tfvars`. Terraform reads it on every apply, and without it `maintenance_alarm_email` falls back to `""`, which destroys the subscription — the alarm keeps firing into a topic with no subscribers, so nothing looks broken but no mail arrives.

**It is gitignored, so anyone else applying this stack needs their own copy with the same value.**
