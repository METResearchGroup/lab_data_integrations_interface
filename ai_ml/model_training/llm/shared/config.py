from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
QWEN_LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]


@dataclass(frozen=True)
class TrainConfig:
    """Settings for one Qwen LoRA training run."""

    model_id: str = DEFAULT_MODEL_ID
    output_dir: Path = Path("/tmp/qwen-lora")
    learning_rate: float = 2e-4
    num_epochs: int = 1
    max_steps: int | None = None
    batch_size: int = 2
    max_seq_length: int = 256
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    seed: int = 1
    target_modules: Iterable[str] = QWEN_LORA_TARGET_MODULES
    bias: str = "none"
    task_type: str = "CAUSAL_LM"
    dtype: torch.float32
