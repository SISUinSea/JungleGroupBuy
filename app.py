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

# 주문 상태 업데이트 API (입금 대기 -> 입금 확인 -> 입금 완료)
@app.route('/api/order/status', methods=['POST'])
def update_order_status():

    data = request.get_json()

    group_buy_id = data.get("groupBuyId")
    order_id = data.get("orderId")
    new_status = data.get("status")

    user_id = session.get("username")

    if not user_id:
        return jsonify({"result":"fail","msg":"로그인이 필요합니다."})

    group_buy = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})

    if not group_buy:
        return jsonify({"result":"fail","msg":"게시글 없음"})

    order = None
    for o in group_buy["orders"]:
        if str(o["_id"]) == order_id:
            order = o
            break

    if not order:
        return jsonify({"result":"fail","msg":"주문 없음"})

    # 유저 찾기
    user = db.users.find_one({"username": user_id})

    if not user:
        return jsonify({"result":"fail","msg":"유저 없음"})

    # -------- 권한 체크 --------

    # 참여자가 입금 완료시.. (입금 대기 -> 작성자 입금 완료)
    if new_status == "paid":

        if str(order["user"]["userId"]) != str(user["_id"]):
            return jsonify({"result":"fail","msg":"본인 주문만 변경 가능"})

        db.group_buys.update_one(
            {
                "_id": ObjectId(group_buy_id),
                "orders._id": ObjectId(order_id)
            },
            {
                "$set":{
                    "orders.$.status":"paid",
                    "orders.$.updatedAt":datetime.now()
                }
            }
        )

    # 작성자가 입금 확인시.. (입금 완료 -> 게시자 입금 확인)
    elif new_status == "confirmed":

        if str(group_buy["author"]["userId"]) != str(user["_id"]):
            return jsonify({"result":"fail","msg":"작성자만 확인 가능"})

        db.group_buys.update_one(
            {
                "_id": ObjectId(group_buy_id),
                "orders._id": ObjectId(order_id)
            },
            {
                "$set":{
                    "orders.$.status":"confirmed",
                    "orders.$.updatedAt":datetime.now()
                },
                "$inc":{
                    "currentAmount": order["totalAmount"]
                }
            }
        )

    else:
        return jsonify({"result":"fail","msg":"잘못된 상태"})

    return jsonify({"result":"success"})

# =====================================================================
# 🚧 [영역 3]
# =====================================================================


    
# @app.route('/api/user/order', methods=['GET']) #내 주문 정보 수집, 페이지번호는 미구현
# def user_order():
#     user_id=session.get('username')
#     if user_id:
#         user_orders=list(db.group_buys.find({'username':user_id}).sort('deadline', 1).limit(10))
#         return render_template('myorder.html', user_orders=user_orders)
#     else:
#         return redirect('/api/login')



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

    current_user_id = session.get("user_id")

    # ObjectId → string 변환
    # 게시자, 참여자 구분용 입니다.. 이거 없으면 구분을 못해서 누구나 입금 확인 할 수 있어요..ㅜㅜ
    if result.get("author"):
        result["author"]["userId"] = str(result["author"]["userId"])

    for order in result.get("orders", []):
        order["user"]["userId"] = str(order["user"]["userId"])

    return render_template(
        'groupBuyDetail.html',
        product=result,
        current_user_id=current_user_id
    )

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


    author_user = db.users.find_one({"_id": ObjectId(session['user_id'])})

    if not author_user:
        return jsonify({"result": "fail", "msg": "유저가 DB에 없습니다."}), 500

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

    order_user = db.users.find_one({"_id": ObjectId(session['user_id'])})
    if not order_user:
        return jsonify({"result": "fail", "msg": "유저가 없습니다."}), 500

    now = datetime.now()


    new_order = {
        "_id": ObjectId(),  # 이 주문표 자체의 고유 ID (삭제 기능을 위해 필요함!)
        "groupBuyId": ObjectId(group_buy_id),
        "user": {
            "userId": order_user["_id"],
            "name": order_user["name"],
            "class": order_user.get("class_number", ""),
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
                # # 현재 총액에는 방금 계산한 금액을 안전하게 더해라($inc)
                # "$inc": {"currentAmount": calculated_total}
            }
        )
    except Exception as e:
        print(f"주문 DB 업데이트 에러: {e}")
        return jsonify({"result": "fail", "msg": "DB 저장 중 오류가 발생했습니다."}), 500

    # 5. 프론트엔드에 성공 신호 보내기 (새로고침을 유도함)
    return jsonify({"result": "success"})

if __name__ == '__main__':
    app.run(debug=True)