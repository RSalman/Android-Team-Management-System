from collections import OrderedDict
from pymongo import MongoClient
from bson.objectid import ObjectId
from flask import Flask
from flask import jsonify
from flask import request
from datetime import datetime, timedelta
from flask_jwt import JWT, jwt_required, current_identity, JWTError
import bcrypt
import dummyData
from datetime import datetime
from voluptuous import Schema, Any, Required, All, Length, Range, MultipleInvalid, Invalid

app = Flask(__name__)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = 'supercomplexrandomvalue'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(seconds=7200) # token expires every 2 hours

client = MongoClient('mongodb://localhost:27017/')
db = client['seg3102']
users = db['users']
student_users = db['students']
instructor_users = db['instructors']
team_params = db['teamParams']
courses = db['courses']
teams = db['teams']


def Date(fmt='%d/%m/%Y %H:%M:%S'):
    return lambda v: datetime.strptime(v, fmt)

def validate_email(email):
     """Validate email."""
     if not "@" in email:
         raise Invalid("The value entered is invalid")
     return email

#Define Schema
schema = Schema({
            "username": Any(str, unicode), 
            "password": Any(str, unicode), 
            "email": validate_email,
            "first_name": Any(str, unicode),
            "last_name" : Any(str, unicode),
            "user_type" : Any(str, unicode),
            "programOfStudy" : Any(str, unicode),
            "course_code" : Any(str, unicode),
            "course_section" : All(Any(str, unicode), Length(min=1, max=1)),
            "minimum_num_students" : All(int, Range(min=1)),
            "maximum_num_students" : All(int, Range(min=1)),
            "deadline" : Date(),
            "team_param_id": Any(str, unicode),
            "team_name" : Any(str, unicode),
            "team_id" :  Any(str, unicode),
            "teamParam_id" : Any(str, unicode)

            })


def authenticate(username, password):
    user = student_users.find_one({"username": username})
    user_type = "student"
    if user is None:
        user = instructor_users.find_one({"username": username})
        user_type = "instructor"
    elif teams.find_one({"liason": username}):
        user_type = "liason"
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
    user = None
    if user_id:
        user = student_users.find_one({"_id": ObjectId(user_id)})    
        if user is None:
            user = instructor_users.find_one({"_id": ObjectId(user_id)})                
    return user

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

@jwt.jwt_error_handler
def error_response_handler(error):
    return jsonify(OrderedDict([
        ('status_code', error.status_code),
        ('error', error.error),
        ('message', error.description),
    ])), error.status_code, error.headers


@app.route('/register', methods=['POST'])
def register():
    required_keys = ['username', 'password', 'email', 'first_name', 'last_name', 'user_type']
    validation = validate_data_format(request, required_keys)
    valid_format = validation[0]
    data = validation[1]
    if valid_format:
        username = request.json['username']
        password = request.json['password']
        email = request.json['email']
        f_name = request.json['first_name']
        l_name = request.json['last_name']
        user_type = request.json['user_type']
        try:
            schema(
                    {
                        "username": username, 
                        "password": password, 
                        "email": email,
                        "first_name": f_name,
                        "last_name" : l_name,
                        "user_type" : user_type
                    })
            conforms_to_schema = True
        except MultipleInvalid as e: 
            conforms_to_schema = False
            if "expected" in e.msg:
                data['message'] = e.path[0] + " is not in the correct format"
            else:
                data['message'] = e.msg + " for " + e.path[0]

        if conforms_to_schema:
            #Check if user already exists
            if student_users.find_one({"username": username}):                    
                data['message'] = "A User with that username already exists"
            elif instructor_users.find_one({"username": username}):                    
                data['message'] = "A User with that username already exists"
            else:         
                if(user_type.strip().lower() == "student"):
                    if 'programOfStudy' not in request.json:
                        data['message'] = "Program of Study was not specified"
                    else:
                        program_of_study = request.json['programOfStudy']
                        register = True
                        try:
                            schema({"programOfStudy" : program_of_study})
                        except MultipleInvalid as e: 
                            data['message'] = "The program of study entered is not a valid program"
                            register = False
                        if register:
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
                elif (user_type.strip().lower() == "instructor"):
                    res = instructor_users.insert_one({
                                "username": username,
                                "password": encrypt(password),
                                "email" : email,
                                "firstName" : f_name,
                                "lastName" : l_name
                            })
                    data['status'] = 200
                    data['message'] = 'Instructor successfully registered!'
                else:
                    data['message'] = 'The user type specified is not valid'
        
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

@app.route('/protected', methods=['POST'])
@jwt_required()
def protected():
    return '%s' % current_identity

@app.route('/createTeamParams', methods=['POST'])
@jwt_required()
def create_team_params():
    user = instructor_users.find_one({'_id': current_identity['_id']})
    required_keys = ['course_code', 'course_section','minimum_num_students', 'maximum_num_students', 'deadline']
    validation = validate_data_format(request, required_keys)
    valid_format = validation[0]
    data = validation[1]

    if valid_format:
        if user:
                course_code = request.json['course_code'].upper()
                course_section = request.json['course_section'].upper()
                minimum_number_of_students = request.json['minimum_num_students']
                maximum_number_of_students = request.json['maximum_num_students'] 
                deadline = request.json['deadline']
                
                try:
                    schema(
                            {
                                "course_code": course_code, 
                                "course_section": course_section,
                                "minimum_num_students" : minimum_number_of_students,
                                "maximum_num_students" : maximum_number_of_students,
                                "deadline" : deadline
                            })
                    conforms_to_schema = True
                except MultipleInvalid as e: 
                    conforms_to_schema = False
                    if "expected" in e.msg:
                        data['message'] = e.path[0] + " is not in the correct format"
                    else:
                        data['message'] = e.msg + " for " + e.path[0]
                    
                if conforms_to_schema:
                    # Search for course by course code & section
                    course = courses.find_one({"courseCode": course_code, "courseSection": course_section})
                    if course is None:
                        data['message'] = "The course code with the specified section does not exist"
                    else:
                        res = team_params.insert_one({
                                "instructorId" : user['_id'],
                                "courseId" : course['_id'],
                                "minimumNumberOfStudents": minimum_number_of_students,
                                "maximumNumberOfStudents": maximum_number_of_students,
                                "deadline": deadline
                            })
                        data['status'] = 200
                        data['message'] = 'Team Parameters were successfully created!'
        else:
            data['message'] = 'You do not have permission to create team parameters'
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

@app.route('/teamParams', methods=['GET'])
@jwt_required()
def get_team_params():
    data = {}
    data['status'] = 200
    teamParams = []
    member_of_team = False
    current_user = student_users.find_one({"_id" : current_identity['_id']})
    if current_user is None:
        current_user = instructor_users.find_one({"_id" : current_identity['_id']})
    for row in team_params.find():
        member_of_team = False
        course = courses.find_one({'_id': row['courseId']})
        instructor = instructor_users.find_one({'_id': row['instructorId']})
        #search if user is a part of a team within the team param
        for team in teams.find({"teamParamId" : row['_id']}):
            if current_user['username'] in team['teamMembers']:
                member_of_team = True      
        obj = {
            "_id": str(row['_id']),
            "courseId": str(course['_id']),
            "InstructorId": str(instructor['_id']),
            "course_code": course['courseCode'],
            "course_section": course['courseSection'],
            "instructor_name": instructor['firstName'] + ' ' + instructor['lastName'],
            "deadline": row['deadline'],
            "minimumNumberOfStudents": row['minimumNumberOfStudents'],
            "maximumNumberOfStudents": row['maximumNumberOfStudents'],         
        }
        if not member_of_team:
            teamParams.append(obj) 
    if len(teamParams) == 0:
        data['message'] = "You are already a member of a team in each team Parameter"   
    else:
        data['message'] = "Data successfully returned"    
    data['teamParams'] = teamParams
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

@app.route('/createTeam', methods=['POST'])
@jwt_required()
def create_team():

    required_keys = ['team_param_id', 'team_name', 'team_members']
    validation = validate_data_format(request, required_keys)
    valid_format = validation[0]
    data = validation[1]

    if valid_format:
            team_param_id = request.json['team_param_id']
            team_name = request.json['team_name']
            team_members = request.json['team_members']
            liason = student_users.find_one({"_id" : current_identity['_id']})
            invalid_liason = True
            if liason:
                liason = liason['username']
                invalid_liason = False
                if liason not in team_members:
                    team_members.append(liason) #Add liason username if it is not already in 

            try:
                schema(
                        {
                            "team_param_id": team_param_id, 
                            "team_name": team_name 
                            #Team_members not included because it is easier to validate lists manually than using library
                        })
                conforms_to_schema = True
            except MultipleInvalid as e: 
                conforms_to_schema = False
                if "expected" in e.msg:
                    data['message'] = e.path[0] + " is not in the correct format"
                else:
                    data['message'] = e.msg + " for " + e.path[0]
                
            if conforms_to_schema:
                valid_info = invalid_object(team_param_id, team_params)
                invalid_team_param = valid_info[0]
                teamParam = valid_info[1]
                
                if invalid_liason:
                    data['message'] = "You do not have permission to perform this operation"
                elif invalid_team_param:
                    data['message'] = "No team parameter exists for the given team parameter ID"
                elif len(team_members) > teamParam['maximumNumberOfStudents']:
                    data['message'] = "You have selected too many members, the maximum number of members allowed is "+ str(teamParam['maximumNumberOfStudents']) 
                elif len(team_members) < teamParam['minimumNumberOfStudents']:
                    data['message'] = "You did not provide enough members, the minimum number of members allowed is "+ str(teamParam['minimumNumberOfStudents'])
                elif teams.find_one({'teamName' : team_name}): #Check within the teams with same teamparam (Valid to have different courses have teams with same name? 
                    data['message'] = "A team already exists with the given team name"
                else:
                    #Check if each username in the list of team_members received is a valid student user
                    createTeam = True
                    members = []
                    for member in team_members:
                        if student_users.find_one({"username" : member}) is None:
                            createTeam = False
                            data['message'] = member + " is not a valid Student username"
                            break
                        members.append(member)

                    if createTeam:
                        #Check if each student in team_members IS NOT in a team with the team param
                        list_of_teams = teams.find({"teamParameterId" : teamParam['_id']})
                        for team in list_of_teams:
                            for student in team_members:
                                if student in team['teamMembers']:
                                    createTeam = False
                                    data['message'] = student + ' is already in a team'
                                    break

                    #If createTeam is still true, then we can insert a new team into the database
                    if createTeam:
                        #Check if members is less than max team size
                        less_than_max = len(members) < teamParam['maximumNumberOfStudents']
                        if less_than_max:
                            status = "incomplete"
                        else:
                            status = "complete"
                        
                        res = teams.insert_one({
                                "teamParamId" : teamParam['_id'],
                                "teamName" : team_name,
                                "dateOfCreation" : datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                                "status" : status,
                                "teamSize" : len(members),
                                "teamMembers": members,
                                "liason" : liason,
                                "requestedMembers" : []
                                
                            })
                        data['status'] = 200
                        data['message'] = 'Team was successfully created!'
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp


@app.route('/students', methods=['GET'])
@jwt_required()
def get_students():
    data = {}
    data['status'] = 200
    list_of_students = []
    for row in student_users.find():
        obj = {
            "_id": str(row['_id']),
            "username": row['username'],
            "firstName": row['firstName'],
            "lastName": row['lastName'],
            "programOfStudy": row['programOfStudy'],
            "email": row['email']
            }
        list_of_students.append(obj)
    data['students'] = list_of_students
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

#Use case : Visualize student Teams
@app.route('/teams', methods=['GET'])
@jwt_required()
def get_teams():
    data = {}
    data['status'] = 200
    list_of_teams = []
    for row in teams.find():
        row['_id'] = str(row['_id'])
        row['teamParamId'] = str(row['teamParamId'])
        list_of_teams.append(row)
    data['teams'] = list_of_teams
    resp = jsonify(data)
    resp.status_code = data['status']

    return resp

#Use case Join Team goes against our design. A student can only join if they are not in a team already
@app.route('/joinTeams', methods=['POST'])
@jwt_required()
def join_teams():
    data = {}
    required_keys = ['team_ids']
    validation = validate_data_format(request, required_keys)
    valid_format = validation[0]
    data = validation[1]

    if valid_format:
        team_ids = request.json['team_ids']
        #Check if team_ids are valid
        invalid_team_ids = False
        
        for id in team_ids:
            invalid_team_ids = invalid_object(id, teams)[0]
            if invalid_team_ids:
                break
        if invalid_team_ids:
            data['message'] = 'A team with id: ' + id + ' does not exist'
        else:
            user = student_users.find_one({"_id": current_identity['_id']})
            if user is None:
                user = instructor_users.find_one({"_id" : current_identity['_id']})
            username = user['username']

            #Check if user already in teams/user already requested teams
            invalid_team_selection = False
            for team in team_ids:
                current_team = teams.find_one({"_id" : ObjectId(team)})
                if username in current_team['requestedMembers'] or username in current_team['teamMembers']:
                    invalid_team_selection = True
                    break

            if invalid_team_selection:
                data['message'] = "You are already a member/requestedMember of one or more teams selected"
            else:
                for team in team_ids:
                    current_team = teams.find_one({"_id" : ObjectId(team)})
                    requests = current_team['requestedMembers']
                    requests.append(username)
                    teams.update_one(
                        {
                            "_id": current_team['_id']
                        },
                        {
                            "$set": {"requestedMembers": requests}
                        })
                data['status'] = 200
                data['message'] = 'Successfully joined teams'
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

#View Requested members of a specified team. Use Case: Accept new Students
@app.route('/viewRequestedMembers', methods=['GET'])
@jwt_required()
def view_requested_members():
    data = {}
    data['status'] = 404
    current_user = student_users.find_one({"_id": ObjectId(current_identity['_id'])})
    
    if current_user:
        if 'team_id' in request.args:
            team_id = request.args['team_id']
            team_validation = invalid_object(team_id, teams)
            invalid_team_id= team_validation[0]
            team = team_validation[0]
            if invalid_team_id:
                data['message'] = "A team with id: " + team_id + " does not exist"
            elif current_user['username'] != team['liason']:
                data['message'] = "Only liasons of the requested team can perform this operation"
            else:
                list_of_requests = team['requestedMembers']
                data['requestedMembers'] = list_of_requests
                data['status'] = 200
                
        else: 
            data['message'] = "No team id was provided"
    else:
        data['message'] = "You do not have permission to perform this operation"

    resp = jsonify(data)
    resp.status_code = data['status']

    return resp

@app.route('/acceptMembers', methods=['POST'])
@jwt_required()
def accept_members():
    current_user = student_users.find_one({"_id": ObjectId(current_identity['_id'])})
    required_keys = ['team_id','list_of_usernames']
    validation = validate_data_format(request, required_keys)
    valid_format = validation[0]
    data = validation[1]

    if current_user is None:
        data['message'] = 'You do not have permission to accept new members'
    elif valid_format:  
        team_id = request.json['team_id']
        list_of_usernames = request.json['list_of_usernames']
        team_validation = invalid_object(team_id, teams) 
        invalid_team = team_validation[0]
        team = team_validation[1] # None if invalid _team is true
        invalid_users = False
        users_in_team = False
        
        if invalid_team:
            data['message'] = 'A team does not exist with the specified id'
        elif team['liason'] != current_user['username']:
            data['message'] = 'Only the liason of the team can perform this operation'
        elif len(list_of_usernames) == 0:
            data['message'] = "The members you would like to add to team must be provided"
        elif team['status'] == "complete":
            data['message'] = "The team selected already has the maximum number of members"
        else:
            for username in list_of_usernames:
                student = student_users.find_one({"username": username})
                if student is None:
                    invalid_users = True
                    break
                elif username in team['teamMembers']:
                    users_in_team = True
                    break

            team_param = team_params.find_one({"_id" : team['teamParamId']})
            max_students = team_param['maximumNumberOfStudents']

            if invalid_users:
                data['message'] = "No student exists with the username: " + username
            elif users_in_team: 
                data['message'] = username + " is already a member of the team"
            elif (len(list_of_usernames) + int(team['teamSize'])) > max_students:
                data['message'] = "Maximum number of students is exceeded if all selected students are added to team"
            else:
                members = team['teamMembers'] + list_of_usernames
                requests = team['requestedMembers']
                #Remove the members in the requests that are going to be added
                for member in members:
                    if member in requests:
                        requests.remove(member)

                if len(members) == max_students:
                    status = "complete"
                else:
                    status = "incomplete"
                teams.update_one(
                    {
                        "_id": team['_id']
                    },
                    {
                        "$set": {"teamMembers": members, "status": status, "requestedMembers" : requests, "teamSize" : len(members)}
                    })
                data['message'] = "Successfully added selected users to team"
                data['status'] = 200
    resp = jsonify(data)
    resp.status_code = data['status']
    return resp

#Return the incomplete teams with the specified team parameter 
@app.route('/teamsInTeamParam', methods=['GET'])
@jwt_required()
def get_incomplete_teams_with_teamParam():
    data = {}
    data['status'] = 404
    current_user = student_users.find_one({"_id": ObjectId(current_identity['_id'])})
    if current_user is None:
        data['message'] = "You do not have permission to perform this operation"
    elif 'teamParam_id' in request.args:
        teamParam_id = request.args['teamParam_id']
        invalid_teamParam_id= invalid_object(teamParam_id, team_params)[0]

        if invalid_teamParam_id:
            data['message'] = "A team Parameter with id: '" + teamParam_id + "' does not exist"
        else:
            list_of_teams = []
            for team in teams.find({'teamParamId' : ObjectId(teamParam_id) , 'status' : 'incomplete' }):
                team['teamParamId'] = str(team['teamParamId'])
                team['_id'] = str(team['_id'])
                list_of_teams.append(team)

            data['list_of_teams'] = list_of_teams
            data['status'] = 200
            
    else: 
        data['message'] = "The team Parameter was not provided"


    resp = jsonify(data)
    resp.status_code = data['status']

    return resp


#Return the teams the current user is a liason for
@app.route('/liasionTeams', methods=['GET'])
@jwt_required()
def get_liasion_teams():
    data = {}
    data['status'] = 404
    current_user = student_users.find_one({"_id" : current_identity['_id']})
    if current_user:
        db_teams = teams.find({"liason" : current_user['username']})
        number_of_teams = db_teams.count()
        if number_of_teams == 0:
            data['message'] = "You are not a liasion of any team"
        else:
            list_of_teams = []
            for team in db_teams:
                team['teamParamId'] = str(team['teamParamId'])
                team['_id'] = str(team['_id'])
                list_of_teams.append(team)
        
            data['teams'] = list_of_teams
    else:
        data['message'] = "You do not have permission to perform this operation"        


    resp = jsonify(data)
    resp.status_code = data['status']

    return resp



#Validates object based on team_id and the specified db to search in
def invalid_object(id, database):
    invalid_id = False
    try:
        obj = database.find_one({"_id" : ObjectId(id)})
        if obj is None:
            invalid_id = True
    except: 
        invalid_id = True
        obj= None
    return (invalid_id, obj)

def validate_data_format (request, required_keys):
    data = {}
    data['status'] = 404   
    valid_data = True 
    if not request.json:
        data['message'] = 'No data was provided'
        valid_data = False
    else:
        valid_data = all(key in request.json for key in required_keys) # Check if request.json contains all the required keys  
        if valid_data:
            valid_data = "" not in request.json.viewvalues() # Check if request.json contains content for all values  
        if valid_data == False:
            data['message'] = 'All fields must be provided!' 
    return (valid_data, data)


if __name__ == "__main__":
    dummyData.dummy_data()
    app.run(port=3001)    

