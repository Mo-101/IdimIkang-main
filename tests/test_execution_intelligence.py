import sys
import os
import unittest
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'observer_bundle'))
from execution_intelligence import compute_execution_features

class TestExecutionIntelligence(unittest.TestCase):
    def setUp(self):
        # Using 4 bps spread (99.98 to 100.02)
        self.base_snapshot = {
            "success": True,
            "bookTicker": {"bidPrice": "99.98", "askPrice": "100.02"},
            "depth": {
                # Level 1: $10,000 at tight prices
                # Level 2: $100,000 at 1% away
                "bids": [
                    ["99.98", str(10000.0/99.98)],
                    ["99.00", str(100000.0/99.00)]
                ],
                "asks": [
                    ["100.02", str(10000.0/100.02)],
                    ["100.90", str(100000.0/100.90)] # Moved inside 1% boundary (mid=100)
                ]
            },
            "klines": [
                [0, "100", "100.1", "99.9", "100", "0", 0, "0", 0, "0", "0", "0"]
            ],
            "latency_ms": 100
        }
        
    def test_spread(self):
        """Test 1: spread"""
        res = compute_execution_features(self.base_snapshot, 1000, "LONG")
        # (100.02 - 99.98) / 100.0 * 10000 = 4 bps
        self.assertAlmostEqual(res["spread_bps"], 4.0)
        self.assertAlmostEqual(res["mid_price"], 100.0)
        
    def test_depth_imbalance(self):
        """Test 2: depth imbalance"""
        res = compute_execution_features(self.base_snapshot, 1000, "LONG")
        self.assertAlmostEqual(res["depth_imbalance"], 0.0, places=4)
        
        # Bid dominates
        snap_bid_dom = dict(self.base_snapshot)
        snap_bid_dom["depth"] = {"bids": [["99.98", "1000"]], "asks": [["100.02", "500"]]}
        res = compute_execution_features(snap_bid_dom, 1000, "LONG")
        self.assertGreater(res["depth_imbalance"], 0)
        
        # Ask dominates
        snap_ask_dom = dict(self.base_snapshot)
        snap_ask_dom["depth"] = {"bids": [["99.98", "500"]], "asks": [["100.02", "1000"]]}
        res = compute_execution_features(snap_ask_dom, 1000, "LONG")
        self.assertLess(res["depth_imbalance"], 0)
        
    def test_slippage_monotonicity(self):
        """Test 3: slippage monotonicity"""
        res_q1 = compute_execution_features(self.base_snapshot, 100, "LONG")
        # Eat deeper but still within book if possible, or just check increase
        res_q2 = compute_execution_features(self.base_snapshot, 70000, "LONG") 
        self.assertGreaterEqual(res_q2["est_slippage_bps"], res_q1["est_slippage_bps"])
        
    def test_exec_score_monotonicity(self):
        """Test 4: exec score monotonicity"""
        base_res = compute_execution_features(self.base_snapshot, 1000, "LONG")
        
        # larger spread: move to 10 bps (99.95 to 100.05)
        # s_spread(4) = 1 - 4/12 = 0.66
        # s_spread(10) = 1 - 10/12 = 0.16
        snap_wide_spread = dict(self.base_snapshot)
        snap_wide_spread["bookTicker"] = {"bidPrice": "99.95", "askPrice": "100.05"}
        wide_res = compute_execution_features(snap_wide_spread, 1000, "LONG")
        self.assertLess(wide_res["exec_score"], base_res["exec_score"])
        
        # larger slippage
        slip_res = compute_execution_features(self.base_snapshot, 70000, "LONG")
        self.assertLess(slip_res["exec_score"], base_res["exec_score"])
        
        # worse depth
        snap_bad_depth = dict(self.base_snapshot)
        snap_bad_depth["depth"] = {"bids": [["99.9", "1"]], "asks": [["100.1", "1"]]}
        bad_depth_res = compute_execution_features(snap_bad_depth, 1000, "LONG")
        self.assertLess(bad_depth_res["exec_score"], base_res["exec_score"])

if __name__ == '__main__':
    unittest.main()
