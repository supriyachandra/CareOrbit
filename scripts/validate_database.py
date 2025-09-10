#!/usr/bin/env python3


import sys
import os
from pymongo import MongoClient
from datetime import datetime
import json

class DatabaseValidator:
    def __init__(self, connection_string="mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client.hospital_management
        self.validation_results = []
    
    def log_validation(self, check_name, success, message=""):
        """Log validation results"""
        status = "✅ VALID" if success else "❌ INVALID"
        print(f"{status}: {check_name}")
        if message:
            print(f"   {message}")
        self.validation_results.append({
            'check': check_name,
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
    
    def validate_collections_exist(self):
        """Validate that required collections exist"""
        required_collections = ['tests', 'test_results']
        existing_collections = self.db.list_collection_names()
        
        for collection in required_collections:
            exists = collection in existing_collections
            self.log_validation(f"Collection '{collection}' exists", exists)
        
        return all(col in existing_collections for col in required_collections)
    
    def validate_indexes(self):
        """Validate that required indexes exist"""
        index_checks = [
            ('tests', ['patient_id', 'visit_id', 'doctor_id', 'created_at']),
            ('test_results', ['test_id', 'created_at'])
        ]
        
        all_valid = True
        for collection_name, expected_indexes in index_checks:
            collection = self.db[collection_name]
            existing_indexes = list(collection.list_indexes())
            
            for expected_index in expected_indexes:
                # Check if index exists (simplified check)
                index_exists = any(
                    expected_index in str(idx.get('key', {})) 
                    for idx in existing_indexes
                )
                self.log_validation(
                    f"Index on '{collection_name}.{expected_index}'", 
                    index_exists
                )
                if not index_exists:
                    all_valid = False
        
        return all_valid
    
    def validate_sample_operations(self):
        """Validate basic CRUD operations work"""
        try:
            # Test insert
            test_doc = {
                'patient_id': 'test_patient',
                'visit_id': 'test_visit',
                'doctor_id': 'test_doctor',
                'test_type': 'Blood Test',
                'test_name': 'Sample Test',
                'status': 'pending',
                'created_at': datetime.now()
            }
            
            result = self.db.tests.insert_one(test_doc)
            insert_success = result.inserted_id is not None
            self.log_validation("Insert Operation", insert_success)
            
            if insert_success:
                # Test find
                found_doc = self.db.tests.find_one({'_id': result.inserted_id})
                find_success = found_doc is not None
                self.log_validation("Find Operation", find_success)
                
                # Test update
                update_result = self.db.tests.update_one(
                    {'_id': result.inserted_id},
                    {'$set': {'status': 'completed'}}
                )
                update_success = update_result.modified_count == 1
                self.log_validation("Update Operation", update_success)
                
                # Test delete (cleanup)
                delete_result = self.db.tests.delete_one({'_id': result.inserted_id})
                delete_success = delete_result.deleted_count == 1
                self.log_validation("Delete Operation", delete_success)
                
                return all([insert_success, find_success, update_success, delete_success])
            
            return False
            
        except Exception as e:
            self.log_validation("Sample Operations", False, str(e))
            return False
    
    def validate_data_integrity(self):
        """Validate data integrity constraints"""
        try:
            # Check for any orphaned test results
            test_ids = set(str(doc['_id']) for doc in self.db.tests.find({}, {'_id': 1}))
            orphaned_results = list(self.db.test_results.find({
                'test_id': {'$nin': list(test_ids)}
            }))
            
            orphaned_count = len(orphaned_results)
            integrity_valid = orphaned_count == 0
            
            self.log_validation(
                "Data Integrity", 
                integrity_valid,
                f"Found {orphaned_count} orphaned test results"
            )
            
            return integrity_valid
            
        except Exception as e:
            self.log_validation("Data Integrity", False, str(e))
            return False
    
    def run_validation(self):
        """Run all database validations"""
        print("🔍 Starting Database Validation for Tests Module")
        print("=" * 60)
        
        validations = [
            self.validate_collections_exist,
            self.validate_indexes,
            self.validate_sample_operations,
            self.validate_data_integrity
        ]
        
        passed = 0
        total = len(validations)
        
        for validation in validations:
            if validation():
                passed += 1
        
        print("\n" + "=" * 60)
        print(f"📊 Validation Results: {passed}/{total} checks passed")
        
        if passed == total:
            print("🎉 Database validation successful! All checks passed.")
        else:
            print(f"⚠️  {total - passed} validations failed. Please check the database setup.")
        
        return passed == total

def main():
    """Main validation execution"""
    print("Database Validation for Hospital Management System - Tests Module")
    print("Make sure MongoDB is running and accessible")
    print()
    
    try:
        validator = DatabaseValidator()
        success = validator.run_validation()
        
        # Save validation results
        with open('database_validation_results.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_checks': len(validator.validation_results),
                'passed_checks': sum(1 for r in validator.validation_results if r['success']),
                'results': validator.validation_results
            }, f, indent=2)
        
        print(f"\n📄 Detailed results saved to database_validation_results.json")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
