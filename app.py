import pymongo
from flask import Flask, render_template, request, jsonify, redirect, session, flash
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
# =====================================================================
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
        flash('로그인 성공!', 'success')  # flash
        return redirect('/')
    
    # 로그인 실패...
    alert_msg = "아이디와 비밀번호를 확인하세요."
    return render_template('login.html', alert_msg=alert_msg)

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
# 🚧 [영역 3]
# =====================================================================
<<<<<<< HEAD
@app.route('/api/user/me', methods=['GET', 'POST']) #마이페이지 정보 수집
def user_me():
    user_id=session.get('username')
    if not user_id:
        return redirect('/api/login')
    
    if request.method == 'GET':
        return render_template('password_confirm.html')
    
=======
@app.route('/mypage', methods=['GET'])
@login_required
def user_me():
    user_id = session.get('username')

    if user_id:
        user_info = db.users.find_one(
            {'username': user_id},
            {'password': 0}
        )
        return render_template('mypage.html', user_info=user_info)
>>>>>>> b23f32c12a311f384b26baa18a9eb796901ffce6
    else:
        password_receive=request.form['password_give']
        user=db.users.find_one({'username':user_id})
        hashed_password=user.get('hashed_password')
        if hashed_password and bcrypt.checkpw(password_receive.encode('uft-8'), hashed_password):
            user_info=db.users.find_one({'username':user_id}, {'hashed_password': 0})
            return render_template('mypage.html', user_info=user_info)
        else:
            return "<script>alert('비밀번호가 일치하지 않습니다.'); history.back();</script>"

<<<<<<< HEAD

@app.route('/api/user/update', methods=['POST']) #정보수정(이름, 반, 기수)
=======
@app.route('/update', methods=['POST'])
>>>>>>> b23f32c12a311f384b26baa18a9eb796901ffce6
def user_update():
    user_id=session.get('username')

    if not user_id:
<<<<<<< HEAD
        return redirect('/api/login')
    
    name=request.form.get('name','').strip()
    class_number=request.form.get('class_number','').strip()
    generation=request.form.get('generation','').strip()
    print(f"DEBUG: '{name}', '{class_number}', '{generation}'")

    if not name or not class_number or not generation:
        return "<script>alert('모든 정보를 올바르게 입력해주세요.'); history.back();</script>"

    db.users.update_one({'username': session['username']}, {'$set': {
        'name':name,
        'class_number':class_number,
        'generation':generation
    }})
    
    return "<script>alert('수정이 완료되었습니다!'); window.location.href='/api/user/me';</script>"
=======
        return redirect('/login')

    name=request.form.get('name','').strip()
    class_number=request.form.get('class_number','').strip()
    generation=request.form.get('generation','').strip()

    print(request.form)
    print("SESSION USER:", user_id)
    print("SESSION:", session)
    
    if not name or not class_number or not generation:
        return "<script>alert('모든 필드를 입력해주세요.'); history.back();</script>"

    result = db.users.update_one(
        {'username': user_id},
        {'$set': {
            'name': name,
            'class_number': class_number,
            'generation': generation
        }}
    )

    print("MATCHED:", result.matched_count)
    print("MODIFIED:", result.modified_count)
    if result.matched_count == 0:
        return "<script>alert('사용자를 찾을 수 없습니다'); location.href='/mypage';</script>"
    return "<script>alert('수정 완료'); location.href='/mypage';</script>"
>>>>>>> b23f32c12a311f384b26baa18a9eb796901ffce6

    
@app.route('/api/user/order', methods=['GET']) #내 주문 정보 수집, 페이지번호는 미구현
def user_order():
    user_id=session.get('username')
    if user_id:
        user_orders=list(db.group_buys.find({'username':user_id}).sort('deadline', 1).limit(10))
        return render_template('myorder.html', user_orders=user_orders)
    else:
        return redirect('/api/login')



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


@app.route('/api/order', methods=['POST'])
def api_add_order():
    # 1. 프론트엔드에서 보낸 데이터 받기
    data = request.get_json()
    group_buy_id = data.get('groupBuyId')
    items = data.get('items', [])

    calculated_total = sum(item.get('price', 0) * item.get('quantity', 0) for item in items)

    if not group_buy_id or not items:
        return jsonify({"result": "fail", "msg": "잘못된 요청입니다."}), 400

    ## TODO. 세션 구현 후 실제 유저로 연결하기
    order_user = db.user.find_one({"name": "잠만보"})
    if not order_user:
        return jsonify({"result": "fail", "msg": "테스트 유저(잠만보)가 없습니다."}), 500

    now = datetime.now()


    new_order = {
        "_id": ObjectId(),  # 이 주문표 자체의 고유 ID (삭제 기능을 위해 필요함!)
        "groupBuyId": ObjectId(group_buy_id),
        "user": {
            "userId": order_user["_id"],
            "name": order_user["name"],
            "class": order_user.get("class", ""),
            "generation": order_user.get("generation", 0)
        },
        "status": "pending",
        "totalAmount": calculated_total,  # 백엔드가 직접 계산한 금액
        "items": items,
        "createdAt": now,
        "updatedAt": now
    }

    # 4. DB 업데이트 (동시성 방어 및 원자성 보장)
    try:
        db.group_buys.update_one(
            {"_id": ObjectId(group_buy_id)},
            {
                # 배열에는 새로운 주문을 쑤셔 넣고($push)
                "$push": {"orders": new_order},
                # 현재 총액에는 방금 계산한 금액을 안전하게 더해라($inc)
                "$inc": {"currentAmount": calculated_total}
            }
        )
    except Exception as e:
        print(f"주문 DB 업데이트 에러: {e}")
        return jsonify({"result": "fail", "msg": "DB 저장 중 오류가 발생했습니다."}), 500

    # 5. 프론트엔드에 성공 신호 보내기 (새로고침을 유도함)
    return jsonify({"result": "success"})

if __name__ == '__main__':
    app.run(debug=True)