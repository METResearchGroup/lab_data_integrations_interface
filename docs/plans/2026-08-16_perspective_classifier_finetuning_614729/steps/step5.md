# Step 5: Wire up SageMaker training and its supporting IAM role

## Goal

Any label can train on SageMaker instead of a local machine, using a scoped IAM role instead of broad account access.

## Scope

Step 5 adds the launch script and the Terraform module for its execution role. It does not change `trainer.py`, since SageMaker runs the exact same `train.py` entrypoint against channel-mounted data.

## Re-verify AWS access first, with your own credentials

The findings in `plan.md` came from one IAM user's credentials during planning and may not match the access the implementer has. Before writing any code in this step, run these checks and record the output in `README.md`:

```bash
python3 -c "import boto3; print(boto3.client('sts').get_caller_identity())"
python3 -c "import boto3; print(boto3.client('s3').list_objects_v2(Bucket='lab-data-integrations-interface', MaxKeys=1))"
python3 -c "import boto3; print(boto3.client('sagemaker').list_training_jobs(MaxResults=1))"
```

If any of these three commands fail with `AccessDenied`, stop and flag it. Do not attempt to work around a permissions gap by widening scope beyond what this step's Terraform module asks for.

## Files to inspect

- [`terraform/bluesky_ingestion_jetstream/maintenance.tf`](../../../terraform/bluesky_ingestion_jetstream/maintenance.tf) for this repo's existing `aws_iam_role` plus `aws_iam_role_policy` pattern scoped to one S3 prefix.
- [`terraform/data_platform/main.tf`](../../../terraform/data_platform/main.tf), which declares the `lab-data-integrations-interface` bucket this new role will be scoped into.
- The `mirrorView-task` files `experiments/predict_keep_remove_2026_07_01/models/modernbert/main.tf` and `launch_sagemaker.py`, fetched the same way as in Step 2, for the exact IAM policy statements and the `HuggingFace` estimator call this step adapts.

## Files allowed to change

- `terraform/perspective_classifiers/main.tf`
- `experiments/perspective_classifiers_2026_08_16/launch_sagemaker.py`
- `experiments/perspective_classifiers_2026_08_16/README.md`

## Files forbidden to change

- `terraform/bluesky_ingestion_jetstream/**`
- `terraform/data_platform/**`
- `experiments/perspective_classifiers_2026_08_16/trainer.py`

## Contract to freeze

`terraform/perspective_classifiers/main.tf` creates one `aws_iam_role` named `perspective-classifiers-sagemaker-execution`, trusted by `sagemaker.amazonaws.com`, with one `aws_iam_role_policy` scoped to:

- List and read/write/delete objects under `s3://lab-data-integrations-interface/perspective-classifiers-training/*` only, plus `s3:ListBucket` on the bucket itself conditioned on that same prefix, mirroring the condition style in `maintenance.tf`.
- CloudWatch Logs write access under `/aws/sagemaker/*` log groups.
- `ecr:GetAuthorizationToken` and pull-only ECR actions scoped to the Amazon Deep Learning Container account, since this step uses SageMaker's built-in Hugging Face container and never pushes a custom image.
- `cloudwatch:PutMetricData` scoped to the `aws/sagemaker/TrainingJobs` namespace.

It outputs `sagemaker_execution_role_arn`.

`launch_sagemaker.py` mirrors `mirrorView-task`'s `launch_sagemaker.py`:

- `--label` (required, must be in `labels.TRAINED_LABELS`), `--config` (default `configs/base.yaml`), `--run-id` (default a UTC timestamp), `--wait`, `--limit`, `--num-train-epochs`.
- Uploads `data/<label>/train.parquet` and `data/<label>/test.parquet` to `s3://lab-data-integrations-interface/perspective-classifiers-training/<label>/<run_id>/data/`.
- Submits a `sagemaker.huggingface.HuggingFace` estimator with `entry_point="train.py"`, `source_dir` set to the experiment package directory, `role` read from a required `SAGEMAKER_ROLE_ARN` environment variable (the Terraform output above), `instance_type="ml.g4dn.xlarge"`, and the same `transformers_version` / `pytorch_version` / `py_version` combination already proven for ModernBERT in `mirrorView-task`.
- Passes `--label` and `--config` through as SageMaker hyperparameters so the same `train.py` entrypoint runs unmodified inside the job.

## Implementation order

1. Run the re-verification commands above and record the result.
2. Write `terraform/perspective_classifiers/main.tf`, then run `terraform init` and `terraform plan` inside `terraform/perspective_classifiers/` and read the plan output before ever running `terraform apply`.
3. Apply it, capture `sagemaker_execution_role_arn` from the output, and record it in `README.md` (the ARN itself is not a secret; do not record the AWS access keys used to create it).
4. Write `launch_sagemaker.py`.
5. Launch one real SageMaker run for one label with `--limit 64 --num-train-epochs 1 --wait` and confirm it finishes with `TrainingJobStatus` of `Completed`.

## Pass

- `terraform -chdir=terraform/perspective_classifiers plan` shows only the new role, its policy, and its outputs, and touches no other Terraform state.
- `PYTHONPATH=. uv run --extra modernbert-training python experiments/perspective_classifiers_2026_08_16/launch_sagemaker.py --label moral_outrage --limit 64 --num-train-epochs 1 --wait` prints a job name and exits `0`.
- `python3 -c "import boto3; print(boto3.client('sagemaker').describe_training_job(TrainingJobName='<printed job name>')['TrainingJobStatus'])"` prints `Completed`.

## Fail

- Reusing the `mirrorView-task` role (`mirrorview-qwen-finetune-sm-exec` or `modernbert-sagemaker-execution`) instead of creating a role scoped to this project's own bucket and prefix.
- A policy statement scoped to the whole `lab-data-integrations-interface` bucket instead of the `perspective-classifiers-training/` prefix.
- Running `terraform apply` before reading `terraform plan` output, or running it against credentials that have not been re-verified per the steps above.
