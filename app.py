from dotenv import load_dotenv  # .env 파일에서 환경변수 로드 (시크릿 키 등)
load_dotenv()

import pymongo
from flask import Flask, render_template, request, jsonify, redirect, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt  # 비밀번호 암호화 라이브러리
from functools import wraps      # 로그인 상태 체크 데코레이터
import re
import requests
import os

app = Flask(__name__)
app.secret_key = 'jungle'
client = MongoClient(
    'mongodb+srv://jungle_for_all:1234@junglegroupbuy.vvvtwuf.mongodb.net/?appName=jungleGroupBuy',
    tlsAllowInvalidCertificates=True
)
db = client.jungle_groupbuy

bcrypt = Bcrypt(app)

app.config['JSON_AS_ASCII'] = False
app.json.ensure_ascii = False

# =========================
# 공통 유틸
# =========================

GROUPBUY_STATUSES = {
    "open": "모집중",
    "closed": "마감",
    "hidden": "숨김",
    "purchased": "구매완료",
    "delivered": "배송완료",
}
VALID_GROUPBUY_STATUS_SET = set(GROUPBUY_STATUSES.keys())


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def get_logged_in_user_doc():
    """현재 로그인한 유저 문서(users)를 반환 (없으면 None)"""
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def is_author_of_groupbuy(group_buy_doc, user_doc):
    if not group_buy_doc or not user_doc:
        return False
    author = group_buy_doc.get("author", {})
    return str(author.get("userId")) == str(user_doc.get("_id"))


# =====================================================================
# 🚧 [영역 1] 회원가입
# =====================================================================
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

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        strong_pw_pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*])[a-zA-Z0-9!@#$%^&*]{8,20}$'
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if not all([username, password, name, email, generation, class_number]):
            return "<script>alert('모든 항목을 입력해주세요.'); history.back();</script>"

        if not re.match(r'^[a-zA-Z0-9_]{4,12}$', username):
            return "<script>alert('아이디 형식이 올바르지 않습니다.'); history.back();</script>"

        if not re.match(strong_pw_pattern, password):
            return "<script>alert('비밀번호가 보안 규칙에 맞지 않습니다.'); history.back();</script>"
        if password != password_check:
            return "<script>alert('비밀번호가 일치하지 않습니다.'); history.back();</script>"

        if not re.match(r'^.{2,30}$', name):
            return "<script>alert('이름은 2-30자 이내여야 합니다.'); history.back();</script>"

        if not re.match(email_pattern, email):
            return "<script>alert('이메일 형식이 올바르지 않습니다.'); history.back();</script>"

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
    return jsonify({"isDuplicate": True if user else False})


# =====================================================================
# 🚧 [영역 2] 로그인/로그아웃
# =====================================================================
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    user = db.users.find_one({'username': username})

    if user and bcrypt.check_password_hash(user['password'], password):
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        flash('로그인 성공!', 'success')
        return redirect('/')

    alert_msg = "아이디와 비밀번호를 확인하세요."
    return render_template('login.html', alert_msg=alert_msg)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# =====================================================================
# ✅ 주문 상태 업데이트 API (입금 대기 -> 입금 완료 -> 입금 확인)
# =====================================================================
@app.route('/api/order/status', methods=['POST'])
def update_order_status():
    data = request.get_json()

    group_buy_id = data.get("groupBuyId")
    order_id = data.get("orderId")
    new_status = data.get("status")

    # 로그인 체크
    user_doc = get_logged_in_user_doc()
    if not user_doc:
        return jsonify({"result": "fail", "msg": "로그인이 필요합니다."})

    group_buy = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
    if not group_buy:
        return jsonify({"result": "fail", "msg": "게시글 없음"})

    # 주문 찾기
    order = None
    for o in group_buy.get("orders", []):
        if str(o["_id"]) == str(order_id):
            order = o
            break

    if not order:
        return jsonify({"result": "fail", "msg": "주문 없음"})

    # -------- 권한/로직 체크 --------
    if new_status == "paid":
        # 참여자가 본인 주문만 입금완료로 변경 가능
        if str(order["user"]["userId"]) != str(user_doc["_id"]):
            return jsonify({"result": "fail", "msg": "본인 주문만 변경 가능"})

        db.group_buys.update_one(
            {"_id": ObjectId(group_buy_id), "orders._id": ObjectId(order_id)},
            {"$set": {"orders.$.status": "paid", "orders.$.updatedAt": datetime.now()}}
        )

    elif new_status == "confirmed":
        # 작성자만 입금확인 가능
        if not is_author_of_groupbuy(group_buy, user_doc):
            return jsonify({"result": "fail", "msg": "작성자만 확인 가능"})

        db.group_buys.update_one(
            {"_id": ObjectId(group_buy_id), "orders._id": ObjectId(order_id)},
            {
                "$set": {"orders.$.status": "confirmed", "orders.$.updatedAt": datetime.now()},
                "$inc": {"currentAmount": order["totalAmount"]}
            }
        )
    else:
        return jsonify({"result": "fail", "msg": "잘못된 상태"})

    return jsonify({"result": "success"})


# =====================================================================
# 🚧 [영역 3] 마이페이지
# =====================================================================
@app.route('/mypage', methods=['GET', 'POST'])
@login_required
def user_me():
    user_id = session.get('username')
    if not user_id:
        return redirect('/login')

    if request.method == 'GET':
        user_info = db.users.find_one({'username': user_id}, {'password': 0})
        return render_template('password_confirm.html', user_info=user_info)
    else:
        password_receive = request.form['password_give']
        user = db.users.find_one({'username': user_id})
        db_password = user.get('password')

        if db_password and bcrypt.check_password_hash(db_password, password_receive):
            user_info = db.users.find_one({'username': user_id}, {'password': 0})
            return render_template('mypage.html', user_info=user_info)
        else:
            return "<script>alert('비밀번호가 일치하지 않습니다.'); history.back();</script>"


@app.route('/update', methods=['POST'])
def user_update():
    user_id = session.get('username')
    if not user_id:
        return redirect('/login')

    name = request.form.get('name', '').strip()
    class_number = request.form.get('class_number', '').strip()
    generation = request.form.get('generation', '').strip()

    if not name or not class_number or not generation:
        return "<script>alert('모든 필드를 입력해주세요.'); history.back();</script>"

    result = db.users.update_one(
        {'username': user_id},
        {'$set': {'name': name, 'class_number': class_number, 'generation': generation}}
    )

    if result.matched_count == 0:
        return "<script>alert('사용자를 찾을 수 없습니다'); location.href='/mypage';</script>"
    return "<script>alert('수정 완료'); location.href='/mypage';</script>"


@app.route('/update/password', methods=['POST'])
def update_password():
    user_id = session.get('username')
    if not user_id:
        return redirect('/login')

    new_password = request.form.get('new_password', '').strip()
    new_password_confirm = request.form.get('new_password_confirm', '').strip()

    if not new_password or not new_password_confirm:
        return "<script>alert('모든 비밀번호 필드를 입력해주세요.'); history.back();</script>"

    if new_password != new_password_confirm:
        return "<script>alert('비밀번호가 서로 일치하지 않습니다.'); history.back();</script>"

    hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.users.update_one({'username': user_id}, {'$set': {'password': hashed_new_password}})

    return "<script>alert('비밀번호가 성공적으로 변경되었습니다.'); location.href='/mypage';</script>"

@app.route('/api/user/order', methods=['GET']) #나의 주문
@login_required
def my_order_list():
    # 1. 세션에서 아이디(username) 가져오기
    user_id = session.get('username')

    # 2. DB에서 내 진짜 '이름(name)' 찾아오기 (매칭을 위해 필수!)
    user_info = db.users.find_one({'username': user_id})
    if not user_info:
        return redirect('/api/login')

    real_name = user_info.get('name')

    # 3. 쿼리 설정: (내가 방장인 아이디) OR (참여자 명단에 내 실명)
    # 컬렉션 이름 'group_buys' 확인 완료!
    query = {
        '$or': [
            {'username': user_id},             # 내가 만든 공구
            {'orders.user.name': real_name}    # 내가 참여한 공구
        ]
    }

    # 4. 데이터 가져오기 (마감일 순)
    my_orders = list(db.group_buys.find(query).sort('deadline', 1))
    # 5. HTML의 {% for item in items %} 에 맞춰 'items'로 전달
    return render_template('myorder.html', items=my_orders)


# =====================================================================
# 🚧 [영역 4] 공동구매 목록/상세/생성
# =====================================================================
@app.route('/', methods=['GET'])
def getGroupBuyList():
    result_list = list(db.group_buys.find({}).sort("createdAt", pymongo.DESCENDING))
    current_user_id = session.get('user_id')

    for group in result_list:
        group['is_author'] = current_user_id == str(group['author']["userId"])
        group['is_participant'] = any(order['user']['userId'] == current_user_id for order in group.get('orders', []))

        # 상태명도 같이 만들어두면 템플릿에서 편함 (없어도 무방)
        group['statusLabel'] = GROUPBUY_STATUSES.get(group.get("status", ""), group.get("status", ""))

    return render_template('groupBuyList.html', items=result_list)


@app.route('/group-buy/<groupbuyid>', methods=['GET'])
def getGroupBuy(groupbuyid):
    result = db.group_buys.find_one({'_id': ObjectId(groupbuyid)})
    if result is None:
        return "게시글을 찾을 수 없습니다.", 404

    current_user_id = session.get("user_id")

    # ObjectId → string 변환 (템플릿에서 비교용)
    if result.get("author"):
        result["author"]["userId"] = str(result["author"]["userId"])

    for order in result.get("orders", []):
        order["user"]["userId"] = str(order["user"]["userId"])

    # 작성자 여부/상태 라벨
    is_author = (current_user_id == result["author"]["userId"]) if current_user_id else False
    status_label = GROUPBUY_STATUSES.get(result.get("status", ""), result.get("status", ""))

    return render_template(
        'groupBuyDetail.html',
        product=result,
        current_user_id=current_user_id,
        is_author=is_author,
        status_label=status_label,
        status_map=GROUPBUY_STATUSES
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

    if 'user_id' not in session:
        return jsonify({"result": "fail", "msg": "로그인이 필요합니다."}), 401

    author_user = db.users.find_one({"_id": ObjectId(session['user_id'])})
    if not author_user:
        return jsonify({"result": "fail", "msg": "유저가 DB에 없습니다."}), 500

    now = datetime.now()
    new_group_buy = {
        "groupBuyNumber": now.strftime("%Y%m%d%H%M%S"),
        "author": {
            "userId": author_user["_id"],
            "name": author_user["name"],
            "class": author_user.get("class", ""),
            "generation": author_user.get("generation", 0)
        },
        "targetAmount": 30000,
        "currentAmount": total_amount,
        "deadline": deadline_date,
        "status": "open",  # ✅ 기본은 모집중
        "openChatUrl": open_chat_url,
        "createdAt": now,
        "updatedAt": now,
        "orders": orders
    }

    result = db.group_buys.insert_one(new_group_buy)
    return jsonify({"result": "success", "inserted_id": str(result.inserted_id)})


# =====================================================================
# ✅ 게시글 상태 변경 API (작성자만)
# - 모집중(open), 마감(closed), 숨김(hidden), 구매완료(purchased), 배송완료(delivered)
# =====================================================================
@app.route('/api/group-buy/status', methods=['POST'])
def api_update_group_buy_status():
    data = request.get_json()

    group_buy_id = data.get("groupBuyId")
    new_status = data.get("status")

    if not group_buy_id or not new_status:
        return jsonify({"result": "fail", "msg": "잘못된 요청입니다."}), 400

    if new_status not in VALID_GROUPBUY_STATUS_SET:
        return jsonify({"result": "fail", "msg": "허용되지 않은 상태값입니다."}), 400

    user_doc = get_logged_in_user_doc()
    if not user_doc:
        return jsonify({"result": "fail", "msg": "로그인이 필요합니다."}), 401

    group_buy = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
    if not group_buy:
        return jsonify({"result": "fail", "msg": "게시글 없음"}), 404

    if not is_author_of_groupbuy(group_buy, user_doc):
        return jsonify({"result": "fail", "msg": "작성자만 상태 변경이 가능합니다."}), 403

    db.group_buys.update_one(
        {"_id": ObjectId(group_buy_id)},
        {"$set": {"status": new_status, "updatedAt": datetime.now()}}
    )

    return jsonify({"result": "success", "status": new_status, "statusLabel": GROUPBUY_STATUSES[new_status]})


# =====================================================================
# productId를 제공하면 상품명, 가격을 반환합니다.
# =====================================================================
@app.route('/api/product-detail/<productId>', methods=['GET'])
def getProductDetail(productId):
    productInfo = db.productInfo.find_one({'productId': productId})
    if productInfo and datetime.now() <= productInfo.get('ttl', datetime.min):
        productInfo.pop('_id', None)
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

        db.productInfo.update_one(
            {"productId": productId},
            {"$set": product_info},
            upsert=True
        )

        product_info['ttl'] = product_info['ttl'].isoformat()
        return jsonify(product_info)

    except Exception as e:
        print(f"에러 발생 원인: {e}")
        return jsonify({"result": "fail", "msg": str(e)}), 500


# =====================================================================
# ✅ 주문 추가 API
# - 모집중(open)일 때만 주문 가능 (서버에서 강제 차단)
# =====================================================================
@app.route('/api/order', methods=['POST'])
def api_add_order():
    data = request.get_json()
    group_buy_id = data.get('groupBuyId')
    items = data.get('items', [])

    if not group_buy_id or not items:
        return jsonify({"result": "fail", "msg": "잘못된 요청입니다."}), 400

    # 로그인 체크
    if 'user_id' not in session:
        return jsonify({"result": "fail", "msg": "로그인이 필요합니다."}), 401

    # ✅ 게시글 상태 체크 (모집중만 주문 가능)
    group_buy = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
    if not group_buy:
        return jsonify({"result": "fail", "msg": "게시글이 없습니다."}), 404

    if group_buy.get("status") != "open":
        status_label = GROUPBUY_STATUSES.get(group_buy.get("status", ""), group_buy.get("status", ""))
        return jsonify({"result": "fail", "msg": f"현재 상태({status_label})에서는 신청/주문이 불가능합니다."}), 403

    calculated_total = sum(item.get('price', 0) * item.get('quantity', 0) for item in items)

    order_user = db.users.find_one({"_id": ObjectId(session['user_id'])})
    if not order_user:
        return jsonify({"result": "fail", "msg": "유저가 없습니다."}), 500

    now = datetime.now()

    new_order = {
        "_id": ObjectId(),
        "groupBuyId": ObjectId(group_buy_id),
        "user": {
            "userId": order_user["_id"],
            "name": order_user["name"],
            "class": order_user.get("class_number", ""),
            "generation": order_user.get("generation", 0)
        },
        "status": "pending",
        "totalAmount": calculated_total,
        "items": items,
        "createdAt": now,
        "updatedAt": now
    }

    try:
        db.group_buys.update_one(
            {"_id": ObjectId(group_buy_id)},
            {"$push": {"orders": new_order}}
        )
    except Exception as e:
        print(f"주문 DB 업데이트 에러: {e}")
        return jsonify({"result": "fail", "msg": "DB 저장 중 오류가 발생했습니다."}), 500

    return jsonify({"result": "success"})


@app.route('/api/group-buy/<group_buy_id>/order/<order_id>', methods=['DELETE'])
def api_delete_order(group_buy_id, order_id):
    try:
        # 해당 공동구매 글 조회
        group_buy = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
        if not group_buy:
            return jsonify({"result": "fail", "msg": "존재하지 않는 공동주문입니다."}), 404

        # 삭제할 주문 찾기 (배열 순회)
        target_order = None
        for o in group_buy.get("orders", []):
            if str(o.get("_id")) == order_id:
                target_order = o
                break

        if not target_order:
            return jsonify({"result": "fail", "msg": "삭제할 주문을 찾을 수 없습니다."}), 404

        # 권한 검증 (주문자 본인 || 방장)
        current_user_id = session.get('user_id')
        if not current_user_id:
            return jsonify({"result": "fail", "msg": "로그인이 필요합니다."}), 401

        order_user_id = str(target_order["user"]["userId"])
        author_id = str(group_buy["author"]["userId"])

        # 본인도 아니고 방장도 아니라면 거부
        if current_user_id != order_user_id and current_user_id != author_id:
            return jsonify({"result": "fail", "msg": "주문을 삭제할 권한이 없습니다."}), 403


        # 금액이 포함된 경우에는 그 금액도 빼야함
        if target_order["status"] != "pending":
            amount_to_subtract = -target_order["totalAmount"]

            db.group_buys.update_one(
                {"_id": ObjectId(group_buy_id)},
                {
                    "$pull": {"orders": {"_id": ObjectId(order_id)}},
                    "$inc": {"currentAmount": amount_to_subtract}
                }
            )
        db.group_buys.update_one({"_id": ObjectId(group_buy_id)},
                {
                    "$pull": {"orders": {"_id": ObjectId(order_id)}}
                })
        return jsonify({"result": "success", "msg": "주문이 정상적으로 삭제되었습니다."})

    except Exception as e:
        print(f"주문 삭제 중 서버 에러: {e}")
        return jsonify({"result": "fail", "msg": "서버 내부 에러가 발생했습니다."}), 500


if __name__ == '__main__':
    app.run(port=5001, debug=True)