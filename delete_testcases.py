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
SECTION_ID = _env_int("TESTRAIL_SECTION_ID", 4033162)
JSON_FILE_PATH = _env_str("TESTRAIL_JSON_FILE", "testcases.json") or "testcases.json"

# Try password first, fallback to API key
AUTH_PASSWORD = PASSWORD

# Rate limiting: delay between requests (in seconds)
REQUEST_DELAY = 0.5

def get_test_cases_from_section(auth, section_id):
    """Get all test cases from a section"""
    url = f"{TESTRAIL_URL}/index.php?/api/v2/get_cases/{section_id}"
    response = requests.get(url, auth=auth)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to get test cases. Status: {response.status_code}")
        print(f"Response: {response.text}")
        return []

def delete_test_cases():
    if not USERNAME:
        print("Error: Set TESTRAIL_USERNAME in .env (see .env.example).")
        return
    if not PASSWORD.strip() and not API_KEY:
        print("Error: Set TESTRAIL_PASSWORD and/or TESTRAIL_API_KEY in .env (see .env.example).")
        return

    # 1. Load test case titles from JSON file
    try:
        with open(JSON_FILE_PATH, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {JSON_FILE_PATH} not found.")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in {JSON_FILE_PATH}. {e}")
        return

    # Extract cases array from JSON
    if isinstance(data, list):
        json_cases = data
    elif isinstance(data, dict) and 'cases' in data:
        json_cases = data['cases']
    else:
        print("Error: JSON must contain an array of cases or an object with 'cases' key.")
        return

    if not json_cases:
        print("Error: No test cases found in JSON file.")
        return

    # Create set of titles from JSON for matching
    json_titles = {case.get('title', '').strip() for case in json_cases if case.get('title')}
    print(f"Found {len(json_titles)} unique test case titles in JSON file.\n")

    # 2. Test authentication
    print("Testing authentication...")
    auth_password = AUTH_PASSWORD
    auth = (USERNAME, auth_password)
    test_url = f"{TESTRAIL_URL}/index.php?/api/v2/get_user_by_email&email={USERNAME}"
    test_response = requests.get(test_url, auth=auth)
    
    if test_response.status_code == 200:
        print("✓ Authentication successful!\n")
    else:
        print(f"✗ Authentication with password failed. Status: {test_response.status_code}")
        print(f"Trying with API key instead...")
        auth_password = API_KEY
        auth = (USERNAME, auth_password)
        test_response = requests.get(test_url, auth=auth)
        if test_response.status_code == 200:
            print("✓ Authentication with API key successful!\n")
        else:
            print(f"✗ Both password and API key failed.")
            return

    # 3. Get all test cases from the section
    print(f"Fetching test cases from section {SECTION_ID}...")
    section_cases = get_test_cases_from_section(auth, SECTION_ID)
    
    if not section_cases:
        print("No test cases found in the section.")
        return

    print(f"Found {len(section_cases)} test cases in section.\n")

    # 4. Match test cases by title
    cases_to_delete = []
    for case in section_cases:
        case_title = case.get('title', '').strip()
        if case_title in json_titles:
            cases_to_delete.append(case)

    if not cases_to_delete:
        print("No matching test cases found to delete.")
        print("Titles in section don't match titles in JSON file.")
        return

    print(f"Found {len(cases_to_delete)} matching test cases to delete.\n")
    
    # 5. Confirm deletion
    print("Test cases to be deleted:")
    for case in cases_to_delete[:10]:  # Show first 10
        print(f"  - ID: {case['id']} | {case['title'][:60]}")
    if len(cases_to_delete) > 10:
        print(f"  ... and {len(cases_to_delete) - 10} more")
    
    confirm = input(f"\n⚠️  WARNING: This will permanently delete {len(cases_to_delete)} test cases. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Deletion cancelled.")
        return

    # 6. Delete test cases
    print(f"\nDeleting {len(cases_to_delete)} test cases...")
    deleted_cases = []
    failed_cases = []
    
    for idx, case in enumerate(cases_to_delete, 1):
        case_id = case['id']
        case_title = case.get('title', 'Untitled')
        
        if idx == 1 or idx % 10 == 0 or idx == len(cases_to_delete):
            percentage = (idx / len(cases_to_delete)) * 100
            print(f"[{idx}/{len(cases_to_delete)} ({percentage:.1f}%)] Deleting: {case_title[:60]}...")
        
        url = f"{TESTRAIL_URL}/index.php?/api/v2/delete_case/{case_id}"
        
        try:
            response = requests.post(url, auth=auth, timeout=30)
            
            if response.status_code == 200:
                deleted_cases.append(case)
                if idx == 1 or idx % 10 == 0 or idx == len(cases_to_delete):
                    print(f"  ✓ Deleted - ID: {case_id}")
            else:
                failed_cases.append((case_title, case_id, response.status_code, response.text))
                print(f"  ✗ Failed - Status: {response.status_code} | Error: {response.text[:100]}")
        except requests.exceptions.Timeout:
            failed_cases.append((case_title, case_id, "Timeout", "Request timed out"))
            print(f"  ✗ Failed - Request timeout")
        except requests.exceptions.RequestException as e:
            failed_cases.append((case_title, case_id, "Error", str(e)))
            print(f"  ✗ Failed - Request error: {str(e)[:100]}")
        
        if idx < len(cases_to_delete):
            time.sleep(REQUEST_DELAY)

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Total cases to delete: {len(cases_to_delete)}")
    print(f"Successfully deleted: {len(deleted_cases)} ({len(deleted_cases)/len(cases_to_delete)*100:.1f}%)")
    print(f"Failed: {len(failed_cases)} ({len(failed_cases)/len(cases_to_delete)*100:.1f}%)")
    
    if failed_cases:
        print(f"\n✗ Failed deletions (showing first 10):")
        for title, case_id, status, error in failed_cases[:10]:
            print(f"  - ID: {case_id} | {title[:50]}")
            print(f"    Status: {status} | Error: {str(error)[:80]}")
        if len(failed_cases) > 10:
            print(f"  ... and {len(failed_cases) - 10} more failures")

if __name__ == "__main__":
    delete_test_cases()

