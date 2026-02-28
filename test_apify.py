#!/usr/bin/env python3
"""
Test script for Apify API integration
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_apify_token():
    """Test if APIFY_API_TOKEN is set"""
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("❌ APIFY_API_TOKEN not found in environment variables")
        print("Please create a .env file with:")
        print("APIFY_API_TOKEN=your_apify_api_token_here")
        return False
    
    if token == "your_apify_api_token_here":
        print("❌ APIFY_API_TOKEN is set to placeholder value")
        print("Please replace with your actual Apify API token")
        return False
    
    print(f"✅ APIFY_API_TOKEN is set (length: {len(token)})")
    return True

def test_import():
    """Test if we can import the apify_api module"""
    try:
        from services.apify_api import fetch_instagram_data
        print("✅ Successfully imported apify_api module")
        return True
    except Exception as e:
        print(f"❌ Failed to import apify_api module: {e}")
        return False

def test_api_call():
    """Test a simple API call"""
    try:
        from services.apify_api import fetch_instagram_data
        
        # Test with a simple username
        print("Testing API call with username 'instagram'...")
        result = fetch_instagram_data("instagram", post_limit=1)
        
        if result:
            print("✅ API call successful")
            print(f"Profile data keys: {list(result.get('profile', {}).keys())}")
            print(f"Posts count: {len(result.get('posts', []))}")
            return True
        else:
            print("❌ API call returned no data")
            return False
            
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Apify API Integration")
    print("=" * 40)
    
    tests = [
        ("Environment Token", test_apify_token),
        ("Module Import", test_import),
        ("API Call", test_api_call)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        if test_func():
            passed += 1
        else:
            print(f"   Test failed: {test_name}")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Apify integration is working.")
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

