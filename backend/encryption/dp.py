"""Differential privacy for embeddings (Option C).

Mechanism: the Laplace mechanism applied to each embedding independently
(local DP). For a privacy budget epsilon the released vector satisfies

    Pr[M(x) in S] <= exp(epsilon) * Pr[M(x') in S]   for ANY two chunks x, x'.

Getting the sensitivity right matters. After clipping embeddings to the unit L2
ball (radius C), the worst-case L1 distance between two embeddings in d
dimensions is

    Delta_1 = 2 * C * sqrt(d)          (about 55.4 for d = 768, C = 1)

so the per-coordinate noise scale is b = Delta_1 / epsilon. Using
`Laplace(0, 1/epsilon)` (as in some write-ups) silently assumes Delta_1 = 1 and
does NOT give epsilon-DP for unit embeddings.

Consequence that must be stated plainly: at epsilon = 1.0 the noise per
coordinate (~55) is about 1500x larger than the signal per coordinate (~0.036),
so retrieval over noised embeddings is no better than random. See
docs/ENCRYPTION_SECURITY_REPORT.md and scripts/bench_dp_utility.py for the
measured privacy/utility curve. Epsilon is therefore a deployment decision, not
a constant; the mechanism below is exact for whatever epsilon is configured.

Re-normalising after adding noise is post-processing, so it does not weaken
the guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

_rng = np.random.default_rng()  # OS-seeded PCG64


@dataclass(frozen=True)
class DPParams:
    epsilon: float
    dim: int
    clip_norm: float = 1.0

    @property
    def l1_sensitivity(self) -> float:
        return 2.0 * self.clip_norm * math.sqrt(self.dim)

    @property
    def laplace_scale(self) -> float:
        return self.l1_sensitivity / self.epsilon

    def describe(self) -> dict:
        return {
            "mechanism": "laplace",
            "scope": "per-embedding (local DP)",
            "epsilon": self.epsilon,
            "delta": 0.0,
            "clip_norm_l2": self.clip_norm,
            "l1_sensitivity": round(self.l1_sensitivity, 4),
            "noise_scale_b": round(self.laplace_scale, 6),
        }


def clip_l2(vec: np.ndarray, clip_norm: float = 1.0) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return vec * min(1.0, clip_norm / norm)


def laplace_embedding(
    embedding: Sequence[float],
    epsilon: float,
    clip_norm: float = 1.0,
    rng: Optional[np.random.Generator] = None,
    normalize_input: bool = True,
) -> tuple[np.ndarray, DPParams]:
    """Return (noisy unit-norm embedding, params). Raises on epsilon <= 0."""
    if not (epsilon > 0 and math.isfinite(epsilon)):
        raise ValueError("epsilon must be a positive finite number")
    x = np.asarray(embedding, dtype=np.float64)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("embedding must be a non-empty 1-D vector")
    if normalize_input:
        n = np.linalg.norm(x)
        x = x / n if n > 0 else x
    x = clip_l2(x, clip_norm)
    params = DPParams(epsilon=epsilon, dim=x.size, clip_norm=clip_norm)
    noise = (rng or _rng).laplace(0.0, params.laplace_scale, size=x.size)
    y = x + noise
    n = np.linalg.norm(y)
    return (y / n if n > 0 else y), params


# --------------------------------------------------------------------------
# Training-time DP (Opacus). Optional; torch/opacus are NOT in the runtime image.
# --------------------------------------------------------------------------
def setup_privacy_engine_sync(
    model: Any,
    optimizer: Any,
    data_loader: Any,
    epsilon: float = 1.0,
    delta: float = 1e-5,
    epochs: int = 1,
    max_grad_norm: float = 1.0,
) -> dict:
    """Attach Opacus DP-SGD to an existing (model, optimizer, data_loader).

    Returns a dict with the wrapped objects, the privacy engine and the
    effective sampling rate. The caller must build `optimizer` *after* making
    the model Opacus-compatible (see ModuleValidator.fix), because fix() can
    replace layers and therefore parameters.
    """
    try:
        from opacus import PrivacyEngine
        from opacus.validators import ModuleValidator
    except ImportError as exc:  # pragma: no cover - depends on optional deps
        raise RuntimeError(
            "Opacus is not installed. Install the optional training stack with "
            "`pip install -r requirements-dp-training.txt`."
        ) from exc

    errors = ModuleValidator.validate(model, strict=False)
    if errors:
        raise ValueError(
            "Model is not Opacus-compatible: "
            + "; ".join(str(e) for e in errors[:5])
            + ". Run `model = ModuleValidator.fix(model)` BEFORE creating the optimizer."
        )

    dataset_size = len(data_loader.dataset)
    batch_size = getattr(data_loader, "batch_size", None) or 1
    engine = PrivacyEngine(accountant="rdp")
    private_model, private_optimizer, private_loader = engine.make_private_with_epsilon(
        module=model,
        optimizer=optimizer,
        data_loader=data_loader,
        target_epsilon=epsilon,
        target_delta=delta,
        epochs=epochs,
        max_grad_norm=max_grad_norm,
    )
    return {
        "privacy_engine": engine,
        "model": private_model,
        "optimizer": private_optimizer,
        "data_loader": private_loader,
        "sample_rate": batch_size / dataset_size,
        "noise_multiplier": private_optimizer.noise_multiplier,
        "target_epsilon": epsilon,
        "target_delta": delta,
        "epsilon_spent": lambda: engine.get_epsilon(delta),
    }
