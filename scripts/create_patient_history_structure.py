#!/usr/bin/env python3
"""
Script to create and populate patient history database structure
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_comprehensive_patient_history():
    """Create comprehensive patient history tracking system"""
    try:
        client = MongoClient('mongodb://localhost:27017/')
        db = client.careorbit_db
        
        logger.info("Creating comprehensive patient history structure...")
        
        # Create patient_history collection with comprehensive tracking
        logger.info("Setting up patient_history collection...")
        
        # Create visit_summary collection for optimized queries
        logger.info("Setting up visit_summary collection...")
        
        # Migrate existing data
        logger.info("Migrating existing visit data...")
        visits = list(db.visit.find())
        visit_summaries = []
        patient_histories = []
        
        for visit in visits:
            # Get related data
            patient = db.patient.find_one({"_id": visit["patient_id"]})
            doctor = db.doctor.find_one({"_id": visit["doctor_id"]})
            department = db.department.find_one({"_id": visit["department_id"]})
            tests = list(db.tests.find({"visit_id": visit["_id"]}))
            
            # Create visit summary
            visit_summary = {
                "patient_id": visit["patient_id"],
                "visit_id": visit["_id"],
                "visit_date": visit.get("visit_date", visit.get("visit_date_time", datetime.now())),
                "doctor_id": visit["doctor_id"],
                "doctor_name": doctor["name"] if doctor else "Unknown",
                "department_id": visit["department_id"],
                "department_name": department["department_name"] if department else "Unknown",
                "chief_complaint": visit.get("reason_for_visit", ""),
                "symptoms": visit.get("symptoms", ""),
                "diagnosis": visit.get("diagnosis", ""),
                "medications": visit.get("medications", ""),
                "instructions": visit.get("instructions", ""),
                "tests_ordered": [
                    {
                        "test_id": str(test["_id"]),
                        "test_name": test["test_name"],
                        "test_type": test["test_type"],
                        "status": test["status"],
                        "results": test.get("results", ""),
                        "assigned_date": test["assigned_date"],
                        "completed_date": test.get("completed_date")
                    } for test in tests
                ],
                "follow_up_date": visit.get("follow_up_date"),
                "visit_status": visit.get("status", "completed"),
                "created_at": visit.get("created_at", datetime.now()),
                "updated_at": datetime.now()
            }
            visit_summaries.append(visit_summary)
            
            # Create patient history entry if visit is completed
            if visit.get("status") == "completed" and (visit.get("diagnosis") or visit.get("medications")):
                history_entry = {
                    "patient_id": visit["patient_id"],
                    "visit_id": visit["_id"],
                    "event_type": "visit_completed",
                    "event_date": visit.get("visit_date", visit.get("visit_date_time", datetime.now())),
                    "event_data": {
                        "doctor_name": doctor["name"] if doctor else "Unknown",
                        "department_name": department["department_name"] if department else "Unknown",
                        "chief_complaint": visit.get("reason_for_visit", ""),
                        "symptoms": visit.get("symptoms", ""),
                        "diagnosis": visit.get("diagnosis", ""),
                        "medications": visit.get("medications", ""),
                        "instructions": visit.get("instructions", ""),
                        "test_results": [test.get("results", "") for test in tests if test.get("results")],
                        "follow_up_date": visit.get("follow_up_date")
                    },
                    "created_at": datetime.now(),
                    "created_by": visit["doctor_id"]
                }
                patient_histories.append(history_entry)
        
        # Insert visit summaries
        if visit_summaries:
            db.visit_summary.drop()
            db.visit_summary.insert_many(visit_summaries)
            logger.info(f"Created {len(visit_summaries)} visit summaries")
        
        # Insert patient histories
        if patient_histories:
            db.patient_history.drop()
            db.patient_history.insert_many(patient_histories)
            logger.info(f"Created {len(patient_histories)} patient history entries")
        
        # Create indexes for optimal performance
        logger.info("Creating indexes for patient history collections...")
        
        # Visit summary indexes
        db.visit_summary.create_index([("patient_id", 1)])
        db.visit_summary.create_index([("visit_date", -1)])
        db.visit_summary.create_index([("patient_id", 1), ("visit_date", -1)])
        db.visit_summary.create_index([("doctor_id", 1)])
        db.visit_summary.create_index([("department_id", 1)])
        
        # Patient history indexes
        db.patient_history.create_index([("patient_id", 1)])
        db.patient_history.create_index([("event_date", -1)])
        db.patient_history.create_index([("patient_id", 1), ("event_date", -1)])
        db.patient_history.create_index([("event_type", 1)])
        
        logger.info("Patient history structure created successfully!")
        
        # Generate summary statistics
        total_patients = db.patient.count_documents({})
        total_visits = db.visit.count_documents({})
        total_summaries = db.visit_summary.count_documents({})
        total_histories = db.patient_history.count_documents({})
        
        print("\n" + "="*60)
        print("PATIENT HISTORY STRUCTURE CREATED SUCCESSFULLY")
        print("="*60)
        print(f"Total Patients: {total_patients}")
        print(f"Total Visits: {total_visits}")
        print(f"Visit Summaries Created: {total_summaries}")
        print(f"Patient History Entries: {total_histories}")
        print("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating patient history structure: {str(e)}")
        return False

if __name__ == "__main__":
    success = create_comprehensive_patient_history()
    if not success:
        sys.exit(1)
