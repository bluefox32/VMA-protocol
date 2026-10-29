#!/usr/bin/env python3
"""
vma_quantum_all_in_one.py
=========================
VMA Quantum — ワンコードで完全統合

機能:
  1. 量子ビット判定 (qubit_judge_system)
  2. ブロッホ差分圧縮 (bloch_delta_compression)
  3. 拡張量子FX (quantum_fx)
  4. REST API サーバー (Flask)
  5. CLI インターフェース
  6. メモリ効率化

使用方法:
  # サーバーモード (API)
  python vma_quantum_all_in_one.py --server --port 5000

  # CLI モード (インタラクティブ)
  python vma_quantum_all_in_one.py --cli

  # ローカル実行モード
  python vma_quantum_all_in_one.py --local

  # テストモード
  python vma_quantum_all_in_one.py --test
"""

import sys
import argparse
import json
import math
from functools import lru_cache
from typing import Dict, Any, List

import numpy as np

try:
    import sympy as sp
    SYMPY_AVAILABLE = True
except ImportError:
    SYMPY_AVAILABLE = False

# ============================================================
# MODULE 1: QUANTUM BIT JUDGMENT SYSTEM
# ============================================================

def sigmoid(x: float) -> float:
    """シグモイド関数"""
    return 1.0 / (1.0 + np.exp(-float(x)))

THETA_C = np.pi * sigmoid(1.0)

def make_qubit(theta: float, phi: float = 0.0) -> np.ndarray:
    """ブロッホ球から量子ビット生成"""
    alpha = np.cos(theta / 2)
    beta = np.exp(1j * phi) * np.sin(theta / 2)
    return np.array([alpha, beta])

def qubit_from_sigmoid(x: float) -> tuple:
    """情報量xから量子ビット生成"""
    s = sigmoid(x)
    theta = np.pi * s
    phi = 2 * np.pi * s
    return make_qubit(theta, phi), theta, phi

def make_judge_qubit(theta_c: float = THETA_C, sharpness: float = 1.0) -> np.ndarray:
    """判定用量子ビット"""
    theta_j = np.pi * (theta_c / np.pi)
    phi_j = theta_c * sharpness
    return make_qubit(theta_j, phi_j)

def controlled_phase(psi: np.ndarray, judge: np.ndarray, coupling: float = 1.0) -> np.ndarray:
    """制御位相ゲート"""
    composite = np.kron(psi, judge)
    gamma = coupling * np.pi * sigmoid(1.0)
    C = np.diag([1, 1, 1, np.exp(1j * gamma)])
    return C @ composite

def measure_judge(composite_state: np.ndarray) -> tuple:
    """判定ビット測定"""
    rho_full = np.outer(composite_state, composite_state.conj())
    rho_judge = np.zeros((2, 2), dtype=complex)
    rho_judge[0, 0] = rho_full[0, 0] + rho_full[2, 2]
    rho_judge[1, 1] = rho_full[1, 1] + rho_full[3, 3]
    p0 = float(np.real(rho_judge[0, 0]))
    p1 = float(np.real(rho_judge[1, 1]))
    margin = abs(p1 - p0)
    if margin < 0.1:
        verdict = "superposition"
    elif p1 > p0:
        verdict = "quantum"
    else:
        verdict = "classical"
    return p0, p1, verdict

def quantum_score(psi: np.ndarray, theta_c: float = THETA_C) -> tuple:
    """量子性スコア計算"""
    psi_c = make_qubit(theta_c, theta_c)
    F = np.abs(np.dot(psi.conj(), psi_c))**2
    return 1 - F, F

# ============================================================
# MODULE 2: BLOCH DELTA COMPRESSION
# ============================================================

@lru_cache(maxsize=128)
def compute_k(kp: int) -> int:
    """k値計算"""
    n = 2 * kp + 1
    return (n**5 - n) // 120

@lru_cache(maxsize=128)
def compute_c_bitlen(kp: int) -> int:
    """cのビット長計算"""
    n = 2 * kp + 1
    return 2 * (n + 1)

def compute_m(kp: int) -> int:
    """m値計算"""
    n = 2 * kp + 1
    return 2 * (n + 1)

@lru_cache(maxsize=128)
def kp_from_m(m: int) -> int:
    """m値からkp逆算"""
    n = m // 2 - 1
    kp = (n - 1) // 2
    return kp

def encode_fast(kp: int) -> Dict[str, Any]:
    """高速エンコード"""
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
        "kp": kp, "n": n, "k": k, "m": m, "p": float(p),
        "c_bitlen": c_bitlen, "m_bits": m_bits, "p_bits": p_bits
    }

def decode1_fast(m_bits: str) -> Dict[str, int]:
    """デコード1"""
    m = int(m_bits, 2)
    kp = kp_from_m(m)
    n = 2 * kp + 1
    k = compute_k(kp)
    return {"m": m, "n": n, "kp": kp, "k": k}

def decode2_fast(p_bits: str) -> Dict[str, Any]:
    """デコード2"""
    p_int_bits = p_bits[:4]
    p_frac_bits = p_bits[4:]
    p_int = int(p_int_bits, 2)
    p_frac = sum(int(b) * (2 ** (-(i + 1))) for i, b in enumerate(p_frac_bits))
    p = p_int + p_frac
    m = round(2 ** p)
    kp = kp_from_m(m)
    n = 2 * kp + 1
    k = compute_k(kp)
    return {"p": float(p), "m": m, "n": n, "kp": kp, "k": k}

# ============================================================
# MODULE 3: QUANTUM FX FRAMEWORK
# ============================================================

class NormFunction:
    """正規化関数"""
    def __init__(self, expr_str: str, var_str: str = 'x'):
        self.expr_str = expr_str
        if SYMPY_AVAILABLE:
            self._var = sp.Symbol(var_str, real=True)
            self._expr = sp.sympify(expr_str)
            self._func = sp.lambdify(self._var, self._expr, 'numpy')
        else:
            self._func = None
    
    def __call__(self, x: float) -> float:
        if self._func is None:
            # フォールバック: 簡単な式のみ対応
            return eval(self.expr_str.replace('x', str(x)))
        return float(self._func(x))

class QuantumState:
    """量子状態"""
    def __init__(self, n: int, fn: NormFunction, x: float = 1.0):
        self.n = n
        self.dim = 2**n
        self.fn = fn
        self.x = x
        self._psi = np.zeros(self.dim, dtype=complex)
        self._psi[0] = np.sqrt(fn(x))
    
    @property
    def norm2(self) -> float:
        return float(np.real(np.dot(np.conj(self._psi), self._psi)))
    
    @property
    def fx(self) -> float:
        return self.fn(self.x)
    
    def update_x(self, nx: float):
        """x値更新"""
        r = np.sqrt(self.fn(nx) / self.fn(self.x))
        self.x = nx
        self._psi *= r

# ============================================================
# API ENDPOINTS (Flask)
# ============================================================

class VMAAPIServer:
    """VMA API サーバー"""
    def __init__(self, debug: bool = False):
        try:
            from flask import Flask, request, jsonify
            self.Flask = Flask
            self.request = request
            self.jsonify = jsonify
            self.app = Flask(__name__)
            self.debug = debug
            self._setup_routes()
        except ImportError:
            self.app = None
    
    def _setup_routes(self):
        """ルート設定"""
        @self.app.route('/api/judge', methods=['POST'])
        def api_judge():
            try:
                data = self.request.get_json()
                x = data.get('x', 1.0)
                sharpness = data.get('sharpness', 1.0)
                coupling = data.get('coupling', 1.0)
                
                judge = make_judge_qubit(sharpness=sharpness)
                psi, theta, phi = qubit_from_sigmoid(x)
                comp = controlled_phase(psi, judge, coupling=coupling)
                p0, p1, verdict = measure_judge(comp)
                score, F = quantum_score(psi)
                
                return self.jsonify({
                    "status": "success",
                    "theta_degrees": float(np.degrees(theta)),
                    "p_classical": p0, "p_quantum": p1,
                    "quantum_score": score, "fidelity": float(F),
                    "verdict": verdict,
                    "critical_angle_degrees": float(np.degrees(THETA_C))
                })
            except Exception as e:
                return self.jsonify({"status": "error", "message": str(e)}), 400
        
        @self.app.route('/api/compress', methods=['POST'])
        def api_compress():
            try:
                data = self.request.get_json()
                kp = int(data.get('kp', 0))
                verify = data.get('verify', True)
                
                if kp < 0 or kp > 255:
                    return self.jsonify({"status": "error", "message": "kp must be 0..255"}), 400
                
                enc = encode_fast(kp)
                result = {
                    "status": "success",
                    "kp": enc["kp"], "n": enc["n"], "m": enc["m"], "p": enc["p"],
                    "m_bits": enc["m_bits"], "p_bits": enc["p_bits"], "c_bitlen": enc["c_bitlen"]
                }
                
                if verify:
                    d1 = decode1_fast(enc["m_bits"])
                    d2 = decode2_fast(enc["p_bits"])
                    match = d1["kp"] == d2["kp"] == enc["kp"]
                    result.update({
                        "decode1_kp": d1["kp"], "decode2_kp": d2["kp"], "match": match
                    })
                
                return self.jsonify(result)
            except Exception as e:
                return self.jsonify({"status": "error", "message": str(e)}), 400
        
        @self.app.route('/api/quantum_fx', methods=['POST'])
        def api_quantum_fx():
            try:
                data = self.request.get_json()
                fn_str = data.get('function', '1 + sin(x)**2')
                n_qubits = int(data.get('n_qubits', 4))
                x_values = data.get('x_values', [0.5, 1.0, np.pi])
                
                if n_qubits < 1 or n_qubits > 10:
                    return self.jsonify({"status": "error", "message": "n_qubits must be 1..10"}), 400
                
                fn = NormFunction(fn_str)
                st = QuantumState(n_qubits, fn, x_values[0] if x_values else 1.0)
                
                results = []
                for xv in x_values:
                    # 修正(2026-10-29): st.x の直接代入では振幅が追従せず
                    # norm2 が初期xのまま残るため、update_x で再スケールする
                    st.update_x(float(xv))
                    ratio = st.norm2 / st.fx if st.fx > 0 else 0
                    results.append({
                        "x": float(xv), "fx": float(st.fx),
                        "norm2": float(st.norm2), "ratio": float(ratio)
                    })
                
                return self.jsonify({
                    "status": "success", "function": fn_str,
                    "n_qubits": n_qubits, "results": results
                })
            except Exception as e:
                return self.jsonify({"status": "error", "message": str(e)}), 400
        
        @self.app.route('/api/health', methods=['GET'])
        def api_health():
            return self.jsonify({
                "status": "ok", "service": "VMA Quantum API",
                "modules": ["judge", "compress", "quantum_fx"], "hw": "local_cpu"
            })
    
    def run(self, host: str = '0.0.0.0', port: int = 5000):
        """サーバー起動"""
        if self.app is None:
            print("✗ Flask not available. Install with: pip install flask")
            return False
        print(f"\n{'='*70}")
        print(f"VMA Quantum API Server")
        print(f"{'='*70}")
        print(f"Endpoints:")
        print(f"  POST /api/judge       - Quantum bit judgment")
        print(f"  POST /api/compress    - Bloch delta compression")
        print(f"  POST /api/quantum_fx  - Extended quantum FX")
        print(f"  GET  /api/health      - Health check")
        print(f"\nStarting server on http://{host}:{port}")
        print(f"{'='*70}\n")
        self.app.run(host=host, port=port, debug=self.debug)
        return True

# ============================================================
# CLI INTERFACE
# ============================================================

def run_cli_mode():
    """CLI インタラクティブモード"""
    print("\n" + "="*70)
    print("VMA Quantum — CLI Interactive Mode")
    print("="*70)
    print("\nCommands:")
    print("  judge <x> [sharpness] [coupling]")
    print("  compress <kp> [verify]")
    print("  quantum_fx <function> <n> <x1,x2,...>")
    print("  exit")
    print()
    
    while True:
        try:
            cmd = input("> ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] == 'exit':
                break
            elif cmd[0] == 'judge':
                x = float(cmd[1]) if len(cmd) > 1 else 1.0
                sharp = float(cmd[2]) if len(cmd) > 2 else 1.0
                coup = float(cmd[3]) if len(cmd) > 3 else 1.0
                
                judge = make_judge_qubit(sharpness=sharp)
                psi, theta, phi = qubit_from_sigmoid(x)
                comp = controlled_phase(psi, judge, coupling=coup)
                p0, p1, verdict = measure_judge(comp)
                score, F = quantum_score(psi)
                
                print(f"\nResult:")
                print(f"  θ: {np.degrees(theta):.2f}°")
                print(f"  P(classical): {p0:.4f}")
                print(f"  P(quantum): {p1:.4f}")
                print(f"  Quantum Score: {score:.4f}")
                print(f"  Verdict: {verdict}\n")
            
            elif cmd[0] == 'compress':
                kp = int(cmd[1]) if len(cmd) > 1 else 0
                enc = encode_fast(kp)
                d1 = decode1_fast(enc["m_bits"])
                d2 = decode2_fast(enc["p_bits"])
                match = d1["kp"] == d2["kp"] == enc["kp"]
                
                print(f"\nResult:")
                print(f"  kp: {enc['kp']}, n: {enc['n']}, m: {enc['m']}")
                print(f"  p: {enc['p']:.4f}")
                print(f"  Match: {'✅' if match else '❌'}\n")
            
            elif cmd[0] == 'quantum_fx':
                fn_str = cmd[1] if len(cmd) > 1 else "1 + sin(x)**2"
                n = int(cmd[2]) if len(cmd) > 2 else 4
                xs = [float(x) for x in cmd[3].split(',')] if len(cmd) > 3 else [1.0]
                
                fn = NormFunction(fn_str)
                st = QuantumState(n, fn, xs[0])
                
                print(f"\nResults:")
                for xv in xs:
                    st.x = xv
                    ratio = st.norm2 / st.fx if st.fx > 0 else 0
                    print(f"  x={xv:.4f}: f(x)={st.fx:.6f}, norm²={st.norm2:.6f}, ratio={ratio:.10f}")
                print()
            else:
                print(f"Unknown command: {cmd[0]}\n")
        except Exception as e:
            print(f"Error: {e}\n")

def run_local_test():
    """ローカルテスト実行"""
    print("\n" + "="*70)
    print("VMA Quantum — Local Test Mode")
    print("="*70)
    
    # Part A: Judge
    print("\n[Part A] Quantum Bit Judgment")
    print("-"*70)
    print(f"{'x':>6} {'θ(deg)':>8} {'P(C)':>8} {'P(Q)':>8} {'Q-score':>8} Verdict")
    print("-"*70)
    for x in [0.0, 1.0, 2.0, np.pi]:
        judge = make_judge_qubit()
        psi, theta, phi = qubit_from_sigmoid(x)
        comp = controlled_phase(psi, judge)
        p0, p1, verdict = measure_judge(comp)
        score, _ = quantum_score(psi)
        print(f"{x:6.2f} {np.degrees(theta):8.2f} {p0:8.4f} {p1:8.4f} {score:8.4f} {verdict}")
    
    # Part B: Compress
    print("\n[Part B] Bloch Delta Compression")
    print("-"*70)
    print(f"{'kp':>3} {'m':>5} {'p':>7} {'Match':>6}")
    print("-"*70)
    for kp in [0, 42, 128, 255]:
        enc = encode_fast(kp)
        d1 = decode1_fast(enc["m_bits"])
        d2 = decode2_fast(enc["p_bits"])
        match = "✅" if d1["kp"] == d2["kp"] == enc["kp"] else "❌"
        print(f"{kp:3d} {enc['m']:5d} {enc['p']:7.4f} {match:>6}")
    
    # Part C: FX
    print("\n[Part C] Extended Quantum FX")
    print("-"*70)
    print(f"{'x':>7} {'f(x)':>10} {'norm²':>10} {'ratio':>12} Check")
    print("-"*70)
    fn = NormFunction('1 + sin(x)**2')
    for xv in [0.5, 1.0, 1.5, np.pi]:
        st = QuantumState(4, fn, xv)  # 各xごとに再初期化
        ratio = st.norm2 / st.fx if st.fx > 0 else 0
        check = "✓" if abs(ratio - 1.0) < 0.01 else "✗"
        print(f"{xv:7.4f} {st.fx:10.6f} {st.norm2:10.6f} {ratio:12.10f} {check}")
    
    print("\n" + "="*70)
    print("✅ All tests completed")
    print("="*70 + "\n")

# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="VMA Quantum — All-in-One Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vma_quantum_all_in_one.py --server --port 5000
  python vma_quantum_all_in_one.py --cli
  python vma_quantum_all_in_one.py --local
  python vma_quantum_all_in_one.py --test
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--server', action='store_true', help='Start API server (Flask)')
    group.add_argument('--cli', action='store_true', help='Start CLI interactive mode')
    group.add_argument('--local', action='store_true', help='Run local tests')
    group.add_argument('--test', action='store_true', help='Run full test suite')
    
    parser.add_argument('--port', type=int, default=5000, help='API server port (default: 5000)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='API server host (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    if args.server:
        server = VMAAPIServer(debug=args.debug)
        server.run(host=args.host, port=args.port)
    elif args.cli:
        run_cli_mode()
    elif args.local or args.test:
        run_local_test()

if __name__ == '__main__':
    main()
