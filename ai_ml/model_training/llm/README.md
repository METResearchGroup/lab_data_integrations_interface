# LLM models

For training LLM models, we'll use a basic recipe of open-weights LLM + LoRA fine-tuning.

Our stack:

- HuggingFace: source for open-weights models.
- AWS Sagemaker: source for model training compute.
- S3: store training data.
- Weights & Biases: training curves for model.

We'll use a basic LoRA recipe for most models, with default params.

Each model will, by and large, be defined by configuration and by its own train.py
