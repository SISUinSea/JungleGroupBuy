import pymongo
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

@app.route('/', methods=['GET'])
def getGroupBuyList():
    result_list = list(db.group_buys.find({}).sort("createdAt", pymongo.DESCENDING))

    return render_template('groupBuyList.html', items=result_list)


@app.route('/group-buy/<groupbuyid>', methods=['GET'])
def getGroupBuy(groupbuyid):
    result = db.group_buys.find_one({'_id': ObjectId(groupbuyid)})
    if result is None:
        return "게시글을 찾을 수 없습니다.", 404
    return render_template('groupBuyDetail.html', product=result)

@app.route('/group-buy/create', methods=['GET'])
def getGroupBuyCreate():

    return render_template('groupBuyCreate.html')


@app.route('/api/group-buy', methods=['POST'])
def api_create_group_buy():
    data = request.get_json()

    deadline_str = data.get('deadline')
    open_chat_url = data.get('openChatUrl')
    orders = data.get('order', [])
    total_amount = data.get('totalAmount', 0)

    if not deadline_str or not open_chat_url:
        return jsonify({"result": "fail", "msg": "필수 데이터가 누락되었습니다."}), 400

    try:
        deadline_date = datetime.strptime(deadline_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"result": "fail", "msg": "잘못된 날짜 형식입니다."}), 400

    # TODO: 나중에는 session['user_id'] 등을 통해 실제 로그인 유저를 가져와야
    # TODO: todo....... user > users 컬렉션으로 변경되었음
    author_user = db.user.find_one({"name": "메타몽"})

    if not author_user:
        return jsonify({"result": "fail", "msg": "테스트 유저(메타몽)가 DB에 없습니다."}), 500

    # [최종 DB 입력용 데이터 조립]
    now = datetime.now()
    new_group_buy = {
        "groupBuyNumber": now.strftime("%Y%m%d%H%M%S"),  # 임시로 현재시간 기반 번호 생성
        "author": {
            "userId": author_user["_id"],
            "name": author_user["name"],
            "class": author_user.get("class", ""),
            "generation": author_user.get("generation", 0)
        },
        "targetAmount": 30000,  # 다이소 무료배송 고정값
        "currentAmount": total_amount,  # 현재는 0 (경로 B)
        "deadline": deadline_date,  # Date 객체!
        "status": "open",
        "openChatUrl": open_chat_url,
        "createdAt": now,
        "updatedAt": now,
        "orders": orders  # 현재는 빈 배열 [] (경로 B)
    }

    # DB에 밀어 넣기
    result = db.group_buys.insert_one(new_group_buy)

    # [응답] 프론트엔드가 기다리는 'inserted_id'를 반드시 문자열로 변환해서 줘야 합니다.
    # JS의 window.location.href = `/group-buy/${result.inserted_id}`; 가 작동하게 됨!
    return jsonify({
        "result": "success",
        "inserted_id": str(result.inserted_id)
    })



# ============================================================================
if __name__ == '__main__':
    app.run('0.0.0.0', port=5001, debug=True)
