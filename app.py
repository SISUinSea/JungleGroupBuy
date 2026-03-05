import pymongo
from flask import Flask, render_template, request, jsonify, redirect, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt # 비밀번호 암호화 라이브러리
from functools import wraps     # 로그인 상태 체크 데코레이터
import re

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
        password_check = request.form['password_check']
        name = request.form['name']
        email = request.form['slack_email']
        generation = request.form['generation']
        class_number = request.form['class_number']
        createdAt = datetime.now()

        # 비밀번호 암호화
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # 서버 측 유효성 검증 규칙
        strong_pw_pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*])[a-zA-Z0-9!@#$%^&*]{8,20}$'
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        # 1. 누락 값 확인
        if not all([username, password, name, email, generation, class_number]):
            return "<script>alert('모든 항목을 입력해주세요.'); history.back();</script>"

        # 2. 아이디 형식 확인
        if not re.match(r'^[a-zA-Z0-9_]{4,12}$', username):
            return "<script>alert('아이디 형식이 올바르지 않습니다.'); history.back();</script>"

        # 3. 비밀번호 강도 확인
        if not re.match(strong_pw_pattern, password):
            return "<script>alert('비밀번호가 보안 규칙에 맞지 않습니다.'); history.back();</script>"
        if password != password_check:
            return "<script>alert('비밀번호가 일치하지 않습니다.'); history.back();</script>"

        if not re.match(r'^.{2,30}$', name):
            return "<script>alert('이름은 2-30자 이내여야 합니다.'); history.back();</script>"

        # 4. 이메일 형식 확인
        if not re.match(email_pattern, email):
            return "<script>alert('이메일 형식이 올바르지 않습니다.'); history.back();</script>"

        # 5. DB 중복 최종 확인
        if db.users.find_one({'username': username}):
            return "<script>alert('이미 존재하는 아이디입니다.'); history.back();</script>"

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
        return "<script>alert('회원가입이 완료되었습니다!'); location.href='/login';</script>"

@app.route('/signup/username_duplicate_check', methods=['POST'])
def username_duplicate_check():
    data = request.get_json()
    requested_username = data.get('username')

    user = db.users.find_one({'username': requested_username})

    if user:
        is_duplicate = True
    else:
        is_duplicate = False
    
    return jsonify({
        "isDuplicate": is_duplicate
    })


     

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
@app.route('/mypage', methods=['GET', 'POST']) # 1. POST 추가
@login_required
def user_me():
    user_id = session.get('username')
    if not user_id:
        return redirect('/login')

    # 처음 접속했을 때 (GET): 비밀번호 입력창 보여주기
    if request.method == 'GET':
        user_info = db.users.find_one({'username': user_id}, {'password': 0})
        return render_template('password_confirm.html', user_info=user_info)

    # 비밀번호 입력 후 [확인] 눌렀을 때 (POST): 비밀번호 검증
    else:
        password_receive = request.form['password_give']
        user = db.users.find_one({'username': user_id})
        db_password = user.get('password')

        if db_password and bcrypt.check_password_hash(db_password, password_receive):
            user_info = db.users.find_one({'username': user_id}, {'password': 0})
            return render_template('mypage.html', user_info=user_info)
        else:
            return "<script>alert('비밀번호가 일치하지 않습니다.'); history.back();</script>"

@app.route('/update', methods=['POST']) #내정보 수정(이름, 반, 기수)
def user_update():
    user_id=session.get('username')

    if not user_id:
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
    
@app.route('/update/password', methods=['POST']) #비밀번호 변경
def update_password():
    user_id=session.get('username')
    if not user_id:
        return redirect('/login')
    
    new_password=request.form.get('new_password','').strip()
    new_password_confirm=request.form.get('new_password_confirm','').strip()

    if not new_password or not new_password_confirm:
        return "<script>alert('모든 비밀번호 필드를 입력해주세요.'); history.back();</script>"
    
    if new_password != new_password_confirm:
        return "<script>alert('비밀번호가 서로 일치하지 않습니다.'); history.back();</script>"
    
    hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.users.update_one(
        {'username': user_id},
        {'$set': {'password': hashed_new_password}}
    )

    return "<script>alert('비밀번호가 성공적으로 변경되었습니다.'); location.href='/mypage';</script>"
    

@app.route('/api/user/order', methods=['GET']) #나의 주문
def user_order():
    user_id = session.get('username')
    if not user_id:
        return redirect('/api/login')

    # 💡 수정 포인트: 'username' -> 'orders.user.username'
    # '내가 방장인 것' + '내가 주문자로 참여한 것' 모두 보고 싶다면 $or를 씁니다.
    query = {
        '$or': [
            {'name': user_id},             # 내가 방장인 경우
            {'orders.user.name': user_id}  # 내가 주문자로 참여한 경우
        ]
    }

    # 조건에 맞는 공동구매 목록을 마감일 순으로 10개 가져오기
    user_orders = list(db.group_buys.find(query).sort('deadline', 1).limit(10))

    return render_template('myorder.html', user_orders=user_orders)

@app.route('/api/my/order', methods=['GET']) #나의 주문 목록
@login_required
def my_order():
    user_id = session.get('username')

    # orders 배열 내부의 user.username이 나인 게시글을 전부 찾습니다.
    # 내가 주문을 1개를 했든 5개를 했든, 해당 '게시글'이 결과로 나옵니다.
    my_orders = list(db.groupbuys.find(
        {'orders.user.name': user_id}, 
        {'_id': 0}
    ))

    # 중복 제거가 필요할 수도 있지만, find 쿼리 자체가 해당 문서(document)를 찾는 거라 
    # 한 게시글에 내 주문이 여러 개 있어도 게시글은 한 번만 나옵니다.
    return render_template('myorder.html', items=my_orders)


# =====================================================================
# 🚧 [영역 4]
# =====================================================================

@app.route('/', methods=['GET'])
def getGroupBuyList():
    result_list = list(db.group_buys.find({}).sort("createdAt", pymongo.DESCENDING))
    current_user_id = session.get('user_id')

    for group in result_list:
        group['is_author'] = current_user_id == str(group['author']["userId"])
        group['is_participant'] = any(order['user']['userId'] == current_user_id for order in group['orders'])


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




# productId를 제공하면 상품명, 가격을 반환합니다.
import requests

app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False
@app.route('/api/product-detail/<productId>', methods=['GET'])
def getProductDetail(productId):
    productInfo = db.productInfo.find_one({'productId': productId})
    productInfo.pop('_id', None)
    if productInfo and datetime.now() <= productInfo.get('ttl', datetime.min):
        print("cached data is used!!!", productInfo.get("productName"))
        productInfo['ttl'] = productInfo['ttl'].isoformat()
        return jsonify(productInfo)
    else:
        print("cache expired.... new request")

    headers = {
        'authority': 'fapi.daisomall.co.kr',
        'method': 'POST',
        'path': '/pd/pdr/pdDtl/selPdDtlInfo',
        'scheme': 'https',
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'ko-KR,ko;q=0.9',
        'content-type': 'application/json',
        'cookie': 'grb_ck@cefe24f9=681bc0ff-0d4b-c8fe-8c98-23d52784994cd4; grb_recent_member_id@cefe24f9=2000155318; grb_ui@cefe24f9=9eeec5f8-6374-c375-f2ab-bdf4381d9c50; DM_DVC=81f79da2-ef4f-42f6-82e7-58fa554c3aee; grb_id_permission@cefe24f9=fail; grb_ip_permission@cefe24f9=fail',
        'origin': 'https://www.daisomall.co.kr',
        'priority': 'u=1, i',
        'referer': 'https://www.daisomall.co.kr/',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Brave";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'
    }
    payload = {"pdNo": productId}
    try:
        response = requests.post(
            "https://fapi.daisomall.co.kr/pd/pdr/pdDtl/selPdDtlInfo",
            headers=headers,
            json=payload,
            timeout=5
        )

        response.raise_for_status()
        result_json = response.json()


        data = result_json.get('data', {})

        product_info = {
            "productId": data.get('pdNo'),
            "productName": data.get('exhPdNm') or data.get('pdNm'),
            "price": data.get('pdPrc'),
            "imageUrl": f"https://www.daisomall.co.kr{data.get('imgUrl')}" if data.get('imgUrl') else None,
            "status": "success",
            "ttl": datetime.now() + timedelta(hours=24)
        }

        # 없으면 새로 만들되 있으면 기존의 productId에 덮어쓰기!!
        db.productInfo.update_one(
            {"productId": productId},
            {"$set": product_info}, upsert=True)


        product_info['ttl'] = product_info['ttl'].isoformat()
        return jsonify(product_info)

    except Exception as e:
        print(f"에러 발생 원인: {e}")
        return jsonify({"result": "fail", "msg": str(e)}), 500


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
    app.run(port = 5001, debug=True)