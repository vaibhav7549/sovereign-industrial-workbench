"""Sovereign encryption layer: CKKS homomorphic search + differential privacy.

Modules
  keys      master key -> HKDF subkeys, AES-256-GCM, MACs
  he        CKKS key holder (secret) and evaluator (public-only) on TenSEAL
  dp        Laplace mechanism for embeddings; Opacus DP-SGD hook for training
  vault     local SQLite store of CKKS ciphertexts + sealed chunk text
  envelope  text extraction, chunking, the encrypted atom format for Atomic
  audit     HMAC-chained, plaintext-free audit log
  pipeline  ingest / search orchestration
"""
