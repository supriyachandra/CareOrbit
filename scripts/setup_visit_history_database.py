from pymongo import MongoClient
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_visit_history_database():
    """
    Set up comprehensive visit history database structure for patient records
    """
    try:
        # Connect to MongoDB
        client = MongoClient('mongodb://localhost:27017/')
        db = client['careorbit_db']
        
        logger.info("Setting up visit history database structure...")
        
        # 1. Create indexes for better performance
        logger.info("Creating database indexes...")
        
        # Patient collection indexes
        db.patient.create_index([("patient_id", 1)], unique=True)
        db.patient.create_index([("contact_number", 1)])
        db.patient.create_index([("name", 1)])
        db.patient.create_index([("created_at", -1)])
        
        # Visit collection indexes
        db.visit.create_index([("patient_id", 1), ("visit_date", -1)])
        db.visit.create_index([("doctor_id", 1), ("visit_date", -1)])
        db.visit.create_index([("department_id", 1)])
        db.visit.create_index([("status", 1)])
        db.visit.create_index([("visit_date", -1)])
        
        # Prescription collection indexes
        db.prescription.create_index([("patient_id", 1), ("prescription_timestamp", -1)])
        db.prescription.create_index([("visit_id", 1)], unique=True)
        db.prescription.create_index([("doctor_id", 1)])
        
        # Patient history summary collection indexes
        db.patient_history.create_index([("patient_id", 1), ("visit_date", -1)])
        db.patient_history.create_index([("visit_id", 1)], unique=True)
        
        # Tests collection indexes
        db.tests.create_index([("patient_id", 1), ("assigned_date", -1)])
        db.tests.create_index([("visit_id", 1)])
        db.tests.create_index([("status", 1)])
        
        logger.info("Database indexes created successfully")
        
        # 2. Ensure all existing visits have proper structure
        logger.info("Updating existing visit records...")
        
        visits_updated = 0
        for visit in db.visit.find({}):
            update_data = {}
            
            # Ensure visit has all required fields
            if 'status' not in visit:
                update_data['status'] = 'completed'
            
            if 'created_at' not in visit:
                update_data['created_at'] = visit.get('visit_date', datetime.now())
            
            if 'visit_type' not in visit:
                update_data['visit_type'] = 'regular'
            
            if 'priority' not in visit:
                update_data['priority'] = 'normal'
            
            if update_data:
                db.visit.update_one({'_id': visit['_id']}, {'$set': update_data})
                visits_updated += 1
        
        logger.info(f"Updated {visits_updated} visit records")
        
        # 3. Create patient history summary for existing visits
        logger.info("Creating patient history summaries...")
        
        # Clear existing patient history to rebuild
        db.patient_history.delete_many({})
        
        history_created = 0
        for visit in db.visit.find({}).sort('visit_date', -1):
            try:
                patient = db.patient.find_one({'_id': visit['patient_id']})
                doctor = db.doctor.find_one({'_id': visit.get('doctor_id')})
                department = db.department.find_one({'_id': visit.get('department_id')})
                
                if patient:
                    history_entry = {
                        'patient_id': visit['patient_id'],
                        'visit_id': visit['_id'],
                        'patient_name': patient['name'],
                        'patient_id_string': patient['patient_id'],
                        'doctor_name': doctor['name'] if doctor else 'Unknown Doctor',
                        'department_name': department['department_name'] if department else 'Unknown Department',
                        'visit_date': visit.get('visit_date', datetime.now()),
                        'reason_for_visit': visit.get('reason_for_visit', ''),
                        'symptoms': visit.get('symptoms', ''),
                        'diagnosis': visit.get('diagnosis', ''),
                        'medications': visit.get('medications', ''),
                        'instructions': visit.get('instructions', ''),
                        'follow_up_date': visit.get('follow_up_date'),
                        'status': visit.get('status', 'completed'),
                        'visit_type': visit.get('visit_type', 'regular'),
                        'priority': visit.get('priority', 'normal'),
                        'created_at': visit.get('created_at', datetime.now()),
                        'completed_at': visit.get('prescription_timestamp', visit.get('visit_date', datetime.now()))
                    }
                    
                    db.patient_history.insert_one(history_entry)
                    history_created += 1
                    
            except Exception as e:
                logger.error(f"Error creating history for visit {visit['_id']}: {e}")
                continue
        
        logger.info(f"Created {history_created} patient history entries")
        
        # 4. Update patient records with visit statistics
        logger.info("Updating patient visit statistics...")
        
        patients_updated = 0
        for patient in db.patient.find({}):
            try:
                # Count total visits
                total_visits = db.visit.count_documents({'patient_id': patient['_id']})
                
                # Get last visit date
                last_visit = db.visit.find_one(
                    {'patient_id': patient['_id']},
                    sort=[('visit_date', -1)]
                )
                
                # Count completed visits
                completed_visits = db.visit.count_documents({
                    'patient_id': patient['_id'],
                    'status': 'completed'
                })
                
                update_data = {
                    'total_visits': total_visits,
                    'completed_visits': completed_visits,
                    'last_visit_date': last_visit['visit_date'] if last_visit else None,
                    'updated_at': datetime.now()
                }
                
                db.patient.update_one({'_id': patient['_id']}, {'$set': update_data})
                patients_updated += 1
                
            except Exception as e:
                logger.error(f"Error updating patient {patient['_id']}: {e}")
                continue
        
        logger.info(f"Updated {patients_updated} patient records with visit statistics")
        
        # 5. Create comprehensive prescription records
        logger.info("Creating comprehensive prescription records...")
        
        prescriptions_created = 0
        for visit in db.visit.find({'status': 'completed'}):
            try:
                # Check if prescription record already exists
                existing_prescription = db.prescription.find_one({'visit_id': visit['_id']})
                
                if not existing_prescription and (visit.get('diagnosis') or visit.get('medications')):
                    patient = db.patient.find_one({'_id': visit['patient_id']})
                    doctor = db.doctor.find_one({'_id': visit.get('doctor_id')})
                    department = db.department.find_one({'_id': visit.get('department_id')})
                    
                    if patient:
                        # Calculate age
                        today = datetime.now()
                        age = 0
                        if isinstance(patient.get('date_of_birth'), datetime):
                            age = today.year - patient['date_of_birth'].year
                            if today.month < patient['date_of_birth'].month or \
                               (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                                age -= 1
                        
                        prescription_record = {
                            'visit_id': visit['_id'],
                            'patient_id': visit['patient_id'],
                            'patient_name': patient['name'],
                            'patient_age': age,
                            'patient_id_string': patient['patient_id'],
                            'doctor_id': visit.get('doctor_id'),
                            'doctor_name': doctor['name'] if doctor else 'Unknown Doctor',
                            'department_id': visit.get('department_id'),
                            'department_name': department['department_name'] if department else 'Unknown Department',
                            'visit_date': visit.get('visit_date', datetime.now()),
                            'reason_for_visit': visit.get('reason_for_visit', ''),
                            'symptoms': visit.get('symptoms', ''),
                            'diagnosis': visit.get('diagnosis', ''),
                            'medications': visit.get('medications', ''),
                            'instructions': visit.get('instructions', ''),
                            'follow_up_date': visit.get('follow_up_date'),
                            'prescription_timestamp': visit.get('prescription_timestamp', visit.get('visit_date', datetime.now())),
                            'created_at': datetime.now(),
                            'status': 'active'
                        }
                        
                        db.prescription.insert_one(prescription_record)
                        prescriptions_created += 1
                        
            except Exception as e:
                logger.error(f"Error creating prescription for visit {visit['_id']}: {e}")
                continue
        
        logger.info(f"Created {prescriptions_created} comprehensive prescription records")
        
        # 6. Verify data integrity
        logger.info("Verifying data integrity...")
        
        total_patients = db.patient.count_documents({})
        total_visits = db.visit.count_documents({})
        total_history_entries = db.patient_history.count_documents({})
        total_prescriptions = db.prescription.count_documents({})
        
        logger.info(f"Database summary:")
        logger.info(f"  - Total patients: {total_patients}")
        logger.info(f"  - Total visits: {total_visits}")
        logger.info(f"  - Total history entries: {total_history_entries}")
        logger.info(f"  - Total prescriptions: {total_prescriptions}")
        
        # Check for any patients without history
        patients_without_history = []
        for patient in db.patient.find({}):
            history_count = db.patient_history.count_documents({'patient_id': patient['_id']})
            if history_count == 0:
                visit_count = db.visit.count_documents({'patient_id': patient['_id']})
                if visit_count > 0:
                    patients_without_history.append(patient['patient_id'])
        
        if patients_without_history:
            logger.warning(f"Found {len(patients_without_history)} patients with visits but no history entries")
        else:
            logger.info("All patients with visits have corresponding history entries")
        
        logger.info("Visit history database setup completed successfully!")
        
        return {
            'success': True,
            'patients_updated': patients_updated,
            'visits_updated': visits_updated,
            'history_created': history_created,
            'prescriptions_created': prescriptions_created,
            'total_patients': total_patients,
            'total_visits': total_visits,
            'total_history_entries': total_history_entries,
            'total_prescriptions': total_prescriptions
        }
        
    except Exception as e:
        logger.error(f"Error setting up visit history database: {e}")
        return {'success': False, 'error': str(e)}
    
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    result = setup_visit_history_database()
    if result['success']:
        print("✅ Visit history database setup completed successfully!")
        print(f"📊 Summary: {result['patients_updated']} patients updated, {result['history_created']} history entries created")
    else:
        print(f"❌ Database setup failed: {result['error']}")
