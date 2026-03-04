from flask import Flask, render_template, request, jsonify, redirect, session
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = 'jungle'
client = MongoClient('mongodb+srv://jungle_for_all:1234@junglegroupbuy.vvvtwuf.mongodb.net/?appName=jungleGroupBuy', tlsAllowInvalidCertificates=True)
db = client.jungle_groupbuy

# =====================================================================
# 🚧 [영역 1]
# =====================================================================


# =====================================================================
# 🚧 [영역 2]
# =====================================================================




# =====================================================================
# 🚧 [영역 3]
@app.route('/api/user/me', methods=['GET']) #마이페이지 정보 수집
def user_me():
    session['username']='test_user'
    user_id=session.get('username')
    if user_id:
        user_info=db.user.find_one({'username':user_id}, {'hashed_pw':0})
        return render_template('mypage.html', user_info=user_info)
    else:
        return redirect('/api/login')
    
@app.route('/api/user/order', methods=['GET']) #내 주문 정보 수집, 페이지번호는 미구현
def user_order():
    user_id=session.get('username')
    if user_id:
        user_orders=list(db.group_buys.find({'username':user_id}).sort('deadline', 1).limit(10))
        return render_template('.html', user_orders=user_orders)
    else:
        return redirect('/api/login')

#마이페이지 정보 수정 반영
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
