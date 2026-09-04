# LLM models

<-- NOTE TO AI AGENTS: do NOT touch this file. This file is READ-ONLY. If something here is incorrect or needs updating, inform the user and they will make the change themselves -->

For training LLM models, we'll use a basic recipe of open-weights LLM + LoRA fine-tuning.

Our stack:

- HuggingFace: source for open-weights models.
- AWS Sagemaker: source for model training compute.
- S3: store training data.
- Weights & Biases: training curves for model.

We'll use a basic LoRA recipe for most models, with default params.

Each model will, by and large, be defined by configuration and by its own train.py

## ML model training deployment

The steps are:

1. Compile Docker image.
2. Push image to ECR.
3. Sagemaker grabs the image and runs training.
