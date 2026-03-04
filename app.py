from flask import Flask, render_template, request, jsonify, redirect, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'jungle'
client = MongoClient('mongodb+srv://jungle_for_all:1234@junglegroupbuy.vvvtwuf.mongodb.net/?appName=jungleGroupBuy', tlsAllowInvalidCertificates=True)
db = client.jungle_groupbuy

# =====================================================================
# 🚧 [영역 1]
# =====================================================================
@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    password = request.form['password']
    name = request.form['name']
    email = request.form['slack_email']
    generation = request.form['generation']
    class_number = request.form['class_number']
    createdAt = datetime.now()

    user_info = {'username': username, 'password': password, 'name': name, 'email': email, 'generation': generation, 'class_number': class_number, 'createdAt': createdAt}
    db.users.insert_one(user_info)

    return redirect('/login')

# =====================================================================
# 🚧 [영역 2]
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
