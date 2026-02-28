#!/usr/bin/env python3
"""
Test script to verify the profile loading fixes
Run with: py test_profile_fix.py [username]
Make sure Flask app is running first: py app.py
"""

import requests
import json
import time
import sys

# Configuration
BASE_URL = "http://localhost:5000"
TEST_USERNAME = "test_influencer"  # Replace with actual influencer username from your data

def test_profile_loading():
    print("🧪 Testing Profile Loading Functionality")
    print("=" * 50)
    
    # Test 1: Check if basic routes are accessible
    print("\n1. Testing basic routes...")
    try:
        response = requests.get(f"{BASE_URL}/get_niches", timeout=5)
        if response.status_code == 200:
            print("✅ Get niches endpoint working")
            niches = response.json()
            print(f"   Available niches: {niches}")
        else:
            print(f"❌ Get niches failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("   Make sure Flask app is running on http://localhost:5000")
        return False
    
    # Test 2: Check profile loading endpoint
    print(f"\n2. Testing profile load endpoint for '{TEST_USERNAME}'...")
    try:
        response = requests.get(f"{BASE_URL}/profile/load/{TEST_USERNAME}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Profile load endpoint working: {data}")
        else:
            print(f"❌ Profile load failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Profile load error: {e}")
    
    # Test 3: Check progress endpoint
    print(f"\n3. Testing progress check endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/profile/check-progress/{TEST_USERNAME}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Progress check working: {data}")
        elif response.status_code == 404:
            print("✅ Progress check working (no progress found - expected)")
        else:
            print(f"❌ Progress check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Progress check error: {e}")
    
    # Test 4: Check result endpoint  
    print(f"\n4. Testing result endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/profile/result/{TEST_USERNAME}", timeout=5)
        if response.status_code == 200:
            print("✅ Result endpoint working (profile data found)")
        elif response.status_code == 404:
            print("✅ Result endpoint working (no results yet - expected)")
        else:
            print(f"❌ Result endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Result endpoint error: {e}")
    
    # Test 5: Check main profile route
    print(f"\n5. Testing main profile route...")
    try:
        response = requests.get(f"{BASE_URL}/profile/{TEST_USERNAME}", timeout=5)
        if response.status_code == 200:
            print("✅ Main profile route working")
            # Check if it's loading page or actual profile
            if "profile_loading" in response.text or "Analyzing Profile" in response.text:
                print("   → Shows loading page (expected for new profiles)")
            elif "Profile Loading Error" in response.text:
                print("   → Shows error page (check if influencer data exists)")
            else:
                print("   → Shows actual profile page")
        elif response.status_code == 302:
            print("✅ Profile route redirecting (probably to login)")
        else:
            print(f"❌ Profile route failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Profile route error: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("If all tests show ✅, your profile loading should work!")
    print("If you see ❌, check the Flask console for error messages.")
    print("\nTo test in browser:")
    print("1. Go to http://localhost:5000/brand")
    print("2. Select a niche and load influencers") 
    print("3. Click on an influencer profile link")
    print("4. You should see the loading page, then the profile")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        TEST_USERNAME = sys.argv[1]
        print(f"Using username: {TEST_USERNAME}")
    
    test_profile_loading()