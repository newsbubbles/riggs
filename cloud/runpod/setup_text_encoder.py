"""Stage Kimodo's text encoder from a non-gated, license-compliant Llama-3 mirror.

Why: Kimodo's encoder is McGill-NLP's public LLM2Vec (mntp + supervised), but those
sit on Llama-3-8B, and loading them pulls Meta's GATED copy of the base weights —
which needs manual Meta approval. Llama 3's Community License permits redistribution
(mirrors must keep the license + a "Built with Meta Llama 3" notice), so we use a
non-gated mirror of the identical weights. This removes the Meta gate: animation then
needs only an HF token.

What it does (all into $TEXT_ENCODERS_DIR, which Kimodo joins onto the encoder ids):
  1. download the two public McGill LLM2Vec repos (base mntp + supervised peft)
  2. download the Llama-3 base from a non-gated mirror, into the meta-llama/ path,
     and force its config.json `_name_or_path` to the canonical id (so Kimodo's
     Llama-3 chat-template branch fires and tokenization matches training)
  3. rewrite each McGill repo's adapter_config base_model_name_or_path to the local
     mirror so nothing reaches out to the gated meta-llama repo at load time

Then run kimodo_gen with TEXT_ENCODERS_DIR set and TEXT_ENCODER_MODE=local.

Env: TEXT_ENCODERS_DIR (required), HF_TOKEN/HF_ACCESS_TOKEN (for the public downloads),
     KIMODO_LLAMA_MIRROR (default NousResearch/Meta-Llama-3-8B-Instruct).
"""
import json
import os
import sys

from huggingface_hub import snapshot_download

CANON = "meta-llama/Meta-Llama-3-8B-Instruct"
MNTP = "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp"          # encoder base (public)
SUP = "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"  # peft (public)


def main():
    ted = os.environ["TEXT_ENCODERS_DIR"]
    token = os.environ.get("HF_TOKEN") or os.environ.get("HF_ACCESS_TOKEN")
    mirror = os.environ.get("KIMODO_LLAMA_MIRROR", "NousResearch/Meta-Llama-3-8B-Instruct")

    def fetch(repo_id, dst_rel):
        dst = os.path.join(ted, dst_rel)
        if not os.path.isdir(dst) or not os.listdir(dst):
            print(f">> downloading {repo_id} -> {dst}")
            snapshot_download(repo_id=repo_id, local_dir=dst, token=token)
        return dst

    # 1. public McGill encoder pieces
    mntp_dir = fetch(MNTP, MNTP)
    fetch(SUP, SUP)
    # 2. Llama-3 base from a non-gated mirror, placed under the canonical path
    base_dir = fetch(mirror, CANON)

    # force canonical _name_or_path so Kimodo's Llama-3 tokenization branch matches
    cfg_path = os.path.join(base_dir, "config.json")
    if os.path.isfile(cfg_path):
        cfg = json.load(open(cfg_path))
        cfg["_name_or_path"] = CANON
        json.dump(cfg, open(cfg_path, "w"), indent=2)

    # 3. point each McGill adapter_config at the LOCAL base (never the gated repo)
    for d in (mntp_dir, os.path.join(ted, SUP)):
        ac = os.path.join(d, "adapter_config.json")
        if os.path.isfile(ac):
            data = json.load(open(ac))
            if "base_model_name_or_path" in data:
                data["base_model_name_or_path"] = base_dir
                json.dump(data, open(ac, "w"), indent=2)
                print(f">> repointed adapter base in {ac}")

    print("TEXT_ENCODER_READY")


if __name__ == "__main__":
    main()
