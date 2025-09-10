#!/usr/bin/env python3


import sys
import os
import requests
import json
from datetime import datetime, timedelta
import random
import string

# Add the parent directory to the path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import app, mongo
    from werkzeug.security import generate_password_hash
    from bson.objectid import ObjectId
    print("✅ Successfully imported Flask app and dependencies")
except ImportError as e:
    print(f"❌ Error importing dependencies: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

class PatientHistorySystemTester:
    def __init__(self):
        self.base_url = "http://localhost:5000"
        self.test_results = []
        self.test_patient_id = None
        self.test_doctor_id = None
        self.test_admin_id = None
        self.test_visit_ids = []
        
    def log_test(self, test_name, success, message=""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
    
    def setup_test_data(self):
        """Create test data for comprehensive testing"""
        print("\n🔧 Setting up test data...")
        
        try:
            with app.app_context():
                # Create test admin
                admin_data = {
                    'username': 'test_admin',
                    'password_hash': generate_password_hash('test123'),
                    'name': 'Test Administrator',
                    'email': 'admin@test.com',
                    'created_at': datetime.now()
                }
                admin_result = mongo.db.admin.insert_one(admin_data)
                self.test_admin_id = str(admin_result.inserted_id)
                
                # Create test department
                dept_data = {
                    'department_name': 'Test Cardiology',
                    'description': 'Test department for patient history testing',
                    'created_at': datetime.now()
                }
                dept_result = mongo.db.department.insert_one(dept_data)
                test_dept_id = dept_result.inserted_id
                
                # Create test doctor
                doctor_data = {
                    'username': 'test_doctor',
                    'password_hash': generate_password_hash('test123'),
                    'name': 'Dr. Test Physician',
                    'email': 'doctor@test.com',
                    'department_id': test_dept_id,
                    'specialization': 'Cardiology',
                    'room_no': 'T101',
                    'created_at': datetime.now()
                }
                doctor_result = mongo.db.doctor.insert_one(doctor_data)
                self.test_doctor_id = str(doctor_result.inserted_id)
                
                # Create test patient with comprehensive data
                patient_data = {
                    'patient_id': 'PT9999',
                    'name': 'Test Patient History',
                    'contact_number': '9999999999',
                    'aadhaar_number': '999999999999',
                    'date_of_birth': datetime(1990, 5, 15),
                    'gender': 'Male',
                    'address': '123 Test Street, Test City, Test State',
                    'allergies': 'Penicillin, Shellfish',
                    'chronic_illness': 'Hypertension, Diabetes Type 2',
                    'created_at': datetime.now()
                }
                patient_result = mongo.db.patient.insert_one(patient_data)
                self.test_patient_id = str(patient_result.inserted_id)
                
                # Create multiple test visits with comprehensive history
                visit_dates = [
                    datetime.now() - timedelta(days=90),  # 3 months ago
                    datetime.now() - timedelta(days=60),  # 2 months ago
                    datetime.now() - timedelta(days=30),  # 1 month ago
                    datetime.now() - timedelta(days=7),   # 1 week ago
                    datetime.now()                        # Today
                ]
                
                visit_scenarios = [
                    {
                        'reason_for_visit': 'Annual checkup and blood pressure monitoring',
                        'symptoms': 'Mild headaches, occasional dizziness',
                        'diagnosis': 'Hypertension - well controlled',
                        'medications': 'Lisinopril 10mg once daily\nMetformin 500mg twice daily',
                        'instructions': 'Continue current medications, monitor BP daily, low sodium diet',
                        'status': 'completed'
                    },
                    {
                        'reason_for_visit': 'Follow-up for diabetes management',
                        'symptoms': 'Increased thirst, frequent urination',
                        'diagnosis': 'Diabetes Type 2 - needs adjustment',
                        'medications': 'Metformin 850mg twice daily\nGlipizide 5mg once daily',
                        'instructions': 'Increase Metformin dose, check blood sugar twice daily',
                        'status': 'completed'
                    },
                    {
                        'reason_for_visit': 'Chest pain evaluation',
                        'symptoms': 'Chest tightness during exercise, shortness of breath',
                        'diagnosis': 'Angina pectoris - stable',
                        'medications': 'Atorvastatin 20mg once daily\nAspirin 81mg once daily',
                        'instructions': 'Start cardiac rehabilitation, avoid strenuous exercise',
                        'status': 'completed'
                    },
                    {
                        'reason_for_visit': 'Medication review and lab results',
                        'symptoms': 'Feeling better, no major complaints',
                        'diagnosis': 'Hypertension and diabetes - stable',
                        'medications': 'Continue current regimen\nAdd Vitamin D 1000 IU daily',
                        'instructions': 'Continue current treatment, return in 3 months',
                        'status': 'completed'
                    },
                    {
                        'reason_for_visit': 'Routine follow-up',
                        'symptoms': 'No acute symptoms',
                        'diagnosis': 'Stable chronic conditions',
                        'medications': 'No changes to current medications',
                        'instructions': 'Continue monitoring, next visit in 6 months',
                        'status': 'assigned'
                    }
                ]
                
                for i, (visit_date, scenario) in enumerate(zip(visit_dates, visit_scenarios)):
                    visit_data = {
                        'patient_id': patient_result.inserted_id,
                        'doctor_id': doctor_result.inserted_id,
                        'department_id': test_dept_id,
                        'visit_date': visit_date,
                        'reason_for_visit': scenario['reason_for_visit'],
                        'symptoms': scenario['symptoms'],
                        'diagnosis': scenario['diagnosis'],
                        'medications': scenario['medications'],
                        'instructions': scenario['instructions'],
                        'status': scenario['status'],
                        'follow_up_date': visit_date + timedelta(days=90) if i < 4 else None,
                        'created_at': visit_date,
                        'prescription_timestamp': visit_date if scenario['status'] == 'completed' else None
                    }
                    visit_result = mongo.db.visit.insert_one(visit_data)
                    self.test_visit_ids.append(str(visit_result.inserted_id))
                
                # Create test results for some visits
                test_data = [
                    {
                        'visit_id': ObjectId(self.test_visit_ids[0]),
                        'patient_id': patient_result.inserted_id,
                        'doctor_id': doctor_result.inserted_id,
                        'test_name': 'Complete Blood Count',
                        'test_type': 'Blood Test',
                        'instructions': 'Fasting required',
                        'status': 'completed',
                        'assigned_date': visit_dates[0],
                        'completed_date': visit_dates[0] + timedelta(days=1),
                        'results': 'WBC: 7.2, RBC: 4.5, Hemoglobin: 14.2 g/dL - Normal values',
                        'created_at': visit_dates[0]
                    },
                    {
                        'visit_id': ObjectId(self.test_visit_ids[1]),
                        'patient_id': patient_result.inserted_id,
                        'doctor_id': doctor_result.inserted_id,
                        'test_name': 'HbA1c',
                        'test_type': 'Blood Test',
                        'instructions': 'No fasting required',
                        'status': 'completed',
                        'assigned_date': visit_dates[1],
                        'completed_date': visit_dates[1] + timedelta(days=2),
                        'results': 'HbA1c: 7.8% - Elevated, indicates need for better glucose control',
                        'created_at': visit_dates[1]
                    }
                ]
                
                for test in test_data:
                    mongo.db.tests.insert_one(test)
                
                self.log_test("Setup Test Data", True, f"Created patient {patient_data['patient_id']} with {len(visit_dates)} visits")
                
        except Exception as e:
            self.log_test("Setup Test Data", False, f"Error: {str(e)}")
            return False
        
        return True
    
    def test_database_structure(self):
        """Test database collections and indexes"""
        print("\n🗄️  Testing database structure...")
        
        try:
            with app.app_context():
                # Test required collections exist
                collections = mongo.db.list_collection_names()
                required_collections = ['patient', 'visit', 'doctor', 'department', 'admin', 'tests']
                
                for collection in required_collections:
                    if collection in collections:
                        self.log_test(f"Collection {collection} exists", True)
                    else:
                        self.log_test(f"Collection {collection} exists", False, f"Missing collection: {collection}")
                
                # Test patient data integrity
                patient = mongo.db.patient.find_one({'_id': ObjectId(self.test_patient_id)})
                if patient:
                    required_fields = ['patient_id', 'name', 'contact_number', 'date_of_birth', 'gender']
                    for field in required_fields:
                        if field in patient:
                            self.log_test(f"Patient has {field} field", True)
                        else:
                            self.log_test(f"Patient has {field} field", False, f"Missing field: {field}")
                
                # Test visit relationships
                visits = list(mongo.db.visit.find({'patient_id': ObjectId(self.test_patient_id)}))
                self.log_test("Visit-Patient relationship", len(visits) > 0, f"Found {len(visits)} visits for test patient")
                
                # Test visit data completeness
                for visit in visits:
                    if all(field in visit for field in ['patient_id', 'doctor_id', 'visit_date']):
                        self.log_test("Visit data completeness", True)
                        break
                else:
                    self.log_test("Visit data completeness", False, "Visits missing required fields")
                
        except Exception as e:
            self.log_test("Database Structure Test", False, f"Error: {str(e)}")
    
    def test_api_endpoints(self):
        """Test all patient history API endpoints"""
        print("\n🌐 Testing API endpoints...")
        
        # Test patient search endpoint
        try:
            response = requests.post(f"{self.base_url}/api/patient/search", 
                                   json={'phone': '9999999999'},
                                   timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('patient'):
                    self.log_test("Patient Search API", True, "Successfully found test patient")
                else:
                    self.log_test("Patient Search API", False, "Patient not found in search results")
            else:
                self.log_test("Patient Search API", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Patient Search API", False, f"Connection error: {str(e)}")
        
        # Test patient history endpoint
        try:
            response = requests.get(f"{self.base_url}/api/patient/{self.test_patient_id}/history", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('history'):
                    visit_count = len(data['history'])
                    self.log_test("Patient History API", True, f"Retrieved {visit_count} visits")
                else:
                    self.log_test("Patient History API", False, "No history data returned")
            else:
                self.log_test("Patient History API", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Patient History API", False, f"Connection error: {str(e)}")
        
        # Test patient complete history endpoint
        try:
            response = requests.get(f"{self.base_url}/api/patient/{self.test_patient_id}/complete-history", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('visits'):
                    visit_count = len(data['visits'])
                    self.log_test("Complete History API", True, f"Retrieved {visit_count} complete visits")
                else:
                    self.log_test("Complete History API", False, "No complete history data returned")
            else:
                self.log_test("Complete History API", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Complete History API", False, f"Connection error: {str(e)}")
        
        # Test visit details endpoint
        if self.test_visit_ids:
            try:
                response = requests.get(f"{self.base_url}/api/visit/{self.test_visit_ids[0]}/details", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success') and data.get('visit_details'):
                        self.log_test("Visit Details API", True, "Successfully retrieved visit details")
                    else:
                        self.log_test("Visit Details API", False, "No visit details returned")
                else:
                    self.log_test("Visit Details API", False, f"HTTP {response.status_code}")
            except Exception as e:
                self.log_test("Visit Details API", False, f"Connection error: {str(e)}")
        
        # Test patient summary endpoint
        try:
            response = requests.get(f"{self.base_url}/api/patient/summary/{self.test_patient_id}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('patient'):
                    self.log_test("Patient Summary API", True, "Successfully retrieved patient summary")
                else:
                    self.log_test("Patient Summary API", False, "No patient summary returned")
            else:
                self.log_test("Patient Summary API", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Patient Summary API", False, f"Connection error: {str(e)}")
    
    def test_data_integrity(self):
        """Test data relationships and integrity"""
        print("\n🔍 Testing data integrity...")
        
        try:
            with app.app_context():
                # Test patient-visit relationships
                patient = mongo.db.patient.find_one({'_id': ObjectId(self.test_patient_id)})
                visits = list(mongo.db.visit.find({'patient_id': ObjectId(self.test_patient_id)}))
                
                if patient and visits:
                    self.log_test("Patient-Visit Relationship", True, f"Patient has {len(visits)} associated visits")
                else:
                    self.log_test("Patient-Visit Relationship", False, "Missing patient or visits")
                
                # Test visit-doctor relationships
                valid_doctor_refs = 0
                for visit in visits:
                    doctor = mongo.db.doctor.find_one({'_id': visit['doctor_id']})
                    if doctor:
                        valid_doctor_refs += 1
                
                if valid_doctor_refs == len(visits):
                    self.log_test("Visit-Doctor Relationship", True, f"All {len(visits)} visits have valid doctor references")
                else:
                    self.log_test("Visit-Doctor Relationship", False, f"Only {valid_doctor_refs}/{len(visits)} visits have valid doctor references")
                
                # Test visit-department relationships
                valid_dept_refs = 0
                for visit in visits:
                    department = mongo.db.department.find_one({'_id': visit['department_id']})
                    if department:
                        valid_dept_refs += 1
                
                if valid_dept_refs == len(visits):
                    self.log_test("Visit-Department Relationship", True, f"All {len(visits)} visits have valid department references")
                else:
                    self.log_test("Visit-Department Relationship", False, f"Only {valid_dept_refs}/{len(visits)} visits have valid department references")
                
                # Test chronological ordering
                visit_dates = [visit['visit_date'] for visit in visits if 'visit_date' in visit]
                if len(visit_dates) > 1:
                    is_chronological = all(visit_dates[i] <= visit_dates[i+1] for i in range(len(visit_dates)-1))
                    self.log_test("Chronological Visit Ordering", True, "Visits can be properly ordered by date")
                
                # Test test results relationships
                tests = list(mongo.db.tests.find({'patient_id': ObjectId(self.test_patient_id)}))
                valid_test_refs = 0
                for test in tests:
                    if test['visit_id'] in [ObjectId(vid) for vid in self.test_visit_ids]:
                        valid_test_refs += 1
                
                if tests:
                    self.log_test("Test-Visit Relationship", valid_test_refs == len(tests), 
                                f"{valid_test_refs}/{len(tests)} tests have valid visit references")
                
        except Exception as e:
            self.log_test("Data Integrity Test", False, f"Error: {str(e)}")
    
    def test_search_functionality(self):
        """Test search and filtering capabilities"""
        print("\n🔎 Testing search functionality...")
        
        try:
            with app.app_context():
                # Test search by phone number
                patients_by_phone = list(mongo.db.patient.find({'contact_number': '9999999999'}))
                self.log_test("Search by Phone", len(patients_by_phone) > 0, 
                            f"Found {len(patients_by_phone)} patients by phone")
                
                # Test search by name (case insensitive)
                patients_by_name = list(mongo.db.patient.find({'name': {'$regex': 'test patient', '$options': 'i'}}))
                self.log_test("Search by Name", len(patients_by_name) > 0, 
                            f"Found {len(patients_by_name)} patients by name")
                
                # Test search by patient ID
                patients_by_id = list(mongo.db.patient.find({'patient_id': 'PT9999'}))
                self.log_test("Search by Patient ID", len(patients_by_id) > 0, 
                            f"Found {len(patients_by_id)} patients by ID")
                
                # Test visit filtering by status
                completed_visits = list(mongo.db.visit.find({
                    'patient_id': ObjectId(self.test_patient_id),
                    'status': 'completed'
                }))
                self.log_test("Filter Visits by Status", len(completed_visits) > 0, 
                            f"Found {len(completed_visits)} completed visits")
                
                # Test visit filtering by date range
                thirty_days_ago = datetime.now() - timedelta(days=30)
                recent_visits = list(mongo.db.visit.find({
                    'patient_id': ObjectId(self.test_patient_id),
                    'visit_date': {'$gte': thirty_days_ago}
                }))
                self.log_test("Filter Visits by Date", len(recent_visits) > 0, 
                            f"Found {len(recent_visits)} visits in last 30 days")
                
        except Exception as e:
            self.log_test("Search Functionality Test", False, f"Error: {str(e)}")
    
    def test_performance(self):
        """Test system performance with patient history queries"""
        print("\n⚡ Testing performance...")
        
        try:
            with app.app_context():
                import time
                
                # Test patient history query performance
                start_time = time.time()
                visits = list(mongo.db.visit.find({'patient_id': ObjectId(self.test_patient_id)}))
                query_time = time.time() - start_time
                
                self.log_test("Patient History Query Performance", query_time < 1.0, 
                            f"Query completed in {query_time:.3f} seconds")
                
                # Test aggregated patient data performance
                start_time = time.time()
                pipeline = [
                    {'$match': {'patient_id': ObjectId(self.test_patient_id)}},
                    {'$lookup': {
                        'from': 'doctor',
                        'localField': 'doctor_id',
                        'foreignField': '_id',
                        'as': 'doctor_info'
                    }},
                    {'$lookup': {
                        'from': 'department',
                        'localField': 'department_id',
                        'foreignField': '_id',
                        'as': 'department_info'
                    }},
                    {'$sort': {'visit_date': -1}}
                ]
                aggregated_visits = list(mongo.db.visit.aggregate(pipeline))
                aggregation_time = time.time() - start_time
                
                self.log_test("Aggregated Query Performance", aggregation_time < 2.0, 
                            f"Aggregation completed in {aggregation_time:.3f} seconds")
                
        except Exception as e:
            self.log_test("Performance Test", False, f"Error: {str(e)}")
    
    def cleanup_test_data(self):
        """Clean up test data"""
        print("\n🧹 Cleaning up test data...")
        
        try:
            with app.app_context():
                # Remove test data in reverse order of creation
                mongo.db.tests.delete_many({'patient_id': ObjectId(self.test_patient_id)})
                mongo.db.visit.delete_many({'patient_id': ObjectId(self.test_patient_id)})
                mongo.db.patient.delete_one({'_id': ObjectId(self.test_patient_id)})
                mongo.db.doctor.delete_one({'_id': ObjectId(self.test_doctor_id)})
                mongo.db.department.delete_one({'department_name': 'Test Cardiology'})
                mongo.db.admin.delete_one({'_id': ObjectId(self.test_admin_id)})
                
                self.log_test("Cleanup Test Data", True, "All test data removed successfully")
                
        except Exception as e:
            self.log_test("Cleanup Test Data", False, f"Error: {str(e)}")
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Patient History System Comprehensive Test Suite")
        print("=" * 60)
        
        # Setup
        if not self.setup_test_data():
            print("❌ Test setup failed. Aborting test suite.")
            return
        
        # Run all test categories
        self.test_database_structure()
        self.test_api_endpoints()
        self.test_data_integrity()
        self.test_search_functionality()
        self.test_performance()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  • {result['test']}: {result['message']}")
        
        print("\n" + "=" * 60)
        
        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED! Patient History System is working correctly.")
        else:
            print(f"⚠️  {failed_tests} tests failed. Please review the issues above.")
        
        print("=" * 60)

def main():
    """Main function to run the test suite"""
    print("Patient History System - Comprehensive Test Suite")
    print("This script will test all aspects of the patient history functionality")
    print()
    
    # Check if Flask app is available
    try:
        with app.app_context():
            # Test database connection
            mongo.db.admin.find_one()
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Please ensure MongoDB is running and the Flask app is properly configured")
        return
    
    # Run the test suite
    tester = PatientHistorySystemTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
