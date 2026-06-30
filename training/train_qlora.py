"""QLoRA fine-tune the Gemma 4 E4B dispatcher on data/train.jsonl.

Tuned to fit an RTX 3080 Ti (12 GB): NF4 4-bit base, LoRA adapters, batch 1 +
grad-accum, gradient checkpointing, paged 8-bit AdamW, seq len 2048.

Run:  python training/train_qlora.py
Out:  models/dispatcher-e4b-qlora/   (LoRA adapter — set dispatcher.mode=finetuned)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Pin HF cache to E: BEFORE importing torch/transformers/datasets (C: is too small).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pc_agent.hf_cache  # noqa: F401,E402

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemma_chat import normalize_for_gemma  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="huihui-ai/Huihui-gemma-4-E2B-it-abliterated")
    ap.add_argument("--data", default=str(ROOT / "data" / "train.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "models" / "dispatcher-e4b-qlora"))
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--seq_len", type=int, default=2048)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max_steps", type=int, default=-1, help="cap steps (smoke/trial runs)")
    ap.add_argument("--limit", type=int, default=0, help="use only the first N examples")
    ap.add_argument("--resume", action="store_true", help="resume from latest checkpoint in --out")
    ap.add_argument("--from_adapter", default="",
                    help="warm-start LoRA weights from an existing adapter dir (fresh optimizer)")
    ap.add_argument("--save_steps", type=int, default=200, help="checkpoint interval")
    ap.add_argument("--throttle", type=float, default=0.0,
                    help="seconds to pause after each step (lowers sustained GPU power/heat)")
    args = ap.parse_args()

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tok = AutoTokenizer.from_pretrained(args.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=quant, torch_dtype=torch.bfloat16, device_map="auto",
    )
    model.config.use_cache = False

    # Free the vision/audio towers: a text-only dispatcher never uses them, and on a
    # 12GB card they steal the ~1-1.5GB headroom training needs (otherwise it thrashes
    # at ~60s/step). Safe — text-only batches never invoke the towers.
    import gc
    _base = getattr(model, "model", model)
    for _t in ("vision_tower", "audio_tower"):
        if getattr(_base, _t, None) is not None:
            setattr(_base, _t, None)
    gc.collect()
    torch.cuda.empty_cache()

    # The language-model projections are bare Linear4bit (PEFT-supported); only the
    # vision/audio towers use Gemma4ClippableLinear (unsupported). Regex-target the
    # language model's attn+mlp projections directly, excluding the towers.
    if args.from_adapter:
        from peft import PeftModel
        print(f"warm-starting LoRA from {args.from_adapter}", flush=True)
        model = PeftModel.from_pretrained(model, args.from_adapter, is_trainable=True)
        lora = None   # model is already a PeftModel; don't create a fresh adapter
    else:
        lora = LoraConfig(
            r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
            target_modules=r"model\.language_model\.layers\.\d+\."
                           r"(self_attn\.(q_proj|k_proj|v_proj|o_proj)|"
                           r"mlp\.(gate_proj|up_proj|down_proj))",
        )

    ds = load_dataset("json", data_files=args.data, split="train")
    if args.limit:
        ds = ds.select(range(min(args.limit, len(ds))))

    def fmt(batch):
        return {"text": [tok.apply_chat_template(normalize_for_gemma(m), tokenize=False,
                                                 add_generation_prompt=False)
                         for m in batch["messages"]]}

    ds = ds.map(fmt, batched=True, remove_columns=ds.column_names)

    sft = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.accum,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        bf16=True,
        logging_steps=10,
        save_strategy="steps",      # checkpoint periodically so an early stop keeps progress
        save_steps=args.save_steps,
        save_total_limit=3,
        max_length=args.seq_len,        # TRL >=1.x renamed max_seq_length -> max_length
        dataset_text_field="text",
        packing=True,
        report_to="none",
    )

    callbacks = []
    if args.throttle > 0:
        import time as _time
        from transformers import TrainerCallback

        class _Throttle(TrainerCallback):
            def on_step_end(self, a, s, c, **k):
                import torch as _t
                _t.cuda.synchronize()
                _time.sleep(args.throttle)   # let the GPU power/heat settle between steps

        callbacks = [_Throttle()]

    trainer = SFTTrainer(model=model, args=sft, train_dataset=ds,
                         processing_class=tok, peft_config=lora, callbacks=callbacks)
    # --resume continues from the latest checkpoint in --out (survives a hang/stop).
    trainer.train(resume_from_checkpoint=args.resume)
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    print(f"\nSaved adapter -> {args.out}\nSet dispatcher.mode: finetuned in config.yaml")


if __name__ == "__main__":
    main()
