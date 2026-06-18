import urllib.request
import urllib.error
import json
import uuid
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

# ============================
# Counters
# ============================
passed = 0
failed = 0
total = 0

def make_request(url, method="GET", data=None):
    headers = {'Content-Type': 'application/json'}
    req_data = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.getcode(), response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except urllib.error.URLError as e:
        return 0, str(e.reason)

def parse(body):
    try:
        return json.loads(body)
    except:
        return body

def assert_test(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  ✅ PASS: {name}")
    else:
        failed += 1
        print(f"  ❌ FAIL: {name}" + (f" — {detail}" if detail else ""))

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_response(status_code, data):
    print(f"    Status: {status_code}")
    if isinstance(data, dict) or isinstance(data, list):
        print(f"    Response: {json.dumps(data, indent=4, default=str)[:500]}")
    else:
        print(f"    Response: {str(data)[:500]}")
    print()


# ============================
# 1. HEALTH CHECK
# ============================
def test_health_check():
    print_section("1. HEALTH CHECK — GET /")
    
    status, body = make_request(f"{BASE_URL}/")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Service status is 'running'", data.get("status") == "running")
    assert_test("Redis dependency is 'ok'", data.get("dependencies", {}).get("redis") == "ok")
    assert_test("Database dependency is 'ok'", data.get("dependencies", {}).get("database") == "ok")


# ============================
# 2. PLATFORM REGISTRATION
# ============================
def test_register_platform():
    print_section("2. PLATFORM REGISTRATION — POST /register-platform")
    
    uid = str(uuid.uuid4())[:8]
    name = f"TestPlatform_{uid}"
    email = f"test_{uid}@example.com"
    
    # 2a. Valid registration
    print("\n  --- 2a. Valid Registration ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "POST", {"name": name, "email": email})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response status is 'success'", data.get("status") == "success")
    assert_test("platform_id is returned", data.get("platform_id") is not None)
    assert_test("platform_id is a positive integer", isinstance(data.get("platform_id"), int) and data.get("platform_id") > 0)
    
    platform_id = data.get("platform_id")
    
    # 2b. Duplicate registration
    print("\n  --- 2b. Duplicate Name (expect 409) ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "POST", {"name": name, "email": "other@example.com"})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 409 (Conflict)", status == 409)
    assert_test("Error detail mentions 'already exists'", "already exists" in str(data.get("detail", "")))
    
    # 2c. Invalid email
    print("\n  --- 2c. Invalid Email (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "POST", {"name": "BadEmailTest", "email": "not-an-email"})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422 (Validation Error)", status == 422)
    assert_test("Validation detail is present", data.get("detail") is not None)
    
    # 2d. Empty name
    print("\n  --- 2d. Empty Name (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "POST", {"name": "", "email": "valid@example.com"})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422 (Validation Error)", status == 422)
    
    # 2e. Missing fields entirely
    print("\n  --- 2e. Missing All Fields (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "POST", {})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422 (Validation Error)", status == 422)
    
    return platform_id, name, email


# ============================
# 3. CONTENT MODERATION
# ============================
def test_moderate_content(platform_id):
    print_section("3. CONTENT MODERATION — POST /moderate")
    
    # 3a. Valid moderation request
    print("\n  --- 3a. Valid Request ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "text": "This is a normal, friendly message for testing purposes.",
        "platform_id": platform_id,
        "age": "25"
    })
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response status is 'queued'", data.get("status") == "queued")
    assert_test("request_id is a valid UUID", len(str(data.get("request_id", ""))) == 36)
    assert_test("queue_name is present", data.get("queue_name") is not None)
    assert_test("queue_size is a positive integer", isinstance(data.get("queue_size"), int) and data.get("queue_size") > 0)
    
    request_id_1 = data.get("request_id")
    
    # 3b. Another request with potentially flaggable content
    print("\n  --- 3b. Request With Potentially Flaggable Content ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "text": "I hate you and I want to destroy everything. You're the worst person ever!",
        "platform_id": platform_id,
        "age": "15"
    })
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response status is 'queued'", data.get("status") == "queued")
    
    request_id_2 = data.get("request_id")
    
    # 3c. Missing required fields
    print("\n  --- 3c. Missing 'text' field (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "platform_id": platform_id,
        "age": "20"
    })
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422", status == 422)
    
    # 3d. Missing platform_id and age
    print("\n  --- 3d. Missing platform_id and age (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "text": "Just text, nothing else."
    })
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422", status == 422)
    assert_test("Both platform_id and age are flagged as missing",
                len(data.get("detail", [])) >= 2)
    
    # 3e. Empty text
    print("\n  --- 3e. Empty Text (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "text": "",
        "platform_id": platform_id,
        "age": "20"
    })
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422 (text min_length=1)", status == 422)
    
    # 3f. Empty body
    print("\n  --- 3f. Empty Body (expect 422) ---")
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {})
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422", status == 422)
    
    return request_id_1, request_id_2


# ============================
# 4. QUEUE STATISTICS
# ============================
def test_queue_stats():
    print_section("4. QUEUE STATISTICS — GET /queue/stats")
    
    status, body = make_request(f"{BASE_URL}/queue/stats")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("queue_name is present", data.get("queue_name") is not None)
    assert_test("queue_size is a non-negative integer", isinstance(data.get("queue_size"), int) and data.get("queue_size") >= 0)


# ============================
# 5. LIST PLATFORMS (DB read)
# ============================
def test_list_platforms(expected_name):
    print_section("5. LIST PLATFORMS — GET /platforms (Database Read)")
    
    status, body = make_request(f"{BASE_URL}/platforms")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response is a list", isinstance(data, list))
    assert_test("At least 1 platform exists in DB", len(data) >= 1)
    
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        assert_test("Each platform has 'id' field", "id" in first)
        assert_test("Each platform has 'name' field", "name" in first)
        assert_test("Each platform has 'email' field", "email" in first)
        
        # Check that the platform we just registered is present
        names = [p.get("name") for p in data]
        assert_test(f"Newly registered platform '{expected_name}' is in DB", expected_name in names)


# ============================
# 6. MODERATION RESULTS (DB read)
# ============================
def test_moderation_results(platform_id):
    print_section("6. MODERATION RESULTS — GET /moderation-results (Database Read)")
    
    # 6a. Fetch all results
    print("\n  --- 6a. Fetch All Results ---")
    status, body = make_request(f"{BASE_URL}/moderation-results")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response is a list", isinstance(data, list))
    
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        assert_test("Result has 'request_id'", "request_id" in first)
        assert_test("Result has 'platform_id'", "platform_id" in first)
        assert_test("Result has 'platform_name'", "platform_name" in first)
        assert_test("Result has 'post_category'", "post_category" in first)
        assert_test("Result has 'confidence_score'", "confidence_score" in first)
        assert_test("Result has 'reason'", "reason" in first)
        assert_test("Result has 'completed_at'", "completed_at" in first)
        assert_test("confidence_score is a float between 0 and 1",
                     isinstance(first.get("confidence_score"), (int, float)) and 0 <= first["confidence_score"] <= 1)
    else:
        print("    ⚠️  No results found — worker may not have processed yet. This is expected if tested immediately.")
    
    # 6b. Filter by platform_id
    print("\n  --- 6b. Filter by Platform ID ---")
    status, body = make_request(f"{BASE_URL}/moderation-results?platform_id={platform_id}")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response is a list", isinstance(data, list))
    
    if isinstance(data, list):
        all_match = all(r.get("platform_id") == platform_id for r in data)
        assert_test(f"All results belong to platform_id={platform_id}", all_match or len(data) == 0)
    
    # 6c. Filter by non-existent platform
    print("\n  --- 6c. Filter by Non-Existent Platform (expect empty list) ---")
    status, body = make_request(f"{BASE_URL}/moderation-results?platform_id=99999")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("Response is an empty list", isinstance(data, list) and len(data) == 0)


# ============================
# 7. ADMIN DASHBOARD STATS (DB aggregation)
# ============================
def test_admin_dashboard_stats():
    print_section("7. ADMIN DASHBOARD STATS — GET /admin/dashboard-stats")
    
    status, body = make_request(f"{BASE_URL}/admin/dashboard-stats")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 200", status == 200)
    assert_test("'total_platforms' is present and is int", isinstance(data.get("total_platforms"), int))
    assert_test("'total_moderation_results' is present and is int", isinstance(data.get("total_moderation_results"), int))
    assert_test("'avg_confidence_score' is present", "avg_confidence_score" in data)
    assert_test("'categories' is present and is dict", isinstance(data.get("categories"), dict))
    assert_test("'queue_size' is present and is int", isinstance(data.get("queue_size"), int))
    assert_test("total_platforms >= 1", data.get("total_platforms", 0) >= 1)


# ============================
# 8. EDGE CASES & ERROR HANDLING
# ============================
def test_edge_cases():
    print_section("8. EDGE CASES & ERROR HANDLING")
    
    # 8a. Non-existent endpoint
    print("\n  --- 8a. Non-Existent Endpoint (expect 404) ---")
    status, body = make_request(f"{BASE_URL}/this-does-not-exist")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 404", status == 404)
    
    # 8b. Wrong HTTP method on register
    print("\n  --- 8b. GET /register-platform (wrong method, expect 405) ---")
    status, body = make_request(f"{BASE_URL}/register-platform", "GET")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 405 (Method Not Allowed)", status == 405)
    
    # 8c. Wrong HTTP method on moderate
    print("\n  --- 8c. GET /moderate (wrong method, expect 405) ---")
    status, body = make_request(f"{BASE_URL}/moderate", "GET")
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 405 (Method Not Allowed)", status == 405)
    
    # 8d. Malformed JSON body
    print("\n  --- 8d. Malformed JSON Body (expect 422) ---")
    req = urllib.request.Request(
        f"{BASE_URL}/register-platform",
        data=b"this is not json",
        headers={'Content-Type': 'application/json'},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode('utf-8')
    data = parse(body)
    print_response(status, data)
    
    assert_test("Status code is 422 (invalid JSON)", status == 422)
    
    # 8e. Very long text in moderation
    print("\n  --- 8e. Very Long Text in Moderation ---")
    long_text = "Hello world! " * 500
    status, body = make_request(f"{BASE_URL}/moderate", "POST", {
        "text": long_text,
        "platform_id": 1,
        "age": "20"
    })
    data = parse(body)
    print(f"    Status: {status}")
    print(f"    Response: queued={data.get('status', 'unknown')}, request_id={str(data.get('request_id', ''))[:20]}...")
    print()
    
    assert_test("Long text is accepted (status 200)", status == 200)


# ============================
# MAIN
# ============================
if __name__ == "__main__":
    print("\n" + "🔥" * 30)
    print("   COMPREHENSIVE API & DATABASE TEST SUITE")
    print("🔥" * 30)
    
    # Check API is reachable first
    try:
        status, _ = make_request(f"{BASE_URL}/")
        if status == 0:
            print("\n❌ Cannot reach API at", BASE_URL)
            print("   Make sure the server is running: python3 main.py")
            sys.exit(1)
    except:
        print("\n❌ Cannot reach API at", BASE_URL)
        sys.exit(1)
    
    test_health_check()
    
    platform_id, name, email = test_register_platform()
    
    test_moderate_content(platform_id or 1)
    
    test_queue_stats()
    
    test_list_platforms(name)
    
    # Wait a few seconds for the worker to process at least some results
    print("\n⏳ Waiting 8 seconds for the worker to process queued items...")
    time.sleep(8)
    
    test_moderation_results(platform_id or 1)
    
    test_admin_dashboard_stats()
    
    test_edge_cases()
    
    # ============================
    # SUMMARY
    # ============================
    print("\n" + "=" * 60)
    print(f"  📊 TEST SUMMARY")
    print(f"  ─────────────────────────────")
    print(f"  Total:  {total}")
    print(f"  Passed: {passed} ✅")
    print(f"  Failed: {failed} ❌")
    pct = (passed / total * 100) if total > 0 else 0
    print(f"  Rate:   {pct:.1f}%")
    print("=" * 60)
    
    if failed > 0:
        print("\n⚠️  Some tests failed. Check the output above for details.")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")
        sys.exit(0)
