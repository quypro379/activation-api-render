from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

@app.route('/activate', methods=['POST'])
def activate_key():
    data = request.json
    key = data.get('key')
    hardware_id = data.get('hardware_id')

    if not key or not hardware_id:
        return jsonify({"success": False, "error": "Thiếu dữ liệu"}), 400

    try:
        doc_ref = db.collection('licenses').document(key)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({"success": False, "error": "Key không hợp lệ"}), 200

        data_doc = doc.to_dict()

        if data_doc.get('hardware_id') and data_doc['hardware_id'] != hardware_id:
            return jsonify({"success": False, "error": "Key này đã dùng cho máy khác"}), 200

        if not data_doc.get('hardware_id'):
            doc_ref.update({
                "hardware_id": hardware_id,
                "activated_at": firestore.SERVER_TIMESTAMP
            })

        return jsonify({"success": True, "license_type": data_doc['license_type']}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "API is running!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
