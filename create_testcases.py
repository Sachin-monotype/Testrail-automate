import json
import os
import requests
import time

try:
    from dotenv import load_dotenv

    _root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass


def _env_str(key, default=""):
    return (os.getenv(key) or default).strip()


def _env_int(key, default):
    val = os.getenv(key)
    if val is None or str(val).strip() == "":
        return default
    return int(val)


# --- CONFIGURATION (from .env; see .env.example) ---
TESTRAIL_URL = _env_str("TESTRAIL_URL", "https://type.testrail.com").rstrip("/")
USERNAME = _env_str("TESTRAIL_USERNAME")
PASSWORD = os.getenv("TESTRAIL_PASSWORD") or ""
API_KEY = _env_str("TESTRAIL_API_KEY")
# Section id = group_id in TestRail suite URL when grouped by section
SECTION_ID = _env_int("TESTRAIL_SECTION_ID", 4033162)
JSON_FILE_PATH = _env_str("TESTRAIL_JSON_FILE", "testcases.json") or "testcases.json"

# Try password first, fallback to API key
AUTH_PASSWORD = PASSWORD

# Rate limiting: delay between requests (in seconds) to avoid overwhelming the API
REQUEST_DELAY = 0.5  # 500ms delay between requests

def upload_test_cases():
    if not USERNAME:
        print("Error: Set TESTRAIL_USERNAME in .env (see .env.example).")
        return
    if not PASSWORD.strip() and not API_KEY:
        print("Error: Set TESTRAIL_PASSWORD and/or TESTRAIL_API_KEY in .env (see .env.example).")
        return

    # 1. Load data from JSON file
    try:
        with open(JSON_FILE_PATH, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {JSON_FILE_PATH} not found.")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in {JSON_FILE_PATH}. {e}")
        return

    # 2. Extract cases array from JSON
    # Handle both formats: direct array or object with 'cases' key
    if isinstance(data, list):
        cases = data
    elif isinstance(data, dict) and 'cases' in data:
        cases = data['cases']
    else:
        print("Error: JSON must contain an array of cases or an object with 'cases' key.")
        return

    if not cases:
        print("Error: No test cases found in JSON file.")
        return

    # 3. Test authentication first with a simple GET request
    print("Testing authentication...")
    auth_password = AUTH_PASSWORD
    auth = (USERNAME, auth_password)
    test_url = f"{TESTRAIL_URL}/index.php?/api/v2/get_user_by_email&email={USERNAME}"
    test_response = requests.get(test_url, auth=auth)
    
    if test_response.status_code == 200:
        print("✓ Authentication successful!\n")
    else:
        print(f"✗ Authentication with password failed. Status: {test_response.status_code}")
        print(f"Response: {test_response.text}")
        print(f"\nTrying with API key instead...")
        auth_password = API_KEY
        auth = (USERNAME, auth_password)
        test_response = requests.get(test_url, auth=auth)
        if test_response.status_code == 200:
            print("✓ Authentication with API key successful!\n")
        else:
            print(f"✗ Both password and API key failed.")
            print(f"Please verify your credentials.")
            return

    # 4. Setup API details for adding cases
    # Endpoint: add_case/{section_id} (singular - adds one case at a time)
    url = f"{TESTRAIL_URL}/index.php?/api/v2/add_case/{SECTION_ID}"
    headers = {'Content-Type': 'application/json'}
    auth = (USERNAME, auth_password)

    # 5. Send POST request for each case
    total_cases = len(cases)
    print(f"Uploading {total_cases} cases to section {SECTION_ID}...")
    print(f"Progress will be shown every 10 cases\n")
    created_cases = []
    failed_cases = []
    
    for idx, case in enumerate(cases, 1):
        case_title = case.get('title', 'Untitled')
        # Show progress every 10 cases or for first/last case
        if idx == 1 or idx % 10 == 0 or idx == total_cases:
            percentage = (idx / total_cases) * 100
            print(f"[{idx}/{total_cases} ({percentage:.1f}%)] Adding: {case_title[:60]}...")
        
        # Remove type_id if present (may be invalid for this instance)
        case_data = case.copy()
        if 'type_id' in case_data:
            del case_data['type_id']
        
        try:
            response = requests.post(url, headers=headers, auth=auth, json=case_data, timeout=30)
            
            if response.status_code == 200:
                created_case = response.json()
                created_cases.append(created_case)
                if idx == 1 or idx % 10 == 0 or idx == total_cases:
                    print(f"  ✓ Created - ID: {created_case['id']}")
            else:
                failed_cases.append((case_title, response.status_code, response.text))
                print(f"  ✗ Failed - Status: {response.status_code} | Error: {response.text[:100]}")
        except requests.exceptions.Timeout:
            failed_cases.append((case_title, "Timeout", "Request timed out after 30 seconds"))
            print(f"  ✗ Failed - Request timeout")
        except requests.exceptions.RequestException as e:
            failed_cases.append((case_title, "Error", str(e)))
            print(f"  ✗ Failed - Request error: {str(e)[:100]}")
        
        # Rate limiting: add delay between requests
        if idx < total_cases:
            time.sleep(REQUEST_DELAY)

    # 6. Summary
    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Total cases processed: {total_cases}")
    print(f"Successfully created: {len(created_cases)} ({len(created_cases)/total_cases*100:.1f}%)")
    print(f"Failed: {len(failed_cases)} ({len(failed_cases)/total_cases*100:.1f}%)")
    
    if created_cases:
        print(f"\n✓ Successfully created test case IDs:")
        for case in created_cases[:10]:  # Show first 10 IDs
            print(f"  - ID: {case['id']} | {case['title'][:50]}")
        if len(created_cases) > 10:
            print(f"  ... and {len(created_cases) - 10} more")
    
    if failed_cases:
        print(f"\n✗ Failed cases (showing first 10):")
        for title, status, error in failed_cases[:10]:
            print(f"  - {title[:60]}")
            print(f"    Status: {status} | Error: {str(error)[:80]}")
        if len(failed_cases) > 10:
            print(f"  ... and {len(failed_cases) - 10} more failures")

if __name__ == "__main__":
    upload_test_cases()