#!/usr/bin/env python3

import requests
import json
import os
import sys
import time
from datetime import datetime
import base64

# Test configuration
BASE_URL = "http://localhost:5000"
TEST_DOCTOR_ID = "test_doctor_123"
TEST_PATIENT_ID = "test_patient_456"
TEST_VISIT_ID = "test_visit_789"

class TestsIntegrationTester:
    def __init__(self):
        self.session = requests.Session()
        self.test_results = []
        
    def log_test(self, test_name, success, message=""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"   {message}")
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
    
    def test_database_connection(self):
        """Test database connectivity and collections"""
        try:
            # This would normally connect to MongoDB
            # For now, we'll test via API endpoints
            response = self.session.get(f"{BASE_URL}/api/test_types")
            success = response.status_code == 200
            self.log_test("Database Connection", success, 
                         f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Database Connection", False, str(e))
            return False
    
    def test_get_test_types(self):
        """Test getting predefined test types"""
        try:
            response = self.session.get(f"{BASE_URL}/api/test_types")
            success = response.status_code == 200
            if success:
                data = response.json()
                success = len(data.get('test_types', [])) > 0
            self.log_test("Get Test Types", success, 
                         f"Found {len(data.get('test_types', []))} test types")
            return success
        except Exception as e:
            self.log_test("Get Test Types", False, str(e))
            return False
    
    def test_assign_test(self):
        """Test assigning a test to a patient"""
        try:
            test_data = {
                'patient_id': TEST_PATIENT_ID,
                'visit_id': TEST_VISIT_ID,
                'test_type': 'Blood Test',
                'test_name': 'Complete Blood Count',
                'instructions': 'Fasting required for 12 hours',
                'priority': 'high',
                'notes': 'Check for anemia'
            }
            
            response = self.session.post(f"{BASE_URL}/api/assign_test", 
                                       json=test_data)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                self.test_id = data.get('test_id')
                success = self.test_id is not None
            
            self.log_test("Assign Test", success, 
                         f"Test ID: {getattr(self, 'test_id', 'None')}")
            return success
        except Exception as e:
            self.log_test("Assign Test", False, str(e))
            return False
    
    def test_get_patient_tests(self):
        """Test retrieving patient tests"""
        try:
            response = self.session.get(f"{BASE_URL}/api/patient_tests/{TEST_PATIENT_ID}")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                tests = data.get('tests', [])
                success = len(tests) > 0
            
            self.log_test("Get Patient Tests", success, 
                         f"Found {len(tests)} tests")
            return success
        except Exception as e:
            self.log_test("Get Patient Tests", False, str(e))
            return False
    
    def test_file_upload(self):
        """Test file upload functionality"""
        try:
            # Create a test file
            test_content = "This is a test medical report content."
            test_filename = "test_report.txt"
            
            # Test with form data
            files = {'file': (test_filename, test_content, 'text/plain')}
            data = {
                'test_id': getattr(self, 'test_id', 'test_123'),
                'result_value': 'Normal',
                'notes': 'Test file upload'
            }
            
            response = self.session.post(f"{BASE_URL}/api/update_test_results", 
                                       files=files, data=data)
            success = response.status_code == 200
            
            if success:
                result = response.json()
                self.uploaded_filename = result.get('filename')
                success = self.uploaded_filename is not None
            
            self.log_test("File Upload", success, 
                         f"Uploaded: {getattr(self, 'uploaded_filename', 'None')}")
            return success
        except Exception as e:
            self.log_test("File Upload", False, str(e))
            return False
    
    def test_file_download(self):
        """Test file download functionality"""
        try:
            if not hasattr(self, 'uploaded_filename'):
                self.log_test("File Download", False, "No file to download")
                return False
            
            response = self.session.get(f"{BASE_URL}/api/download_test_file/{self.uploaded_filename}")
            success = response.status_code == 200
            
            if success:
                success = len(response.content) > 0
            
            self.log_test("File Download", success, 
                         f"Downloaded {len(response.content)} bytes")
            return success
        except Exception as e:
            self.log_test("File Download", False, str(e))
            return False
    
    def test_update_test_results(self):
        """Test updating test results"""
        try:
            update_data = {
                'test_id': getattr(self, 'test_id', 'test_123'),
                'result_value': 'Hemoglobin: 14.2 g/dL',
                'status': 'completed',
                'notes': 'Results within normal range'
            }
            
            response = self.session.post(f"{BASE_URL}/api/update_test_results", 
                                       json=update_data)
            success = response.status_code == 200
            
            self.log_test("Update Test Results", success, 
                         f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Update Test Results", False, str(e))
            return False
    
    def test_delete_test(self):
        """Test deleting a test"""
        try:
            if not hasattr(self, 'test_id'):
                self.log_test("Delete Test", False, "No test ID to delete")
                return False
            
            response = self.session.delete(f"{BASE_URL}/api/delete_test/{self.test_id}")
            success = response.status_code == 200
            
            self.log_test("Delete Test", success, 
                         f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Delete Test", False, str(e))
            return False
    
    def run_all_tests(self):
        """Run all integration tests"""
        print("🧪 Starting Hospital Management System - Tests Module Integration Tests")
        print("=" * 70)
        
        tests = [
            self.test_database_connection,
            self.test_get_test_types,
            self.test_assign_test,
            self.test_get_patient_tests,
            self.test_file_upload,
            self.test_file_download,
            self.test_update_test_results,
            self.test_delete_test
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            if test():
                passed += 1
            time.sleep(0.5)  # Small delay between tests
        
        print("\n" + "=" * 70)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! The tests module is working correctly.")
        else:
            print(f"⚠️  {total - passed} tests failed. Please check the implementation.")
        
        return passed == total

def main():
    """Main test execution"""
    tester = TestsIntegrationTester()
    
    print("Starting integration tests...")
    print("Make sure the Flask application is running on http://localhost:5000")
    print()
    
    # Wait for user confirmation
    input("Press Enter to start tests (or Ctrl+C to cancel)...")
    
    success = tester.run_all_tests()
    
    # Save test results
    with open('test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(tester.test_results),
            'passed_tests': sum(1 for r in tester.test_results if r['success']),
            'results': tester.test_results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to test_results.json")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
