"""The brain: Gemma 4 12B for chat + (optionally) the E4B dispatcher model.

Loads 4-bit (NF4) so the 12B fits the 3080 Ti's 12 GB. Exposes a simple
.generate(prompt) and .chat(messages) interface used by run.py and dispatcher.py.
"""
from __future__ import annotations

from pathlib import Path

from . import hf_cache  # noqa: F401  (sets HF_HOME on E: before transformers loads)
from .config import Config


def _merge_system(messages: list[dict]) -> list[dict]:
    """Gemma's chat template rejects a 'system' role — fold it into the first
    user turn so a system persona can still be used."""
    if not messages or messages[0].get("role") != "system":
        return messages
    sys_txt, rest = messages[0]["content"], [dict(m) for m in messages[1:]]
    for m in rest:
        if m["role"] == "user":
            m["content"] = f"{sys_txt}\n\n{m['content']}"
            return rest
    return rest


class LLM:
    def __init__(self, model_id: str, local_dir: str | Path | None,
                 load_in_4bit: bool = True, max_new_tokens: int = 768,
                 temperature: float = 0.7, adapter_dir: str | Path | None = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        source = str(local_dir) if local_dir and Path(local_dir).exists() else model_id
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

        quant = None
        if load_in_4bit:
            quant = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )

        self.tok = AutoTokenizer.from_pretrained(source)
        self.model = AutoModelForCausalLM.from_pretrained(
            source,
            quantization_config=quant,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        if adapter_dir and Path(adapter_dir).exists():
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, str(adapter_dir))
        self.model.eval()

    def chat(self, messages: list[dict], max_new_tokens: int | None = None,
             temperature: float | None = None) -> str:
        import torch
        inputs = self.tok.apply_chat_template(
            _merge_system(messages), add_generation_prompt=True, return_tensors="pt"
        ).to(self.model.device)
        temp = self.temperature if temperature is None else temperature
        with torch.no_grad():
            out = self.model.generate(
                inputs,
                max_new_tokens=max_new_tokens or self.max_new_tokens,
                do_sample=temp > 0,
                temperature=max(temp, 1e-5),
                pad_token_id=self.tok.eos_token_id,
            )
        return self.tok.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()

    def generate(self, prompt: str, max_new_tokens: int | None = None,
                 temperature: float | None = None) -> str:
        return self.chat([{"role": "user", "content": prompt}],
                         max_new_tokens or 256,
                         0.0 if temperature is None else temperature)


def load_brain(cfg: Config) -> LLM:
    return LLM(
        model_id=cfg.get("brain.model_id"),
        local_dir=cfg.path("brain.local_dir"),
        load_in_4bit=cfg.get("brain.load_in_4bit", True),
        max_new_tokens=cfg.get("brain.max_new_tokens", 768),
        temperature=cfg.get("brain.temperature", 0.7),
    )


def load_dispatcher(cfg: Config, brain: LLM | None = None) -> LLM:
    """In 'prompt' mode reuse the brain; in 'finetuned' mode load E4B + adapter."""
    if cfg.get("dispatcher.mode", "prompt") == "prompt" and brain is not None:
        return brain
    return LLM(
        model_id=cfg.get("dispatcher.base_model_id"),
        local_dir=None,
        load_in_4bit=cfg.get("dispatcher.load_in_4bit", True),
        max_new_tokens=cfg.get("dispatcher.max_new_tokens", 256),
        temperature=cfg.get("dispatcher.temperature", 0.0),
        adapter_dir=cfg.path("dispatcher.adapter_dir"),
    )
