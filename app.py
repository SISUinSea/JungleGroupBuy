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
import threading
import time

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

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

GROUPBUY_STATUSES = {
    "open": "모집중",
    "closed": "마감",
    "hidden": "숨김",
    "purchased": "구매완료",
    "delivered": "배송완료",
}
VALID_GROUPBUY_STATUS_SET = set(GROUPBUY_STATUSES.keys())

# SLACK 관련..
def slack_api(method: str, payload: dict):
    if not SLACK_BOT_TOKEN:
        return {"ok": False, "error": "missing_SLACK_BOT_TOKEN"}
    url = f"https://slack.com/api/{method}"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        res = requests.post(url, headers=headers, data=payload, timeout=5)
        return res.json()
    except Exception as e:
        return {"ok": False, "error": f"request_failed: {e}"}

def slack_user_id_by_email(email: str):
    if not email:
        return None
    res = slack_api("users.lookupByEmail", {"email": email})
    if res.get("ok") and res.get("user"):
        return res["user"]["id"]
    return None

def mention(uid: str) -> str:
    return f"<@{uid}>" if uid else ""

# Slack user id lookup 캐시 (이메일 -> uid). 워크스페이스 사용자 많아도 lookupByEmail 호출을 줄이기 위함
_SLACK_UID_CACHE = {}

def slack_uid_by_user_id(user_id: str):
    if not user_id:
        return None
    try:
        u = db.users.find_one({"_id": ObjectId(user_id)}, {"email": 1})
    except Exception:
        return None
    if not u:
        return None
    email = (u.get("email") or "").strip()
    if not email:
        return None
    if email in _SLACK_UID_CACHE:
        return _SLACK_UID_CACHE[email]
    uid = slack_user_id_by_email(email)
    _SLACK_UID_CACHE[email] = uid
    return uid

def groupbuy_member_uids(group_buy_doc: dict):
    uids = []
    # author
    author = (group_buy_doc or {}).get("author") or {}
    author_id = author.get("userId")
    if author_id:
        uids.append(slack_uid_by_user_id(str(author_id)))
    # participants (orders.user.userId)
    for o in (group_buy_doc or {}).get("orders", []) or []:
        uid = slack_uid_by_user_id(str((o.get("user") or {}).get("userId")))
        if uid:
            uids.append(uid)
    # dedupe while preserving order
    seen=set()
    out=[]
    for uid in uids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out

def slack_notify_groupbuy(group_buy_doc: dict, text: str):
    if not SLACK_CHANNEL_ID:
        return {"ok": False, "error": "missing_SLACK_CHANNEL_ID"}

    uids = groupbuy_member_uids(group_buy_doc)
    mentions = " ".join(mention(uid) for uid in uids if uid)
    final_text = f"{text}\n{mentions}".strip()

    return slack_api("chat.postMessage", {"channel": SLACK_CHANNEL_ID, "text": final_text})

def _gb_flag_get(group_buy_doc: dict, key: str):
    return ((group_buy_doc or {}).get("slackFlags") or {}).get(key) is True

def _gb_flag_set(group_buy_id: str, key: str):
    db.group_buys.update_one(
        {"_id": ObjectId(group_buy_id)},
        {"$set": {f"slackFlags.{key}": True, "updatedAt": datetime.now()}}
    )

def _check_and_notify_target_reached(group_buy_id: str):
    gb = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
    if not gb:
        return

    target = gb.get("targetAmount", 0) or 0
    current = gb.get("currentAmount", 0) or 0

    if target <= 0 or current < target:
        return

    # 여기서 "먼저" flag를 원자적으로 선점함.
    # 이미 누가 보냈으면 matched_count=0 이라서 아래 알림이 안 나가도록 수정.
    claim = db.group_buys.update_one(
        {
            "_id": ObjectId(group_buy_id),
            "slackFlags.targetReached": {"$ne": True}
        },
        {
            "$set": {
                "slackFlags.targetReached": True,
                "updatedAt": datetime.now()
            }
        }
    )

    if claim.matched_count == 0:
        return

    # claim 성공한 1건만 여기까지 내려옴
    gb_latest = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
    slack_notify_groupbuy(
        gb_latest or gb,
        f"✅ 목표 금액 달성! (현재 {current:,} / 목표 {target:,}원)\n공구번호: {gb.get('groupBuyNumber')}"
    )
    
def _deadline_job_once():
    now = datetime.now()
    # 모집중(open)이고 deadline <= now 이며 아직 알림 안 간 것
    cursor = db.group_buys.find({
        "status": "open",
        "deadline": {"$lte": now},
        "slackFlags.deadlineReached": {"$ne": True},
    })
    for gb in cursor:
        slack_notify_groupbuy(gb, f"⏰ 마감일이 되었습니다.\n공구번호: {gb.get('groupBuyNumber')}")
        _gb_flag_set(str(gb["_id"]), "deadlineReached")

def start_deadline_watcher():
    def _loop():
        while True:
            try:
                _deadline_job_once()
            except Exception as e:
                print("deadline watcher error:", e)
            time.sleep(60)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
###

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def get_logged_in_user_doc():
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


    if user:
        is_duplicate = True
    else:
        is_duplicate = False
    
    return jsonify({
        "isDuplicate": is_duplicate
    })

@app.route('/group-buy/<groupbuyid>/delete', methods=['POST'])
def groupBy_delete(groupbuyid):
    result = db.group_buys.find_one({'_id': ObjectId(groupbuyid)})

    if result is None:
        return jsonify({"result":"fail", "message": "공동주문 글을 찾을 수 없습니다."}), 404

    current_user_id = session.get("user_id")
    author_id = str(result["author"]["userId"])

    if author_id != current_user_id:
        return jsonify({"result":"fail","message":"작성자만 삭제할 수 있습니다."})

    orders = result["orders"]

    if any(str(order["user"]["userId"]) != author_id for order in orders):
        return jsonify({"result":"fail","message":"본인 이외에 참여자가 있는 공동주문 글은 삭제 할 수 없습니다."})

    status = result["status"]
    if result["status"] != "open":
        return jsonify({"result":"fail","message":"모집 이후 단계에서는 공동주문 글을 삭제 할 수 없습니다."})

    db.group_buys.delete_one({'_id': ObjectId(groupbuyid)})
    return jsonify({'result': 'success'})



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
        _check_and_notify_target_reached(group_buy_id)
    else:
        return jsonify({"result": "fail", "msg": "잘못된 상태"})

    return jsonify({"result": "success"})

# =====================================================================
# ✅ SLACK TEST API (슬랙 봇 토큰, 채널 ID 설정 후 테스트용으로 활용)
# =====================================================================
@app.route("/api/slack/test/auth", methods=["GET"])
def slack_test_auth():
    res = slack_api("auth.test", {})
    return jsonify(res), (200 if res.get("ok") else 400)

@app.route("/api/slack/test/lookup", methods=["POST"])
def slack_test_lookup():
    """
    테스트 1) 이메일 -> Slack User ID 조회가 되는지 확인
    Body: { "email": "someone@company.com" }
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()

    uid = slack_user_id_by_email(email)
    if not uid:
        return jsonify({
            "ok": False,
            "msg": "lookup failed",
            "email": email,
            "detail": "Check users:read.email scope, email exists in workspace, token valid"
        }), 400

    return jsonify({
        "ok": True,
        "email": email,
        "user_id": uid,
        "mention": mention(uid)
    })
    
# test용
@app.route("/api/slack/test/users", methods=["GET"])
def slack_test_users():
    res = slack_api("users.list", {})
    return jsonify(res), (200 if res.get("ok") else 400)

@app.route("/api/slack/test/post", methods=["POST"])
def slack_test_post():
    """
    테스트 2) 채널로 메시지 전송 + 멘션이 실제로 울리는지 확인
    Body 예:
    {
      "text": "테스트 메시지입니다",
      "mention_user_id": "U0123456789"   // optional
    }
    또는
    {
      "text": "테스트 메시지입니다",
      "mention_email": "someone@company.com"  // optional (lookup 후 멘션)
    }
    """
    if not SLACK_CHANNEL_ID:
        return jsonify({"ok": False, "error": "missing_SLACK_CHANNEL_ID"}), 400

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "Slack test from Flask").strip()

    mention_user_id = (data.get("mention_user_id") or "").strip()
    mention_email = (data.get("mention_email") or "").strip()

    uid = None
    if mention_user_id:
        uid = mention_user_id
    elif mention_email:
        uid = slack_user_id_by_email(mention_email)

    final_text = text
    if uid:
        final_text += f"\n{mention(uid)}"

    res = slack_api("chat.postMessage", {
        "channel": SLACK_CHANNEL_ID,
        "text": final_text
    })

    # Slack 응답 그대로 반환(디버깅 편하게)
    status = 200 if res.get("ok") else 400
    return jsonify(res), status

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
    data = request.get_json(silent=True) or {}

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

    old_status = group_buy.get("status")

    if not is_author_of_groupbuy(group_buy, user_doc):
        return jsonify({"result": "fail", "msg": "작성자만 상태 변경이 가능합니다."}), 403

    # 상태 업데이트
    db.group_buys.update_one(
        {"_id": ObjectId(group_buy_id)},
        {"$set": {"status": new_status, "updatedAt": datetime.now()}}
    )

    # ✅ 상태 변경 알림: 공구 관련자만 멘션, 공구당/상태당 1회
    if old_status != new_status:
        flag_key = f"status_{new_status}"
        if new_status in ("closed", "purchased", "delivered") and not _gb_flag_get(group_buy, flag_key):
            status_label = GROUPBUY_STATUSES.get(new_status, new_status)
            gb_latest = db.group_buys.find_one({"_id": ObjectId(group_buy_id)})
            slack_notify_groupbuy(
                gb_latest or group_buy,
                f"📌 공구 상태 변경: {status_label}\n공구번호: {group_buy.get('groupBuyNumber')}"
            )
            _gb_flag_set(group_buy_id, flag_key)

    return jsonify({
        "result": "success",
        "status": new_status,
        "statusLabel": GROUPBUY_STATUSES[new_status]
    })
    
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
        if target_order["status"] == "confirmed":
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
    # debug reloader 때문에 2번 실행되는 거 방지
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        start_deadline_watcher()
    app.run(host='0.0.0.0', port=5001)