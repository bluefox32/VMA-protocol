# VMA-protocol

Materials for the VMA protocol. The original distribution is stored as zip archives (files 104.zip and files 105.zip); fixed unpacked sources are also provided at the repository root (see below).

## Contents

- `files 104.zip` — VMA Quantum REST API set (server, client, deployment guide)
- `files 105.zip` — VMA Quantum all-in-one (single-file server / CLI / local test)

## Fixed sources (2026-10-29)

- `vma_api_server.py` — the files 104 server with the quantum FX endpoint fixed
- `vma_quantum_all_in_one.py` — the files 105 all-in-one with the same FX fix

Fix detail: in the FX endpoint, the state was previously assigned a new x directly (`st.x = ...`), so the amplitudes never followed and `norm2`/`ratio` stayed at the first x value for every later x. The fixed code re-scales via `update_x` (105) or re-initialises the state per x (104 default path), and all ratios now evaluate to 1.0.

The zip archives above were also replaced with FX-fixed builds on 2026-10-29, so the archives and the root `.py` files now contain the same fixed code.

## License

MIT License - see [LICENSE](LICENSE) for details.
