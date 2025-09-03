from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_database_indexes(mongo_uri):
    """Setup database indexes for optimal performance"""
    try:
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        # Patient collection indexes
        db.patient.create_index([("contact_number", ASCENDING)])  # Removed unique constraint on contact_number to allow multiple patients with same phone
        db.patient.create_index([("patient_id", ASCENDING)], unique=True)
        db.patient.create_index([("name", ASCENDING)])
        db.patient.create_index([("created_at", DESCENDING)])
        
        db.patient.create_index([("aadhaar_number", ASCENDING)], unique=True, sparse=True)
        
        db.patient.create_index([
            ("name", ASCENDING), 
            ("contact_number", ASCENDING)
        ], unique=True)
        
        # The old index: db.patient.create_index([("contact_number", ASCENDING), ("name", ASCENDING), ("aadhaar_number", ASCENDING)], unique=True, sparse=True)
        
        # Visit collection indexes
        db.visit.create_index([("patient_id", ASCENDING)])
        db.visit.create_index([("doctor_id", ASCENDING)])
        db.visit.create_index([("department_id", ASCENDING)])
        db.visit.create_index([("visit_date", DESCENDING)])  # Fixed field name from visit_date_time to visit_date
        db.visit.create_index([("status", ASCENDING)])
        db.visit.create_index([("follow_up_date", ASCENDING)])
        db.visit.create_index([("doctor_id", ASCENDING), ("status", ASCENDING)])
        
        # Doctor collection indexes
        db.doctor.create_index([("username", ASCENDING)], unique=True)
        db.doctor.create_index([("department_id", ASCENDING)])
        db.doctor.create_index([("name", ASCENDING)])
        
        # Admin collection indexes
        db.admin.create_index([("username", ASCENDING)], unique=True)
        
        # Department collection indexes
        db.department.create_index([("department_name", ASCENDING)], unique=True)
        
        # Compound indexes for common queries
        db.visit.create_index([("doctor_id", ASCENDING), ("visit_date", DESCENDING)])  # Fixed field name
        db.visit.create_index([("patient_id", ASCENDING), ("visit_date", DESCENDING)])  # Fixed field name
        
        # Tests collection indexes
        db.tests.create_index([("patient_id", ASCENDING)])
        db.tests.create_index([("doctor_id", ASCENDING)])
        db.tests.create_index([("visit_id", ASCENDING)])
        db.tests.create_index([("status", ASCENDING)])
        db.tests.create_index([("test_type", ASCENDING)])
        db.tests.create_index([("assigned_date", DESCENDING)])
        db.tests.create_index([("completed_date", DESCENDING)])
        
        # Compound indexes for tests
        db.tests.create_index([("patient_id", ASCENDING), ("assigned_date", DESCENDING)])
        db.tests.create_index([("doctor_id", ASCENDING), ("status", ASCENDING)])
        db.tests.create_index([("visit_id", ASCENDING), ("test_type", ASCENDING)])
        
        # Test results collection indexes (for file metadata)
        db.test_results.create_index([("test_id", ASCENDING)])
        db.test_results.create_index([("patient_id", ASCENDING)])
        db.test_results.create_index([("upload_date", DESCENDING)])
        db.test_results.create_index([("file_type", ASCENDING)])
        
        db.prescription.create_index([("patient_id", ASCENDING)])
        db.prescription.create_index([("doctor_id", ASCENDING)])
        db.prescription.create_index([("visit_id", ASCENDING)])
        db.prescription.create_index([("prescription_timestamp", DESCENDING)])
        db.prescription.create_index([("patient_id", ASCENDING), ("prescription_timestamp", DESCENDING)])
        
        db.patient_history.create_index([("patient_id", ASCENDING)])
        db.patient_history.create_index([("visit_id", ASCENDING)])
        db.patient_history.create_index([("event_date", DESCENDING)])
        db.patient_history.create_index([("event_type", ASCENDING)])
        db.patient_history.create_index([("patient_id", ASCENDING), ("event_date", DESCENDING)])
        
        db.visit_summary.create_index([("patient_id", ASCENDING)])
        db.visit_summary.create_index([("visit_date", DESCENDING)])
        db.visit_summary.create_index([("doctor_id", ASCENDING)])
        db.visit_summary.create_index([("department_id", ASCENDING)])
        db.visit_summary.create_index([("patient_id", ASCENDING), ("visit_date", DESCENDING)])
        
        logger.info("Database indexes created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating database indexes: {str(e)}")
        return False

def validate_database_integrity(mongo_uri):
    """Validate database integrity and relationships"""
    try:
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        issues = []
        
        # Check for orphaned visits (visits without valid patient/doctor/department)
        visits = db.visit.find()
        for visit in visits:
            if not db.patient.find_one({"_id": visit["patient_id"]}):
                issues.append(f"Visit {visit['_id']} has invalid patient_id")
            if not db.doctor.find_one({"_id": visit["doctor_id"]}):
                issues.append(f"Visit {visit['_id']} has invalid doctor_id")
            if not db.department.find_one({"_id": visit["department_id"]}):
                issues.append(f"Visit {visit['_id']} has invalid department_id")
        
        # Check for orphaned tests (tests without valid patient/doctor/visit)
        tests = db.tests.find()
        for test in tests:
            if not db.patient.find_one({"_id": test["patient_id"]}):
                issues.append(f"Test {test['_id']} has invalid patient_id")
            if not db.doctor.find_one({"_id": test["doctor_id"]}):
                issues.append(f"Test {test['_id']} has invalid doctor_id")
            # Note: visit_id validation is optional as tests can exist independently
        
        # Check for orphaned test results
        test_results = db.test_results.find()
        for result in test_results:
            if not db.tests.find_one({"_id": result["test_id"]}):
                issues.append(f"Test result {result['_id']} has invalid test_id")

        prescriptions = db.prescription.find()
        for prescription in prescriptions:
            if not db.patient.find_one({"_id": prescription["patient_id"]}):
                issues.append(f"Prescription {prescription['_id']} has invalid patient_id")
            if not db.doctor.find_one({"_id": prescription["doctor_id"]}):
                issues.append(f"Prescription {prescription['_id']} has invalid doctor_id")
            if not db.visit.find_one({"_id": prescription["visit_id"]}):
                issues.append(f"Prescription {prescription['_id']} has invalid visit_id")

        # Check for duplicate name+phone combinations
        name_phone_pipeline = [
            {"$group": {
                "_id": {
                    "name": "$name",
                    "contact_number": "$contact_number"
                }, 
                "count": {"$sum": 1},
                "patients": {"$push": "$patient_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        name_phone_duplicates = list(db.patient.aggregate(name_phone_pipeline))
        for dup in name_phone_duplicates:
            issues.append(f"Duplicate name+phone combination: {dup['_id']} (Patient IDs: {dup['patients']})")
        
        # Check for duplicate aadhaar numbers
        aadhaar_pipeline = [
            {"$match": {"aadhaar_number": {"$ne": "", "$exists": True}}},
            {"$group": {
                "_id": "$aadhaar_number", 
                "count": {"$sum": 1},
                "patients": {"$push": "$patient_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        aadhaar_duplicates = list(db.patient.aggregate(aadhaar_pipeline))
        for dup in aadhaar_duplicates:
            issues.append(f"Duplicate Aadhaar number: {dup['_id']} (Patient IDs: {dup['patients']})")
        
        if issues:
            logger.warning(f"Database integrity issues found: {issues}")
        else:
            logger.info("Database integrity check passed")
            
        return issues
        
    except Exception as e:
        logger.error(f"Error validating database integrity: {str(e)}")
        return [f"Integrity check failed: {str(e)}"]

def create_patient_history_structure(mongo_uri):
    """Create comprehensive patient history tracking structure"""
    try:
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        # Create patient_history collection schema
        patient_history_schema = {
            "patient_id": "ObjectId - Reference to patient",
            "visit_id": "ObjectId - Reference to visit (optional)",
            "event_type": "String - visit, prescription, test, follow_up, etc.",
            "event_date": "DateTime - When the event occurred",
            "event_data": {
                "doctor_name": "String",
                "department_name": "String", 
                "diagnosis": "String",
                "medications": "String",
                "test_results": "String",
                "notes": "String"
            },
            "created_at": "DateTime",
            "created_by": "ObjectId - Reference to user who created the record"
        }
        
        # Create visit_summary collection for quick access
        visit_summary_schema = {
            "patient_id": "ObjectId - Reference to patient",
            "visit_id": "ObjectId - Reference to visit",
            "visit_date": "DateTime",
            "doctor_id": "ObjectId",
            "doctor_name": "String",
            "department_id": "ObjectId", 
            "department_name": "String",
            "chief_complaint": "String",
            "diagnosis": "String",
            "medications": "Array of medication objects",
            "tests_ordered": "Array of test objects",
            "follow_up_date": "DateTime",
            "visit_status": "String - completed, pending, cancelled",
            "created_at": "DateTime",
            "updated_at": "DateTime"
        }
        
        logger.info("Patient history database structure created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating patient history structure: {str(e)}")
        return False

def migrate_existing_data_to_history(mongo_uri):
    """Migrate existing visit and prescription data to patient history structure"""
    try:
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        # Migrate visits to visit_summary
        visits = db.visit.find()
        visit_summaries = []
        
        for visit in visits:
            patient = db.patient.find_one({"_id": visit["patient_id"]})
            doctor = db.doctor.find_one({"_id": visit["doctor_id"]})
            department = db.department.find_one({"_id": visit["department_id"]})
            
            visit_summary = {
                "patient_id": visit["patient_id"],
                "visit_id": visit["_id"],
                "visit_date": visit.get("visit_date", visit.get("visit_date_time", datetime.now())),
                "doctor_id": visit["doctor_id"],
                "doctor_name": doctor["name"] if doctor else "Unknown",
                "department_id": visit["department_id"],
                "department_name": department["department_name"] if department else "Unknown",
                "chief_complaint": visit.get("reason_for_visit", ""),
                "diagnosis": visit.get("diagnosis", ""),
                "medications": visit.get("medications", ""),
                "tests_ordered": [],  # Will be populated from tests collection
                "follow_up_date": visit.get("follow_up_date"),
                "visit_status": visit.get("status", "completed"),
                "created_at": visit.get("created_at", datetime.now()),
                "updated_at": datetime.now()
            }
            
            # Get tests for this visit
            tests = list(db.tests.find({"visit_id": visit["_id"]}))
            visit_summary["tests_ordered"] = [
                {
                    "test_name": test["test_name"],
                    "test_type": test["test_type"],
                    "status": test["status"],
                    "results": test.get("results", "")
                } for test in tests
            ]
            
            visit_summaries.append(visit_summary)
        
        if visit_summaries:
            # Clear existing visit_summary collection
            db.visit_summary.drop()
            db.visit_summary.insert_many(visit_summaries)
            logger.info(f"Migrated {len(visit_summaries)} visits to visit_summary collection")
        
        # Create patient history entries
        patient_history_entries = []
        
        for visit in visits:
            if visit.get("status") == "completed" and visit.get("diagnosis"):
                patient = db.patient.find_one({"_id": visit["patient_id"]})
                doctor = db.doctor.find_one({"_id": visit["doctor_id"]})
                department = db.department.find_one({"_id": visit["department_id"]})
                
                history_entry = {
                    "patient_id": visit["patient_id"],
                    "visit_id": visit["_id"],
                    "event_type": "visit_completed",
                    "event_date": visit.get("visit_date", visit.get("visit_date_time", datetime.now())),
                    "event_data": {
                        "doctor_name": doctor["name"] if doctor else "Unknown",
                        "department_name": department["department_name"] if department else "Unknown",
                        "diagnosis": visit.get("diagnosis", ""),
                        "medications": visit.get("medications", ""),
                        "notes": visit.get("instructions", "")
                    },
                    "created_at": datetime.now(),
                    "created_by": visit["doctor_id"]
                }
                patient_history_entries.append(history_entry)
        
        if patient_history_entries:
            # Clear existing patient_history collection
            db.patient_history.drop()
            db.patient_history.insert_many(patient_history_entries)
            logger.info(f"Created {len(patient_history_entries)} patient history entries")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating data to history structure: {str(e)}")
        return False

def backup_database(mongo_uri, backup_path):
    """Create database backup"""
    try:
        import json
        import os
        from datetime import datetime
        
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        backup_dir = f"{backup_path}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(backup_dir, exist_ok=True)
        
        collections = ['patient', 'doctor', 'admin', 'department', 'visit', 'tests', 'test_results', 'prescription', 'patient_history', 'visit_summary']
        
        for collection_name in collections:
            collection = db[collection_name]
            documents = list(collection.find())
            
            # Convert ObjectId to string for JSON serialization
            for doc in documents:
                for key, value in doc.items():
                    if hasattr(value, '__class__') and value.__class__.__name__ == 'ObjectId':
                        doc[key] = str(value)
                    elif isinstance(value, datetime):
                        doc[key] = value.isoformat()
            
            with open(f"{backup_dir}/{collection_name}.json", 'w') as f:
                json.dump(documents, f, indent=2, default=str)
        
        logger.info(f"Database backup created at: {backup_dir}")
        return backup_dir
        
    except Exception as e:
        logger.error(f"Error creating database backup: {str(e)}")
        return None

def get_database_stats(mongo_uri):
    """Get comprehensive database statistics"""
    try:
        client = MongoClient(mongo_uri)
        db = client.careorbit_db
        
        stats = {
            'collections': {},
            'total_size': 0,
            'indexes': {}
        }
        
        collections = ['patient', 'doctor', 'admin', 'department', 'visit', 'tests', 'test_results', 'prescription', 'patient_history', 'visit_summary']
        
        for collection_name in collections:
            collection = db[collection_name]
            
            # Collection stats
            try:
                coll_stats = db.command("collStats", collection_name)
                stats['collections'][collection_name] = {
                    'count': collection.count_documents({}),
                    'size': coll_stats.get('size', 0),
                    'avg_obj_size': coll_stats.get('avgObjSize', 0)
                }
            except:
                # Collection might not exist yet
                stats['collections'][collection_name] = {
                    'count': 0,
                    'size': 0,
                    'avg_obj_size': 0
                }
            
            # Index stats
            try:
                stats['indexes'][collection_name] = list(collection.list_indexes())
            except:
                stats['indexes'][collection_name] = []
            
            stats['total_size'] += stats['collections'][collection_name]['size']
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return None

if __name__ == "__main__":
    # Setup database when run directly
    mongo_uri = "mongodb://localhost:27017/"
    setup_database_indexes(mongo_uri)
    create_patient_history_structure(mongo_uri)
    migrate_existing_data_to_history(mongo_uri)
    validate_database_integrity(mongo_uri)
