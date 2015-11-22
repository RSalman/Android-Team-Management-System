from pymongo import MongoClient
from bson.objectid import ObjectId
from flask import Flask
from flask import jsonify
from flask import request
from datetime import datetime
from flask_jwt import JWT, jwt_required, current_identity, JWTError
import bcrypt
import dummyData

app = Flask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = 'supercomplexrandomvalue'

client = MongoClient('mongodb://localhost:27017/')
db = client['seg3102']
users = db['users']
student_users = db['students']
instructor_users = db['instructors']
team_params = db['teamParams']
courses = db['courses']


def authenticate(username, password):
    user = student_users.find_one({"username": username})
    user_type = "student"
    if user is None:
        user = instructor_users.find_one({"username": username})
        user_type = "instructor"        
    if user:
        user['type'] = user_type
        passMatch = bcrypt.hashpw(password.encode('utf-8'), user['password'].encode('utf-8')) == user['password'].encode('utf-8')
        if passMatch:                    
            return user
        else:
            raise JWTError('Bad credentials', 'Incorrect password!', status_code=404)
    else:
        raise JWTError('Bad credentials', 'User not found!', status_code=404)

def identity(payload):
    user_id = payload['identity']
    if user_id:     
        return users.find_one({"_id": ObjectId(user_id)})
    return None

def encrypt(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

jwt = JWT(app, authenticate, identity)

@jwt.jwt_payload_handler
def payload_handler(identity):
    iat = datetime.utcnow()
    exp = iat + app.config.get('JWT_EXPIRATION_DELTA')
    nbf = iat + app.config.get('JWT_NOT_BEFORE_DELTA')    
    identity = str(identity["_id"])
    return {'exp': exp, 'iat': iat, 'nbf': nbf, 'identity': identity}

@jwt.auth_response_handler
def auth_response_handler(access_token, identity):
    return jsonify({
        'access_token': access_token.decode('utf-8'),
        'user_type': identity['type']
    })

@app.route('/register', methods=['POST'])
def register():
    data = {}
    data['status'] = 404
    if not request.json:
        data['message'] = 'No data was provided'
    else:
        try:
            username = request.json['username']
            password = request.json['password']
            email = request.json['email']
            f_name = request.json['first_name']
            l_name = request.json['last_name']
            user_type = request.json['user_type']

            #Check if user already exists
            if student_users.find_one({"username": username}):                    
                data['message'] = "Student with that username already exists"
            elif instructor_users.find_one({"username": username}):                    
                data['message'] = "Instructor with that username already exists"
            else:         
                if(user_type.strip().lower() == "student"):
                    program_of_study = request.json['programOfStudy']
                    res = student_users.insert_one({
                        "username": username,
                        "password": encrypt(password),
                        "email" : email,
                        "firstName" : f_name,
                        "lastName" : l_name,
                        "programOfStudy" : program_of_study
                    })
                    data['status'] = 200
                    data['message'] = 'Student successfully registered!'
                else:
                    res = instructor_users.insert_one({
                            "username": username,
                            "password": encrypt(password),
                            "email" : email,
                            "firstName" : f_name,
                            "lastName" : l_name
                        })
                    data['status'] = 200
                    data['message'] = 'Instructor successfully registered!'
        except :
            data['message'] = 'All required fields were not provided!'
               
        
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

@app.route('/protected', methods=['POST'])
@jwt_required()
def protected():
    return '%s' % current_identity

@app.route('/createTeamParams', methods=['POST'])
#@jwt_required()
def create_team_params():
    data = {}
    #user_id = current_identity['_id']
    #if instructor.findOne({'_id':current_identity['_id']})
    required_keys = ['course_code', 'course_section','minimum_num_students', 'maximum_num_students', 'deadline']
    data['status'] = 404
    if not request.json:
        data['message'] = 'No data was provided'
    elif all(key in request.json for key in required_keys):        # Check if request.json contains all the required keys        
            course_code = request.json['course_code']
            course_section = request.json['course_section']
            minimum_number_of_students = request.json['minimum_num_students']
            maximum_number_of_students = request.json['maximum_num_students'] 
            deadline = request.json['deadline']
            #SHOULD HAVE VALIDATION HERE THAT CHECKS WHETHER THE PARAMETERS ARE IN CORRECT FORMAT (DATE, INTEGER, ETC.)
            
            # Search for course by course code
            course = courses.find_one({"courseCode": course_code, "courseSection": course_section})
            if course is None:
                data['message'] = "The course code given does not exist"
            else:
                res = team_params.insert_one({
                        "courseId" : course['_id'],
                        "minimumNumberOfStudents": minimum_number_of_students,
                        "maximumNumberOfStudents": minimum_number_of_students,
                        "deadline": deadline
                    })
                data['status'] = 200
                data['message'] = 'Team Parameters were successfully created!'
    else:
        data['message'] = 'All fields must be provided!'                
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

@app.route('/teamParams', methods=['GET'])
def get_team_params():
    data = {}
    data['status'] = 200
    teamParams = []
    for row in team_params.find():
        row['_id'] = str(row['_id'])
        course = courses.find_one({'_id': row['courseId']})
        row['courseId'] = str(row['courseId'])
        row['course_code'] = course['courseCode']
        row['course_section'] = course['courseSection']
        teamParams.append(row)
        
        
    data['teamParams'] = teamParams
    resp = jsonify(data)
    resp.status_code = data['status']

    return resp

@app.route('/createTeam', methods=['POST'])
def create_team():
    data = {}
    #user_id = current_identity['_id']
    #if instructor.findOne({'_id':current_identity['_id']})
    data['status'] = 404    
    if not request.json:
        data['message'] = 'No data was provided'
    else:
        try:
            instructor_id = "" # COME BACK TO ADD IDENTITY
            team_paramter_id = request.json['course_code']
            minimum_number_of_students = request.json['minimumNumberOfStudents']
            maximum_number_of_students = request.json['maximumNumberOfStudents'] 
            deadline = request.json['deadline']

            #Search for course by course code
            course = courses.find_one({"courseCode": course_code})
            if course is None:
                data['message'] = "The course code given does not exist"
            else:
                res = team_params.insert_one({
                        "courseCode" : course['_id'],
                        "minimumNumberOfStudents": minimum_number_of_students,
                        "maximumNumberOfStudents": minimum_number_of_students,
                        "deadline": deadline
                    })
                data['status'] = 200
                data['message'] = 'Team Parameters were successfully created!'
        except :
            data['message'] = 'All fields must be provided!'
            exception = True
                
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp


if __name__ == "__main__":
    dummyData.dummy_data()
    app.run(port=3001, host='0.0.0.0')    

