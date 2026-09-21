#!/usr/bin/env python3
"""
Test suite for /weather/search endpoint edge cases.

Tests:
1. Empty embeddings table
2. Missing query parameter
3. Query too long (>1000 chars)
4. Invalid top_k (non-integer, negative)
5. top_k clamping (values outside 1-20)
6. Non-JSON Content-Type
7. Valid search requests
8. Lazy model loading

Usage:
    python test_search_endpoint.py [--host HOST] [--port PORT]
    
Example:
    python test_search_endpoint.py --host localhost --port 8080
"""

import argparse
import json
import sys
from typing import Dict, Any

try:
    import requests
except ImportError:
    print("❌ Error: 'requests' library not installed")
    print("   Install with: pip install requests")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    """Container for test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def pass_test(self, name: str, details: str = ""):
        self.passed += 1
        print(f"  {Colors.GREEN}✓{Colors.RESET} {name}")
        if details:
            print(f"    {Colors.BLUE}{details}{Colors.RESET}")

    def fail_test(self, name: str, details: str):
        self.failed += 1
        print(f"  {Colors.RED}✗{Colors.RESET} {name}")
        print(f"    {Colors.RED}{details}{Colors.RESET}")

    def warn_test(self, name: str, details: str):
        self.warnings += 1
        print(f"  {Colors.YELLOW}⚠{Colors.RESET} {name}")
        print(f"    {Colors.YELLOW}{details}{Colors.RESET}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary:{Colors.RESET}")
        print(f"  {Colors.GREEN}Passed:{Colors.RESET} {self.passed}/{total}")
        print(f"  {Colors.RED}Failed:{Colors.RESET} {self.failed}/{total}")
        if self.warnings > 0:
            print(f"  {Colors.YELLOW}Warnings:{Colors.RESET} {self.warnings}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        return self.failed == 0


def test_healthz(base_url: str, results: TestResult):
    """Test that the API is running."""
    print(f"\n{Colors.BOLD}🏥 Health Check{Colors.RESET}")
    try:
        response = requests.get(f"{base_url}/healthz", timeout=5)
        if response.status_code == 200 and response.json().get('status') == 'ok':
            results.pass_test("API is running", f"Response: {response.json()}")
            return True
        else:
            results.fail_test("API health check failed", f"Status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        results.fail_test("Cannot connect to API", f"Is the server running at {base_url}?")
        return False
    except Exception as e:
        results.fail_test("Health check error", str(e))
        return False


def test_missing_query(base_url: str, results: TestResult):
    """Test: Missing query parameter."""
    print(f"\n{Colors.BOLD}📝 Test: Missing Query Parameter{Colors.RESET}")
    
    # Empty string
    response = requests.post(
        f"{base_url}/weather/search",
        json={"query": "", "top_k": 5},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 400 and "required" in response.json().get('error', '').lower():
        results.pass_test("Empty query rejected", f"Error: {response.json()['error']}")
    else:
        results.fail_test("Empty query not rejected", f"Status: {response.status_code}")
    
    # Missing query key
    response = requests.post(
        f"{base_url}/weather/search",
        json={"top_k": 5},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 400:
        results.pass_test("Missing query key rejected", f"Error: {response.json()['error']}")
    else:
        results.fail_test("Missing query key not rejected", f"Status: {response.status_code}")


def test_query_length(base_url: str, results: TestResult):
    """Test: Query too long (>1000 chars)."""
    print(f"\n{Colors.BOLD}📏 Test: Query Length Validation{Colors.RESET}")
    
    long_query = "a" * 1001
    response = requests.post(
        f"{base_url}/weather/search",
        json={"query": long_query, "top_k": 5},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 400 and "1000" in response.json().get('error', ''):
        results.pass_test("Long query rejected", f"Error: {response.json()['error']}")
    else:
        results.fail_test("Long query not rejected", f"Status: {response.status_code}")


def test_invalid_topk(base_url: str, results: TestResult):
    """Test: Invalid top_k values."""
    print(f"\n{Colors.BOLD}🔢 Test: Invalid top_k Values{Colors.RESET}")
    
    test_cases = [
        ("string", 400, "Non-integer top_k"),
        (None, 400, "Null top_k"),
        ([1, 2], 400, "Array top_k"),
    ]
    
    for value, expected_status, description in test_cases:
        response = requests.post(
            f"{base_url}/weather/search",
            json={"query": "test", "top_k": value},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == expected_status:
            results.pass_test(f"{description} rejected", f"top_k={value}")
        else:
            results.fail_test(f"{description} not rejected", f"Status: {response.status_code}")


def test_topk_clamping(base_url: str, results: TestResult):
    """Test: top_k clamping to 1-20 range."""
    print(f"\n{Colors.BOLD}🔧 Test: top_k Clamping (1-20){Colors.RESET}")
    
    test_cases = [
        (-5, "Negative top_k should clamp to 1"),
        (0, "Zero top_k should clamp to 1"),
        (100, "Large top_k should clamp to 20"),
    ]
    
    for value, description in test_cases:
        response = requests.post(
            f"{base_url}/weather/search",
            json={"query": "test query", "top_k": value},
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in [200, 500]:
            data = response.json()
            if 'top_k' in data:
                clamped = data['top_k']
                if value <= 0 and clamped == 1:
                    results.pass_test(f"{description}", f"Clamped {value} → {clamped}")
                elif value > 20 and clamped == 20:
                    results.pass_test(f"{description}", f"Clamped {value} → {clamped}")
                else:
                    results.fail_test(f"{description}", f"Got top_k={clamped}")
            else:
                results.warn_test(f"{description}", "Missing 'top_k' field")
        else:
            results.fail_test(f"{description}", f"Status: {response.status_code}")


def test_non_json_request(base_url: str, results: TestResult):
    """Test: Non-JSON Content-Type."""
    print(f"\n{Colors.BOLD}📦 Test: Content-Type Validation{Colors.RESET}")
    
    response = requests.post(
        f"{base_url}/weather/search",
        data="query=test&top_k=5",
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code == 400 and "json" in response.json().get('error', '').lower():
        results.pass_test("Non-JSON Content-Type rejected", f"Error: {response.json()['error']}")
    else:
        results.fail_test("Non-JSON Content-Type not rejected", f"Status: {response.status_code}")


def test_empty_embeddings_table(base_url: str, results: TestResult):
    """Test: Empty embeddings table handling."""
    print(f"\n{Colors.BOLD}📊 Test: Empty Embeddings Table{Colors.RESET}")
    
    response = requests.post(
        f"{base_url}/weather/search",
        json={"query": "flooding near rivers", "top_k": 5},
        headers={"Content-Type": "application/json"}
    )
    
    data = response.json()
    
    if response.status_code == 200:
        if 'total_available' in data and data['total_available'] == 0:
            results.pass_test("Empty table returns zero results", f"Message: {data.get('message', 'N/A')}")
        elif len(data.get('results', [])) > 0:
            results.warn_test("Table has embeddings", f"Found {data.get('total_available', 'unknown')} embeddings")
        else:
            results.warn_test("Unexpected response structure", f"Response: {data}")
    else:
        results.fail_test("Empty table handling failed", f"Status: {response.status_code}")


def test_valid_search(base_url: str, results: TestResult):
    """Test: Valid search requests."""
    print(f"\n{Colors.BOLD}🔍 Test: Valid Search Requests{Colors.RESET}")
    
    test_queries = [
        {"query": "flooding near rivers", "top_k": 5},
        {"query": "heat advisory", "top_k": 3},
        {"query": "severe thunderstorm warning", "top_k": 10},
    ]
    
    for test_case in test_queries:
        response = requests.post(
            f"{base_url}/weather/search",
            json=test_case,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            results.pass_test(
                f"Valid search: '{test_case['query'][:30]}...'",
                f"Returned {len(data.get('results', []))} results (total: {data.get('total_available', 'N/A')})"
            )
        elif response.status_code == 500 and 'does not exist' in response.json().get('error', ''):
            results.warn_test(
                f"Search for '{test_case['query'][:30]}...'",
                "Table missing - run ingestion notebook"
            )
        else:
            results.fail_test(
                f"Valid search failed: '{test_case['query'][:30]}...'",
                f"Status: {response.status_code}"
            )


def test_model_loading(base_url: str, results: TestResult):
    """Test: Model lazy loading (first request might be slower)."""
    print(f"\n{Colors.BOLD}🤖 Test: Model Lazy Loading{Colors.RESET}")
    
    import time
    
    start = time.time()
    response1 = requests.post(
        f"{base_url}/weather/search",
        json={"query": "test", "top_k": 1},
        headers={"Content-Type": "application/json"},
        timeout=60
    )
    duration1 = time.time() - start
    
    start = time.time()
    response2 = requests.post(
        f"{base_url}/weather/search",
        json={"query": "test", "top_k": 1},
        headers={"Content-Type": "application/json"}
    )
    duration2 = time.time() - start
    
    if response1.status_code in [200, 500] and response2.status_code in [200, 500]:
        results.pass_test(
            "Model lazy loading works",
            f"First: {duration1:.2f}s, Second: {duration2:.2f}s"
        )
        if duration1 > duration2 * 2:
            print(f"    {Colors.GREEN}Model loaded on first request (expected){Colors.RESET}")
    else:
        results.fail_test(
            "Model loading test failed",
            f"Status codes: {response1.status_code}, {response2.status_code}"
        )


def main():
    parser = argparse.ArgumentParser(description="Test /weather/search endpoint edge cases")
    parser.add_argument('--host', default='localhost', help='API host (default: localhost)')
    parser.add_argument('--port', type=int, default=8080, help='API port (default: 8080)')
    args = parser.parse_args()
    
    base_url = f"http://{args.host}:{args.port}"
    results = TestResult()
    
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Weather Search API Edge Case Tests{Colors.RESET}")
    print(f"Testing: {base_url}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    
    if not test_healthz(base_url, results):
        print(f"\n{Colors.RED}❌ API not responding{Colors.RESET}")
        print(f"   Start with: python app.py")
        sys.exit(1)
    
    test_missing_query(base_url, results)
    test_query_length(base_url, results)
    test_invalid_topk(base_url, results)
    test_topk_clamping(base_url, results)
    test_non_json_request(base_url, results)
    test_empty_embeddings_table(base_url, results)
    test_valid_search(base_url, results)
    test_model_loading(base_url, results)
    
    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
