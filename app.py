from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response, send_file
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from functools import wraps
import os
import logging
import re
import base64
import mimetypes
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()  # Load variables from .env
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["MONGO_URI"] = "mongodb://localhost:27017/careorbit_db"

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads/test_results'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
ALLOWED_MIME_TYPES = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_file(file, filename=None):
    """Enhanced file validation with size and MIME type checking"""
    try:
        if filename is None:
            filename = file.filename if hasattr(file, 'filename') else 'unknown'
        
        # Check if file has a filename
        if not filename or filename == '':
            return False, "No filename provided"
        
        # Check file extension
        if not allowed_file(filename):
            return False, f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        
        # Check file size for uploaded files
        if hasattr(file, 'seek') and hasattr(file, 'tell'):
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer
            
            if file_size > MAX_FILE_SIZE:
                return False, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            
            if file_size == 0:
                return False, "Empty file not allowed"
        
        # Validate filename characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', secure_filename(filename)):
            return False, "Invalid characters in filename"
        
        return True, "File is valid"
        
    except Exception as e:
        return False, f"File validation error: {str(e)}"

def cleanup_old_files():
    """Clean up files older than 30 days"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            return
        
        cutoff_date = datetime.now() - timedelta(days=30)
        
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path):
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_modified < cutoff_date:
                    # Check if file is still referenced in database
                    file_in_use = mongo.db.tests.find_one({
                        'result_files.stored_filename': filename
                    })
                    
                    if not file_in_use:
                        try:
                            os.remove(file_path)
                            logging.info(f"Cleaned up old file: {filename}")
                        except OSError as e:
                            logging.error(f"Error removing file {filename}: {e}")
    except Exception as e:
        logging.error(f"Error during file cleanup: {e}")

# Initialize PyMongo
mongo = PyMongo(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

class User(UserMixin):
    def __init__(self, user_id, username, role, name):
        self.id = user_id
        self.username = username
        self.role = role
        self.name = name

@login_manager.user_loader
def load_user(user_id):
    # Try to find user in admin collection
    admin = mongo.db.admin.find_one({'_id': ObjectId(user_id)})
    if admin:
        return User(str(admin['_id']), admin['username'], 'admin', admin['name'])
    
    # Try to find user in doctor collection
    doctor = mongo.db.doctor.find_one({'_id': ObjectId(user_id)})
    if doctor:
        return User(str(doctor['_id']), doctor['username'], 'doctor', doctor['name'])
    
    return None

def role_required(roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin/login')
def admin_login():
    return render_template('admin_login.html')

@app.route('/doctor/login')
def doctor_login():
    return render_template('doctor_login.html')

@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/departments')
@role_required('admin')
def admin_departments():
    patient_id = request.args.get('patient_id')
    if not patient_id:
        return redirect(url_for('admin_dashboard'))
    
    patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return redirect(url_for('admin_dashboard'))
    
    # Calculate age
    today = datetime.now()
    age = today.year - patient['date_of_birth'].year
    if today.month < patient['date_of_birth'].month or \
       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
        age -= 1
    
    patient['age'] = age
    return render_template('departments.html', patient=patient)

@app.route('/admin/doctors')
@role_required('admin')
def admin_doctors():
    patient_id = request.args.get('patient_id')
    department_id = request.args.get('department_id')
    department_name = request.args.get('department_name')
    
    if not patient_id or not department_id:
        return redirect(url_for('admin_dashboard'))
    
    patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return redirect(url_for('admin_dashboard'))
    
    # Calculate age
    today = datetime.now()
    age = today.year - patient['date_of_birth'].year
    if today.month < patient['date_of_birth'].month or \
       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
        age -= 1
    
    patient['age'] = age
    return render_template('doctors.html', patient=patient, department_name=department_name)

@app.route('/admin/search-results')
@role_required(['admin'])
def admin_search_results():
    return render_template('search_results.html')

@app.route('/admin/patients')
@role_required('admin')
def admin_patients():
    return render_template('patient_management.html')

@app.route('/admin/manage-doctors')
@role_required('admin')
def admin_manage_doctors():
    return render_template('manage_doctors.html')

@app.route('/api/doctor/past-patients')
@role_required('doctor')
def get_past_patients():
    try:
        doctor_id = current_user.id
        
        # Get patients from the past 1 month
        one_month_ago = datetime.now() - timedelta(days=30)
        
        visits = list(mongo.db.visit.find({
            'doctor_id': ObjectId(doctor_id),
            'visit_date': {'$gte': one_month_ago},
            'status': 'completed'
        }).sort('visit_date', -1))
        
        past_patients = []
        for visit in visits:
            patient = mongo.db.patient.find_one({'_id': visit['patient_id']})
            if patient:
                # Calculate age
                try:
                    today_date = datetime.now()
                    if isinstance(patient['date_of_birth'], datetime):
                        age = today_date.year - patient['date_of_birth'].year
                        if today_date.month < patient['date_of_birth'].month or \
                           (today_date.month == today_date.month and today_date.day < patient['date_of_birth'].day):
                            age -= 1
                    else:
                        age = 0
                except:
                    age = 0
                
                patient_data = {
                    'visit_id': str(visit['_id']),
                    'patient_id': patient['patient_id'],
                    'name': patient['name'],
                    'age': age,
                    'gender': patient['gender'],
                    'contact_number': patient['contact_number'],
                    'visit_date': visit['visit_date'].strftime('%Y-%m-%d %H:%M'),
                    'symptoms': visit.get('symptoms', ''),
                    'diagnosis': visit.get('diagnosis', ''),
                    'medications': visit.get('medications', ''),
                    'instructions': visit.get('instructions', ''),
                    'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else ''
                }
                past_patients.append(patient_data)
        
        return jsonify({'success': True, 'past_patients': past_patients})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching past patients: {str(e)}'})

@app.route('/doctor/dashboard')
@role_required('doctor')
def doctor_dashboard():
    try:
        doctor_id = current_user.id
        
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_id)})
        doctor_info = {
            'name': doctor.get('name', session.get('username', 'Unknown')),
            'department': 'Unknown Department'  # Default value
        } if doctor else None
        
        if doctor and 'department_id' in doctor:
            department = mongo.db.department.find_one({'_id': ObjectId(doctor['department_id'])})
            if department:
                doctor_info['department'] = department.get('department_name', 'Unknown Department')
        
        # Get today's assigned patients with patient details
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        print(f"Doctor {doctor_id} looking for visits between {start_of_day} and {end_of_day}")
        
        visits = list(mongo.db.visit.find({
            'doctor_id': ObjectId(doctor_id),
            'visit_date': {'$gte': start_of_day, '$lte': end_of_day}
        }).sort([('status', 1), ('visit_date', 1)]))  # Sort by status first (assigned/pending before completed), then by time
        
        print(f"Found {len(visits)} visits for doctor {doctor_id}")
        
        patients_data = []
        for visit in visits:
            patient = mongo.db.patient.find_one({'_id': visit['patient_id']})
            if patient:
                # Calculate age
                try:
                    today_date = datetime.now()
                    if isinstance(patient['date_of_birth'], datetime):
                        age = today_date.year - patient['date_of_birth'].year
                        if today_date.month < patient['date_of_birth'].month or \
                           (today_date.month == today_date.month and today_date.day < patient['date_of_birth'].day):
                            age -= 1
                    else:
                        age = 0
                except:
                    age = 0
                
                visit_data = {
                    '_id': str(visit['_id']),
                    'patient_details': {
                        'patient_id': patient['patient_id'],
                        'name': patient['name'],
                        'contact_number': patient['contact_number'],
                        'gender': patient['gender'],
                        'address': patient['address'],
                        'age': age,  # Added age to patient_details
                        'allergies': patient.get('allergies', 'None'),
                        'chronic_conditions': patient.get('chronic_illness', 'None'),
                        '_id': str(patient['_id'])  # Add MongoDB ObjectId for history functionality
                    },
                    'reason_for_visit': visit.get('reason_for_visit', 'General consultation'),
                    'visit_date': visit['visit_date'],  # Fixed field name
                    'status': visit['status'],
                    'symptoms': visit.get('symptoms', ''),
                    'diagnosis': visit.get('diagnosis', ''),
                    'medications': visit.get('medications', ''),
                    'instructions': visit.get('instructions', ''),
                    'follow_up_date': visit.get('follow_up_date')
                }
                patients_data.append(visit_data)
        
        print(f"Returning {len(patients_data)} patients to template")
        return render_template('doctor_dashboard.html', patients=patients_data, doctor_info=doctor_info)
        
    except Exception as e:
        print(f"Doctor dashboard error: {str(e)}")
        return render_template('doctor_dashboard.html', patients=[], doctor_info=None)

@app.route('/api/doctor/search-patients', methods=['POST'])
@role_required('doctor')
def doctor_search_patients():
    try:
        data = request.get_json()
        search_term = data.get('search_term', '').strip()
        
        if not search_term:
            return jsonify({'success': False, 'message': 'Search term is required'})
        
        # Search patients by name, phone, or patient ID
        search_regex = re.compile(search_term, re.IGNORECASE)
        patients = list(mongo.db.patient.find({
            '$or': [
                {'name': search_regex},
                {'contact_number': search_regex},
                {'patient_id': search_regex}
            ]
        }))
        
        patients_data = []
        for patient in patients:
            # Get recent visit count and last visit date
            recent_visits = mongo.db.visit.count_documents({'patient_id': patient['_id']})
            last_visit = mongo.db.visit.find_one(
                {'patient_id': patient['_id']}, 
                sort=[('visit_date', -1)]
            )
            
            # Calculate age
            try:
                today_date = datetime.now()
                if isinstance(patient['date_of_birth'], datetime):
                    age = today_date.year - patient['date_of_birth'].year
                    if today_date.month < patient['date_of_birth'].month or \
                       (today_date.month == today_date.month and today_date.day < patient['date_of_birth'].day):
                        age -= 1
                else:
                    age = 0
            except:
                age = 0
            
            patient_data = {
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'contact_number': patient['contact_number'],
                'gender': patient['gender'],
                'age': age,
                'allergies': patient.get('allergies', 'None'),
                'chronic_conditions': patient.get('chronic_illness', 'None'),
                'recent_visits': recent_visits,
                'last_visit': last_visit['visit_date'].strftime('%b %d, %Y') if last_visit else 'Never'
            }
            patients_data.append(patient_data)
        
        return jsonify({
            'success': True,
            'patients': patients_data
        })
        
    except Exception as e:
        print(f"Doctor patient search error: {str(e)}")
        return jsonify({'success': False, 'message': 'Search error occurred'})

@app.route('/api/admin/login', methods=['POST'])
def admin_login_api():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        admin = mongo.db.admin.find_one({'username': username})
        
        if admin and check_password_hash(admin['password_hash'], password):
            user = User(str(admin['_id']), admin['username'], 'admin', admin['name'])
            login_user(user)
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'redirect': '/admin/dashboard'
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Login error occurred'})

@app.route('/api/doctor/login', methods=['POST'])
def doctor_login_api():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        doctor = mongo.db.doctor.find_one({'username': username})
        
        if doctor and check_password_hash(doctor['password_hash'], password):
            user = User(str(doctor['_id']), doctor['username'], 'doctor', doctor['name'])
            login_user(user)
            session['user_id'] = str(doctor['_id'])
            session['user_role'] = 'doctor'
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'redirect': '/doctor/dashboard'
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Login error occurred'})

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/patient/search', methods=['POST'])
@role_required('admin')
def search_patient():
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        name = data.get('name', '').strip()
        
        query = {}
        if phone:
            query['contact_number'] = phone
        if name:
            query['name'] = {'$regex': name, '$options': 'i'}
            
        if not query:
            return jsonify({'success': False, 'message': 'Please provide search criteria'})
        
        print(f"Searching for patient with query: {query}")
        patient = mongo.db.patient.find_one(query)
        print(f"Patient found: {patient is not None}")
        
        if patient:
            try:
                today = datetime.now()
                if isinstance(patient['date_of_birth'], datetime):
                    age = today.year - patient['date_of_birth'].year
                    if today.month < patient['date_of_birth'].month or \
                       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                        age -= 1
                else:
                    age = 0  # Default age if date_of_birth is not a datetime
            except Exception as age_error:
                print(f"Age calculation error: {age_error}")
                age = 0

            patient_data = {
                '_id': str(patient['_id']),
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'contact_number': patient['contact_number'],
                'age': age,
                'gender': patient['gender'],
                'address': patient['address'],
                'allergies': patient.get('allergies', ''),
                'chronic_illness': patient.get('chronic_illness', ''),
                'aadhaar_number': patient.get('aadhaar_number', ''),
                'date_of_birth': patient['date_of_birth']
            }

            try:
                visits = list(mongo.db.visit.find(
                    {'patient_id': patient['_id']}
                ))
                
                # Sort visits by visit_date if it exists, otherwise by _id
                visits.sort(key=lambda x: x.get('visit_date', x.get('_id')), reverse=True)

                visit_history = []
                for visit in visits:
                    try:
                        doctor = mongo.db.doctor.find_one({'_id': visit.get('doctor_id')})
                        department = mongo.db.department.find_one({'_id': visit.get('department_id')})

                        visit_date = visit.get('visit_date_time') or visit.get('visit_date')
                        if visit_date:
                            if isinstance(visit_date, datetime):
                                visit_date_str = visit_date.strftime('%Y-%m-%d %H:%M')
                            else:
                                visit_date_str = str(visit_date)
                        else:
                            visit_date_str = 'Date not available'

                        visit_data = {
                            'visit_id': str(visit['_id']),
                            'visit_date_time': visit_date_str,
                            'doctor_name': doctor['name'] if doctor else 'Unknown',
                            'department_name': department['department_name'] if department else 'Unknown',
                            'diagnosis': visit.get('diagnosis', ''),
                            'medications': visit.get('medications', ''),
                            'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else '',
                            'prescription_image': visit.get('prescription_image', '')  # Added prescription image field
                        }
                        visit_history.append(visit_data)
                    except Exception as visit_error:
                        print(f"Error processing visit: {visit_error}")
                        continue

            except Exception as visit_history_error:
                print(f"Error retrieving visit history: {visit_history_error}")
                visit_history = []

            patient_data['visits'] = visit_history

            return jsonify({'success': True, 'patient': patient_data})
        else:
            return jsonify({'success': False, 'message': 'Patient not found'})
            
    except Exception as e:
        print(f"Patient search error: {str(e)}")
        return jsonify({'success': False, 'message': f'Search error: {str(e)}'})

@app.route('/api/patient/register', methods=['POST'])
@role_required(['admin'])
def register_patient():
    try:
        data = request.get_json()
        
        required_fields = ['name', 'phone', 'dob', 'gender', 'address']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field.title()} is required'})
        
        existing_name_phone = mongo.db.patient.find_one({
            'name': data['name'].strip(),
            'contact_number': data['phone'].strip()
        })
        
        if existing_name_phone:
            return jsonify({
                'success': False, 
                'message': f'A patient with the name "{data["name"]}" and phone number "{data["phone"]}" is already registered (Patient ID: {existing_name_phone["patient_id"]})'
            })
        
        aadhaar = data.get('aadhaar', '').strip()
        if aadhaar:
            existing_aadhaar = mongo.db.patient.find_one({
                'aadhaar_number': aadhaar
            })
            
            if existing_aadhaar:
                return jsonify({
                    'success': False, 
                    'message': f'A patient with Aadhaar number "{aadhaar}" is already registered (Patient ID: {existing_aadhaar["patient_id"]})'
                })
        
        # Generate patient ID
        last_patient = mongo.db.patient.find_one(sort=[('patient_id', -1)])
        if last_patient:
            last_id = int(last_patient['patient_id'][2:])  # Remove 'PT' prefix
            new_patient_id = f"PT{last_id + 1:04d}"
        else:
            new_patient_id = "PT0001"
        
        patient_data = {
            'patient_id': new_patient_id,
            'name': data['name'].strip(),
            'contact_number': data['phone'].strip(),  # Frontend sends 'phone'
            'aadhaar_number': aadhaar,  # Frontend sends 'aadhaar'
            'date_of_birth': datetime.strptime(data['dob'], '%Y-%m-%d'),  # Frontend sends 'dob'
            'gender': data['gender'],
            'address': data['address'].strip(),
            'allergies': data.get('allergies', '').strip(),
            'chronic_illness': data.get('chronic_illness', '').strip(),
            'created_at': datetime.now()
        }
        
        try:
            result = mongo.db.patient.insert_one(patient_data)
        except Exception as db_error:
            if 'duplicate key' in str(db_error).lower():
                if 'name' in str(db_error) and 'contact_number' in str(db_error):
                    return jsonify({
                        'success': False, 
                        'message': 'A patient with this name and phone number combination already exists'
                    })
                elif 'aadhaar_number' in str(db_error):
                    return jsonify({
                        'success': False, 
                        'message': 'A patient with this Aadhaar number already exists'
                    })
                else:
                    return jsonify({
                        'success': False, 
                        'message': 'Patient registration failed due to duplicate information'
                    })
            else:
                raise db_error
        
        if result.inserted_id:
            # Calculate age for response
            today = datetime.now()
            age = today.year - patient_data['date_of_birth'].year
            if today.month < patient_data['date_of_birth'].month or \
               (today.month == patient_data['date_of_birth'].month and today.day < patient_data['date_of_birth'].day):
                age -= 1
            
            patient_data['_id'] = str(result.inserted_id)
            patient_data['age'] = age
            patient_data['visits'] = []  # New patient has no visits
            
            return jsonify({
                'success': True, 
                'message': 'Patient registered successfully',
                'patient': patient_data
            })
        else:
            return jsonify({'success': False, 'message': 'Registration failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})

@app.route('/api/patients/by-phone', methods=['POST'])
@role_required(['admin'])
def search_patients_by_phone():
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'message': 'Phone number is required'})
        
        # Find all patients with this phone number
        patients = list(mongo.db.patient.find({'contact_number': phone}))
        
        patients_data = []
        for patient in patients:
            # Calculate age
            try:
                today = datetime.now()
                if isinstance(patient['date_of_birth'], datetime):
                    age = today.year - patient['date_of_birth'].year
                    if today.month < patient['date_of_birth'].month or \
                       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                        age -= 1
                else:
                    age = 0
            except:
                age = 0

            # Get visit history
            try:
                visits = list(mongo.db.visit.find({'patient_id': patient['_id']}))
                visits.sort(key=lambda x: x.get('visit_date', x.get('_id')), reverse=True)

                visit_history = []
                for visit in visits:
                    try:
                        doctor = mongo.db.doctor.find_one({'_id': visit.get('doctor_id')})
                        department = mongo.db.department.find_one({'_id': visit.get('department_id')})

                        visit_date = visit.get('visit_date')
                        if visit_date:
                            if isinstance(visit_date, datetime):
                                visit_date_str = visit_date.strftime('%Y-%m-%d %H:%M')
                            else:
                                visit_date_str = str(visit_date)
                        else:
                            visit_date_str = 'Date not available'

                        visit_data = {
                            'visit_id': str(visit['_id']),
                            'visit_date_time': visit_date_str,
                            'doctor_name': doctor['name'] if doctor else 'Unknown',
                            'department_name': department['department_name'] if department else 'Unknown',
                            'diagnosis': visit.get('diagnosis', ''),
                            'medications': visit.get('medications', ''),
                            'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else ''
                        }
                        visit_history.append(visit_data)
                    except Exception as visit_error:
                        continue
            except:
                visit_history = []

            patient_data = {
                '_id': str(patient['_id']),
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'contact_number': patient['contact_number'],
                'age': age,
                'gender': patient['gender'],
                'address': patient['address'],
                'allergies': patient.get('allergies', ''),
                'chronic_illness': patient.get('chronic_illness', ''),
                'aadhaar_number': patient.get('aadhaar_number', ''),
                'date_of_birth': patient['date_of_birth'],
                'visits': visit_history
            }
            patients_data.append(patient_data)
        
        return jsonify({'success': True, 'patients': patients_data})
        
    except Exception as e:
        print(f"Phone search error: {str(e)}")
        return jsonify({'success': False, 'message': f'Search error: {str(e)}'})

@app.route('/api/patients/by-name', methods=['POST'])
@role_required(['admin'])
def search_patients_by_name():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'message': 'Name is required'})
        
        # Find patients with similar names
        patients = list(mongo.db.patient.find({'name': {'$regex': name, '$options': 'i'}}))
        
        patients_data = []
        for patient in patients:
            # Calculate age
            try:
                today = datetime.now()
                if isinstance(patient['date_of_birth'], datetime):
                    age = today.year - patient['date_of_birth'].year
                    if today.month < patient['date_of_birth'].month or \
                       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                        age -= 1
                else:
                    age = 0
            except:
                age = 0

            # Get visit history
            try:
                visits = list(mongo.db.visit.find({'patient_id': patient['_id']}))
                visits.sort(key=lambda x: x.get('visit_date', x.get('_id')), reverse=True)

                visit_history = []
                for visit in visits:
                    try:
                        doctor = mongo.db.doctor.find_one({'_id': visit.get('doctor_id')})
                        department = mongo.db.department.find_one({'_id': visit.get('department_id')})

                        visit_date = visit.get('visit_date')
                        if visit_date:
                            if isinstance(visit_date, datetime):
                                visit_date_str = visit_date.strftime('%Y-%m-%d %H:%M')
                            else:
                                visit_date_str = str(visit_date)
                        else:
                            visit_date_str = 'Date not available'

                        visit_data = {
                            'visit_id': str(visit['_id']),
                            'visit_date_time': visit_date_str,
                            'doctor_name': doctor['name'] if doctor else 'Unknown',
                            'department_name': department['department_name'] if department else 'Unknown',
                            'diagnosis': visit.get('diagnosis', ''),
                            'medications': visit.get('medications', ''),
                            'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else ''
                        }
                        visit_history.append(visit_data)
                    except Exception as visit_error:
                        continue
            except:
                visit_history = []

            patient_data = {
                '_id': str(patient['_id']),
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'contact_number': patient['contact_number'],
                'age': age,
                'gender': patient['gender'],
                'address': patient['address'],
                'allergies': patient.get('allergies', ''),
                'chronic_illness': patient.get('chronic_illness', ''),
                'aadhaar_number': patient.get('aadhaar_number', ''),
                'date_of_birth': patient['date_of_birth'],
                'visits': visit_history
            }
            patients_data.append(patient_data)
        
        return jsonify({'success': True, 'patients': patients_data})
        
    except Exception as e:
        print(f"Name search error: {str(e)}")
        return jsonify({'success': False, 'message': f'Search error: {str(e)}'})

@app.route('/api/departments')
@role_required('admin')
def get_departments():
    try:
        departments = list(mongo.db.department.find({}, {'_id': 1, 'department_name': 1}))
        for dept in departments:
            dept['_id'] = str(dept['_id'])
        return jsonify(departments)
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error fetching departments'})

@app.route('/api/doctors/stats')
@role_required('admin')
def get_doctors_stats():
    try:
        # Get total doctors count
        total_doctors = mongo.db.doctor.count_documents({})
        
        # Get total departments count
        total_departments = mongo.db.department.count_documents({})
        
        # Get doctors active today (with visits today)
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        active_doctors = mongo.db.visit.distinct('doctor_id', {
            'visit_date': {'$gte': start_of_day, '$lte': end_of_day}
        })
        
        # Calculate average patients per day per doctor
        total_visits_today = mongo.db.visit.count_documents({
            'visit_date': {'$gte': start_of_day, '$lte': end_of_day}
        })
        
        avg_patients_per_day = round(total_visits_today / total_doctors, 1) if total_doctors > 0 else 0
        
        return jsonify({
            'total_doctors': total_doctors,
            'total_departments': total_departments,
            'active_today': len(active_doctors),
            'avg_patients_per_day': avg_patients_per_day
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error fetching doctor stats'})

@app.route('/api/doctors/list')
@role_required('admin')
def get_doctors_list():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        search = request.args.get('search', '').strip()
        department = request.args.get('department', '').strip()
        sort_by = request.args.get('sort', 'name')
        
        # Build query
        query = {}
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'username': {'$regex': search, '$options': 'i'}},
                {'specialization': {'$regex': search, '$options': 'i'}},
                {'room_no': {'$regex': search, '$options': 'i'}}
            ]
        
        if department:
            query['department_id'] = ObjectId(department)
        
        # Sort options
        sort_options = {
            'name': [('name', 1)],
            'department': [('department_id', 1)],
            'specialization': [('specialization', 1)],
            'created_at': [('created_at', -1)]
        }
        sort_criteria = sort_options.get(sort_by, [('name', 1)])
        
        # Get total count
        total = mongo.db.doctor.count_documents(query)
        
        # Get paginated results
        skip = (page - 1) * per_page
        doctors = list(mongo.db.doctor.find(query).sort(sort_criteria).skip(skip).limit(per_page))
        
        # Enrich doctor data with department info and current load
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        doctor_list = []
        for doctor in doctors:
            # Get department name
            department_name = 'N/A'
            if 'department_id' in doctor:
                dept = mongo.db.department.find_one({'_id': doctor['department_id']})
                if dept:
                    department_name = dept['department_name']
            
            # Get current patient load
            current_load = mongo.db.visit.count_documents({
                'doctor_id': doctor['_id'],
                'visit_date': {'$gte': start_of_day, '$lte': end_of_day},
                'status': {'$in': ['assigned', 'in_progress']}
            })
            
            doctor_data = {
                '_id': str(doctor['_id']),
                'name': doctor['name'],
                'username': doctor['username'],
                'email': doctor.get('email', ''),
                'phone': doctor.get('phone', ''),
                'department_id': str(doctor.get('department_id', '')),
                'department_name': department_name,
                'specialization': doctor.get('specialization', ''),
                'room_no': doctor.get('room_no', ''),
                'current_load': current_load,
                'created_at': doctor.get('created_at', datetime.now()).strftime('%Y-%m-%d') if doctor.get('created_at') else 'N/A'
            }
            doctor_list.append(doctor_data)
        
        total_pages = (total + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'doctors': doctor_list,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching doctors: {str(e)}'})

@app.route('/api/doctor/register', methods=['POST'])
@role_required('admin')
def register_doctor():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'username', 'password', 'department_id', 'specialization']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field.replace("_", " ").title()} is required'})
        
        # Check if username already exists
        existing_doctor = mongo.db.doctor.find_one({'username': data['username'].strip()})
        if existing_doctor:
            return jsonify({'success': False, 'message': 'Username already exists'})
        
        # Check if admin with same username exists
        existing_admin = mongo.db.admin.find_one({'username': data['username'].strip()})
        if existing_admin:
            return jsonify({'success': False, 'message': 'Username already exists in admin accounts'})
        
        # Hash password
        password_hash = generate_password_hash(data['password'])
        
        doctor_data = {
            'name': data['name'].strip(),
            'username': data['username'].strip(),
            'password_hash': password_hash,
            'email': data.get('email', '').strip(),
            'phone': data.get('phone', '').strip(),
            'department_id': ObjectId(data['department_id']),
            'specialization': data['specialization'].strip(),
            'room_no': data.get('room_no', '').strip(),
            'created_at': datetime.now(),
            'created_by': ObjectId(current_user.id)
        }
        
        result = mongo.db.doctor.insert_one(doctor_data)
        
        if result.inserted_id:
            return jsonify({
                'success': True,
                'message': 'Doctor registered successfully',
                'doctor_id': str(result.inserted_id)
            })
        else:
            return jsonify({'success': False, 'message': 'Registration failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})

@app.route('/api/doctor/<doctor_id>')
@role_required('admin')
def get_doctor_details(doctor_id):
    try:
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_id)})
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        # Get department name
        department_name = 'N/A'
        if 'department_id' in doctor:
            dept = mongo.db.department.find_one({'_id': doctor['department_id']})
            if dept:
                department_name = dept['department_name']
        
        doctor_data = {
            '_id': str(doctor['_id']),
            'name': doctor['name'],
            'username': doctor['username'],
            'email': doctor.get('email', ''),
            'phone': doctor.get('phone', ''),
            'department_id': str(doctor.get('department_id', '')),
            'department_name': department_name,
            'specialization': doctor.get('specialization', ''),
            'room_no': doctor.get('room_no', ''),
            'created_at': doctor.get('created_at', datetime.now()).strftime('%Y-%m-%d') if doctor.get('created_at') else 'N/A'
        }
        
        return jsonify({'success': True, 'doctor': doctor_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching doctor: {str(e)}'})

@app.route('/api/doctor/<doctor_id>/update', methods=['PUT'])
@role_required('admin')
def update_doctor(doctor_id):
    try:
        data = request.get_json()
        
        # Check if doctor exists
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_id)})
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        # Check if username is being changed and if it already exists
        if data.get('username') and data['username'].strip() != doctor['username']:
            existing_doctor = mongo.db.doctor.find_one({
                'username': data['username'].strip(),
                '_id': {'$ne': ObjectId(doctor_id)}
            })
            if existing_doctor:
                return jsonify({'success': False, 'message': 'Username already exists'})
            
            # Check admin collection too
            existing_admin = mongo.db.admin.find_one({'username': data['username'].strip()})
            if existing_admin:
                return jsonify({'success': False, 'message': 'Username already exists in admin accounts'})
        
        update_data = {
            'name': data.get('name', doctor['name']).strip(),
            'username': data.get('username', doctor['username']).strip(),
            'email': data.get('email', doctor.get('email', '')).strip(),
            'phone': data.get('phone', doctor.get('phone', '')).strip(),
            'specialization': data.get('specialization', doctor.get('specialization', '')).strip(),
            'room_no': data.get('room_no', doctor.get('room_no', '')).strip(),
            'updated_at': datetime.now(),
            'updated_by': ObjectId(current_user.id)
        }
        
        if data.get('department_id'):
            update_data['department_id'] = ObjectId(data['department_id'])
        
        result = mongo.db.doctor.update_one(
            {'_id': ObjectId(doctor_id)},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Doctor updated successfully'})
        else:
            return jsonify({'success': True, 'message': 'No changes made'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Update error: {str(e)}'})

@app.route('/api/doctor/<doctor_id>/change-password', methods=['PUT'])
@role_required('admin')
def admin_change_doctor_password(doctor_id):
    try:
        data = request.get_json()
        new_password = data.get('password')
        
        if not new_password:
            return jsonify({'success': False, 'message': 'New password is required'})
        
        # Check if doctor exists
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_id)})
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        result = mongo.db.doctor.update_one(
            {'_id': ObjectId(doctor_id)},
            {'$set': {
                'password_hash': hashed_password,
                'password': hashed_password,  # Update both fields for compatibility
                'updated_at': datetime.now()
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update password'})
            
    except Exception as e:
        print(f"Admin password change error: {str(e)}")
        return jsonify({'success': False, 'message': 'Error changing password'})

@app.route('/api/doctor/change-password', methods=['PUT'])
@role_required('doctor')
def doctor_change_password():
    try:
        data = request.get_json()
        doctor_user_id = session.get('user_id')  # Use user_id instead of username
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'message': 'Both current and new passwords are required'})
        
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_user_id)})
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        # Check password in both possible fields
        password_valid = False
        if 'password_hash' in doctor and doctor['password_hash']:
            password_valid = check_password_hash(doctor['password_hash'], current_password)
        elif 'password' in doctor and doctor['password']:
            password_valid = check_password_hash(doctor['password'], current_password)
        
        if not password_valid:
            return jsonify({'success': False, 'message': 'Current password is incorrect'})
        
        # Update password
        hashed_password = generate_password_hash(new_password)
        result = mongo.db.doctor.update_one(
            {'_id': ObjectId(doctor_user_id)},
            {'$set': {
                'password_hash': hashed_password,
                'password': hashed_password,  # Update both fields for compatibility
                'updated_at': datetime.now()
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to update password'})
            
    except Exception as e:
        print(f"Password change error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/doctor/<doctor_id>/delete', methods=['DELETE'])
@role_required('admin')
def delete_doctor(doctor_id):
    try:
        # Check if doctor exists
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_id)})
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        # Check if doctor has any visits (prevent deletion if they have patient history)
        visit_count = mongo.db.visit.count_documents({'doctor_id': ObjectId(doctor_id)})
        if visit_count > 0:
            return jsonify({
                'success': False, 
                'message': f'Cannot delete doctor. They have {visit_count} patient visits in the system. Consider deactivating instead.'
            })
        
        # Delete the doctor
        result = mongo.db.doctor.delete_one({'_id': ObjectId(doctor_id)})
        
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Doctor deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete doctor'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Delete error: {str(e)}'})

@app.route('/api/doctors/export')
@role_required('admin')
def export_doctors():
    try:
        import csv
        import io
        
        # Get all doctors with department info
        doctors = list(mongo.db.doctor.find({}))
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Name', 'Username', 'Email', 'Phone', 'Department', 
            'Specialization', 'Room Number', 'Join Date'
        ])
        
        # Write doctor data
        for doctor in doctors:
            # Get department name
            department_name = 'N/A'
            if 'department_id' in doctor:
                dept = mongo.db.department.find_one({'_id': doctor['department_id']})
                if dept:
                    department_name = dept['department_name']
            
            writer.writerow([
                doctor['name'],
                doctor['username'],
                doctor.get('email', ''),
                doctor.get('phone', ''),
                department_name,
                doctor.get('specialization', ''),
                doctor.get('room_no', ''),
                doctor.get('created_at', datetime.now()).strftime('%Y-%m-%d') if doctor.get('created_at') else 'N/A'
            ])
        
        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=doctors_export_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Export error: {str(e)}'})

@app.route('/api/doctors/<department_id>')
@role_required('admin')
def get_doctors_by_department(department_id):
    try:
        doctors = list(mongo.db.doctor.find(
            {'department_id': ObjectId(department_id)},
            {'_id': 1, 'name': 1, 'specialization': 1, 'room_no': 1}
        ))
        
        # Calculate current load for each doctor
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        for doctor in doctors:
            doctor['_id'] = str(doctor['_id'])
            # Count today's visits for this doctor
            visit_count = mongo.db.visit.count_documents({
                'doctor_id': ObjectId(doctor['_id']),
                'visit_date': {'$gte': start_of_day, '$lte': end_of_day},
                'status': {'$in': ['assigned', 'in_progress']}
            })
            
            doctor['current_load'] = visit_count
            
            if visit_count <= 3:
                doctor['load'] = 'Light'
            elif visit_count <= 6:
                doctor['load'] = 'Medium'
            else:
                doctor['load'] = 'Heavy'
            
        return jsonify(doctors)
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error fetching doctors'})

@app.route('/api/assign-patient', methods=['POST'])
@role_required('admin')
def assign_patient():
    try:
        data = request.get_json()
        
        visit_data = {
            'patient_id': ObjectId(data['patient_id']),
            'doctor_id': ObjectId(data['doctor_id']),
            'department_id': ObjectId(data['department_id']),
            'reason_for_visit': data.get('reason_for_visit', 'General consultation'),
            'visit_date': datetime.now(),
            'status': 'assigned',
            'created_at': datetime.now()
        }
        
        result = mongo.db.visit.insert_one(visit_data)
        
        if result.inserted_id:
            return jsonify({
                'success': True, 
                'message': 'Patient assigned to doctor successfully',
                'visit_id': str(result.inserted_id)
            })
        else:
            return jsonify({'success': False, 'message': 'Assignment failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Assignment error: {str(e)}'})

@app.route('/api/visit/assign', methods=['POST'])
@role_required('admin')
def assign_visit():
    try:
        data = request.get_json()
        
        visit_data = {
            'patient_id': ObjectId(data['patient_id']),
            'doctor_id': ObjectId(data['doctor_id']),
            'department_id': ObjectId(data['department_id']),
            'reason_for_visit': data['reason_for_visit'],
            'visit_date': datetime.now(),
            'status': 'assigned',
            'created_at': datetime.now()
        }
        
        result = mongo.db.visit.insert_one(visit_data)
        
        if result.inserted_id:
            return jsonify({
                'success': True, 
                'message': 'Patient assigned to doctor successfully',
                'visit_id': str(result.inserted_id)
            })
        else:
            return jsonify({'success': False, 'message': 'Assignment failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Assignment error occurred'})

@app.route('/api/doctor/patients')
@role_required('doctor')
def get_doctor_patients():
    try:
        doctor_id = current_user.id
        
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        visits = list(mongo.db.visit.find({
            'doctor_id': ObjectId(doctor_id),
            'visit_date': {'$gte': start_of_day, '$lte': end_of_day},
            'status': {'$in': ['assigned', 'in_progress']}
        }))
        
        patients = []
        for visit in visits:
            patient = mongo.db.patient.find_one({'_id': visit['patient_id']})
            if patient:
                # Calculate age
                try:
                    today_date = datetime.now()
                    if isinstance(patient['date_of_birth'], datetime):
                        age = today_date.year - patient['date_of_birth'].year
                        if today_date.month < patient['date_of_birth'].month or \
                           (today_date.month == today_date.month and today_date.day < patient['date_of_birth'].day):
                            age -= 1
                    else:
                        age = 0
                except:
                    age = 0
                
                patients.append({
                    'visit_id': str(visit['_id']),
                    'patient_id': patient['patient_id'],
                    'name': patient['name'],
                    'age': age,
                    'gender': patient['gender'],
                    'reason_for_visit': visit['reason_for_visit'],
                    'status': visit['status'],
                    'visit_time': visit['visit_date'].strftime('%H:%M')
                })
        
        return jsonify({'success': True, 'patients': patients})
        
    except Exception as e:
        print(f"Get doctor patients error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching patients: {str(e)}'})


@app.route('/api/patient/<patient_id>/history')
@role_required(['admin', 'doctor'])  # Allow both admin and doctor to access patient history
def get_patient_history(patient_id):
    try:
        # Find patient by patient_id (string) or ObjectId
        try:
            patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
        except:
            patient = mongo.db.patient.find_one({'patient_id': patient_id})
        
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found'})
        
        # Get all visits for this patient
        visits = list(mongo.db.visit.find({
            'patient_id': patient['_id']
        }).sort('visit_date', -1))
        
        history = []
        for visit in visits:
            try:
                doctor = mongo.db.doctor.find_one({'_id': visit.get('doctor_id')})
                department = mongo.db.department.find_one({'_id': visit.get('department_id')})
                
                visit_data = {
                    'visit_id': str(visit['_id']),
                    'visit_date': visit['visit_date'].strftime('%Y-%m-%d %H:%M') if visit.get('visit_date') else 'Unknown',
                    'doctor_name': doctor['name'] if doctor else 'Unknown Doctor',
                    'department_name': department['department_name'] if department else 'Unknown Department',
                    'reason_for_visit': visit.get('reason_for_visit', ''),
                    'symptoms': visit.get('symptoms', ''),
                    'diagnosis': visit.get('diagnosis', ''),
                    'medications': visit.get('medications', ''),
                    'instructions': visit.get('instructions', ''),
                    'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else '',
                    'status': visit.get('status', 'unknown')
                }
                history.append(visit_data)
            except Exception as visit_error:
                print(f"Error processing visit: {visit_error}")
                continue
        
        # Calculate patient age
        try:
            today = datetime.now()
            if isinstance(patient['date_of_birth'], datetime):
                age = today.year - patient['date_of_birth'].year
                if today.month < patient['date_of_birth'].month or \
                   (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                    age -= 1
            else:
                age = 0
        except:
            age = 0
        
        patient_info = {
            'patient_id': patient['patient_id'],
            'name': patient['name'],
            'age': age,
            'gender': patient['gender'],
            'contact_number': patient['contact_number'],
            'address': patient['address'],
            'allergies': patient.get('allergies', 'None'),
            'chronic_illness': patient.get('chronic_illness', 'None')
        }
        
        return jsonify({
            'success': True,
            'patient': patient_info,
            'history': history,
            'visits': history  # For backward compatibility
        })
        
    except Exception as e:
        print(f"Patient history error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching patient history: {str(e)}'})

@app.route('/api/prescription/<visit_id>')
@role_required('doctor')
def get_prescription(visit_id):
    try:
        visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not visit:
            return jsonify({'success': False, 'message': 'Visit not found'})
        
        patient = mongo.db.patient.find_one({'_id': visit['patient_id']})
        doctor = mongo.db.doctor.find_one({'_id': visit['doctor_id']})
        
        prescription_data = {
            'visit_id': str(visit['_id']),
            'symptoms': visit.get('symptoms', ''),
            'diagnosis': visit.get('diagnosis', ''),
            'medications': visit.get('medications', ''),
            'instructions': visit.get('instructions', ''),
            'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else '',
            'patient': {
                'name': patient['name'],
                'patient_id': patient['patient_id'],
                'age': patient['age'],
                'gender': patient['gender'],
                'allergies': patient.get('allergies', 'None'),
                'chronic_conditions': patient.get('chronic_illness', 'None')
            },
            'doctor': {
                'name': doctor['name'],
                'department': doctor['department']
            },
            'visit_date': visit['visit_date'],
            'prescription_timestamp': visit.get('prescription_timestamp')
        }
        
        return jsonify({'success': True, 'prescription': prescription_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching prescription: {str(e)}'})

@app.route('/api/visit/<visit_id>/details')
@role_required(['admin', 'doctor'])
def get_visit_details(visit_id):
    try:
        # Get visit details
        visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not visit:
            return jsonify({'success': False, 'message': 'Visit not found'})
        
        # Get patient, doctor, and department information
        patient = mongo.db.patient.find_one({'_id': visit['patient_id']})
        doctor = mongo.db.doctor.find_one({'_id': visit['doctor_id']})
        department = mongo.db.department.find_one({'_id': visit['department_id']})
        
        # Get prescription details from prescription collection
        prescription = mongo.db.prescription.find_one({'visit_id': ObjectId(visit_id)})
        
        visit_details = {
            'visit_id': str(visit['_id']),
            'visit_date': visit['visit_date'].strftime('%Y-%m-%d %H:%M') if visit.get('visit_date') else 'Date not available',
            'patient': {
                'name': patient['name'] if patient else 'Unknown',
                'patient_id': patient['patient_id'] if patient else 'Unknown',
                'age': patient.get('age', 0) if patient else 0,
                'gender': patient['gender'] if patient else 'Unknown',
                'contact_number': patient['contact_number'] if patient else 'Unknown'
            },
            'doctor': {
                'name': doctor['name'] if doctor else 'Unknown',
                'department': doctor.get('department', 'Unknown') if doctor else 'Unknown'
            },
            'department_name': department['department_name'] if department else 'Unknown',
            'reason_for_visit': visit.get('reason_for_visit', ''),
            'symptoms': visit.get('symptoms', prescription.get('symptoms', '') if prescription else ''),
            'diagnosis': visit.get('diagnosis', prescription.get('diagnosis', '') if prescription else ''),
            'medications': visit.get('medications', prescription.get('medications', '') if prescription else ''),
            'instructions': visit.get('instructions', prescription.get('instructions', '') if prescription else ''),
            'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else (prescription['follow_up_date'].strftime('%Y-%m-%d') if prescription and prescription.get('follow_up_date') else ''),
            'status': visit.get('status', 'pending'),
            'prescription_timestamp': visit.get('prescription_timestamp', prescription.get('prescription_timestamp') if prescription else None)
        }
        
        return jsonify({'success': True, 'visit_details': visit_details})
        
    except Exception as e:
        print(f"Error fetching visit details: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching visit details: {str(e)}'})

@app.route('/api/prescription/edit', methods=['POST'])
@role_required(['doctor'])
def edit_prescription():
    try:
        data = request.get_json()
        visit_id = data.get('visit_id')
        
        if not visit_id:
            return jsonify({'success': False, 'message': 'Visit ID is required'})
        
        # Get current visit data for audit trail
        current_visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not current_visit:
            return jsonify({'success': False, 'message': 'Visit not found'})
        
        # Create audit trail entry
        audit_entry = {
            'visit_id': ObjectId(visit_id),
            'doctor_id': ObjectId(session['user_id']),
            'edited_at': datetime.now(),
            'original_data': {
                'symptoms': current_visit.get('symptoms', ''),
                'diagnosis': current_visit.get('diagnosis', ''),
                'medications': current_visit.get('medications', ''),
                'instructions': current_visit.get('instructions', ''),
                'follow_up_date': current_visit.get('follow_up_date')
            },
            'new_data': {
                'symptoms': data.get('symptoms', ''),
                'diagnosis': data.get('diagnosis', ''),
                'medications': data.get('medications', ''),
                'instructions': data.get('instructions', ''),
                'follow_up_date': datetime.strptime(data['follow_up_date'], '%Y-%m-%d') if data.get('follow_up_date') else None
            }
        }
        
        # Save audit trail
        mongo.db.prescription_audit.insert_one(audit_entry)
        
        # Update visit record
        update_data = {
            'symptoms': data.get('symptoms', ''),
            'diagnosis': data.get('diagnosis', ''),
            'medications': data.get('medications', ''),
            'instructions': data.get('instructions', ''),
            'last_modified': datetime.now(),
            'modified_by': ObjectId(session['user_id'])
        }
        
        if data.get('follow_up_date'):
            update_data['follow_up_date'] = datetime.strptime(data['follow_up_date'], '%Y-%m-%d')
        
        mongo.db.visit.update_one(
            {'_id': ObjectId(visit_id)},
            {'$set': update_data}
        )
        
        # Update prescription record if exists
        prescription_data = {
            'visit_id': ObjectId(visit_id),
            'patient_id': current_visit['patient_id'],
            'doctor_id': ObjectId(session['user_id']),
            'symptoms': data.get('symptoms', ''),
            'diagnosis': data.get('diagnosis', ''),
            'medications': data.get('medications', ''),
            'instructions': data.get('instructions', ''),
            'follow_up_date': datetime.strptime(data['follow_up_date'], '%Y-%m-%d') if data.get('follow_up_date') else None,
            'created_at': current_visit.get('created_at', datetime.now()),
            'last_modified': datetime.now(),
            'modified_by': ObjectId(session['user_id'])
        }
        
        mongo.db.prescription.update_one(
            {'visit_id': ObjectId(visit_id)},
            {'$set': prescription_data},
            upsert=True
        )
        
        return jsonify({'success': True, 'message': 'Prescription updated successfully'})
        
    except Exception as e:
        logging.error(f"Error editing prescription: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to update prescription'})

@app.route('/api/prescription/<visit_id>/audit')
@role_required(['doctor', 'admin'])
def get_prescription_audit(visit_id):
    try:
        audit_entries = list(mongo.db.prescription_audit.find(
            {'visit_id': ObjectId(visit_id)},
            sort=[('edited_at', -1)]
        ))
        
        audit_history = []
        for entry in audit_entries:
            doctor = mongo.db.doctor.find_one({'_id': entry['doctor_id']})
            audit_history.append({
                'edited_at': entry['edited_at'].strftime('%Y-%m-%d %H:%M:%S'),
                'doctor_name': doctor['name'] if doctor else 'Unknown',
                'original_data': entry['original_data'],
                'new_data': entry['new_data']
            })
        
        return jsonify({'success': True, 'audit_history': audit_history})
        
    except Exception as e:
        logging.error(f"Error fetching audit trail: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to fetch audit trail'})


@app.route('/api/tests/add', methods=['POST'])
@role_required('doctor')
def add_test():
    try:
        data = request.get_json()
        visit_id = data.get('visit_id')
        
        # Get visit details
        visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not visit:
            return jsonify({'success': False, 'message': 'Visit not found'})
        
        test_data = {
            'visit_id': ObjectId(visit_id),
            'patient_id': visit['patient_id'],
            'doctor_id': ObjectId(current_user.id),
            'test_name': data['test_name'],
            'test_type': data['test_type'],
            'instructions': data.get('instructions', ''),
            'status': 'assigned',
            'assigned_date': datetime.now(),
            'completed_date': None,
            'results': None,
            'result_files': [],
            'created_at': datetime.now(),
            'created_by': ObjectId(current_user.id)
        }
        
        result = mongo.db.tests.insert_one(test_data)
        
        if result.inserted_id:
            return jsonify({'success': True, 'message': 'Test assigned successfully', 'test_id': str(result.inserted_id)})
        else:
            return jsonify({'success': False, 'message': 'Failed to assign test'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error assigning test: {str(e)}'})

@app.route('/api/tests/visit/<visit_id>')
@role_required(['doctor', 'admin'])
def get_visit_tests(visit_id):
    try:
        tests = list(mongo.db.tests.find({'visit_id': ObjectId(visit_id)}))
        
        test_list = []
        for test in tests:
            # Get doctor info
            doctor = mongo.db.doctor.find_one({'_id': test['doctor_id']})
            
            test_data = {
                'test_id': str(test['_id']),
                'test_name': test['test_name'],
                'test_type': test['test_type'],
                'instructions': test.get('instructions', ''),
                'status': test['status'],
                'assigned_date': test['assigned_date'].strftime('%Y-%m-%d %H:%M'),
                'completed_date': test['completed_date'].strftime('%Y-%m-%d %H:%M') if test.get('completed_date') else None,
                'results': test.get('results', ''),
                'result_files': test.get('result_files', []),
                'doctor_name': doctor['name'] if doctor else 'Unknown',
                'created_at': test['created_at'].strftime('%Y-%m-%d %H:%M')
            }
            test_list.append(test_data)
        
        return jsonify({'success': True, 'tests': test_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching tests: {str(e)}'})

@app.route('/api/tests/patient/<patient_id>')
@role_required(['doctor', 'admin'])
def get_patient_tests(patient_id):
    try:
        tests = list(mongo.db.tests.find({'patient_id': ObjectId(patient_id)}).sort('assigned_date', -1))
        
        test_list = []
        for test in tests:
            # Get doctor and visit info
            doctor = mongo.db.doctor.find_one({'_id': test['doctor_id']})
            visit = mongo.db.visit.find_one({'_id': test['visit_id']})
            
            test_data = {
                'test_id': str(test['_id']),
                'test_name': test['test_name'],
                'test_type': test['test_type'],
                'instructions': test.get('instructions', ''),
                'status': test['status'],
                'assigned_date': test['assigned_date'].strftime('%Y-%m-%d %H:%M'),
                'completed_date': test['completed_date'].strftime('%Y-%m-%d %H:%M') if test.get('completed_date') else None,
                'results': test.get('results', ''),
                'result_files': test.get('result_files', []),
                'doctor_name': doctor['name'] if doctor else 'Unknown',
                'visit_date': visit['visit_date_time'].strftime('%Y-%m-%d') if visit else 'Unknown',
                'created_at': test['created_at'].strftime('%Y-%m-%d %H:%M')
            }
            test_list.append(test_data)
        
        return jsonify({'success': True, 'tests': test_list})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching patient tests: {str(e)}'})

@app.route('/api/tests/<test_id>/update', methods=['POST'])
@role_required('doctor')
def update_test_results():
    try:
        test_id = request.form.get('test_id') or request.json.get('test_id')
        results = request.form.get('results') or request.json.get('results')
        
        # Get current test
        test = mongo.db.tests.find_one({'_id': ObjectId(test_id)})
        if not test:
            return jsonify({'success': False, 'message': 'Test not found'})
        
        update_data = {
            'results': results,
            'status': 'completed',
            'completed_date': datetime.now(),
            'updated_by': ObjectId(current_user.id),
            'updated_at': datetime.now()
        }
        
        # Handle file uploads if present
        uploaded_files = []
        upload_errors = []
        
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename:
                    is_valid, validation_message = validate_file(file)
                    if not is_valid:
                        upload_errors.append(f"{file.filename}: {validation_message}")
                        continue
                    
                    try:
                        filename = secure_filename(file.filename)
                        # Create unique filename
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        unique_filename = f"{test_id}_{timestamp}_{filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        if os.path.exists(file_path):
                            # Add random suffix if file exists
                            import random
                            random_suffix = random.randint(1000, 9999)
                            name, ext = os.path.splitext(unique_filename)
                            unique_filename = f"{name}_{random_suffix}{ext}"
                            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        file.save(file_path)
                        
                        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                            upload_errors.append(f"{filename}: Failed to save file properly")
                            continue
                        
                        file_info = {
                            'filename': filename,
                            'stored_filename': unique_filename,
                            'file_path': file_path,
                            'file_size': os.path.getsize(file_path),
                            'upload_date': datetime.now(),
                            'uploaded_by': ObjectId(current_user.id),
                            'mime_type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                        }
                        uploaded_files.append(file_info)
                        
                    except Exception as file_error:
                        upload_errors.append(f"{file.filename}: {str(file_error)}")
                        # Clean up partial file if it exists
                        if 'file_path' in locals() and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except:
                                pass
        
        # Handle base64 file uploads from JSON
        if request.json and 'file_uploads' in request.json:
            for file_data in request.json['file_uploads']:
                if 'filename' in file_data and 'content' in file_data:
                    filename = secure_filename(file_data['filename'])
                    
                    is_valid, validation_message = validate_file(None, filename)
                    if not is_valid:
                        upload_errors.append(f"{filename}: {validation_message}")
                        continue
                    
                    try:
                        # Decode base64 content
                        file_content = base64.b64decode(file_data['content'])
                        
                        if len(file_content) > MAX_FILE_SIZE:
                            upload_errors.append(f"{filename}: File too large after decoding")
                            continue
                        
                        if len(file_content) == 0:
                            upload_errors.append(f"{filename}: Empty file after decoding")
                            continue
                        
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        unique_filename = f"{test_id}_{timestamp}_{filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        if os.path.exists(file_path):
                            import random
                            random_suffix = random.randint(1000, 9999)
                            name, ext = os.path.splitext(unique_filename)
                            unique_filename = f"{name}_{random_suffix}{ext}"
                            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        with open(file_path, 'wb') as f:
                            f.write(file_content)
                        
                        file_info = {
                            'filename': filename,
                            'stored_filename': unique_filename,
                            'file_path': file_path,
                            'file_size': len(file_content),
                            'upload_date': datetime.now(),
                            'uploaded_by': ObjectId(current_user.id),
                            'mime_type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                        }
                        uploaded_files.append(file_info)
                        
                    except Exception as file_error:
                        upload_errors.append(f"{filename}: {str(file_error)}")
        
        if uploaded_files:
            # Add new files to existing files
            existing_files = test.get('result_files', [])
            update_data['result_files'] = existing_files + uploaded_files
        
        result = mongo.db.tests.update_one(
            {'_id': ObjectId(test_id)},
            {'$set': update_data}
        )
        
        response_data = {'success': True, 'message': 'Test results updated successfully'}
        
        if uploaded_files:
            response_data['files_uploaded'] = len(uploaded_files)
        
        if upload_errors:
            response_data['upload_errors'] = upload_errors
            response_data['message'] += f" (with {len(upload_errors)} file upload errors)"
        
        if result.modified_count > 0:
            return jsonify(response_data)
        else:
            return jsonify({'success': False, 'message': 'Failed to update test results'})
            
    except Exception as e:
        logging.error(f"Error updating test results: {str(e)}")
        return jsonify({'success': False, 'message': f'Error updating test results: {str(e)}'})

@app.route('/api/tests/<test_id>/files/<file_index>')
@role_required(['doctor', 'admin'])
def download_test_file(test_id, file_index):
    try:
        test = mongo.db.tests.find_one({'_id': ObjectId(test_id)})
        if not test:
            return jsonify({'success': False, 'message': 'Test not found'}), 404
        
        result_files = test.get('result_files', [])
        file_idx = int(file_index)
        
        if file_idx >= len(result_files):
            return jsonify({'success': False, 'message': 'File not found'}), 404
        
        file_info = result_files[file_idx]
        file_path = file_info['file_path']
        
        # Ensure file path is within upload directory
        upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        requested_path = os.path.abspath(file_path)
        
        if not requested_path.startswith(upload_folder):
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'File not found on disk'}), 404
        
        if os.path.getsize(file_path) == 0:
            return jsonify({'success': False, 'message': 'File is empty'}), 404
        
        mime_type = file_info.get('mime_type', 'application/octet-stream')
        
        return send_file(
            file_path, 
            as_attachment=True, 
            download_name=file_info['filename'],
            mimetype=mime_type
        )
        
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid file index'}), 400
    except Exception as e:
        logging.error(f"Error downloading file: {str(e)}")
        return jsonify({'success': False, 'message': f'Error downloading file: {str(e)}'}), 500

@app.route('/api/tests/<test_id>/files/<file_index>/delete', methods=['DELETE'])
@role_required(['doctor', 'admin'])
def delete_test_file(test_id, file_index):
    try:
        test = mongo.db.tests.find_one({'_id': ObjectId(test_id)})
        if not test:
            return jsonify({'success': False, 'message': 'Test not found'}), 404
        
        result_files = test.get('result_files', [])
        file_idx = int(file_index)
        
        if file_idx >= len(result_files):
            return jsonify({'success': False, 'message': 'File not found'}), 404
        
        file_info = result_files[file_idx]
        file_path = file_info['file_path']
        
        # Remove file from filesystem
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                logging.error(f"Error removing file {file_path}: {e}")
        
        # Remove file from database
        result_files.pop(file_idx)
        
        result = mongo.db.tests.update_one(
            {'_id': ObjectId(test_id)},
            {'$set': {'result_files': result_files}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'File deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete file from database'})
            
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid file index'}), 400
    except Exception as e:
        logging.error(f"Error deleting file: {str(e)}")
        return jsonify({'success': False, 'message': f'Error deleting file: {str(e)}'})

@app.route('/api/patients/list')
@role_required(['admin'])
def get_patients_list():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        search = request.args.get('search', '').strip()
        gender = request.args.get('gender', '')
        sort_by = request.args.get('sort', 'created_at')
        order = int(request.args.get('order', -1))
        
        # Build query
        query = {}
        if search:
            search_regex = re.compile(search, re.IGNORECASE)
            query['$or'] = [
                {'name': search_regex},
                {'contact_number': search_regex},
                {'patient_id': search_regex}
            ]
        
        if gender:
            query['gender'] = gender
        
        # Get total count
        total = mongo.db.patient.count_documents(query)
        
        # Get patients with pagination
        skip = (page - 1) * per_page
        patients = list(mongo.db.patient.find(query)
                       .sort(sort_by, order)
                       .skip(skip)
                       .limit(per_page))
        
        # Process patient data
        patients_data = []
        for patient in patients:
            # Calculate age
            try:
                today = datetime.now()
                if isinstance(patient['date_of_birth'], datetime):
                    age = today.year - patient['date_of_birth'].year
                    if today.month < patient['date_of_birth'].month or \
                       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                        age -= 1
                else:
                    age = 0
            except:
                age = 0
            
            # Get visit count and last visit
            visit_count = mongo.db.visit.count_documents({'patient_id': patient['_id']})
            last_visit = mongo.db.visit.find_one(
                {'patient_id': patient['_id']}, 
                sort=[('visit_date', -1)]
            )
            
            patient_data = {
                '_id': str(patient['_id']),
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'contact_number': patient['contact_number'],
                'gender': patient['gender'],
                'age': age,
                'address': patient['address'],
                'allergies': patient.get('allergies', ''),
                'chronic_illness': patient.get('chronic_illness', ''),
                'aadhaar_number': patient.get('aadhaar_number', ''),
                'visit_count': visit_count,
                'last_visit_date': last_visit['visit_date'].strftime('%Y-%m-%d') if last_visit and 'visit_date' in last_visit else None,
                'created_at': patient.get('created_at', datetime.now()).isoformat() if isinstance(patient.get('created_at'), datetime) else str(patient.get('created_at', ''))
            }
            patients_data.append(patient_data)
        
        # Calculate total pages
        total_pages = (total + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'patients': patients_data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        })
        
    except Exception as e:
        print(f"Get patients list error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching patients: {str(e)}'})

@app.route('/api/patients/stats')
@role_required(['admin'])
def get_patients_stats():
    try:
        # Total patients
        total_patients = mongo.db.patient.count_documents({})
        
        # Recent registrations (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_registrations = mongo.db.patient.count_documents({
            'created_at': {'$gte': thirty_days_ago}
        })
        
        # Patients with visits
        patients_with_visits = mongo.db.patient.count_documents({
            '_id': {'$in': [visit['patient_id'] for visit in mongo.db.visit.find({}, {'patient_id': 1})]}
        })
        
        # Age distribution (simplified)
        age_distribution = [
            {'_id': 20, 'count': mongo.db.patient.count_documents({})},  # Simplified for now
        ]
        
        return jsonify({
            'success': True,
            'total_patients': total_patients,
            'recent_registrations': recent_registrations,
            'patients_with_visits': patients_with_visits,
            'age_distribution': age_distribution
        })
        
    except Exception as e:
        print(f"Get patients stats error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching stats: {str(e)}'})

@app.route('/api/patient/<patient_id>')
@role_required(['admin', 'doctor'])
def get_patient_details(patient_id):
    try:
        patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found'})
        
        # Calculate age
        try:
            today = datetime.now()
            if isinstance(patient['date_of_birth'], datetime):
                age = today.year - patient['date_of_birth'].year
                if today.month < patient['date_of_birth'].month or \
                   (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                    age -= 1
                else:
                    age = 0
        except:
            age = 0
        
        patient_data = {
            '_id': str(patient['_id']),
            'patient_id': patient['patient_id'],
            'name': patient['name'],
            'contact_number': patient['contact_number'],
            'gender': patient['gender'],
            'age': age,
            'address': patient['address'],
            'allergies': patient.get('allergies', ''),
            'chronic_illness': patient.get('chronic_illness', ''),
            'aadhaar_number': patient.get('aadhaar_number', ''),
            'date_of_birth': patient['date_of_birth'].isoformat() if isinstance(patient['date_of_birth'], datetime) else str(patient['date_of_birth'])
        }
        
        return jsonify({'success': True, 'patient': patient_data})
        
    except Exception as e:
        print(f"Get patient details error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching patient: {str(e)}'})

@app.route('/api/patient/<patient_id>/complete-history')
@role_required(['admin', 'doctor'])
def get_patient_complete_history(patient_id):
    """Get complete patient history with all details - used by patient report page"""
    try:
        visits = list(mongo.db.visit.find(
            {'patient_id': ObjectId(patient_id)},
            sort=[('visit_date', -1)]
        ))
        
        complete_history = []
        for visit in visits:
            doctor = mongo.db.doctor.find_one({'_id': visit['doctor_id']})
            department = mongo.db.department.find_one({'_id': visit['department_id']})
            
            # Get test results for this visit
            tests = list(mongo.db.tests.find({'visit_id': visit['_id']}))
            test_results = []
            for test in tests:
                test_results.append({
                    'test_name': test.get('test_name', ''),
                    'result': test.get('results', 'Pending'),
                    'date': test.get('result_date', test.get('assigned_date', '')),
                    'status': test.get('status', 'assigned')
                })
            
            visit_record = {
                'visit_id': str(visit['_id']),
                'visit_date': visit['visit_date'].isoformat() if visit.get('visit_date') else '',
                'doctor_name': doctor['name'] if doctor else 'Unknown',
                'department_name': department['department_name'] if department else 'Unknown',
                'chief_complaint': visit.get('reason_for_visit', ''),
                'reason_for_visit': visit.get('reason_for_visit', ''),
                'symptoms': visit.get('symptoms', ''),
                'diagnosis': visit.get('diagnosis', ''),
                'medications': visit.get('medications', ''),
                'instructions': visit.get('instructions', ''),
                'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else '',
                'status': visit.get('status', 'completed'),
                'tests_ordered': test_results,
                'prescription_timestamp': visit.get('prescription_timestamp', '').isoformat() if visit.get('prescription_timestamp') else ''
            }
            complete_history.append(visit_record)
        
        return jsonify({'success': True, 'visits': complete_history})
        
    except Exception as e:
        print(f"Get complete patient history error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error fetching complete history: {str(e)}'})

@app.route('/api/patient/summary/<patient_id>')
@role_required(['doctor', 'admin'])
def get_patient_summary(patient_id):
    try:
        # Get patient basic info
        patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found'})
        
        age = patient.get('age', 0)
        if not age and patient.get('date_of_birth'):
            try:
                if isinstance(patient['date_of_birth'], str):
                    dob = datetime.strptime(patient['date_of_birth'], '%Y-%m-%d')
                else:
                    dob = patient['date_of_birth']
                today = datetime.now()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            except Exception as age_error:
                print(f"Age calculation error: {age_error}")
                age = 0
        
        # Get visit statistics
        total_visits = mongo.db.visit.count_documents({'patient_id': ObjectId(patient_id)})
        completed_visits = mongo.db.visit.count_documents({
            'patient_id': ObjectId(patient_id), 
            'status': 'completed'
        })
        
        # Get last visit date
        last_visit = mongo.db.visit.find_one(
            {'patient_id': ObjectId(patient_id)},
            sort=[('visit_date', -1)]
        )
        
        # Get active medications (from most recent completed visit)
        recent_visit_with_meds = mongo.db.visit.find_one(
            {
                'patient_id': ObjectId(patient_id),
                'medications': {'$exists': True, '$ne': ''},
                'status': 'completed'
            },
            sort=[('visit_date', -1)]
        )
        
        active_medications = 0
        if recent_visit_with_meds and recent_visit_with_meds.get('medications'):
            # Count medications (simple count by splitting on common delimiters)
            meds_text = recent_visit_with_meds['medications']
            active_medications = len([m.strip() for m in meds_text.replace('\n', ',').split(',') if m.strip()])
        
        patient_summary = {
            'patient_id': patient['patient_id'],
            'name': patient['name'],
            'age': age,  # Use calculated age
            'gender': patient['gender'],
            'contact_number': patient.get('contact_number', ''),
            'address': patient.get('address', ''),
            'allergies': patient.get('allergies', ''),
            'chronic_conditions': patient.get('chronic_illness', ''),
            'total_visits': total_visits,
            'completed_visits': completed_visits,
            'last_visit': last_visit['visit_date'].strftime('%Y-%m-%d') if last_visit else None,
            'active_medications': active_medications,
            'registration_date': patient.get('created_at', '').strftime('%Y-%m-%d') if patient.get('created_at') else ''
        }
        
        return jsonify({'success': True, 'patient': patient_summary})
        
    except Exception as e:
        print(f"Patient summary error: {str(e)}")  # Added error logging
        return jsonify({'success': False, 'message': f'Error fetching patient summary: {str(e)}'})

@app.route('/api/patient/report/<patient_id>')
@role_required(['admin'])
def get_patient_report(patient_id):
    try:
        # Get comprehensive patient data for admin report view
        patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found'})
        
        # Get all visits with full details
        visits = list(mongo.db.visit.aggregate([
            {'$match': {'patient_id': ObjectId(patient_id)}},
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
        ]))
        
        # Get all tests for this patient
        all_tests = list(mongo.db.tests.find({'patient_id': ObjectId(patient_id)}))
        
        # Format visit data
        formatted_visits = []
        for visit in visits:
            doctor_info = visit['doctor_info'][0] if visit['doctor_info'] else {}
            dept_info = visit['department_info'][0] if visit['department_info'] else {}
            
            # Get tests for this visit
            visit_tests = [test for test in all_tests if test.get('visit_id') == visit['_id']]
            
            formatted_visit = {
                'visit_id': str(visit['_id']),
                'visit_date': visit['visit_date'].isoformat() if visit.get('visit_date') else '',
                'doctor_name': doctor_info.get('name', 'Unknown'),
                'department': dept_info.get('department_name', 'Unknown'),
                'reason_for_visit': visit.get('reason_for_visit', ''),
                'symptoms': visit.get('symptoms', ''),
                'diagnosis': visit.get('diagnosis', ''),
                'medications': visit.get('medications', ''),
                'instructions': visit.get('instructions', ''),
                'follow_up_date': visit['follow_up_date'].strftime('%Y-%m-%d') if visit.get('follow_up_date') else '',
                'status': visit.get('status', 'pending'),
                'tests': [{
                    'test_name': test.get('test_name', ''),
                    'test_type': test.get('test_type', ''),
                    'status': test.get('status', 'assigned'),
                    'results': test.get('results', ''),
                    'assigned_date': test.get('assigned_date', '').strftime('%Y-%m-%d') if test.get('assigned_date') else '',
                    'result_date': test.get('result_date', '').strftime('%Y-%m-%d') if test.get('result_date') else ''
                } for test in visit_tests]
            }
            formatted_visits.append(formatted_visit)
        
        # Calculate statistics
        total_visits = len(visits)
        completed_visits = len([v for v in visits if v.get('status') == 'completed'])
        pending_visits = len([v for v in visits if v.get('status') in ['assigned', 'in_progress']])
        
        report_data = {
            'patient_info': {
                'patient_id': patient['patient_id'],
                'name': patient['name'],
                'age': patient['age'],
                'gender': patient['gender'],
                'contact_number': patient.get('contact_number', ''),
                'address': patient.get('address', ''),
                'allergies': patient.get('allergies', ''),
                'chronic_conditions': patient.get('chronic_illness', ''),
                'registration_date': patient.get('created_at', '').strftime('%Y-%m-%d') if patient.get('created_at') else ''
            },
            'statistics': {
                'total_visits': total_visits,
                'completed_visits': completed_visits,
                'pending_visits': pending_visits,
                'total_tests': len(all_tests),
                'completed_tests': len([t for t in all_tests if t.get('status') == 'completed'])
            },
            'visits': formatted_visits
        }
        
        return jsonify({'success': True, 'report': report_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error generating patient report: {str(e)}'})

@app.route('/api/visit/record', methods=['POST'])
@role_required(['admin'])
def record_new_visit():
    try:
        data = request.get_json()
        
        # Create comprehensive visit record
        visit_data = {
            'patient_id': ObjectId(data['patient_id']),
            'doctor_id': ObjectId(data['doctor_id']),
            'department_id': ObjectId(data['department_id']),
            'reason_for_visit': data.get('reason_for_visit', ''),
            'visit_date': datetime.now(),
            'status': 'assigned',
            'created_at': datetime.now(),
            'created_by': ObjectId(session['user_id']),
            'visit_type': data.get('visit_type', 'regular'),  # regular, follow-up, emergency
            'priority': data.get('priority', 'normal'),  # low, normal, high, urgent
            'notes': data.get('admin_notes', '')
        }
        
        result = mongo.db.visit.insert_one(visit_data)
        
        if result.inserted_id:
            # Update patient's last visit date
            mongo.db.patient.update_one(
                {'_id': ObjectId(data['patient_id'])},
                {'$set': {'last_visit_date': datetime.now()}}
            )
            
            # Create entry in patient history summary
            patient = mongo.db.patient.find_one({'_id': ObjectId(data['patient_id'])})
            doctor = mongo.db.doctor.find_one({'_id': ObjectId(data['doctor_id'])})
            department = mongo.db.department.find_one({'_id': ObjectId(data['department_id'])})
            
            history_entry = {
                'patient_id': ObjectId(data['patient_id']),
                'visit_id': result.inserted_id,
                'patient_name': patient['name'] if patient else 'Unknown',
                'doctor_name': doctor['name'] if doctor else 'Unknown',
                'department_name': department['department_name'] if department else 'Unknown',
                'visit_date': datetime.now(),
                'reason_for_visit': data.get('reason_for_visit', ''),
                'status': 'assigned',
                'created_at': datetime.now()
            }
            
            mongo.db.patient_history.insert_one(history_entry)
            
            return jsonify({
                'success': True,
                'message': 'Visit recorded successfully',
                'visit_id': str(result.inserted_id)
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to record visit'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error recording visit: {str(e)}'})

@app.route('/api/prescription/add', methods=['POST'])
@role_required('doctor')
def add_prescription():
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle form data with files
            data = request.form.to_dict()
            visit_id = data['visit_id']
        else:
            # Handle JSON data
            data = request.get_json()
            visit_id = data['visit_id']
        
        # Get visit details
        visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not visit:
            return jsonify({'success': False, 'message': 'Visit not found'})
        
        doctor_id = session.get('user_id')
        if not doctor_id:
            return jsonify({'success': False, 'message': 'Doctor session not found'})
        
        uploaded_files = []
        upload_errors = []
        
        # Create prescription upload folder if it doesn't exist
        prescription_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'prescriptions')
        os.makedirs(prescription_upload_folder, exist_ok=True)
        
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename:
                    is_valid, validation_message = validate_file(file)
                    if not is_valid:
                        upload_errors.append(f"{file.filename}: {validation_message}")
                        continue
                    
                    try:
                        filename = secure_filename(file.filename)
                        # Create unique filename for prescription
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        unique_filename = f"prescription_{visit_id}_{timestamp}_{filename}"
                        file_path = os.path.join(prescription_upload_folder, unique_filename)
                        
                        if os.path.exists(file_path):
                            import random
                            random_suffix = random.randint(1000, 9999)
                            name, ext = os.path.splitext(unique_filename)
                            unique_filename = f"{name}_{random_suffix}{ext}"
                            file_path = os.path.join(prescription_upload_folder, unique_filename)
                        
                        file.save(file_path)
                        
                        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                            upload_errors.append(f"{filename}: Failed to save file properly")
                            continue
                        
                        file_info = {
                            'filename': filename,
                            'stored_filename': unique_filename,
                            'file_path': file_path,
                            'file_size': os.path.getsize(file_path),
                            'upload_date': datetime.now(),
                            'uploaded_by': ObjectId(doctor_id),
                            'mime_type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                        }
                        uploaded_files.append(file_info)
                        
                    except Exception as file_error:
                        upload_errors.append(f"{file.filename}: {str(file_error)}")
                        if 'file_path' in locals() and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except:
                                pass
        
        prescription_data = {
            'symptoms': data.get('symptoms', ''),
            'diagnosis': data.get('diagnosis', ''),
            'medications': data.get('medications', ''),
            'instructions': data.get('instructions', ''),
            'follow_up_date': datetime.strptime(data['follow_up_date'], '%Y-%m-%d') if data.get('follow_up_date') else None,
            'prescription_timestamp': datetime.now(),
            'status': 'completed',
            'prescribed_by': ObjectId(doctor_id),
            'last_modified': datetime.now(),
            'tests': data.get('tests', []),
            'attached_files': uploaded_files  # Store actual file info instead of just names
        }
        
        # Update visit with prescription data
        result = mongo.db.visit.update_one(
            {'_id': ObjectId(visit_id)},
            {'$set': prescription_data}
        )
        
        # Create comprehensive prescription record for history
        patient = mongo.db.patient.find_one({'_id': ObjectId(visit['patient_id'])})
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(visit['doctor_id'])})
        department = mongo.db.department.find_one({'_id': ObjectId(visit['department_id'])})
        
        patient_age = 0
        if patient:
            if 'age' in patient and patient['age']:
                patient_age = patient['age']
            elif 'date_of_birth' in patient and patient['date_of_birth']:
                try:
                    if isinstance(patient['date_of_birth'], str):
                        dob = datetime.strptime(patient['date_of_birth'], '%Y-%m-%d')
                    else:
                        dob = datetime.strptime(patient['date_of_birth'], '%Y-%m-%d') if isinstance(patient['date_of_birth'], str) else patient['date_of_birth']
                    today = datetime.now()
                    patient_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                except (ValueError, TypeError):
                    patient_age = 0
        
        prescription_record = {
            'visit_id': ObjectId(visit_id),
            'patient_id': visit['patient_id'],
            'patient_name': patient['name'] if patient else 'Unknown',
            'patient_age': patient_age,
            'doctor_id': visit['doctor_id'],
            'doctor_name': doctor['name'] if doctor else 'Unknown',
            'department_id': visit['department_id'],
            'department_name': department['department_name'] if department else 'Unknown',
            'visit_date': visit['visit_date'],
            'reason_for_visit': visit.get('reason_for_visit', ''),
            'symptoms': data.get('symptoms', ''),
            'diagnosis': data.get('diagnosis', ''),
            'medications': data.get('medications', ''),
            'instructions': data.get('instructions', ''),
            'follow_up_date': datetime.strptime(data['follow_up_date'], '%Y-%m-%d') if data.get('follow_up_date') else None,
            'prescription_timestamp': datetime.now(),
            'created_at': datetime.now(),
            'status': 'active',
            'tests': data.get('tests', []),
            'attached_files': uploaded_files  # Store actual file info
        }
        
        mongo.db.prescription.insert_one(prescription_record)
        
        # Update patient history summary
        mongo.db.patient_history.update_one(
            {'visit_id': ObjectId(visit_id)},
            {'$set': {
                'symptoms': data.get('symptoms', ''),
                'diagnosis': data.get('diagnosis', ''),
                'medications': data.get('medications', ''),
                'instructions': data.get('instructions', ''),
                'follow_up_date': datetime.strptime(data['follow_up_date'], '%Y-%m-%d') if data.get('follow_up_date') else None,
                'status': 'completed',
                'completed_at': datetime.now(),
                'tests': data.get('tests', []),
                'attached_files': uploaded_files  # Store actual file info
            }},
            upsert=True
        )
        
        response_data = {'success': True, 'message': 'Prescription added successfully'}
        
        if uploaded_files:
            response_data['files_uploaded'] = len(uploaded_files)
        
        if upload_errors:
            response_data['upload_errors'] = upload_errors
            response_data['message'] += f" (with {len(upload_errors)} file upload errors)"
        
        if result.modified_count > 0:
            return jsonify(response_data)
        else:
            return jsonify({'success': False, 'message': 'Failed to add prescription'})
            
    except Exception as e:
        print(f"Error in add_prescription: {str(e)}")
        return jsonify({'success': False, 'message': f'Error adding prescription: {str(e)}'})

@app.route('/api/prescription/<visit_id>/files/<file_index>')
@role_required(['doctor', 'admin'])
def download_prescription_file(visit_id, file_index):
    try:
        visit = mongo.db.visit.find_one({'_id': ObjectId(visit_id)})
        if not visit:
            return jsonify({'success': False, 'message': 'Visit not found'}), 404
        
        attached_files = visit.get('attached_files', [])
        file_idx = int(file_index)
        
        if file_idx >= len(attached_files):
            return jsonify({'success': False, 'message': 'File not found'}), 404
        
        file_info = attached_files[file_idx]
        file_path = file_info['file_path']
        
        # Ensure file path is within upload directory
        upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        requested_path = os.path.abspath(file_path)
        
        if not requested_path.startswith(upload_folder):
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'File not found on disk'}), 404
        
        if os.path.getsize(file_path) == 0:
            return jsonify({'success': False, 'message': 'File is empty'}), 404
        
        mime_type = file_info.get('mime_type', 'application/octet-stream')
        
        return send_file(
            file_path, 
            as_attachment=True, 
            download_name=file_info['filename'],
            mimetype=mime_type
        )
        
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid file index'}), 400
    except Exception as e:
        logging.error(f"Error downloading prescription file: {str(e)}")
        return jsonify({'success': False, 'message': f'Error downloading file: {str(e)}'}), 500

@app.route('/admin/patient-report')
@role_required('admin')
def admin_patient_report():
    patient_id = request.args.get('patient_id')
    if not patient_id:
        return redirect(url_for('admin_dashboard'))
    
    patient = mongo.db.patient.find_one({'_id': ObjectId(patient_id)})
    if not patient:
        return redirect(url_for('admin_dashboard'))
    
    # Calculate age
    today = datetime.now()
    age = today.year - patient['date_of_birth'].year
    if today.month < patient['date_of_birth'].month or \
       (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
        age -= 1
    
    patient['age'] = age
    return render_template('patient_report.html', patient=patient)

@app.route('/api/patient/<patient_id>/update', methods=['PUT'])
@role_required(['admin'])
def update_patient_by_id(patient_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'contact_number', 'date_of_birth', 'gender', 'address']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'})
        
        # Calculate age from date of birth
        try:
            dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - dob.year
            if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
                age -= 1
        except:
            age = 0
        
        # Update patient data
        update_data = {
            'name': data['name'],
            'contact_number': data['contact_number'],
            'aadhaar_number': data.get('aadhaar_number', ''),
            'date_of_birth': dob,
            'age': age,
            'gender': data['gender'],
            'address': data['address'],
            'allergies': data.get('allergies', ''),
            'chronic_illness': data.get('chronic_illness', ''),
            'updated_at': datetime.now()
        }
        
        result = mongo.db.patient.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Patient updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'No changes made or patient not found'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating patient: {str(e)}'})

@app.route('/api/patient/update', methods=['POST'])
@role_required(['admin'])
def update_patient_post():
    try:
        data = request.get_json()
        patient_id = data.get('patient_id')
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required'})
        
        # Validate required fields
        required_fields = ['name', 'contact_number', 'date_of_birth', 'gender', 'address']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'})
        
        # Calculate age from date of birth
        try:
            dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - dob.year
            if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
                age -= 1
        except:
            age = 0
        
        # Update patient data
        update_data = {
            'name': data['name'],
            'contact_number': data['contact_number'],
            'aadhaar_number': data.get('aadhaar_number', ''),
            'date_of_birth': dob,
            'age': age,
            'gender': data['gender'],
            'address': data['address'],
            'allergies': data.get('allergies', ''),
            'chronic_illness': data.get('chronic_illness', ''),
            'updated_at': datetime.now()
        }
        
        result = mongo.db.patient.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Patient updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'No changes made or patient not found'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating patient: {str(e)}'})

@app.route('/api/patients/export')
@role_required(['admin'])
def export_patients():
    try:
        import csv
        import io
        
        # Get all patients
        patients = list(mongo.db.patient.find({}))
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Patient ID', 'Name', 'Contact Number', 'Age', 'Gender', 
            'Address', 'Allergies', 'Chronic Illness', 'Aadhaar Number', 
            'Date of Birth', 'Registration Date'
        ])
        
        # Write patient data
        for patient in patients:
            # Calculate age if not present
            age = patient.get('age', 0)
            if not age and patient.get('date_of_birth'):
                try:
                    if isinstance(patient['date_of_birth'], datetime):
                        today = datetime.now()
                        age = today.year - patient['date_of_birth'].year
                        if today.month < patient['date_of_birth'].month or \
                           (today.month == patient['date_of_birth'].month and today.day < patient['date_of_birth'].day):
                            age -= 1
                except:
                    age = 0
            
            # Format dates
            dob_str = ''
            if patient.get('date_of_birth'):
                if isinstance(patient['date_of_birth'], datetime):
                    dob_str = patient['date_of_birth'].strftime('%Y-%m-%d')
                else:
                    dob_str = str(patient['date_of_birth'])
            
            reg_date_str = ''
            if patient.get('created_at'):
                if isinstance(patient['created_at'], datetime):
                    reg_date_str = patient['created_at'].strftime('%Y-%m-%d')
                else:
                    reg_date_str = str(patient['created_at'])
            
            writer.writerow([
                patient.get('patient_id', ''),
                patient.get('name', ''),
                patient.get('contact_number', ''),
                age,
                patient.get('gender', ''),
                patient.get('address', ''),
                patient.get('allergies', ''),
                patient.get('chronic_illness', ''),
                patient.get('aadhaar_number', ''),
                dob_str,
                reg_date_str
            ])
        
        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=patients_export_{datetime.now().strftime("%Y-%m-%d")}.csv'
        
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Export error: {str(e)}'}), 500

@app.route('/doctor/profile')
@role_required('doctor')
def doctor_profile():
    return render_template('doctor_profile.html')

@app.route('/api/doctor/profile')
@role_required('doctor')
def get_doctor_profile():
    try:
        doctor_username = session.get('username')
        user_id = session.get('user_id')
        
        print(f"[DEBUG] Session data - username: {doctor_username}, user_id: {user_id}")
        
        if not doctor_username and not user_id:
            return jsonify({'success': False, 'message': 'No doctor session found'})
        
        doctor = None
        
        # Try username first
        if doctor_username:
            doctor = mongo.db.doctor.find_one({'username': doctor_username})
            print(f"[DEBUG] Doctor found by username: {doctor is not None}")
        
        # Try user_id if username lookup failed
        if not doctor and user_id:
            try:
                if isinstance(user_id, str):
                    doctor = mongo.db.doctor.find_one({'_id': ObjectId(user_id)})
                else:
                    doctor = mongo.db.doctor.find_one({'_id': user_id})
                print(f"[DEBUG] Doctor found by user_id: {doctor is not None}")
            except Exception as id_error:
                print(f"[DEBUG] Invalid ObjectId: {id_error}")
        
        # Try finding by any matching field
        if not doctor and doctor_username:
            doctor = mongo.db.doctor.find_one({
                '$or': [
                    {'username': doctor_username},
                    {'email': doctor_username},
                    {'name': {'$regex': doctor_username, '$options': 'i'}}
                ]
            })
            print(f"[DEBUG] Doctor found by flexible search: {doctor is not None}")
        
        if not doctor:
            print(f"[DEBUG] Creating default doctor profile for session")
            default_doctor = {
                'name': 'Dr. ' + (doctor_username or 'Unknown'),
                'username': doctor_username or 'doctor',
                'email': '',
                'phone': '',
                'room_no': '',
                'specialization': 'General Medicine',
                'department_id': None,
                'created_at': datetime.now()
            }
            
            # Insert default doctor and get the ID
            result = mongo.db.doctor.insert_one(default_doctor)
            doctor = mongo.db.doctor.find_one({'_id': result.inserted_id})
            
            # Update session with new doctor ID
            session['user_id'] = str(result.inserted_id)
            print(f"[DEBUG] Created default doctor with ID: {result.inserted_id}")
        
        # Get department info
        department = None
        if doctor.get('department_id'):
            try:
                if isinstance(doctor['department_id'], str):
                    department = mongo.db.department.find_one({'_id': ObjectId(doctor['department_id'])})
                else:
                    department = mongo.db.department.find_one({'_id': doctor['department_id']})
            except Exception as dept_error:
                print(f"[DEBUG] Department lookup error: {dept_error}")
        
        total_patients = 0
        try:
            total_patients = mongo.db.visit.count_documents({
                'doctor_id': doctor['_id'], 
                'status': {'$in': ['completed', 'prescribed']}
            })
        except Exception as stats_error:
            print(f"[DEBUG] Stats calculation error: {stats_error}")
        
        doctor_data = {
            '_id': str(doctor['_id']),
            'name': doctor.get('name', 'Unknown Doctor'),
            'username': doctor.get('username', 'Unknown'),
            'email': doctor.get('email', ''),
            'phone': doctor.get('phone', ''),
            'room_no': doctor.get('room_no', ''),
            'specialization': doctor.get('specialization', 'General Medicine'),
            'department_name': department.get('department_name', 'General Medicine') if department else 'General Medicine',
            'department_id': str(doctor.get('department_id', '')),
            'created_at': doctor.get('created_at', datetime.now()).strftime('%Y-%m-%d') if doctor.get('created_at') else '',
            'total_patients': total_patients
        }
        
        print(f"[DEBUG] Returning doctor data for: {doctor_data['name']}")
        return jsonify({'success': True, 'doctor': doctor_data})
        
    except Exception as e:
        print(f"[ERROR] Doctor profile error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})

@app.route('/api/visit/update-prescription-image', methods=['POST'])
@role_required('doctor')
def update_visit_prescription_image():
    try:
        data = request.get_json()
        visit_id = data.get('visit_id')
        prescription_image = data.get('prescription_image')
        
        if not visit_id or not prescription_image:
            return jsonify({'success': False, 'message': 'Missing required data'})
        
        # Update the visit with prescription image path
        result = mongo.db.visit.update_one(
            {'_id': ObjectId(visit_id)},
            {'$set': {'prescription_image': prescription_image}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Prescription image updated'})
        else:
            return jsonify({'success': False, 'message': 'Visit not found or not updated'})
            
    except Exception as e:
        print(f"[ERROR] Update prescription image error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/doctor/statistics')
@role_required('doctor')
def get_doctor_statistics():
    try:
        doctor_user_id = session.get('user_id')
        doctor = mongo.db.doctor.find_one({'_id': ObjectId(doctor_user_id)})
        
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'})
        
        doctor_id = doctor['_id']
        
        # Count total patients treated
        total_patients = mongo.db.visit.count_documents({
            'doctor_id': doctor_id, 
            'status': {'$in': ['completed', 'prescribed']}
        })
        
        # Count today's patients
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        today_patients = mongo.db.visit.count_documents({
            'doctor_id': doctor_id,
            'visit_date': {'$gte': today, '$lt': tomorrow}
        })
        
        # Count completed patients (today)
        completed_patients = mongo.db.visit.count_documents({
            'doctor_id': doctor_id,
            'visit_date': {'$gte': today, '$lt': tomorrow},
            'status': {'$in': ['completed', 'prescribed']}
        })
        
        # Count pending patients (today)
        pending_patients = mongo.db.visit.count_documents({
            'doctor_id': doctor_id,
            'visit_date': {'$gte': today, '$lt': tomorrow},
            'status': {'$in': ['assigned', 'in_progress', 'pending']}
        })
        
        # Count total prescriptions
        total_prescriptions = mongo.db.prescription.count_documents({'doctor_id': doctor_id})
        if total_prescriptions == 0:
            total_prescriptions = mongo.db.visit.count_documents({
                'doctor_id': doctor_id,
                'status': {'$in': ['completed', 'prescribed']},
                '$or': [
                    {'medications': {'$exists': True, '$ne': ''}},
                    {'diagnosis': {'$exists': True, '$ne': ''}}
                ]
            })
        
        stats = {
            'total_patients': total_patients,
            'today_patients': today_patients,
            'completed_patients': completed_patients,
            'pending_patients': pending_patients,
            'total_prescriptions': total_prescriptions
        }
        
        return jsonify({'success': True, 'stats': stats})
        
    except Exception as e:
        print(f"Statistics error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/doctor/profile/update', methods=['PUT'])
@role_required('doctor')
def update_doctor_profile():
    try:
        data = request.get_json()
        doctor_username = session.get('username')
        
        # Check if username is being changed and if it's unique
        if data.get('username') != doctor_username:
            existing_doctor = mongo.db.doctor.find_one({'username': data.get('username')})
            existing_admin = mongo.db.admin.find_one({'username': data.get('username')})
            
            if existing_doctor or existing_admin:
                return jsonify({'success': False, 'message': 'Username already exists'})
        
        # Update doctor profile
        update_data = {
            'name': data.get('name'),
            'username': data.get('username'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'specialization': data.get('specialization'),
            'room_no': data.get('room_no'),
            'updated_at': datetime.now()
        }
        
        result = mongo.db.doctor.update_one(
            {'username': doctor_username},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            # Update session username if it was changed
            if data.get('username') != doctor_username:
                session['username'] = data.get('username')
            
            return jsonify({'success': True, 'message': 'Profile updated successfully'})
        else:
            return jsonify({'success': False, 'message': 'No changes made'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# The first instance at line 1113 is kept as it uses user_id which is more reliable

if __name__ == '__main__':
    app.run(debug=True)
