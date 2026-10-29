"""
vma_api_server.py
=================
VMA Quantum を REST API サーバーとして展開

3つのAPIエンドポイント:
  1. POST /api/judge       - 量子ビット判定
  2. POST /api/compress    - ブロッホ差分圧縮
  3. POST /api/quantum_fx  - 拡張量子FX計算

HWリソース: ローカルCPU (GPU/TPU不要)
デプロイ先: 自社サーバー / AWS Lambda / Azure Functions / Google Cloud Run

依存: flask / numpy / sympy
"""

import json
import math
from functools import lru_cache
from fractions import Fraction

import numpy as np
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
# Module 1: Quantum Bit Judgment
# ============================================================

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

THETA_C = np.pi * sigmoid(1.0)

def make_qubit(theta, phi=0.0):
    alpha = np.cos(theta / 2)
    beta = np.exp(1j * phi) * np.sin(theta / 2)
    return np.array([alpha, beta])

def qubit_from_sigmoid(x):
    s = sigmoid(x)
    theta = np.pi * s
    phi = 2 * np.pi * s
    return make_qubit(theta, phi), theta, phi

def make_judge_qubit(theta_c=THETA_C, sharpness=1.0):
    theta_j = np.pi * (theta_c / np.pi)
    phi_j = theta_c * sharpness
    return make_qubit(theta_j, phi_j)

def controlled_phase(psi, judge, coupling=1.0):
    composite = np.kron(psi, judge)
    gamma = coupling * np.pi * sigmoid(1.0)
    C = np.diag([1, 1, 1, np.exp(1j * gamma)])
    return C @ composite

def measure_judge(composite_state):
    rho_full = np.outer(composite_state, composite_state.conj())
    rho_judge = np.zeros((2, 2), dtype=complex)
    rho_judge[0, 0] = rho_full[0, 0] + rho_full[2, 2]
    rho_judge[1, 1] = rho_full[1, 1] + rho_full[3, 3]
    p0 = np.real(rho_judge[0, 0])
    p1 = np.real(rho_judge[1, 1])
    margin = abs(p1 - p0)
    if margin < 0.1:
        verdict = "superposition"
    elif p1 > p0:
        verdict = "quantum"
    else:
        verdict = "classical"
    return p0, p1, verdict

def quantum_score(psi, theta_c=THETA_C):
    psi_c = make_qubit(theta_c, theta_c)
    F = np.abs(np.dot(psi.conj(), psi_c))**2
    return 1 - F, F

# ============================================================
# Module 2: Bloch Delta Compression
# ============================================================

@lru_cache(maxsize=128)
def compute_k(kp: int) -> int:
    n = 2 * kp + 1
    return (n**5 - n) // 120

@lru_cache(maxsize=128)
def compute_c_bitlen(kp: int) -> int:
    n = 2 * kp + 1
    return 2 * (n + 1)

def compute_m(kp: int) -> int:
    n = 2 * kp + 1
    return 2 * (n + 1)

@lru_cache(maxsize=128)
def kp_from_m(m: int) -> int:
    n = m // 2 - 1
    kp = (n - 1) // 2
    return kp

def encode_fast(kp: int) -> dict:
    n = 2 * kp + 1
    k = compute_k(kp)
    m = compute_m(kp)
    p = math.log2(m)
    c_bitlen = compute_c_bitlen(kp)
    
    m_bits = f"{m:016b}"
    p_int = int(p)
    p_frac = p - p_int
    p_int_bits = f"{p_int:04b}"
    
    p_frac_bits = []
    pf = p_frac
    for _ in range(12):
        pf *= 2
        bit = int(pf)
        p_frac_bits.append(str(bit))
        pf -= bit
    p_bits = p_int_bits + "".join(p_frac_bits)
    
    return {
        "kp": kp, "n": n, "k": k, "m": m, "p": p, "c_bitlen": c_bitlen,
        "m_bits": m_bits, "p_bits": p_bits
    }

def decode1_fast(m_bits: str) -> dict:
    m = int(m_bits, 2)
    kp = kp_from_m(m)
    n = 2 * kp + 1
    k = compute_k(kp)
    return {"m": m, "n": n, "kp": kp, "k": k}

def decode2_fast(p_bits: str) -> dict:
    p_int_bits = p_bits[:4]
    p_frac_bits = p_bits[4:]
    p_int = int(p_int_bits, 2)
    p_frac = sum(int(b) * (2 ** (-(i + 1))) for i, b in enumerate(p_frac_bits))
    p = p_int + p_frac
    m = round(2 ** p)
    kp = kp_from_m(m)
    n = 2 * kp + 1
    k = compute_k(kp)
    return {"p": p, "m": m, "n": n, "kp": kp, "k": k}

# ============================================================
# Module 3: Quantum FX
# ============================================================

class NormFunction:
    def __init__(self, expr_str, var_str='x'):
        import sympy as sp
        self.expr_str = expr_str
        self._var = sp.Symbol(var_str, real=True)
        self._expr = sp.sympify(expr_str)
        self._func = sp.lambdify(self._var, self._expr, 'numpy')
    
    def __call__(self, x):
        return float(self._func(x))

class QuantumState:
    def __init__(self, n, fn, x=1.0):
        self.n = n
        self.dim = 2**n
        self.fn = fn
        self.x = x
        self._psi = np.zeros(self.dim, dtype=complex)
        self._psi[0] = np.sqrt(fn(x))
    
    @property
    def norm2(self):
        return float(np.real(np.dot(np.conj(self._psi), self._psi)))
    
    @property
    def fx(self):
        return self.fn(self.x)
    
    def update_x(self, nx):
        r = np.sqrt(self.fn(nx) / self.fn(self.x))
        self.x = nx
        self._psi *= r

# ============================================================
# REST API Endpoints
# ============================================================

@app.route('/api/judge', methods=['POST'])
def api_judge():
    """
    量子ビット判定 API
    
    Request:
      {
        "x": float (因果的情報量),
        "sharpness": float (判定の鋭さ, default=1.0),
        "coupling": float (結合度, default=1.0)
      }
    
    Response:
      {
        "theta_degrees": float,
        "p_classical": float,
        "p_quantum": float,
        "quantum_score": float,
        "fidelity": float,
        "verdict": "quantum|classical|superposition",
        "critical_angle_degrees": float
      }
    """
    try:
        data = request.get_json()
        x = data.get('x', 1.0)
        sharpness = data.get('sharpness', 1.0)
        coupling = data.get('coupling', 1.0)
        
        judge = make_judge_qubit(sharpness=sharpness)
        psi, theta, phi = qubit_from_sigmoid(x)
        comp = controlled_phase(psi, judge, coupling=coupling)
        p0, p1, verdict = measure_judge(comp)
        score, F = quantum_score(psi)
        
        return jsonify({
            "status": "success",
            "theta_degrees": float(np.degrees(theta)),
            "p_classical": float(p0),
            "p_quantum": float(p1),
            "quantum_score": float(score),
            "fidelity": float(F),
            "verdict": verdict,
            "critical_angle_degrees": float(np.degrees(THETA_C))
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/compress', methods=['POST'])
def api_compress():
    """
    ブロッホ差分圧縮 API
    
    Request:
      {
        "kp": int (0..255),
        "verify": bool (デコード検証, default=true)
      }
    
    Response:
      {
        "kp": int,
        "n": int,
        "m": int,
        "p": float,
        "m_bits": str (16bit),
        "p_bits": str (16bit),
        "c_bitlen": int,
        "decode1_kp": int (if verify=true),
        "decode2_kp": int (if verify=true),
        "match": bool (if verify=true)
      }
    """
    try:
        data = request.get_json()
        kp = int(data.get('kp', 0))
        verify = data.get('verify', True)
        
        if kp < 0 or kp > 255:
            return jsonify({"status": "error", "message": "kp must be 0..255"}), 400
        
        enc = encode_fast(kp)
        result = {
            "status": "success",
            "kp": enc["kp"],
            "n": enc["n"],
            "m": enc["m"],
            "p": float(enc["p"]),
            "m_bits": enc["m_bits"],
            "p_bits": enc["p_bits"],
            "c_bitlen": enc["c_bitlen"]
        }
        
        if verify:
            d1 = decode1_fast(enc["m_bits"])
            d2 = decode2_fast(enc["p_bits"])
            match = d1["kp"] == d2["kp"] == enc["kp"]
            result.update({
                "decode1_kp": d1["kp"],
                "decode2_kp": d2["kp"],
                "match": match
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/quantum_fx', methods=['POST'])
def api_quantum_fx():
    """
    拡張量子FX API
    
    Request:
      {
        "function": str (e.g. "1 + sin(x)**2"),
        "n_qubits": int (1..10),
        "x_values": list of float,
        "x_update": bool (state更新, default=false)
      }
    
    Response:
      {
        "function": str,
        "n_qubits": int,
        "results": [
          {
            "x": float,
            "fx": float,
            "norm2": float,
            "ratio": float
          }
        ]
      }
    """
    try:
        data = request.get_json()
        fn_str = data.get('function', '1 + sin(x)**2')
        n_qubits = int(data.get('n_qubits', 4))
        x_values = data.get('x_values', [0.5, 1.0, np.pi])
        x_update = data.get('x_update', False)
        
        if n_qubits < 1 or n_qubits > 10:
            return jsonify({"status": "error", "message": "n_qubits must be 1..10"}), 400
        
        fn = NormFunction(fn_str)
        st = QuantumState(n_qubits, fn, x_values[0] if x_values else 1.0)
        
        results = []
        for xv in x_values:
            if x_update:
                st.update_x(float(xv))
            else:
                # 修正(2026-10-29): st.x の直接代入では振幅が追従せず
                # norm2 が初期xのまま残るため、そのxで状態を作り直す
                st = QuantumState(n_qubits, fn, float(xv))
            
            ratio = st.norm2 / st.fx if st.fx > 0 else 0
            results.append({
                "x": float(xv),
                "fx": float(st.fx),
                "norm2": float(st.norm2),
                "ratio": float(ratio)
            })
        
        return jsonify({
            "status": "success",
            "function": fn_str,
            "n_qubits": n_qubits,
            "results": results
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/health', methods=['GET'])
def api_health():
    """ヘルスチェック"""
    return jsonify({
        "status": "ok",
        "service": "VMA Quantum API",
        "modules": ["judge", "compress", "quantum_fx"],
        "hw": "local_cpu"
    })

@app.route('/api/info', methods=['GET'])
def api_info():
    """API情報"""
    return jsonify({
        "service": "VMA Quantum Integrated Demo",
        "version": "1.0.0",
        "endpoints": [
            {
                "path": "/api/judge",
                "method": "POST",
                "description": "Quantum bit judgment system"
            },
            {
                "path": "/api/compress",
                "method": "POST",
                "description": "Bloch sphere delta compression"
            },
            {
                "path": "/api/quantum_fx",
                "method": "POST",
                "description": "Extended quantum FX framework"
            },
            {
                "path": "/api/health",
                "method": "GET",
                "description": "Health check"
            }
        ],
        "hw": "local_cpu",
        "memory_optimized": True,
        "api_format": "REST/JSON"
    })

# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("="*70)
    print("VMA Quantum API Server")
    print("="*70)
    print("\nEndpoints:")
    print("  POST /api/judge       - Quantum bit judgment")
    print("  POST /api/compress    - Bloch delta compression")
    print("  POST /api/quantum_fx  - Extended quantum FX")
    print("  GET  /api/health      - Health check")
    print("  GET  /api/info        - API information")
    print("\nStarting server on http://localhost:5000")
    print("="*70)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
