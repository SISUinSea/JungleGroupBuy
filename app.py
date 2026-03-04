from flask import Flask, render_template, request, jsonify, redirect, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_bcrypt import Bcrypt # 비밀번호 암호화 라이브러리
from functools import wraps     # 로그인 상태 체크 데코레이터

app = Flask(__name__)
app.secret_key = 'jungle'
client = MongoClient('mongodb+srv://jungle_for_all:1234@junglegroupbuy.vvvtwuf.mongodb.net/?appName=jungleGroupBuy', tlsAllowInvalidCertificates=True)
db = client.jungle_groupbuy

# bcrypt 라이브러리 사용하기 위한 설정입니다. 꼬오옥 상단에 임포트 해줘야 쓸 수 있어요.
bcrypt = Bcrypt(app)

# =====================================================================
# 🚧 [영역 1]
# =====================================================================
# 회원가입 기능
@app.route('/signup')
def sign_up_page():
    return render_template('signup.html')

@app.route('/signup', methods=['POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        email = request.form['slack_email']
        generation = request.form['generation']
        class_number = request.form['class_number']
        createdAt = datetime.now()

        # 비밀번호 암호화
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        user_info = {
            'username': username, 
            'password': hashed_password, 
            'name': name, 
            'email': email, 
            'generation': generation, 
            'class_number': class_number, 
            'createdAt': createdAt
            }
        
        db.users.insert_one(user_info)
        return redirect('/login')
     

# =====================================================================
# 🚧 [영역 2]
# 로그인
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')  # 로그인 페이지로 이동

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    user = db.users.find_one({'username': username})

    if user and bcrypt.check_password_hash(user['password'], password):
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        return redirect('/')  # 로그인 성공, groupBuyList 페이지로 이동 필요.
    
    return "아이디 또는 비밀번호가 올바르지 않습니다."

# 로그인 여부 확인하는 데코레이터 함수입니당. 로그인이 필요한 페이지에 @login_required 데코레이터를 붙여주시면 됩니다!!
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# =====================================================================




# =====================================================================
# 🚧 [영역 3]
# =====================================================================



# =====================================================================
# 🚧 [영역 4]
# =====================================================================

@app.route('/')
def mypage():
    pass

    # 1. DB에 넣을 가짜 데이터(JSON/Dictionary) 만들기
    test_data = {
        "title": "클라우드 DB 연결 테스트",
        "message": "이 데이터가 Atlas에 보인다면 연결 대성공입니다!",
        "author": "리더"
    }

    # 2. 'test_collection'이라는 임시 컬렉션에 데이터 1개 집어넣기 (insert_one)
    result = db.test_collection.insert_one(test_data)

    # 3. 삽입 성공 후, 방금 넣은 데이터의 고유 ID를 화면에 보여주기
    return jsonify({
        "status": "success",
        "message": "MongoDB Atlas 연결 및 데이터 삽입 완벽 성공!",
        "inserted_id": str(result.inserted_id)  # ObjectId를 문자로 변환해서 반환
    })



# ============================================================================
if __name__ == '__main__':
    app.run('0.0.0.0', port=5001, debug=True)
