#!/usr/bin/env python3
"""Quick API connection test"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
API_KEY = os.getenv("CANVAS_API_KEY")

print(f"API URL: {API_URL}")
print(f"API Key: {API_KEY[:20]}..." if API_KEY and len(API_KEY) > 20 else f"API Key: {API_KEY}")
print()

if not API_KEY:
    print("ERROR: No API key found in .env file")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

# Test 1: Get current user (self)
print("Testing: GET /api/v1/users/self")
response = requests.get(f"{API_URL}/api/v1/users/self", headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")

if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
    data = response.json()
    print(f"Success! Logged in as: {data.get('name', 'Unknown')}")
    print(f"User ID: {data.get('id')}")
else:
    print("Response (first 500 chars):")
    print(response.text[:500])
